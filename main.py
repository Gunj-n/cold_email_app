import os
import io
import re
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

# Serve static frontend files
app.mount("/static", StaticFiles(directory="static"), name="static")


def generate_cold_email(profile_text: str, prompt: str) -> str:
    """Generate cold email using OpenAI API based on profile text and custom prompt."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are an expert B2B outbound copywriter. "
                    "Write short, high-conversion cold emails. "
                    "Always return in format:\n"
                    "Subject: <short catchy subject>\n\n"
                    "Body:\n<email body, no signature>"
                )},
                {"role": "user", "content": f"Prompt: {prompt}\n\nProfile:\n{profile_text}"}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {str(e)}")


def parse_email(text: str):
    """Extract subject and body from generated email text."""
    subject = ""
    body = text

    # Find subject
    match = re.search(r"(?i)subject\s*:\s*(.+)", text)
    if match:
        subject = match.group(1).strip()
        body = re.sub(r"(?i)subject\s*:.+\n?", "", text).strip()

    # Remove "Body:" if present
    body = re.sub(r"(?i)^body\s*:\s*", "", body).strip()

    # Remove common signatures
    body = re.sub(r"\n(?:best|thanks|regards|sincerely|cheers)[\s,].*", "", body, flags=re.I | re.S).strip()

    return subject, body


@app.get("/", response_class=HTMLResponse)
def root():
    try:
        with open("static/index.html", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>⚠️ index.html not found in /static folder</h1>", status_code=404)


@app.head("/", response_class=PlainTextResponse)
def head_root():
    return "OK"


@app.post("/generate/")
async def generate_emails(file: UploadFile = File(...), prompt: str = Form(...)):
    try:
        # Ensure Excel file
        if not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
            raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are supported")

        # Read Excel file
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))

        if df.empty:
            raise HTTPException(status_code=400, detail="Uploaded Excel file is empty")

        # Concatenate all columns into one text block
        df["combined_profile"] = df.astype(str).apply(lambda row: " | ".join(row.values), axis=1)

        # Generate cold emails and parse subject/body
        results = df["combined_profile"].apply(lambda text: generate_cold_email(text, prompt))
        parsed = results.apply(parse_email)

        # Create new clean columns
        df["subject"] = parsed.apply(lambda x: x[0])
        df["email"] = parsed.apply(lambda x: x[1])

        df.drop(columns=["combined_profile"], inplace=True)

        # Save to BytesIO
        output = io.BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=output_with_emails.xlsx"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

