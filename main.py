from __future__ import annotations

import os
import json
import time
import base64
import hashlib
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_LANG = "de"
SUPPORTED_LANGS = {"de", "en", "fr", "es", "it", "pt", "nl", "pl", "cs"}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="GrowDoctor Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

analysis_cache: Dict[str, Dict[str, Any]] = {}

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
    "it": {
        "disclaimer_title": "Avviso importante",
        "disclaimer_body": "Questa app fornisce una stima basata su IA dalle foto. Non sostituisce un parere professionale.",
        "privacy_title": "Privacy",
        "privacy_body": "Le foto vengono elaborate solo per l’analisi e non vengono salvate.",
        "already_analyzed": "Questa immagine è già stata analizzata.",
        "age_not_confirmed": "Conferma dell’età mancante.",
    },
    "fr": {
        "disclaimer_title": "Avis important",
        "disclaimer_body": "Cette application fournit une estimation basée sur l’IA à partir de photos. Elle ne remplace pas un avis professionnel.",
        "privacy_title": "Confidentialité",
        "privacy_body": "Les photos sont traitées uniquement pour l’analyse et ne sont pas stockées.",
        "already_analyzed": "Cette image a déjà été analysée.",
        "age_not_confirmed": "Confirmation d’âge manquante.",
    },
    "es": {
        "disclaimer_title": "Aviso importante",
        "disclaimer_body": "Esta app ofrece una estimación basada en IA a partir de fotos. No sustituye el asesoramiento profesional.",
        "privacy_title": "Privacidad",
        "privacy_body": "Las fotos se procesan solo para el análisis y no se almacenan.",
        "already_analyzed": "Esta imagen ya fue analizada.",
        "age_not_confirmed": "Falta confirmación de edad.",
    },
    "pt": {
        "disclaimer_title": "Aviso importante",
        "disclaimer_body": "Este app fornece uma estimativa baseada em IA a partir de fotos. Não substitui aconselhamento profissional.",
        "privacy_title": "Privacidade",
        "privacy_body": "As fotos são processadas apenas para análise e não são armazenadas.",
        "already_analyzed": "Esta imagem já foi analisada.",
        "age_not_confirmed": "Falta confirmação de idade.",
    },
    "nl": {
        "disclaimer_title": "Belangrijke melding",
        "disclaimer_body": "Deze app geeft een AI-inschatting op basis van foto’s. Dit vervangt geen professioneel advies.",
        "privacy_title": "Privacy",
        "privacy_body": "Foto’s worden alleen verwerkt voor analyse en niet opgeslagen.",
        "already_analyzed": "Deze afbeelding is al geanalyseerd.",
        "age_not_confirmed": "Leeftijdsbevestiging ontbreekt.",
    },
    "pl": {
        "disclaimer_title": "Ważna informacja",
        "disclaimer_body": "Aplikacja dostarcza ocenę opartą na AI na podstawie zdjęć. Nie zastępuje porady specjalisty.",
        "privacy_title": "Prywatność",
        "privacy_body": "Zdjęcia są przetwarzane wyłącznie do analizy i nie są zapisywane.",
        "already_analyzed": "Ten obraz był już analizowany.",
        "age_not_confirmed": "Brak potwierdzenia wieku.",
    },
    "cs": {
        "disclaimer_title": "Důležité upozornění",
        "disclaimer_body": "Tato aplikace poskytuje odhad na základě AI z fotografií. Nenahrazuje odbornou radu.",
        "privacy_title": "Soukromí",
        "privacy_body": "Fotografie jsou zpracovány pouze pro analýzu a neukládají se.",
        "already_analyzed": "Tento obrázek již byl analyzován.",
        "age_not_confirmed": "Chybí potvrzení věku.",
    },
}

def t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS[DEFAULT_LANG]).get(key, key)

