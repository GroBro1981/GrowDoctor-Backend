import base64
import json
import os
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import OpenAI
from PIL import Image
from io import BytesIO


# --------- OpenAI Client ---------
# Der API-Key kommt aus der Umgebung (Render: Environment Variable OPENAI_API_KEY)
client = OpenAI()

# --------- FastAPI App ---------
app = FastAPI(
    title="GrowDoctor API",
    description="KI-gestützte Diagnose für Cannabispflanzen (Mängel, Überschuss, Schädlinge, Pilze, Stress).",
    version="1.0.0",
)

# CORS, damit App/Browser zugreifen können
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # später für Produktion einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------- Pydantic Modelle (Antwort) ---------
class DiagnoseAntwort(BaseModel):
    ist_cannabis: bool
    hauptproblem: str
    kategorie: str  # "mangel", "überschuss", "schädling", "pilz", "stress", "unbekannt"
    tags: List[str]
    beschreibung: str
    wahrscheinlichkeit: int  # 0-100
    schweregrad: str  # "leicht", "mittel", "schwer"
    dringlichkeit: str  # "gering", "mittel", "hoch"

    stadium: Optional[str] = None
    betroffene_teile: Optional[List[str]] = None  # z.B. ["obere_triebe", "untere_blaetter"]

    sofort_massnahmen: List[str]
    vorbeugung: List[str]

    bild_feedback: str

    alternative_diagnosen: Optional[List[dict]] = None  # nur Einträge >45%


# --------- Hilfsfunktionen ---------
def _image_to_data_url(image_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """
    Wandelt Bildbytes in eine data:image/...;base64,.... URL um,
    damit das Bild an die OpenAI-Vision-API geschickt werden kann.
    """
    try:
        # Bild einmal mit Pillow öffnen, um sicherzugehen, dass es valide ist
        Image.open(BytesIO(image_bytes))
    except Exception:
        raise HTTPException(status_code=400, detail="Die hochgeladene Datei ist kein gültiges Bild.")

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def _baue_prompt(single_or_multi: str = "single") -> str:
    """
    Erstellt den System-/Userprompt für die Bildanalyse.
    single_or_multi:
        - "single": ein einzelnes Bild
        - "multi": mehrere Bilder (Multi-Foto-Diagnose)
    """
    multi_hinweis = ""
    if single_or_multi == "multi":
        multi_hinweis = (
            "Du bekommst mehrere Bilder derselben Pflanze (z.B. Oberseite, Unterseite, Makro). "
            "Nutze ALLE Bilder zusammen, um eine einzige, konsistente Diagnose zu erstellen. "
        )

    return (
        "Du bist der 'GrowDoctor', ein sehr erfahrener Cannabis-Grow-Berater. "
        "Analysiere das/ die Bild(er) einer Cannabispflanze und erstelle eine Diagnose.\n\n"
        f"{multi_hinweis}"
        "WICHTIG:\n"
        "- Arbeite ausschließlich auf Basis des Bildmaterials.\n"
        "- Wenn etwas unklar ist, mache vorsichtige Einschätzungen und sag das auch so.\n\n"
        "Du sollst IMMER ein JSON-Objekt zurückgeben – KEINEN Fließtext.\n\n"
        "Das JSON MUSS GENAU dieses Schema haben:\n\n"
        "{\n"
        '  \"ist_cannabis\": true/false,\n'
        '  \"hauptproblem\": \"kurzer Titel, z.B. Magnesiummangel\", \n'
        '  \"kategorie\": \"mangel\" | \"überschuss\" | \"schädling\" | \"pilz\" | \"stress\" | \"unbekannt\", \n'
        '  \"tags\": [\"magnesium\", \"stickstoff\", \"thripse\", \"spinnmilben\", ...],\n'
        '  \"beschreibung\": \"kurze Beschreibung der sichtbaren Symptome in DU-Form\", \n'
        '  \"wahrscheinlichkeit\": 0-100,\n'
        '  \"schweregrad\": \"leicht\" | \"mittel\" | \"schwer\", \n'
        '  \"dringlichkeit\": \"gering\" | \"mittel\" | \"hoch\", \n'
        '  \"stadium\": \"wachstum\" | \"vorblüte\" | \"blüte\" | \"späte_blüte\" | null,\n'
        '  \"betroffene_teile\": [\"obere_triebe\", \"mittlere_blaetter\", \"untere_blaetter\", \"buds\", \"stiele\"],\n'
        '  \"sofort_massnahmen\": [\"konkrete Schritt-für-Schritt-Handlung 1\", \"konkrete Handlung 2\", ...],\n'
        '  \"vorbeugung\": [\"präventive Maßnahme 1\", \"präventive Maßnahme 2\", ...],\n'
        '  \"bild_feedback\": \"Feedback zur Bildqualität (Licht, Schärfe, Abstand, Ober-/Unterseite, Makro etc.) in DU-Form\",\n'
        '  \"alternative_diagnosen\": [\n'
        '    {\n'
        '      \"titel\": \"z.B. leichter Stickstoffmangel\",\n'
        '      \"kategorie\": \"mangel\" | \"überschuss\" | \"schädling\" | \"pilz\" | \"stress\" | \"unbekannt\",\n'
        '      \"wahrscheinlichkeit\": 0-100\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "- Liste in \"alternative_diagnosen\" NUR Einträge mit wahrscheinlichkeit >= 45 auf.\n"
        "- Wenn es keine sinnvollen Alternativen gibt, setze \"alternative_diagnosen\": [].\n"
        "- Wenn du dir sehr unsicher bist, wähle kategorie \"unbekannt\" und erkläre das in der Beschreibung.\n"
        "- Erwähne KEINE Produkteamen/Marken, sondern nur Wirkstoff-Typen (z.B. CalMag, PK-Booster, etc.).\n"
        "- Wichtig: Antworte ausschließlich mit gültigem JSON."
    )


def analysiere_bild_mit_openai(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
    multi: bool = False,
) -> dict:
    """
    Schickt das Bild an OpenAI (Vision) und gibt das JSON als Python-Dict zurück.
    """
    data_url = _image_to_data_url(image_bytes, content_type=content_type)

    prompt = _baue_prompt(single_or_multi="multi" if multi else "single")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein erfahrener Cannabis-Grow-Berater namens GrowDoctor. "
                        "Du hilfst Anfängern und Fortgeschrittenen bei der Diagnose von Pflanzenproblemen."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        },
                    ],
                },
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei der Anfrage an OpenAI: {e}")

    try:
        content = response.choices[0].message.content
        # content ist ein String mit JSON (weil response_format=json_object)
        data = json.loads(content)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Antwort von OpenAI konnte nicht als JSON gelesen werden: {e}")


