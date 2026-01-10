from __future__ import annotations

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional, List
import hashlib
import json
import time
import base64
import os

from openai import OpenAI

# =========================
# CONFIG
# =========================

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-mini")
DEFAULT_LANG = "de"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="GrowDoctor Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# SIMPLE CACHE (in-memory)
# =========================

analysis_cache: Dict[str, Dict[str, Any]] = {}

# =========================
# TRANSLATIONS (legal UI)
# =========================

TEXTS = {
    "de": {
        "disclaimer_title": "Wichtiger Hinweis",
        "disclaimer_body": "Diese App liefert eine KI-basierte Einschätzung anhand von Fotos. Sie ersetzt keinen fachlichen Rat.",
        "privacy_title": "Datenschutz",
        "privacy_body": "Fotos werden nur zur Analyse verarbeitet und nicht gespeichert.",
        "already_analyzed": "Dieses Bild wurde bereits analysiert.",
        "age_not_confirmed": "Altersbestätigung fehlt.",
    },
    "en": {
        "disclaimer_title": "Important notice",
        "disclaimer_body": "This app provides an AI-based estimation from photos. It does not replace professional advice.",
        "privacy_title": "Privacy",
        "privacy_body": "Photos are processed only for analysis and not stored.",
        "already_analyzed": "This image has already been analyzed.",
        "age_not_confirmed": "Age confirmation missing.",
    },
}

SUPPORTED_LANGS = {"de", "en", "fr", "es", "it", "pt", "nl", "pl", "cs"}

def t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS[DEFAULT_LANG]).get(key, key)

def normalize_lang(raw: Optional[str]) -> str:
    if not raw:
        return DEFAULT_LANG
    l = raw.strip().lower().replace("_", "-").split("-")[0]  # "en-US" -> "en"
    return l if l in SUPPORTED_LANGS else DEFAULT_LANG

# =========================
# HELPERS
# =========================

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def to_data_url(image: UploadFile, data: bytes) -> str:
    mime = image.content_type or "image/jpeg"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return default

def ensure_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    return []

def ensure_str(v: Any) -> str:
    return "" if v is None else str(v)

def ensure_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return default

def compute_ampel(w: int, ist_unsicher: bool) -> str:
    if ist_unsicher:
        return "gelb"
    if w >= 70:
        return "gruen"
    if w >= 40:
        return "gelb"
    return "rot"

# =========================
# PROMPT
# =========================

def build_prompt(lang: str, photo_position: str, shot_type: str) -> tuple[str, str]:
    system = f"""
You are GrowDoctor, a plant health diagnostic assistant.
Return ONLY valid JSON. No markdown. No extra text.
Never use null. Use "" for missing strings and [] for missing lists.

CRITICAL vision rules:
- Do NOT label trichomes/resin glands as mold.
  Trichomes = crystal-like, sparkling heads (milky/amber/clear) on buds.
  Mold = fuzzy/cottony web-like growth, powdery coating, slime/rot, gray/brown necrosis with fuzz.
  If fuzzy growth is not clearly visible, do NOT claim mold; instead set ist_unsicher=true and request macro close-ups.

Physiology rules:
- Consider leaf age/location:
  Older/lower leaves => more likely MOBILE nutrient issues (N, P, K, Mg) or natural senescence.
  Newer/top growth => more likely IMMOBILE issues (Ca, Fe, S, B, Mn, Zn) or pH/lockout.
- When symptoms conflict or multiple deficiencies appear, prioritize root-zone problems (pH/EC/overwatering/lockout) over single-nutrient feeding advice.
- If lockout/pH is plausible, set duengen_erlaubt=false and recommend measuring pH/EC first.

Language rule:
- Write ALL output text in language: {lang}.
"""

    schema = """
Return JSON with EXACT keys:
- hauptproblem (string)
- kategorie (string)
- wahrscheinlichkeit (0-100 integer)
- beschreibung (string)
- betroffene_teile (list of strings)
- sichtbare_symptome (list of strings)
- moegliche_ursachen (list of strings)
- sofort_massnahmen (list of strings)
- vorbeugung (list of strings)
- bildqualitaet_score (0-100 integer)
- hinweis_bildqualitaet (string)
- ist_unsicher (boolean)
- unsicher_hinweis (string)
- profi_empfohlen (boolean)
- profi_grund (string)
- duengen_erlaubt (boolean)
"""

    user = f"""
Language: {lang}
Photo position: {photo_position}
Shot type: {shot_type}

Task:
Analyze the plant photo and fill the JSON schema.

Constraints:
- Provide practical, non-harmful horticulture guidance.
- If you suspect mold but it could be trichomes, mark uncertain and request macro photos.
{schema}
"""
    return system.strip(), user.strip()

