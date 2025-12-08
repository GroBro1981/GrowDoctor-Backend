import os
import base64
import json

from fastapi import FastAPI, File, UploadFile, HTTPException
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
    description="Bildbasierte Cannabis-Diagnose-API (Diagnose + Reifegrad)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "message": "Canalyzer Backend läuft 😎"}


# --------------------------------------------------
# 🧾 Prompts
# --------------------------------------------------

DIAGNOSIS_PROMPT = """
Du bist ein sehr erfahrener Cannabis-Pflanzenarzt.

Du bekommst ein Foto einer Cannabis-Pflanze (Indoor oder Outdoor).
Deine Aufgabe: Erkenne das wichtigste Problem (NUR EIN Hauptproblem auswählen), z.B.:
- Nährstoffmangel
- Nährstoffüberschuss
- Schädlingsbefall
- Pilzbefall
- Umweltstress
- oder: kein akutes Problem erkennbar

WICHTIG – Unterschied zwischen TRICHOMEN und SCHIMMEL:

- Trichome:
  - kleine, glitzernde Harzdrüsen (wie Frost / Kristalle)
  - sitzen dicht auf Blüten und Zuckerblättern
  - wirken wie viele kleine Punkte oder Pilzstiele mit Köpfen
  - können weiß, milchig oder bernsteinfarben sein
  - können auf Fotos wie „zuckerig bestäubt“ oder wie Mehltau wirken, sind aber NORMAL

- Echter Schimmel / Mehltau:
  - wirkt flauschig, wattig, wolkig oder pulvrig
  - überzieht die Oberfläche wie ein Belag
  - verdeckt teilweise die Pflanzenstruktur
  - die Flächen sehen ungleichmäßig, „angefressen“ oder verrottet aus

REGEL:
- Wenn die weißen Strukturen wie dichte Trichome wirken (kristall-artig, frostig, viele Punkte),
  dann DARFST du NICHT „Schimmel“ diagnostizieren.
- Nur wenn ganz klar eine flauschige, wattige oder pulvrige Struktur zu sehen ist,
  darfst du „Pilzbefall / Schimmel“ als Hauptproblem wählen.
- Wenn du unsicher bist, ob es Schimmel oder nur viele Trichome sind,
  entscheide dich NICHT für Schimmel. Schreibe in die Beschreibung,
  dass die Trichome möglicherweise nur sehr dicht stehen.

Bildqualität:
- Wenn das Bild extrem unscharf ist oder nur ein winziger Ausschnitt gezeigt wird,
  darfst du die Bildqualität kritisieren und eine niedrige Wahrscheinlichkeit setzen.
- Wenn Pflanze / Blätter / Blüten aber gut erkennbar sind, behandle die Bildqualität als ausreichend
  und gib eine normale Diagnose.

Wenn du wirklich kein klares Problem erkennen kannst:
- Setze als Hauptproblem z.B. „kein akutes Problem erkennbar“
- Kategorie: „kein_problem“
- niedrige Wahrscheinlichkeit

ANTWORTE IMMER als gültiges JSON mit GENAU diesem Schema:

{
  "ist_cannabis": true/false,
  "hauptproblem": "kurzer Titel des wichtigsten Problems oder 'kein akutes Problem erkennbar'",
  "kategorie": "mangel|überschuss|schädling|pilz|stress|unbekannt|kein_problem",
  "beschreibung": "Was ist auf dem Bild zu sehen und warum kommst du zu dieser Diagnose?",
  "wahrscheinlichkeit": 0-100,
  "schweregrad": "leicht|mittel|stark|kein_problem",
  "stadium": "keimling|wachstum|blüte|egal",
  "betroffene_teile": ["z.B. untere_blaetter", "obere_triebe"],
  "dringlichkeit": "niedrig|mittel|hoch|sofort_handeln",
  "empfohlene_kontrolle_in_tagen": 0-30,
  "alternativen": [
    {"problem": "anderes mögliches Problem", "wahrscheinlichkeit": 0-100}
  ],
  "sofort_massnahmen": ["konkreter Schritt 1", "konkreter Schritt 2"],
  "vorbeugung": ["konkreter Tipp 1", "konkreter Tipp 2"],
  "bildqualitaet_score": 0-100,
  "hinweis_bildqualitaet": "Hinweis zur Qualität des Fotos und ggf. Verbesserungsvorschläge",
  "foto_empfehlungen": [
    "konkrete Empfehlungen für weitere Fotos (z.B. Blattunterseite, Makroaufnahme)"
  ]
}
"""