# --------- FastAPI Endpunkte ---------


@app.get("/")
def root():
    return {"status": "ok", "message": "GrowDoctor Backend läuft."}


@app.post("/diagnose", response_model=DiagnoseAntwort)
async def diagnose(
    image: UploadFile = File(...),
):
    """
    Ein-Bild-Diagnose (Free-Version).
    Nimmt ein einzelnes Bild entgegen und gibt eine strukturierte Diagnose zurück.
    """
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Bitte lade eine Bilddatei hoch.")

    image_bytes = await image.read()

    ergebnis = analysiere_bild_mit_openai(
        image_bytes=image_bytes,
        content_type=image.content_type,
        multi=False,
    )

    try:
        return DiagnoseAntwort(**ergebnis)
    except Exception:
        # Falls ein Feld fehlt oder anders heißt, werfen wir eine lesbare Fehlermeldung aus
        raise HTTPException(
            status_code=500,
            detail="Die KI-Antwort hatte nicht das erwartete Format. Bitte versuche es mit einem anderen Bild.",
        )


@app.post("/diagnose-multi", response_model=DiagnoseAntwort)
async def diagnose_multi(
    images: List[UploadFile] = File(...),
):
    """
    Multi-Foto-Diagnose (Pro).
    Aktuell wird intern nur das erste Bild an die KI geschickt,
    aber der Prompt ist bereits darauf vorbereitet, später mehrere Bilder
    kombiniert zu verwenden.
    """
    if len(images) == 0:
        raise HTTPException(status_code=400, detail="Bitte lade mindestens ein Bild hoch.")

    # Im einfachsten Fall verwenden wir erstmal nur das erste Bild.
    first_image = images[0]

    if not first_image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Bitte lade gültige Bilddateien hoch.")

    first_bytes = await first_image.read()

    ergebnis = analysiere_bild_mit_openai(
        image_bytes=first_bytes,
        content_type=first_image.content_type,
        multi=True,
    )

    try:
        return DiagnoseAntwort(**ergebnis)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Die KI-Antwort hatte nicht das erwartete Format. Bitte versuche es mit anderen Bildern.",
        )
