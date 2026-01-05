import os
import json
import base64
import hashlib
import time
from typing import Optional, Dict, Any, Tuple

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from openai import OpenAI

# =========================
# Config
# =========================
APP_NAME = "GrowDoctor Backend (Beta - Diagnose Only)"
DEFAULT_LANG = "de"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt. Bitte als Environment Variable in Render setzen.")

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# Max upload size (bytes) - keep it reasonable for Render free
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))  # 8 MB

# "Already analyzed" cache TTL
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", str(30 * 24 * 3600)))  # 30 days

# =========================
# Simple in-memory caches (ok for Beta)
# NOTE: Render free instances can restart -> counters reset.
# =========================
analysis_cache: Dict[str, Dict[str, Any]] = {}   # sha256 -> {ts, result, meta}
usage_counters: Dict[str, int] = {
    "diagnose_requests": 0,
    "unique_clients": 0,
}
seen_clients: Dict[str, float] = {}  # client_id_hash -> first_seen_ts


# =========================
# i18n text snippets (Beta)
# =========================
I18N = {
    "de": {
        "disclaimer_title": "Wichtiger Hinweis",
        "disclaimer_body": "Diese App liefert eine KI-basierte Einschätzung anhand von Fotos. Sie ersetzt keinen fachlichen Rat. Bei starken Symptomen oder Unsicherheit: bitte einen erfahrenen Grower/Experten hinzuziehen.",
        "privacy_title": "Datenschutz",
        "privacy_body": "Fotos werden nur zur Analyse an den KI-Dienst übertragen und von uns nicht gespeichert. Es werden keine personenbezogenen Daten benötigt. Optional kann eine anonyme Client-ID zur Nutzungsstatistik gesendet werden.",
        "age_error": "Altersbestätigung fehlt. Nutzung erst ab 18 Jahren.",
        "file_error": "Ungültige Datei. Bitte ein Bild (jpg/png/webp) hochladen.",
        "too_large": "Bild ist zu groß. Bitte ein kleineres Foto hochladen.",
        "already_analyzed": "Dieses Bild wurde schon analysiert.",
        "reanalyze_hint": "Du kannst trotzdem neu analysieren (force=true).",
        "quality_tips_title": "Foto-Tipps",
        "quality_tips_body": "1) Ganzes Pflanzenbild + 2) Nahaufnahme der betroffenen Stelle. Gute Beleuchtung, scharf, ohne Filter, ruhig halten. Bei Unterseite: Blatt umdrehen und fokussieren.",
    },
    "en": {
        "disclaimer_title": "Important notice",
        "disclaimer_body": "This app provides an AI-based estimate from photos. It does not replace expert advice. If symptoms are severe or you are unsure, consult an experienced grower/expert.",
        "privacy_title": "Privacy",
        "privacy_body": "Photos are only sent for analysis and are not stored by us. No personal data is required. Optionally, an anonymous client ID may be sent for usage statistics.",
        "age_error": "Age confirmation missing. 18+ only.",
        "file_error": "Invalid file. Please upload an image (jpg/png/webp).",
        "too_large": "Image is too large. Please upload a smaller photo.",
        "already_analyzed": "This image was analyzed before.",
        "reanalyze_hint": "You can still reanalyze (force=true).",
        "quality_tips_title": "Photo tips",
        "quality_tips_body": "1) Full plant photo + 2) close-up of affected area. Good light, sharp focus, no filters, keep steady. For underside: flip leaf and focus.",
    },
    "it": {
        "disclaimer_title": "Avviso importante",
        "disclaimer_body": "Questa app fornisce una valutazione basata su IA dalle foto. Non sostituisce un esperto. Se i sintomi sono gravi o hai dubbi, consulta un esperto.",
        "privacy_title": "Privacy",
        "privacy_body": "Le foto vengono inviate solo per l’analisi e non vengono salvate da noi. Non servono dati personali. Facoltativamente puoi inviare un ID anonimo per statistiche d’uso.",
        "age_error": "Conferma età mancante. Solo 18+.",
        "file_error": "File non valido. Carica un’immagine (jpg/png/webp).",
        "too_large": "Immagine troppo grande. Carica una foto più piccola.",
        "already_analyzed": "Questa immagine è stata già analizzata.",
        "reanalyze_hint": "Puoi comunque rianalizzare (force=true).",
        "quality_tips_title": "Consigli foto",
        "quality_tips_body": "1) Foto intera pianta + 2) zoom sulla parte colpita. Buona luce, fuoco nitido, senza filtri, mano ferma. Sottofoglia: gira la foglia e metti a fuoco.",
    },
    "fr": {
        "disclaimer_title": "Avis important",
        "disclaimer_body": "Cette app fournit une estimation IA à partir de photos. Elle ne remplace pas un avis expert. En cas de symptômes sévères ou de doute, consultez un expert.",
        "privacy_title": "Confidentialité",
        "privacy_body": "Les photos sont envoyées uniquement pour l’analyse et ne sont pas stockées par nous. Aucune donnée personnelle requise. Optionnel : un ID anonyme pour les statistiques d’usage.",
        "age_error": "Confirmation d’âge manquante. 18+ uniquement.",
        "file_error": "Fichier invalide. Téléversez une image (jpg/png/webp).",
        "too_large": "Image trop lourde. Téléversez une photo plus petite.",
        "already_analyzed": "Cette image a déjà été analysée.",
        "reanalyze_hint": "Vous pouvez quand même relancer l’analyse (force=true).",
        "quality_tips_title": "Conseils photo",
        "quality_tips_body": "1) Photo plante entière + 2) gros plan zone touchée. Bonne lumière, net, sans filtre, main stable. Dessous: retourner la feuille et faire le focus.",
    },
    "es": {
        "disclaimer_title": "Aviso importante",
        "disclaimer_body": "Esta app ofrece una estimación con IA basada en fotos. No sustituye a un experto. Si los síntomas son fuertes o hay dudas, consulta a un experto.",
        "privacy_title": "Privacidad",
        "privacy_body": "Las fotos solo se envían para el análisis y no las guardamos. No se requieren datos personales. Opcional: un ID anónimo para estadísticas de uso.",
        "age_error": "Falta confirmación de edad. Solo 18+.",
        "file_error": "Archivo inválido. Sube una imagen (jpg/png/webp).",
        "too_large": "La imagen es demasiado grande. Sube una foto más pequeña.",
        "already_analyzed": "Esta imagen ya fue analizada.",
        "reanalyze_hint": "Aun así puedes re-analizar (force=true).",
        "quality_tips_title": "Consejos de foto",
        "quality_tips_body": "1) Foto planta completa + 2) primer plano de la zona afectada. Buena luz, enfoque nítido, sin filtros, mano estable. En el envés: girar hoja y enfocar.",
    },
    "pt": {
        "disclaimer_title": "Aviso importante",
        "disclaimer_body": "Este app fornece uma estimativa por IA com base em fotos. Não substitui um especialista. Se os sintomas forem fortes ou houver dúvida, procure um especialista.",
        "privacy_title": "Privacidade",
        "privacy_body": "As fotos são enviadas apenas para análise e não são guardadas por nós. Não são necessários dados pessoais. Opcional: um ID anónimo para estatísticas.",
        "age_error": "Falta confirmação de idade. Apenas 18+.",
        "file_error": "Ficheiro inválido. Envie uma imagem (jpg/png/webp).",
        "too_large": "Imagem demasiado grande. Envie uma foto menor.",
        "already_analyzed": "Esta imagem já foi analisada.",
        "reanalyze_hint": "Ainda podes reanalisar (force=true).",
        "quality_tips_title": "Dicas de foto",
        "quality_tips_body": "1) Foto da planta inteira + 2) zoom da zona afetada. Boa luz, foco nítido, sem filtros, mão firme. Parte de baixo: virar a folha e focar.",
    },
    "nl": {
        "disclaimer_title": "Belangrijke melding",
        "disclaimer_body": "Deze app geeft een AI-inschatting op basis van foto’s. Dit vervangt geen expertadvies. Bij ernstige symptomen of twijfel: raadpleeg een expert.",
        "privacy_title": "Privacy",
        "privacy_body": "Foto’s worden alleen voor analyse verzonden en door ons niet opgeslagen. Geen persoonsgegevens nodig. Optioneel: anonieme client-ID voor gebruiksstatistiek.",
        "age_error": "Leeftijdsbevestiging ontbreekt. Alleen 18+.",
        "file_error": "Ongeldig bestand. Upload een afbeelding (jpg/png/webp).",
        "too_large": "Afbeelding is te groot. Upload een kleinere foto.",
        "already_analyzed": "Deze afbeelding is al eerder geanalyseerd.",
        "reanalyze_hint": "Je kunt toch opnieuw analyseren (force=true).",
        "quality_tips_title": "Fototips",
        "quality_tips_body": "1) Hele plant + 2) close-up van het probleem. Goed licht, scherp, geen filters, stil houden. Onderkant: blad omdraaien en scherpstellen.",
    },
    "cs": {
        "disclaimer_title": "Důležité upozornění",
        "disclaimer_body": "Aplikace poskytuje odhad pomocí AI z fotek. Nenahrazuje odborníka. Při silných příznacích nebo nejistotě kontaktujte experta.",
        "privacy_title": "Soukromí",
        "privacy_body": "Fotky se posílají jen k analýze a neukládáme je. Nejsou potřeba osobní údaje. Volitelně anonymní ID pro statistiky použití.",
        "age_error": "Chybí potvrzení věku. Pouze 18+.",
        "file_error": "Neplatný soubor. Nahrajte obrázek (jpg/png/webp).",
        "too_large": "Obrázek je příliš velký. Nahrajte menší.",
        "already_analyzed": "Tento obrázek už byl analyzován.",
        "reanalyze_hint": "Můžete i tak znovu analyzovat (force=true).",
        "quality_tips_title": "Tipy na fotku",
        "quality_tips_body": "1) Celá rostlina + 2) detail postižené části. Dobré světlo, ostře, bez filtrů. Spodek: otočit list a zaostřit.",
    },
    "pl": {
        "disclaimer_title": "Ważna informacja",
        "disclaimer_body": "Ta aplikacja daje ocenę AI na podstawie zdjęć. Nie zastępuje eksperta. Przy silnych objawach lub wątpliwościach skonsultuj się z ekspertem.",
        "privacy_title": "Prywatność",
        "privacy_body": "Zdjęcia są wysyłane tylko do analizy i nie są przez nas zapisywane. Nie są wymagane dane osobowe. Opcjonalnie anonimowe ID do statystyk użycia.",
        "age_error": "Brak potwierdzenia wieku. Tylko 18+.",
        "file_error": "Nieprawidłowy plik. Prześlij obraz (jpg/png/webp).",
        "too_large": "Zdjęcie jest za duże. Prześlij mniejsze.",
        "already_analyzed": "To zdjęcie było już analizowane.",
        "reanalyze_hint": "Możesz mimo to ponowić analizę (force=true).",
        "quality_tips_title": "Wskazówki foto",
        "quality_tips_body": "1) Cała roślina + 2) zbliżenie problemu. Dobre światło, ostro, bez filtrów. Spód: odwróć liść i ustaw ostrość.",
    },
}


