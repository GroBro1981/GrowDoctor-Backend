import os
import base64
import json

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

# --------------------------------------------------
# 🔑 OpenAI-Client
# --------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY ist nicht gesetzt. Bitte als Environment Variable hinterlegen."
    )

client = OpenAI(api_key=OPENAI_API_KEY)

# --------------------------------------------------
# 🌐 FastAPI-App
# --------------------------------------------------
app = FastAPI(
    title="Canalyzer Backend",
    description="Bildbasierte Cannabis-Diagnose & Reifegrad-API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # später einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "message": "Canalyzer Backend läuft 😎"}


# --------------------------------------------------
# 🧠 OpenAI Helper – JETZT korrekt mit gpt-4o-mini
# --------------------------------------------------
def _call_openai_json(system_prompt: str, data_url: str, user_text: str) -> dict:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=900,
            temperature=0.1,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Anfrage an OpenAI: {e}"
        )

    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="OpenAI hat kein gültiges JSON zurückgegeben."
        )


# --------------------------------------------------
# 📸 DIAGNOSE ENDPOINT
# --------------------------------------------------
DIAGNOSIS_PROMPT = """
Du bist ein sehr erfahrener Cannabis-Pflanzenarzt.
Analysiere das Bild und gib nur das JSON-Schema zurück, wie besprochen.
"""

@app.post("/diagnose")
async def diagnose(image: UploadFile = File(...)):
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG oder PNG erlaubt.")

    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode()
    data_url = f"data:{image.content_type};base64,{img_base64}"

    result = _call_openai_json(
        DIAGNOSIS_PROMPT,
        data_url,
        "Analysiere dieses Bild."
    )

    return result


# --------------------------------------------------
# 🌼 REIFEGRAD (TRICHOME) ENDPOINT
# --------------------------------------------------
RIPENESS_PROMPT = """
Du analysierst ausschließlich den Reifegrad der Trichome.
"""

@app.post("/ripeness")
async def ripeness(
    image: UploadFile = File(...),
    preference: str = Form("balanced"),
):
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG oder PNG erlaubt.")

    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode()
    data_url = f"data:{image.content_type};base64,{img_base64}"

    text = f"Nutzer-Wunschwirkung: {preference}. Analysiere den Reifegrad der Trichome."

    result = _call_openai_json(
        RIPENESS_PROMPT,
        data_url,
        text
    )
    # --- Trichome-Validierung + Normalisierung ---
def _to_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0

klar = _to_float(result.get("klar"))
milchig = _to_float(result.get("milchig"))
bernstein = _to_float(result.get("bernstein"))

total = klar + milchig + bernstein

# Wenn keine brauchbaren Werte geliefert wurden -> Gate (Bild ungeeignet / KI unsicher)
if total <= 0:
    return {
        "ok": False,
        "ampel": "rot",
        "message": "Keine verwertbaren Trichom-Werte erkannt. Bitte nur Makroaufnahme der Trichome (Köpfe sichtbar).",
        "foto_tipps": [
            "Makro/Zoom nutzen (Trichome müssen als Köpfe sichtbar sein).",
            "Gute Beleuchtung, kein Blitz/Überstrahlen.",
            "Hand ruhig / Auflage nutzen, Fokus auf die Trichome.",
            "Nicht ganze Pflanze/Blatt – nur Blüte/Trichome nah."
        ],
        "min_requirements": [
            "Trichome klar erkennbar (einzelne Köpfe sichtbar)",
            "Scharf (keine Bewegungsunschärfe)",
            "Nahaufnahme der Blüte (Makro/Zoom)",
            "Keine starke Überbelichtung"
        ],
    }

# Normalisieren auf 100%
klar = (klar / total) * 100.0
milchig = (milchig / total) * 100.0
bernstein = (bernstein / total) * 100.0

# Runden + wieder ins Result schreiben
result["klar"] = int(round(klar))
result["milchig"] = int(round(milchig))
result["bernstein"] = int(round(bernstein))

# Rounding-Korrektur (Summe exakt 100)
diff = 100 - (result["klar"] + result["milchig"] + result["bernstein"])
if diff != 0:
    # Korrigiere den größten Wert
    biggest_key = max(["klar", "milchig", "bernstein"], key=lambda k: result[k])
    result[biggest_key] += diff

        # Qualitäts-Gate: ungeeignetes Bild sauber zurückgeben
    if not isinstance(result, dict):
        return {
            "ok": False,
            "ampel": "rot",
            "message": "Ungültige Antwort vom KI-Modell."
        }

    # Wenn das Prompt bereits ein Gate liefert (ok=false), direkt zurückgeben
    if result.get("ok") is False:
        return {
            "ok": False,
            "ampel": result.get("ampel", "rot"),
            "message": result.get("reason") or result.get("message") or "Bild ungeeignet für Reifegrad-Analyse.",
            "foto_tipps": result.get("tips", []),
            "min_requirements": result.get("min_requirements", []),
        }

    # Fallback-Gate: wenn keine typischen Ripeness-Felder vorhanden sind → blocken
    if ("stufe" not in result) and ("trichome" not in result) and ("klar" not in result):
        return {
            "ok": False,
            "ampel": "rot",
            "message": "Bild ungeeignet für Reifegrad-Analyse. Bitte Makroaufnahme der Trichome.",
            "foto_tipps": [
                "Makro/Zoom nutzen (Trichome müssen als einzelne Köpfe sichtbar sein).",
                "Gute Beleuchtung, kein Blitz-Überstrahlen.",
                "Hand ruhig / Auflage nutzen, Fokus auf die Trichome.",
                "Nicht ganze Pflanze/Blatt – nur Blüte/Trichome nah."
            ],
            "min_requirements": [
                "Trichome klar erkennbar (einzelne Köpfe sichtbar)",
                "Scharf (keine Bewegungsunschärfe)",
                "Nahaufnahme der Blüte (Makro/Zoom)",
                "Keine starke Überbelichtung"
            ],
        }

# --- Ampel-Logik erzwingen (deterministisch) ---
klar = result.get("klar", 0)
milchig = result.get("milchig", 0)
bernstein = result.get("bernstein", 0)

if klar >= 60:
    result["ampel"] = "rot"
    result["stufe"] = "zu früh"
elif milchig >= 50 and bernstein < 10:
    result["ampel"] = "gelb"
    result["stufe"] = "fast reif"
elif milchig >= 40 and bernstein >= 10:
    result["ampel"] = "grün"
    result["stufe"] = "erntereif"
else:
    result["ampel"] = "gelb"
    result["stufe"] = "uneindeutig"

    return result
