import os
import io
import base64
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from PIL import Image

# OpenAI-Client aus Umgebungsvariable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt. Bitte Environment Variable setzen.")

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="GrowDoctor Backend", version="1.0.0")

# CORS, damit App / Browser zugreifen können
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "message": "GrowDoctor Backend läuft."}


def image_bytes_to_data_url(image_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Wandelt Bild-Bytes in einen data:-URL-String für OpenAI Vision um."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{content_type};base64,{b64}"


@app.post("/diagnose")
async def diagnose(image: UploadFile = File(...)):
    try:
        # Bild einlesen
        raw_bytes = await image.read()

        # Test: ist das überhaupt ein Bild?
        try:
            Image.open(io.BytesIO(raw_bytes))
        except Exception:
            raise HTTPException(status_code=400, detail="Die Datei ist kein gültiges Bild.")

        data_url = image_bytes_to_data_url(raw_bytes, image.content_type or "image/jpeg")

        system_prompt = """
Du bist GrowDoctor, ein spezialisierter Assistent für Cannabis-Pflanzendiagnosen.
Du analysierst ausschließlich das Bild und gibst eine Diagnose in **sauberem JSON** zurück.

ANTWORTFORMAT (sehr wichtig, NUR dieses JSON, keine Erklärtexte!):

{
  "ist_cannabis": true/false,
  "hauptproblem": "kurzer Titel",
  "kategorie": "mangel|überschuss|schädling|pilz|stress|unbekannt",
  "beschreibung": "kurze Beschreibung auf Deutsch",
  "wahrscheinlichkeit": 0-100,
  "schweregrad": "leicht|mittel|stark",
  "stadium": "wuchs|vorblüte|blüte|spätblüte|unbekannt",
  "betroffene_teile": ["obere_blaetter","untere_blaetter","triebe","buds","ganze_pflanze"],
  "dringlichkeit": "niedrig|mittel|hoch|sofort_handeln",
  "empfohlene_kontrolle_in_tagen": 0-14,
  "sofort_massnahmen": ["Liste von Maßnahmen"],
  "vorbeugung": ["Liste von Tipps"],
  "alternativen": [
    {
      "problem": "Name des Alternativproblems",
      "kategorie": "mangel|überschuss|schädling|pilz|stress|unbekannt",
      "wahrscheinlichkeit": 0-100
    }
  ],
  "bildqualitaet_score": 0-100,
  "hinweis_bildqualitaet": "kurzer Hinweis zur Qualität (Licht, Schärfe, Abstand)",
  "foto_empfehlungen": [
    "z.B. Blattunterseite fotografieren",
    "Makroaufnahme der betroffenen Stelle",
    "Foto bei natürlichem Licht ohne starke Farbstiche"
  ]
}

WICHTIG:
- Liste „alternativen“ NUR Probleme mit Wahrscheinlichkeit >= 45% aufnehmen.
- Wenn du dir nicht sicher bist, setze "kategorie": "unbekannt".
- Bleib sachlich, kurz und eindeutig.
"""

        user_content = [
            {
                "type": "text",
                "text": "Analysiere dieses Bild einer Pflanze und gib NUR das JSON zurück.",
            },
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
        ]

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail="Die KI-Antwort konnte nicht als JSON gelesen werden.",
            )

        # Alternativen unter 45% rausfiltern (zur Sicherheit)
        alternativen = result.get("alternativen", [])
        result["alternativen"] = [
            a for a in alternativen
            if isinstance(a, dict) and a.get("wahrscheinlichkeit", 0) >= 45
        ]

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interner Fehler: {e}")
