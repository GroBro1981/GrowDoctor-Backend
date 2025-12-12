import os
import base64
import json
from datetime import datetime
from typing import Dict, List, Any

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
    title="Canalyzer / GrowDoctor Backend",
    description="Bildbasierte Cannabis-Diagnose-API + Reifegrad + Chat",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware(
        allow_origins=["*"],  # für Entwicklung ok, später einschränken
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
)


@app.get("/")
def root():
    return {"status": "ok", "message": "GrowDoctor Backend läuft 😎"}


# --------------------------------------------------
# 🧾 Prompts: Diagnose & Reifegrad
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
RIPENESS_PROMPT = """
Du bist ein sehr strenger Cannabis-Trichom-Reifegrad-Analyst.
WICHTIG: Du darfst NUR Makro-/Mikro-Aufnahmen von Trichomen analysieren (Trichom-Köpfe klar erkennbar).

1) Qualitäts-Gate (Pflicht):
- Wenn das Bild KEIN echtes Trichom-Makro ist (zu weit weg, nur Bud/Blatt, unscharf, Bewegungsunschärfe, falscher Fokus, zu dunkel/überbelichtet),
  dann gib zurück:
  {
    "ok": false,
    "reason": "no_trichome_macro",
    "min_requirements": [
      "Makro/USB-Mikroskop oder starke Makrolinse",
      "Fokus auf Trichom-Köpfe (nicht Pistillen)",
      "helles, gleichmäßiges Licht (kein Blitz-Glanz)",
      "mindestens 1 sehr scharfes Bild, besser 2-3",
      "Bild nah genug, dass einzelne Trichom-Köpfe sichtbar sind"
    ],
    "tips": [
      "Zoome/geh näher ran bis Trichom-Köpfe groß im Bild sind",
      "Fokus manuell setzen, Handy stabilisieren",
      "Wenn nötig mehrere Bereiche fotografieren (Top Bud + Mitte)"
    ]
  }

2) Analyse-Regeln (nur wenn ok=true):
- Bewerte Trichome nach Köpfen (capitate heads), NICHT nach Pistillen.
- Klassifiziere Anteile in Prozent: klar / milchig / bernstein.
- Milchig = opak/weißlich, nicht durchsichtig.
- Klar = glasig/transparent.
- Bernstein = gelb/orange/braun.

3) Ausgabe:
Gib IMMER gültiges JSON zurück (response_format json_object).
Schema:
{
  "ok": true,
  "stage": "zu_frueh" | "fast_reif" | "reif" | "ueberreif",
  "traffic_light": "red" | "yellow" | "green",
  "trichomes": {"clear": int, "milky": int, "amber": int},
  "estimated_days_to_harvest": int,
  "recommendation": string,
  "confidence": int,
  "notes": [string]
}

4) Ampel-Logik:
- rot/zu_frueh: clear >= 60 ODER milky < 30
- gelb/fast_reif: milky 50-80 UND amber 0-10
- gruen/reif: milky 70-90 UND amber 5-20
- ueberreif: amber > 25

5) Tage-bis-Ernte (grobe Schätzung):
- zu_frueh: 7-21
- fast_reif: 3-10
- reif: 0-5
- ueberreif: 0 (sofort ernten oder Qualität sinkt)

WICHTIG: Wenn du nicht sicher bist, setze confidence niedrig und verlange ein besseres Makro (ok=false).
"""

"""

CHAT_PROMPT_BASE = """
Du bist „GrowDoctor“, ein freundlicher, erfahrener Berater für Cannabis-Anbau und -Pflanzengesundheit.

WICHTIG:
- Du gibst NUR harm-reduzierende Tipps für Kleingärtner und Hobby-Grower.
- Erinnere die Nutzer regelmäßig daran, die Gesetze ihres Landes zu beachten
  und nur dort anzubauen, wo es legal oder geduldet ist.
- Keine Tipps für kommerzielle Großproduktion, Schmuggel oder Verkauf.
- Keine Planung illegaler Aktivitäten.

SPRACHE:
- Antworte IMMER in dieser Sprache: {language_name} ({language_code}).
- Wenn der Nutzer in einer anderen Sprache schreibt, kannst du kurz bestätigen,
  bleibst aber in der gewählten Sprache.