def normalize_lang(raw: Optional[str]) -> str:
    if not raw:
        return DEFAULT_LANG
    l = raw.strip().lower().replace("_", "-").split("-")[0]
    return l if l in SUPPORTED_LANGS else DEFAULT_LANG

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def to_data_url(content_type: Optional[str], data: bytes) -> str:
    mime = content_type or "image/jpeg"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def ensure_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return []

def ensure_str(v: Any) -> str:
    return str(v).strip() if v is not None else ""

def clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        x = int(round(float(v)))
        return max(lo, min(hi, x))
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        chunk = text[start:end + 1]
        try:
            return json.loads(chunk)
        except Exception:
            return {}
    return {}


    # 5) OpenAI call (image + prompt)  ✅ NEUER BLOCK
    data_url = _to_data_url(image, data)
    system_prompt, user_prompt = _diagnose_prompt(lang, photo_position, shot_type)

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
            # garantiert JSON (wichtig für App/Parsing)
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        result_json = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openai_error: {str(e)}")

    # 6) Post-Validation + harte Defaults (damit App nie '0%' oder leere Felder zeigt)
    def _int0(x, default=0):
        try:
            return int(round(float(x)))
        except Exception:
            return default

    # Pflichtfelder absichern
    if "ist_cannabis" not in result_json:
        result_json["ist_cannabis"] = True

    result_json["bildqualitaet_score"] = max(0, min(100, _int0(result_json.get("bildqualitaet_score", 0), 0)))

    # Wahrscheinlichkeit absichern: wenn fehlend/0 aber Diagnose vorhanden -> konservativ 70 setzen
    prob = _int0(result_json.get("wahrscheinlichkeit", 0), 0)
    if prob <= 0 and str(result_json.get("hauptproblem", "")).strip():
        prob = 70
    result_json["wahrscheinlichkeit"] = max(1, min(100, prob)) if str(result_json.get("hauptproblem", "")).strip() else max(0, min(100, prob))

    # Nie "Unbekannt" als Text zulassen
    def _no_unknown(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return s
        if s.lower() == "unbekannt":
            return "Verdacht auf Mischbild (weitere Infos nötig)"
        return s

    result_json["hauptproblem"] = _no_unknown(result_json.get("hauptproblem", ""))
    result_json["beschreibung"] = _no_unknown(result_json.get("beschreibung", ""))

    # Listen defaults
    for k in ["foto_empfehlungen", "sichtbare_symptome", "moegliche_ursachen", "lockout_gruende", "sofort_massnahmen", "vorbeugung"]:
        if k not in result_json or not isinstance(result_json[k], list):
            result_json[k] = []

    if "differential_diagnosen" not in result_json or not isinstance(result_json["differential_diagnosen"], list):
        result_json["differential_diagnosen"] = []

    # Lockout defaults
    if "lockout_verdacht" not in result_json:
        result_json["lockout_verdacht"] = False

    # Düngeregel final erzwingen (entscheidender Schutz!)
    if "duenge_empfehlung" not in result_json or not isinstance(result_json["duenge_empfehlung"], dict):
        result_json["duenge_empfehlung"] = {"erlaubt": False, "grund": "", "hinweis": ""}

    # Mehrfachbild? -> Düngung aus
    multi = False
    if len(result_json["differential_diagnosen"]) >= 2:
        # Wenn die Liste echte Inhalte hat
        probs = [d for d in result_json["differential_diagnosen"] if isinstance(d, dict) and str(d.get("problem", "")).strip()]
        if len(probs) >= 2:
            multi = True

    if result_json["lockout_verdacht"] or multi or result_json["bildqualitaet_score"] < 70:
        result_json["duenge_empfehlung"]["erlaubt"] = False
        if not result_json["duenge_empfehlung"].get("grund"):
            result_json["duenge_empfehlung"]["grund"] = "Lockout/pH/Wasserstress oder Mehrfachbild bzw. Bildqualität – erst Ursache prüfen."
        if not result_json["duenge_empfehlung"].get("hinweis"):
            result_json["duenge_empfehlung"]["hinweis"] = "Keine konkrete Dünge-/Dosierempfehlung. Bitte pH, Gießverhalten und Wurzelzone prüfen und Verlauf beobachten."
    else:
        # Nur wenn wirklich sauber
        if result_json["duenge_empfehlung"].get("erlaubt") is not True:
            result_json["duenge_empfehlung"]["erlaubt"] = True
            if not result_json["duenge_empfehlung"].get("grund"):
                result_json["duenge_empfehlung"]["grund"] = "Ein klares Hauptproblem bei guter Bildqualität und ohne Lockout-Hinweise."
            if not result_json["duenge_empfehlung"].get("hinweis"):
                result_json["duenge_empfehlung"]["hinweis"] = "Wenn du eingreifst, mache es vorsichtig und schrittweise – beobachte 48–72h."

    # 7) Cache speichern
    analysis_cache[img_hash] = {
        "ts": time.time(),
        "result": result_json,
        "meta": {
            "content_type": image.content_type,
            "bytes": len(data),
        },
    }

    # 8) Return (App erwartet result flach!)
    return {
        "status": "ok",
        "already_analyzed": False,
        "image_hash": img_hash,
        "result": result_json,
        "debug_photo_position": photo_position,
        "debug_shot_type": shot_type,
        "legal": {
            "disclaimer_title": t(lang, "disclaimer_title"),
            "disclaimer_body": t(lang, "disclaimer_body"),
            "privacy_title": t(lang, "privacy_title"),
            "privacy_body": t(lang, "privacy_body"),
        },
    }




# =========================
# FastAPI app
# =========================
app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Beta: ok. Später einschränken.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=OPENAI_API_KEY)


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": APP_NAME,
        "model": MODEL_NAME,
    }


