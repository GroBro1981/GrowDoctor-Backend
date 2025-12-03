from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from PIL import Image
import io
import base64
import os

app = FastAPI()

# CORS für App & Browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Key aus Environment-Variable
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def image_to_base64(img_file):
    content = img_file.file.read()
    return base64.b64encode(content).decode("utf-8")

@app.post("/diagnose")
async def diagnose_image(file: UploadFile = File(...)):
    try:
        b64 = image_to_base64(file)

        response = client.responses.create(
            model="gpt-4o-mini",
            input="Analysiere dieses Pflanzenblatt auf Krankheiten, Mängel, Schädlinge oder Stress.",
            image=[{"type": "input_image", "image_base64": b64}]
        )

        result = response.output[0].content[0].text
        return {"diagnose": result}

    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def root():
    return {"status": "GrowDoctor Backend läuft!"}
