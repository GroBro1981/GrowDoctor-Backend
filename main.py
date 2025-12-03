import os
import base64
import json

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

# API-Key aus Umgebungsvariable lesen (Render / lokal .env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    # Falls kein Key gesetzt ist, lieber klarer Fehler als kryptische Exceptions
    raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt. Bitte als Environment Variable hinterlegen.")

# OpenAI-Client initialisieren
client = OpenAI(api_key=OPENAI_API_KEY)

# FastAPI-App erstellen
app = FastAPI(
    title="GrowDoctor Backend",
    description="Bildbasierte Cannabis-Diagnose-API",
    version="1.0.0",
)

# CORS erlauben (damit App / Website zugreifen können)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # für Entwicklung okay, später einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Healthcheck – zeigt an, dass der Server läuft."""
    return {"status": "ok", "message": "GrowDoctor Backend läuft 😎"}


@app.post("/diagnose")
async def diagnose(image: UploadFile = File(...)):
    """
    Nimmt ein Bild (JPG/PNG) entgegen, schickt es an OpenAI
    und gibt eine strukturierte Cannabis-Diagnose zurück.
    """

    # Dateityp prüfen
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG und PNG sind erlaubt.")

    # Bild in Base64 umwandeln
    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{image.content_type};base64,{img_base64}"

    # Prompt mit allen Regeln & gewünschtem JSON-Schema
    prompt = (
        "Du bist ein sehr erfahrener Cannabis-Pflanzenarzt. "
        "Du bekommst ein Foto einer Cannabis-Pflanze (Indoor oder Outdoor). "
        "Deine Aufgabe: Erkenne das wichtigste Problem (NUR EIN Hauptproblem auswählen), "
        "z.B. Nährstoffmangel, Nährstoffüberschuss, Schädlingsbefall, Pilzbefall oder Umweltstress.\n\n"
        "Wenn das Bild schlecht ist (z.B. starkes pink/violettes LED-Growlicht, extrem unscharf, zu nah gezoomt, "
        "kaum Pflanzenteile sichtbar oder nur der Topf), dann musst du das klar sagen und die Wahrscheinlichkeit "
        "niedrig setzen.\n\n"
        "WICHTIG: Wenn für eine sichere Diagnose zusätzliche Fotos nötig wären, dann gib konkrete Empfehlungen ab, z.B.:\n"
        "- \"Blattoberseite separat und scharf fotografieren\"\n"
        "- \"Blattunterseite mit Fokus auf Flecken/Milben fotografieren\"\n"
        "- \"Makroaufnahme der betroffenen Stelle machen (ca. 5–10 cm Abstand)\"\n"
        "- \"Gesamte Pflanze aus etwas Entfernung fotografieren\"\n\n"
        "Beachte folgende Foto-Regeln für gute Diagnose:\n"
        "- Kein Bild direkt unter starkem LED-Growlicht, lieber bei neutralem Licht (Tageslicht, Blitz aus)\n"
        "- Ganze betroffene Blätter oder Pflanzenteile zeigen, nicht nur 1 cm Ausschnitt\n"
        "- Bild nicht verwackelt, Pflanzenstruktur erkennbar\n"
        "- Wenn mehrere Probleme sichtbar sind, wähle das gravierendste als Hauptproblem\n\n"
        "Antworte IMMER als gültiges JSON mit GENAU diesem Schema:\n"
        "{"
        "\"ist_cannabis\": true/false,"
        "\"hauptproblem\": \"kurzer Titel des Problems\","
        "\"kategorie\": \"mangel|überschuss|schädling|pilz|stress|unbekannt\","
        "\"beschreibung\": \"Was ist auf dem Bild zu sehen und warum kommst du zu dieser Diagnose?\","
        "\"wahrscheinlichkeit\": 0-100,"
        "\"schweregrad\": \"leicht|mittel|stark\","
        "\"stadium\": \"keimling|wachstum|blüte|egal\","
        "\"betroffene_teile\": [\"z.B. untere_blaetter\", \"obere_triebe\"],"
        "\"dringlichkeit\": \"niedrig|mittel|hoch|sofort_handeln\","
        "\"empfohlene_kontrolle_in_tagen\": 0-30,"
        "\"alternativen\": ["
        "  {\"problem\": \"anderes mögliches Problem\", \"wahrscheinlichkeit\": 0-100}"
        "],"
        "\"sofort_massnahmen\": [\"konkreter Schritt 1\", \"konkreter Schritt 2\"],"
        "\"vorbeugung\": [\"konkreter Tipp 1\", \"konkreter Tipp 2\"],"
        "\"bildqualitaet_score\": 0-100,"
        "\"hinweis_bildqualitaet\": \"Hinweis zur Qualität des Fotos und ggf. Verbesserungsvorschläge\","
        "\"foto_empfehlungen\": [\"konkrete Empfehlungen für weitere Fotos (z.B. Blattunterseite, Makroaufnahme)\"]"
        "}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analysiere dieses Bild und gib nur das JSON zurück.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        # Falls der OpenAI-Call schiefgeht, klarer Fehler zurück
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Anfrage an OpenAI: {e}",
        )

    # Antwort entnehmen
    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Falls die KI doch kein gültiges JSON geliefert hat
        raise HTTPException(
            status_code=500,
            detail="OpenAI hat kein gültiges JSON zurückgegeben.",
        )

    # Alternativen filtern: alles < 45% raus (nicht für Anfänger anzeigen)
    alternativen = result.get("alternativen") or []
    gefiltert = []
    for alt in alternativen:
        try:
            wahrscheinlichkeit = alt.get("wahrscheinlichkeit", 0)
            if isinstance(wahrscheinlichkeit, (int, float)) and wahrscheinlichkeit >= 45:
                gefiltert.append(alt)
        except Exception:
            # Wenn ein Alternative-Eintrag Mist ist, einfach ignorieren
            continue

    result["alternativen"] = gefiltert

    return result