RIPENESS_PROMPT = """
Du bist ein hochspezialisierter Cannabis-Ernteassistent.

DU BEURTEILST NUR DEN REIFEGRAD DER BLÜTE ANHAND DER TRICHOME.
Du sollst KEINE Krankheiten, keinen Schimmel und keine Nährstoffmängel diagnostizieren.

Du bekommst ein MAKRO-Foto von Trichomen auf einer Cannabis-Blüte.

WICHTIG:
- Trichome = Harzdrüsen / kleine glitzernde „Pilze“ auf Blüte und Blättern.
- Sie können sehr dicht stehen und auf Fotos wie Mehltau oder Schimmel wirken – sind aber NORMAL.
- Du darfst in diesem Modus NIEMALS „Schimmel“ oder „Pilzbefall“ diagnostizieren.
- Auch wenn die Trichome wie weißer Belag aussehen: behandle sie als Trichome, solange keine typische
  flauschige, wattige oder verrottete Struktur zu sehen ist.

Deine Aufgaben:

1. Schätze die Verteilung der Trichome:
   - Anteil KLAR (%) 0–100
   - Anteil MILCHIG (%) 0–100
   - Anteil BERNSTEIN (%) 0–100
   Die Summe darf ungefähr 100 % ergeben.

2. Bestimme eine Reifegrad-Stufe:
   - "zu früh"    → überwiegend klare Trichome
   - "optimal"    → überwiegend milchige Trichome
   - "spät"       → sehr viele bernsteinfarbene Trichome

3. Empfohlene Tage bis Ernte:
   - Wenn schon optimal: 0 Tage.
   - Wenn noch zu früh: positive Zahl (z.B. 5 = noch ca. 5 Tage bis optimal).
   - Wenn deutlich überreif: negative Zahl (z.B. -3 = etwa 3 Tage über dem optimalen Zeitpunkt).

4. Empfehlung:
   - "weiter reifen lassen"
   - "jetzt ernten"
   - "schnellstmöglich ernten"

5. Kurzbeschreibung:
   - Erkläre in 2–5 Sätzen, wie die Trichome ungefähr verteilt sind
     und warum du zu diesem Reifegrad kommst.

Wenn das Foto extrem unscharf ist oder man kaum Trichome erkennt:
- Gib eine sehr vorsichtige Einschätzung ab.
- Setze "empfohlene_tage_bis_ernte" auf 0.
- Setze "reifegrad_stufe" auf "zu früh".
- Empfehlung: "weiter reifen lassen".
- Erkläre in der Beschreibung, dass das Foto für eine genaue Beurteilung ungeeignet ist
  und dass der Nutzer ein schärferes Makro mit Fokus auf den Trichomen machen soll.

ANTWORTE IMMER als gültiges JSON mit GENAU DIESEM SCHEMA:

{
  "reifegrad_stufe": "zu früh" | "optimal" | "spät",
  "beschreibung": "kurze Erklärung, was du an den Trichomen erkennst",
  "empfohlene_tage_bis_ernte": ganze Zahl (negativ, 0 oder positiv),
  "empfehlung": "weiter reifen lassen" | "jetzt ernten" | "schnellstmöglich ernten",
  "trichom_anteile": {
    "klar": ganze Zahl (0-100),
    "milchig": ganze Zahl (0-100),
    "bernstein": ganze Zahl (0-100)
  }
}
"""


# --------------------------------------------------
# 🧠 Hilfsfunktion: OpenAI-Call (gpt-5.1-mini)
# --------------------------------------------------


def _call_openai_json(system_prompt: str, data_url: str, user_text: str) -> dict:
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
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
        msg = str(e)
        if "rate_limit" in msg or "rate_limit_exceeded" in msg:
            raise HTTPException(
                status_code=429,
                detail="OpenAI-Ratelimit erreicht – bitte später erneut versuchen.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Anfrage an OpenAI: {e}",
        )

    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="OpenAI hat kein gültiges JSON zurückgegeben.",
        )


# --------------------------------------------------
# 📸 ENDPOINT 1: Allgemeine Diagnose
# --------------------------------------------------


@app.post("/diagnose")
async def diagnose(image: UploadFile = File(...)):
    """
    Erkennt Probleme wie Mängel, Schädlinge, Stress etc.
    """

    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG und PNG sind erlaubt.")

    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{image.content_type};base64,{img_base64}"

    result = _call_openai_json(
        DIAGNOSIS_PROMPT,
        data_url,
        "Analysiere dieses Bild der Cannabis-Pflanze und gib nur das JSON im Schema zurück.",
    )

    alternativen = result.get("alternativen") or []
    gefiltert = []
    for alt in alternativen:
        try:
            w = alt.get("wahrscheinlichkeit", 0)
            if isinstance(w, (int, float)) and w >= 45:
                gefiltert.append(alt)
        except Exception:
            continue
    result["alternativen"] = gefiltert

    return result


# --------------------------------------------------
# 🌼 ENDPOINT 2: Reifegrad / Trichome
# --------------------------------------------------


@app.post("/ripeness")
async def ripeness(image: UploadFile = File(...)):
    """
    Bewertet NUR den Reifegrad der Blüte anhand der Trichome.
    """

    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG und PNG sind erlaubt.")

    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{image.content_type};base64,{img_base64}"

    result = _call_openai_json(
        RIPENESS_PROMPT,
        data_url,
        "Analysiere NUR den Reifegrad der Blüte anhand der Trichome.",
    )

    stage = result.get("reifegrad_stufe")
    if not isinstance(stage, str) or not stage.strip():
        stage = "zu früh"
    result["reifegrad_stufe"] = stage.strip()

    days = result.get("empfohlene_tage_bis_ernte", 0)
    if not isinstance(days, int):
        try:
            days = int(days)
        except Exception:
            days = 0
    result["empfohlene_tage_bis_ernte"] = days

    rec = result.get("empfehlung")
    if not isinstance(rec, str) or not rec.strip():
        if days > 1:
            rec = "weiter reifen lassen"
        elif days < -1:
            rec = "schnellstmöglich ernten"
        else:
            rec = "jetzt ernten"
    result["empfehlung"] = rec.strip()

    ta = result.get("trichom_anteile") or {}
    safe_ta = {}
    for key in ["klar", "milchig", "bernstein"]:
        val = ta.get(key, 0)
        if not isinstance(val, int):
            try:
                val = int(val)
            except Exception:
                val = 0
        if val < 0:
            val = 0
        if val > 100:
            val = 100
        safe_ta[key] = val
    result["trichom_anteile"] = safe_ta

    return result