STIL:
- Erklär freundlich, klar, in kurzen Absätzen.
- Nutze, wenn sinnvoll, Aufzählungen und konkrete Schritte.
"""

# --------------------------------------------------
# 🧠 Reifegrad-Verlauf (in-memory, pro User)
# --------------------------------------------------

RIPENESS_HISTORY: Dict[str, List[Dict[str, Any]]] = {}


# --------------------------------------------------
# 🧠 Modellwahl & OpenAI-Hilfsfunktionen
# --------------------------------------------------

def _select_model(plan: str) -> str:
    """
    Free/Premium-Umschaltung:
    - "free"  -> gpt-4o-mini  (günstig, schnell)
    - "pro"   -> gpt-4.1-mini (präziser, teurer)
    """
    if not plan:
        plan = "free"
    plan = plan.lower()
    if plan == "pro":
        return "gpt-4.1-mini"
    return "gpt-4o-mini"


def _call_openai_json(
    system_prompt: str,
    data_url: str,
    user_text: str,
    model_name: str,
) -> dict:
    try:
        response = client.chat.completions.create(
            model=model_name,
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


def _call_openai_chat_text(
    system_prompt: str,
    user_text: str,
    model_name: str,
) -> str:
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            max_tokens=900,
            temperature=0.3,
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
            detail=f"Fehler bei der Anfrage an OpenAI (Chat): {e}",
        )

    content = response.choices[0].message.content or ""
    return content.strip()


# --------------------------------------------------
# 📸 ENDPOINT 1: Allgemeine Diagnose
# --------------------------------------------------

@app.post("/diagnose")
async def diagnose(
    image: UploadFile = File(...),
    plan: str = Form("free"),
    user_id: str = Form("anon"),
):
    """
    Erkennt Probleme wie Mängel, Schädlinge, Stress etc.
    """
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG und PNG sind erlaubt.")

    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{image.content_type};base64,{img_base64}"

    user_text = (
        "Analysiere dieses Bild der Cannabis-Pflanze und gib nur das JSON im Schema zurück."
    )

    model_name = _select_model(plan)

    result = _call_openai_json(
        DIAGNOSIS_PROMPT,
        data_url,
        user_text,
        model_name=model_name,
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

    result["_meta"] = {
        "plan": plan,
        "modell": model_name,
        "user_id": user_id,
    }

    return result


# --------------------------------------------------
# 🌼 ENDPOINT 2: Reifegrad / Trichome + Verlauf
# --------------------------------------------------

@app.post("/ripeness")
async def ripeness(
    image: UploadFile = File(...),
    preference: str = Form("balanced"),  # "energetic" | "balanced" | "couchlock"
    plan: str = Form("free"),
    user_id: str = Form("anon"),
):
    """
    Bewertet NUR den Reifegrad der Blüte anhand der Trichome.
    """
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Nur JPG und PNG sind erlaubt.")

    img_bytes = await image.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{image.content_type};base64,{img_base64}"

    if preference == "energetic":
        pref_text = (
            "Der Nutzer wünscht eine eher ENERGETISCHE, aktive Wirkung "
            "(mehr klare/milchige Trichome, weniger bernsteinfarben). "
            "Plane die Ernte eher FRÜHER im optimalen Fenster."
        )
    elif preference == "couchlock":
        pref_text = (
            "Der Nutzer wünscht eine starke, SEDIERENDE Couchlock-Wirkung "
            "(viele bernsteinfarbene Trichome). "
            "Plane die Ernte eher SPÄTER im optimalen Fenster."
        )
    else:
        pref_text = (
            "Der Nutzer wünscht eine AUSGEGLICHENE Wirkung "
            "(Mischung aus milchigen und etwas bernsteinfarbenen Trichomen)."
        )

    user_text = (
        "Analysiere NUR den Reifegrad der Blüte anhand der Trichome. "
        "Berücksichtige folgende Wunschwirkung des Nutzers: "
        f"{pref_text}"
    )

    model_name = _select_model(plan)

    result = _call_openai_json(
        RIPENESS_PROMPT,
        data_url,
        user_text,
        model_name=model_name,
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

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "preference": preference,
        "plan": plan,
        "modell": model_name,
        "result": result,
    }
    history = RIPENESS_HISTORY.setdefault(user_id, [])
    history.append(entry)
    if len(history) > 20:
        history.pop(0)

    result["_meta"] = {
        "user_id": user_id,
        "plan": plan,
        "modell": model_name,
        "history_count": len(history),
    }

    return result


@app.get("/ripeness/history")
def ripeness_history(user_id: str):
    """
    Gibt den Reifegrad-Verlauf für einen Nutzer zurück.
    (Nur in-memory, geht nach Server-Neustart verloren.)
    """
    return RIPENESS_HISTORY.get(user_id, [])


# --------------------------------------------------
# 💬 ENDPOINT 3: Chat with GrowDoctor
# --------------------------------------------------

LANGUAGE_NAMES = {
    "de": "Deutsch",
    "en": "Englisch",
    "fr": "Französisch",
    "it": "Italienisch",
    "es": "Spanisch",
    "pt": "Portugiesisch",
    "cs": "Tschechisch",
    "pl": "Polnisch",
    "nl": "Niederländisch",
}


@app.post("/chat")
async def chat(
    message: str = Form(...),
    language: str = Form("de"),   # Sprachcode: de, en, fr, it, es, pt, cs, pl, nl
    plan: str = Form("free"),
    user_id: str = Form("anon"),
):
    """
    Text-Chat mit GrowDoctor (ohne Bild).
    """
    msg = message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Feld 'message' darf nicht leer sein.")

    lang_code = language.lower()
    if lang_code not in LANGUAGE_NAMES:
        lang_code = "en"
    lang_name = LANGUAGE_NAMES[lang_code]

    model_name = _select_model(plan)

    system_prompt = CHAT_PROMPT_BASE.format(
        language_name=lang_name,
        language_code=lang_code,
    )

    answer = _call_openai_chat_text(
        system_prompt=system_prompt,
        user_text=msg,
        model_name=model_name,
    )

    return {
        "answer": answer,
        "_meta": {
            "language": lang_code,
            "language_name": lang_name,
            "plan": plan,
            "modell": model_name,
            "user_id": user_id,
        },
    }

