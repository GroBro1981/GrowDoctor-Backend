from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional
import hashlib
import json
import time
import base64
import os

from openai import OpenAI

# =========================
# CONFIG
# =========================

MODEL_NAME = "gpt-4.1-mini"
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
# SIMPLE CACHE
# =========================

analysis_cache: Dict[str, Dict[str, Any]] = {}

# =========================
# TRANSLATIONS
# =========================

TEXTS = {
    "de": {
        "disclaimer_title": "Wichtiger Hinweis",
        "disclaimer_body": "Diese App liefert eine KI-basierte Einschätzung anhand von Fotos. Sie ersetzt keinen fachlichen Rat.",
        "privacy_title": "Datenschutz",
        "privacy_body": "Fotos werden nur zur Analyse verarbeitet und nicht gespeichert.",
        "already_analyzed": "Dieses Bild wurde bereits analysiert.",
    },
    "en": {
        "disclaimer_title": "Important notice",
        "disclaimer_body": "This app provides an AI-based estimation from photos. It does not replace professional advice.",
        "privacy_title": "Privacy",
        "privacy_body": "Photos are processed only for analysis and not stored.",
        "already_analyzed": "This image has already been analyzed.",
    },
}

def t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS[DEFAULT_LANG]).get(key, key)

# =========================
# HELPERS
# =========================

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def to_data_url(image: UploadFile, data: bytes) -> str:
    mime = image.content_type or "image/jpeg"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def safe_int(x, default=0):
    try:
        return int(round(float(x)))
    except Exception:
        return default

def ensure_list(v):
    return v if isinstance(v, list) else []

# =========================
# OPENAI PROMPT
# =========================

def build_prompt(lang: str, photo_position: str, shot_type: str):
    system = (
        "You are GrowDoctor, a plant health diagnostic AI.\n"
        "Return ONLY valid JSON.\n"
        "Never return null values.\n"
        "Always fill missing lists with empty arrays.\n"
    )

    user = (
        f"Language: {lang}\n"
        f"Photo position: {photo_position}\n"
        f"Shot type: {shot_type}\n\n"
        "Analyze the plant health.\n"
        "Return JSON with these keys:\n"
        "- hauptproblem (string)\n"
        "- kategorie (string)\n"
        "- wahrscheinlichkeit (0-100)\n"
        "- beschreibung (string)\n"
        "- betroffene_teile (list)\n"
        "- sichtbare_symptome (list)\n"
        "- moegliche_ursachen (list)\n"
        "- sofort_massnahmen (list)\n"
        "- vorbeugung (list)\n"
        "- bildqualitaet_score (0-100)\n"
        "- hinweis_bildqualitaet (string)\n"
        "- ist_unsicher (boolean)\n"
    )

    return system, user

# =========================
# DIAGNOSE ENDPOINT
# =========================

@app.post("/diagnose")
async def diagnose(
    image: UploadFile = File(...),
    lang: str = Form(DEFAULT_LANG),
    age_confirmed: bool = Form(False),
    photo_position: str = Form("unknown"),
    shot_type: str = Form("unknown"),
    client_id: Optional[str] = Form(None),
    force: bool = Form(False),
):
    if not age_confirmed:
        raise HTTPException(status_code=400, detail="Age not confirmed")

    data = await image.read()
    img_hash = sha256_bytes(data)

    # ---------- CACHE ----------
    cached = analysis_cache.get(img_hash)
    if cached and not force:
        return {
            "status": "ok",
            "already_analyzed": True,
            "image_hash": img_hash,
            "result": cached["result"],
            "debug_photo_position": photo_position,
            "debug_shot_type": shot_type,
            "legal": {
                "disclaimer_title": t(lang, "disclaimer_title"),
                "disclaimer_body": t(lang, "disclaimer_body"),
                "privacy_title": t(lang, "privacy_title"),
                "privacy_body": t(lang, "privacy_body"),
            },
        }

    # ---------- OPENAI ----------
    data_url = to_data_url(image, data)
    system_prompt, user_prompt = build_prompt(lang, photo_position, shot_type)

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
        raw = resp.choices[0].message.content
        result = json.loads(raw)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openai_error: {str(e)}")

    # ---------- POST VALIDATION ----------
    result["wahrscheinlichkeit"] = max(1, min(100, safe_int(result.get("wahrscheinlichkeit", 0))))
    result["betroffene_teile"] = ensure_list(result.get("betroffene_teile"))
    result["sichtbare_symptome"] = ensure_list(result.get("sichtbare_symptome"))
    result["moegliche_ursachen"] = ensure_list(result.get("moegliche_ursachen"))
    result["sofort_massnahmen"] = ensure_list(result.get("sofort_massnahmen"))
    result["vorbeugung"] = ensure_list(result.get("vorbeugung"))
    result["bildqualitaet_score"] = max(0, min(100, safe_int(result.get("bildqualitaet_score", 0))))
    result["ist_unsicher"] = bool(result.get("ist_unsicher", False))

    # ---------- CACHE STORE ----------
    analysis_cache[img_hash] = {
        "ts": time.time(),
        "result": result,
    }

    # ---------- FINAL RESPONSE ----------
    return {
        "status": "ok",
        "already_analyzed": False,
        "image_hash": img_hash,
        "result": result,
        "debug_photo_position": photo_position,
        "debug_shot_type": shot_type,
        "legal": {
            "disclaimer_title": t(lang, "disclaimer_title"),
            "disclaimer_body": t(lang, "disclaimer_body"),
            "privacy_title": t(lang, "privacy_title"),
            "privacy_body": t(lang, "privacy_body"),
        },
    }
