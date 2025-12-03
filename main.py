from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import base64
import json

# >>> HIER DEIN OPENAI API KEY EINTRAGEN (in Anführungszeichen lassen!) <<<
client = OpenAI()


# OpenAI-Client initialisieren
client = OpenAI(api_key=OPENAI_API_KEY)

# FastAPI-App erstellen
app = FastAPI()

# CORS erlauben (damit später deine App/Website drauf zugreifen kann)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # für Entwicklung ok, später einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    """Einfacher Check, ob der Server läuft."""
    return {"status": "ok", "message": "GrowDoctor läuft 😎"}

@app.post("/diagnose")
async def diagnose(image: UploadFile = File(...)):
    """
    Nimmt ein Bild (JPG/PNG) entgegen, schickt es an OpenAI
    und gibt eine strukturierte Cannabis-Diagnose zurück.
    """
    # Dateityp prüfen
    if image.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="Nur JPG und PNG erlaubt.")

    # Bild in Base64 umwandeln
    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{image.content_type};base64,{img_base64}"

    # Prompt: erklärt der KI, was sie tun soll und welches JSON wir wollen
    prompt = (
        "Du bist ein sehr erfahrener Cannabis-Pflanzenarzt. "
        "Du bekommst ein Foto einer Pflanze (Indoor oder Outdoor). "
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

    # Anfrage an OpenAI schicken (Bild + Text)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analysiere dieses Bild und gib nur das JSON zurück."
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},  # sorgt dafür, dass wirklich JSON zurückkommt
    )

    # Antwort entnehmen
    result_text = response.choices[0].message.content
    result = json.loads(result_text)

    # 🔹 Alternativen mit Wahrscheinlichkeit < 45% ausfiltern, damit Anfänger nicht verwirrt werden
    alternativen = result.get("alternativen") or []
    gefiltert = []
    for alt in alternativen:
        try:
            wahrscheinlichkeit = alt.get("wahrscheinlichkeit", 0)
            if isinstance(wahrscheinlichkeit, (int, float)) and wahrscheinlichkeit >= 45:
                gefiltert.append(alt)
        except Exception:
            # falls die KI mal Mist baut, ignorieren wir das eine Element einfach
            continue
    result["alternativen"] = gefiltert

    return result

