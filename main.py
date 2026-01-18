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
BETA_FLOWER_NO_MATURITY_RULE = """
IMPORTANT (BETA RULE):
If the image shows a cannabis flower/bud:
- Do NOT analyze maturity or harvest timing
- Do NOT mention trichome colors (clear, milky, cloudy, amber)
- Do NOT give harvest or ripeness advice
- ONLY state whether the flower looks healthy or shows visible problems
- Focus on mold, pests, rot, or visible damage
"""

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
        return default

def compute_ampel(wahrscheinlichkeit: int, ist_unsicher: bool) -> str:
    if ist_unsicher:
        return "gelb"
    if wahrscheinlichkeit >= 70:
        return "gruen"
    if wahrscheinlichkeit >= 40:
        return "gelb"
    return "rot"

def build_system_prompt() -> str:
    return (
        "You are GrowDoctor, a plant health diagnostic assistant.\n"
        "Return ONLY valid JSON (no markdown, no extra text).\n"
        "If NO plant problem is detected (healthy plant / Ampel = green):\n"
        "- Keep the description VERY short (MAX 1 sentence).\n"
        "- Do NOT explain normal or healthy visual features.\n"
        "- Do NOT describe trichomes, pistils, color, structure, or ripeness.\n"
        "- Focus only on: no visible problems detected.\n"

        "FLOWER RULE (MUST): If the photo shows buds or flowers, DO NOT assess ripeness or maturity. Only state whether the buds look HEALTHY or NOT HEALTHY and whether visible mold, rot, pests or other problems are present. Never mention trichomes, harvest timing or maturity stages. If unsure, set ist_unsicher=true.\n"
        "Use exactly the schema provided. Never use null.\n"
        "Use empty string \"\" for missing text and [] for missing lists.\n"
        "\n"
        "Critical visual rule (MUST): Do NOT label trichomes/resin glands as mold.\n"
        "Trichomes look like sparkling/milky/amber crystal heads on buds.\n"
        "Mold is fuzzy/cottony web-like growth, powdery coating, or slimy rot.\n"
        "If you cannot clearly see fuzzy/mycelium/powder, do NOT claim mold.\n"
        "Instead set ist_unsicher=true and request macro close-ups + environment info.\n"
        "\n"
        "Plant physiology (MUST): Always consider leaf age/location.\n"
        "- Older/lower leaves: more likely mobile nutrient issues (N, P, K, Mg) or senescence.\n"
        "- Newer/top growth: more likely immobile issues (Ca, Fe, S, B, Mn, Zn) or pH/lockout.\n"
        "If multiple symptoms conflict, prioritize root-zone/pH/EC/lockout explanation.\n"
        "OUTPUT STYLE (BETA): Keep explanations concise. Use at most 2–3 short sentences per section. Avoid repetition and long descriptions. Be factual and practical.\n"
        "HARD LENGTH LIMITS (BETA): "
        "- hauptproblem: max 1 short sentence. "
        "- beschreibung: max 2 short sentences. "
        "- sichtbare_symptome: max 3 bullet points. "
        "- moegliche_ursachen: max 3 bullet points. "
        "- sofort_massnahmen: max 3 bullet points. "
        "- vorbeugung: max 2 bullet points. "
        "Never exceed these limits.\n"

    )

def build_user_prompt(lang: str, photo_position: str, shot_type: str) -> str:
    return (
        f"Language: {lang}\n"
        f"Photo position: {photo_position}\n"
        f"Shot type: {shot_type}\n\n"
        "Return JSON with EXACTLY these keys:\n"
        "{\n"
        '  "hauptproblem": string,\n'
        '  "kategorie": string,\n'
        '  "wahrscheinlichkeit": number (0-100),\n'
        '  "beschreibung": string,\n'
        '  "betroffene_teile": array of strings,\n'
        '  "sichtbare_symptome": array of strings,\n'
        '  "moegliche_ursachen": array of strings,\n'
        '  "sofort_massnahmen": array of strings,\n'
        '  "vorbeugung": array of strings,\n'
        '  "bildqualitaet_score": number (0-100),\n'
        '  "hinweis_bildqualitaet": string,\n'
        '  "ist_unsicher": boolean,\n'
        '  "unsicher_grund": string,\n'
        '  "duengen_erlaubt": boolean,\n'
        '  "profi_empfohlen": boolean,\n'
        '  "profi_grund": string\n'
        "}\n\n"
        "Rules:\n"
        "- If unsure: set ist_unsicher=true and fill unsicher_grund.\n"
        "- If lockout/pH suspected: set duengen_erlaubt=false and recommend measurement.\n"
        "- If mold is not clearly visible: do NOT claim mold.\n"
    )

def normalize_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    wahrscheinlichkeit = clamp_int(raw.get("wahrscheinlichkeit"), 0, 100, 50)
    ist_unsicher = bool(raw.get("ist_unsicher", False))

    result: Dict[str, Any] = {
        "hauptproblem": ensure_str(raw.get("hauptproblem")),
        "kategorie": ensure_str(raw.get("kategorie")),
        "wahrscheinlichkeit": wahrscheinlichkeit if wahrscheinlichkeit > 0 else 1,
        "beschreibung": ensure_str(raw.get("beschreibung")),
        "betroffene_teile": ensure_list(raw.get("betroffene_teile")),
        "sichtbare_symptome": ensure_list(raw.get("sichtbare_symptome")),
        "moegliche_ursachen": ensure_list(raw.get("moegliche_ursachen")),
        "sofort_massnahmen": ensure_list(raw.get("sofort_massnahmen")),
        "vorbeugung": ensure_list(raw.get("vorbeugung")),
        "bildqualitaet_score": clamp_int(raw.get("bildqualitaet_score"), 0, 100, 60),
        "hinweis_bildqualitaet": ensure_str(raw.get("hinweis_bildqualitaet")),
        "ist_unsicher": ist_unsicher,
        "unsicher_grund": ensure_str(raw.get("unsicher_grund")),
        "duengen_erlaubt": bool(raw.get("duengen_erlaubt", True)),
        "profi_empfohlen": bool(raw.get("profi_empfohlen", False)),
        "profi_grund": ensure_str(raw.get("profi_grund")),
    }
    result["ampel"] = compute_ampel(result["wahrscheinlichkeit"], result["ist_unsicher"])
    return result

def legal_block(lang: str) -> Dict[str, str]:
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