def t(lang: str, key: str) -> str:
    lang = (lang or DEFAULT_LANG).lower().strip()
    if lang not in I18N:
        lang = DEFAULT_LANG
    return I18N[lang].get(key, I18N[DEFAULT_LANG].get(key, key))


# =========================
# Helpers
# =========================
def _cleanup_cache() -> None:
    now = time.time()
    expired = [k for k, v in analysis_cache.items() if now - v.get("ts", 0) > CACHE_TTL_SECONDS]
    for k in expired:
        analysis_cache.pop(k, None)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_client_id(client_id: str) -> str:
    # Store only hashed id (privacy-friendly)
    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()


def _validate_image(upload: UploadFile, data: bytes) -> None:
    if upload.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="file_error")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="too_large")


def _to_data_url(upload: UploadFile, data: bytes) -> str:
    mime = upload.content_type or "image/jpeg"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON extraction:
    - If model returns pure JSON -> parse directly
    - Else find first {...} block
    """
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
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
        "lang": (lang or DEFAULT_LANG),
        "disclaimer_title": t(lang, "disclaimer_title"),
        "disclaimer_body": t(lang, "disclaimer_body"),
        "privacy_title": t(lang, "privacy_title"),
        "privacy_body": t(lang, "privacy_body"),
        "quality_tips_title": t(lang, "quality_tips_title"),
        "quality_tips_body": t(lang, "quality_tips_body"),
    }


@app.get("/metrics")
def metrics():
    """
    Simple anonymous usage stats (Beta).
    """
    _cleanup_cache()
    return {
        "diagnose_requests": usage_counters.get("diagnose_requests", 0),
        "unique_clients": usage_counters.get("unique_clients", 0),
        "cache_size": len(analysis_cache),
        "note": "Render free instances may reset; use app analytics for downloads.",
    }


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

    # ---- normalize inputs (frontend/back compat) ----
    photo_position = (photo_position or "unknown").lower().strip()
    shot_type = (shot_type or "unknown").lower().strip()

    shot_type_map = {
        "whole": "whole_plant",
        "whole_plant": "whole_plant",
        "detail": "closeup",
        "zoom": "closeup",
        "closeup": "closeup",
        "unknown": "unknown",
    }
    shot_type = shot_type_map.get(shot_type, "unknown")

    pos_map = {
        "top": "top",
        "middle": "middle",
        "bottom": "bottom",
        "underside": "underside",
        "under": "underside",
        "unknown": "unknown",
    }
    photo_position = pos_map.get(photo_position, "unknown")
    # -----------------------------------------------

    # 1) Age gate
    if not age_confirmed:
        raise HTTPException(status_code=403, detail="age_error")


    # 2) Read file
    data = await image.read()
    _validate_image(image, data)

    # 3) Track usage (anonymous)
    usage_counters["diagnose_requests"] += 1
    if client_id:
        cid_hash = _hash_client_id(client_id)
        if cid_hash not in seen_clients:
            seen_clients[cid_hash] = time.time()
            usage_counters["unique_clients"] += 1

    # 4) Cache check (same image)
    _cleanup_cache()
    img_hash = _sha256(data)
    cached = analysis_cache.get(img_hash)

    if cached and not force:
        return {
            "status": "ok",
            "already_analyzed": True,
            "message": t(lang, "already_analyzed"),
            "hint": t(lang, "reanalyze_hint"),
            "image_hash": img_hash,
            "result": cached.get("result", {}),
            "debug_photo_position": photo_position, 
            "bebug_shot_type": shot_type,
            "legal": {
                "disclaimer_title": t(lang, "disclaimer_title"),
                "disclaimer_body": t(lang, "disclaimer_body"),
                "privacy_title": t(lang, "privacy_title"),
                "privacy_body": t(lang, "privacy_body"),
            },
        }

    # 5) OpenAI call (image + prompt)
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
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"openai_error: {str(e)}")

    result_json = _extract_json(content)

        # ---- legacy output for Beta/Pro-UI compatibility ----
    def _legacy_from_new_schema(r: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert new schema (analyse/unsicherheit/empfehlung/qualitaet/...) into
        the older flat fields the Flutter UI expects.
        """
        analyse = r.get("analyse") or {}
        qual = r.get("qualitaet") or {}
        uns = r.get("unsicherheit") or {}
        emp = r.get("empfehlung") or {}

        ist_unsicher = bool(uns.get("ist_unsicher", False))
        primary = uns.get("primary") or {}
        secondary = uns.get("secondary") or {}

        # Pick main problem
        if ist_unsicher and primary.get("hauptproblem"):
            hauptproblem = str(primary.get("hauptproblem"))
            kategorie = str(primary.get("kategorie", analyse.get("kategorie", "unbekannt")))
            wahrscheinlichkeit = primary.get("wahrscheinlichkeit", analyse.get("wahrscheinlichkeit", 0))
        else:
            hauptproblem = str(analyse.get("hauptproblem", "unbekannt"))
            kategorie = str(analyse.get("kategorie", "unbekannt"))
            wahrscheinlichkeit = analyse.get("wahrscheinlichkeit", 0)

        # Ensure percentage-like number (0..100)
        try:
            w = float(wahrscheinlichkeit)
        except Exception:
            w = 0.0
        if 0 < w <= 1:
            w = w * 100.0

        # Flatten to old keys
        legacy = {
            "hauptproblem": hauptproblem,
            "kategorie": kategorie,
            "wahrscheinlichkeit": int(round(w)),
            "beschreibung": str(emp.get("kurz") or ""),
            "stadium": "unbekannt",
            "betroffene_teile": analyse.get("symptome") or [],
            "sofort_massnahmen": emp.get("naechste_schritte") or [],
            "vorbeugung": [],
            "alternativen": [],
            "empfohlene_kontrolle_in_tagen": 3,
            "dringlichkeit": "mittel",
            "schweregrad": "mittel",
            "bildqualitaet_score": qual.get("score", 80),
            "hinweis_bildqualitaet": qual.get("hinweis", ""),
            "foto_empfehlungen": (qual.get("foto_tipps") or []),
# helpful flags for UI later
            "ist_unsicher": False if w >= 75 else ist_unsicher,

        }
        return legacy

    legacy_result = _legacy_from_new_schema(result_json)
    # -----------------------------------------------


            # --- GrowDoctor: Ursachenbasierte Sicherheitslogik ---
    details_text = str(result_json.get("details", "")).lower()

    sofort_text = " ".join(
        m.lower() for m in result_json.get("sofortmassnahmen", [])
        if isinstance(m, str)
    )

    problem_text = details_text + " " + sofort_text

    lockout_keywords = [
        "überwässer",
        "staunässe",
        "ph",
        "lockout",
        "wasserstress",
        "stoffwechsel",
        "aufnahme gestört",
        "blockade",
        "wurzelproblem",
        "salz",
        "ec"
    ]

    lockout_detected = any(k in problem_text for k in lockout_keywords)

    if lockout_detected:
        result_json["duenge_empfehlung"] = {
            "erlaubt": False,
            "grund": "Möglicher Nährstoff-Lockout oder pH-/Bewässerungsproblem erkannt.",
            "hinweis": (
                "Keine Düngeempfehlung, da zuerst pH-Wert, Bewässerung "
                "und Wurzelzone stabilisiert werden müssen."
            )
        }


    # 6) Minimal safety defaults if model output missing fields
    if "sicherheit" not in result_json:
        result_json["sicherheit"] = {
            "haertung": "medium",
            "hinweis_experte": True,
            "haftungsausschluss_kurz": t(lang, "disclaimer_body"),
        }
    if "qualitaet" not in result_json:
        result_json["qualitaet"] = {
            "qualitaet_ok": False,
            "gruende": [],
            "foto_tipps": [t(lang, "quality_tips_body")],
        }

    # 7) Store in cache (no photo storage, only hash+result)
    analysis_cache[img_hash] = {
        "ts": time.time(),
        "result": result_json,
        "meta": {
            "content_type": image.content_type,
            "bytes": len(data),
        },
    }

    return {
        "status": "ok",
        "already_analyzed": False,
        "image_hash": img_hash,
        "result": legacy_result,
        "debug_photo_position": photo_position, 
        "debug_shot_type": shot_type,
        "legal": {
            "disclaimer_title": t(lang, "disclaimer_title"),
            "disclaimer_body": t(lang, "disclaimer_body"),
            "privacy_title": t(lang, "privacy_title"),
            "privacy_body": t(lang, "privacy_body"),
        },
    }
