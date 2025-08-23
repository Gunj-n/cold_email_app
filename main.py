import os
import io
import pandas as pd
from fastapi import FastAPI, UploadFile, Form, HTTPException, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=api_key)

app = FastAPI(title="Cold Email Generator")

# Allow frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for testing, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Serve static frontend files (index.html, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

def generate_cold_email(profile_text: str, prompt: str) -> str:
    """Generate cold email using OpenAI API based on profile text and custom prompt."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": (
                    "You are an expert B2B outbound copywriter. "
                    "Write short, high-conversion cold emails. "
                    "Use a warm, human tone. Personalize with specifics from the prospect's role, company, experience, etc."
                )},
                {"role": "user", "content": f"Prompt: {prompt}\n\nProfile:\n{profile_text}"}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"ERROR: {str(e)}"

# ✅ Root route serves frontend
@app.get("/", response_class=HTMLResponse)
def root():
    try:
        with open("static/index.html", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>⚠️ index.html not found in /static folder</h1>", status_code=404)

# ✅ Add HEAD route (for health checks)
@app.head("/", response_class=PlainTextResponse)
def head_root():
    return "OK"

@app.post("/generate/")
async def generate_emails(file: UploadFile = File(...), prompt: str = Form(...)):
    try:
        # Read Excel file
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))

        # Concatenate all columns into one text block
        df["combined_profile"] = df.astype(str).apply(lambda row: " | ".join(row.values), axis=1)

        # Generate cold emails
        df["cold_email"] = df["combined_profile"].apply(lambda text: generate_cold_email(text, prompt))

        # Save to BytesIO
        output = io.BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=output_with_emails.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