@app.get("/legal")
def legal(lang: str = DEFAULT_LANG):
    """
    Backend liefert Texte für App-Seiten (ohne Website nötig).
    """
    return {
        "disclaimer_title": t(lang, "disclaimer_title"),
        "disclaimer_body": t(lang, "disclaimer_body"),
        "privacy_title": t(lang, "privacy_title"),
        "privacy_body": t(lang, "privacy_body"),
    }

@app.get("/health")
def health():
    return {"ok": True, "service": "growdoctor-backend", "version": app.version}

@app.get("/metrics")
def metrics():
    return {"cache_items": len(analysis_cache), "model": MODEL_NAME, "ts": int(time.time())}

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
    lang_final = normalize_lang(lang or language or locale)

    if not age_confirmed:
        raise HTTPException(status_code=400, detail=t(lang_final, "age_not_confirmed"))

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="No image data")

    img_hash = sha256_bytes(data)
    cache_key = f"{img_hash}:{lang_final}"

    cached = analysis_cache.get(cache_key)
    if cached and not force:
        return {
            "status": "ok",
            "already_analyzed": True,
            "message": t(lang_final, "already_analyzed"),
            "image_hash": img_hash,
            "result": cached["result"],
            "legal": legal_block(lang_final),
            "debug": {
                "lang": lang_final,
                "photo_position": photo_position,
                "shot_type": shot_type,
                "client_id": client_id or "",
                "model": MODEL_NAME,
                "cache": True,
            },
        }

    data_url = to_data_url(image.content_type, data)

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_user_prompt(lang_final, photo_position, shot_type)},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw_text = resp.choices[0].message.content or "{}"
        raw_json = json.loads(raw_text)
        result = normalize_result(raw_json)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openai_error: {str(e)}")

    analysis_cache[cache_key] = {"ts": time.time(), "result": result}

    return {
        "status": "ok",
        "already_analyzed": False,
        "message": "",
        "image_hash": img_hash,
        "result": result,
        "legal": legal_block(lang_final),
        "debug": {
            "lang": lang_final,
            "photo_position": photo_position,
            "shot_type": shot_type,
            "client_id": client_id or "",
            "model": MODEL_NAME,
            "cache": False,
        },
    }