# =========================
# HEALTH & METRICS
# =========================

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/metrics")
def metrics():
    # simple stub to prevent 404s from external pings
    return {"status": "ok"}

# =========================
# DIAGNOSE
# =========================

@app.post("/diagnose")
async def diagnose(
    image: UploadFile = File(...),
    lang: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    locale: Optional[str] = Form(None),
    age_confirmed: bool = Form(False),
    photo_position: str = Form("unknown"),
    shot_type: str = Form("unknown"),
    client_id: Optional[str] = Form(None),
    force: bool = Form(False),
):
    if not age_confirmed:
        raise HTTPException(status_code=400, detail=t(DEFAULT_LANG, "age_not_confirmed"))

    lang_final = normalize_lang(lang or language or locale)

    data = await image.read()
    img_hash = sha256_bytes(data)
    cache_key = f"{img_hash}:{lang_final}"

    cached = analysis_cache.get(cache_key)
    if cached and not force:
        return {
            "status": "ok",
            "already_analyzed": True,
            "image_hash": img_hash,
            "result": cached["result"],
            "debug_lang": lang_final,
            "debug_photo_position": photo_position,
            "debug_shot_type": shot_type,
            "legal": {
                "disclaimer_title": t(lang_final, "disclaimer_title"),
                "disclaimer_body": t(lang_final, "disclaimer_body"),
                "privacy_title": t(lang_final, "privacy_title"),
                "privacy_body": t(lang_final, "privacy_body"),
                "already_analyzed": t(lang_final, "already_analyzed"),
            },
        }

    data_url = to_data_url(image, data)
    system_prompt, user_prompt = build_prompt(lang_final, photo_position, shot_type)

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openai_error: {str(e)}")

    # -------------------------
    # POST-VALIDATION / NORMALIZE
    # -------------------------
    result = dict(result) if isinstance(result, dict) else {}

    w = max(0, min(100, safe_int(result.get("wahrscheinlichkeit", 0), 0)))
    ist_unsicher = ensure_bool(result.get("ist_unsicher", False), False)

    normalized = {
        "hauptproblem": ensure_str(result.get("hauptproblem", "")),
        "kategorie": ensure_str(result.get("kategorie", "")),
        "wahrscheinlichkeit": w,
        "beschreibung": ensure_str(result.get("beschreibung", "")),
        "betroffene_teile": ensure_list(result.get("betroffene_teile", [])),
        "sichtbare_symptome": ensure_list(result.get("sichtbare_symptome", [])),
        "moegliche_ursachen": ensure_list(result.get("moegliche_ursachen", [])),
        "sofort_massnahmen": ensure_list(result.get("sofort_massnahmen", [])),
        "vorbeugung": ensure_list(result.get("vorbeugung", [])),
        "bildqualitaet_score": max(0, min(100, safe_int(result.get("bildqualitaet_score", 0), 0))),
        "hinweis_bildqualitaet": ensure_str(result.get("hinweis_bildqualitaet", "")),
        "ist_unsicher": ist_unsicher,
        "unsicher_hinweis": ensure_str(result.get("unsicher_hinweis", "")),
        "profi_empfohlen": ensure_bool(result.get("profi_empfohlen", False), False),
        "profi_grund": ensure_str(result.get("profi_grund", "")),
        "duengen_erlaubt": ensure_bool(result.get("duengen_erlaubt", True), True),
    }

    # deterministically set ampel based on probability + uncertainty (frontend will just display)
    normalized["ampel"] = compute_ampel(normalized["wahrscheinlichkeit"], normalized["ist_unsicher"])

    analysis_cache[cache_key] = {"ts": time.time(), "result": normalized}

    return {
        "status": "ok",
        "already_analyzed": False,
        "image_hash": img_hash,
        "result": normalized,
        "debug_lang": lang_final,
        "debug_photo_position": photo_position,
        "debug_shot_type": shot_type,
        "legal": {
            "disclaimer_title": t(lang_final, "disclaimer_title"),
            "disclaimer_body": t(lang_final, "disclaimer_body"),
            "privacy_title": t(lang_final, "privacy_title"),
            "privacy_body": t(lang_final, "privacy_body"),
            "already_analyzed": t(lang_final, "already_analyzed"),
        },
    }
