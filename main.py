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


def _diagnose_prompt(lang: str, photo_position: str, shot_type: str) -> Tuple[str, str]:
    """
    system_prompt, user_prompt
    """
    system_prompt = (
    "Du bist ein hochspezialisierter Cannabis-Grow-Diagnose-Experte.\n"
    "Analysiere AUSSCHLIESSLICH sichtbare Merkmale im Foto.\n\n"

    "WICHTIG – absolute Prioritäten:\n"
    "- Gib IMMER reines JSON zurück, ohne Markdown, ohne Zusatztext.\n"
    "- Verwechsle NÄHRSTOFF-ÜBERSCHUSS NICHT mit MANGEL.\n"
    "- Wenn Symptome für Mangel UND Überschuss passen könnten:\n"
    "  → markiere UNSICHERHEIT\n"
    "  → liefere ZWEI Diagnosen (primary + secondary) mit Wahrscheinlichkeiten (Summe = 100).\n\n"

    "SICHTBARE UNTERSCHIEDE (bindend):\n"
    "- MANGEL:\n"
    "  - eher gleichmäßige Aufhellung\n"
    "  - beginnt häufig an unteren Blättern\n"
    "  - kein starkes Glänzen\n"
    "- ÜBERSCHUSS / TOX:\n"
    "  - sehr dunkles Grün\n"
    "  - glänzende / ledrige Blätter\n"
    "  - Clawing (Blätter haken nach unten)\n"
    "- LOCKOUT:\n"
    "  - Mischsymptome mehrerer Mängel\n"
    "  - fleckig / inkonsistent\n"
    "  - oft Folge von pH / Salz / Überschuss\n\n"

    "Regeln:\n"
    "- KEINE Anbau- oder Konsumanleitung.\n"
    "- NUR Zustandsanalyse.\n"
    "- Berücksichtige Fotoposition und Shot-Typ.\n"
    "- Bei starker Unsicherheit oder Gefahr:\n"
    "  → hinweis_experte = true\n"
)


    user_prompt = (
    "Foto-Kontext:\n"
    f"- Fotoposition: {photo_position}\n"
    f"- Shot-Typ: {shot_type}\n\n"

    "AUFGABE:\n"
    "1) Prüfe, ob auf dem Bild Cannabis zu sehen ist.\n"
    "   - Wenn KEIN Cannabis oder nicht eindeutig erkennbar: setze ist_cannabis=false und stoppe die Analyse.\n\n"

    "2) Wenn Cannabis:\n"
    "   - Bestimme GENAU EIN Hauptproblem.\n"
    "   - Ordne es EINER Kategorie zu:\n"
    "     naehrstoffmangel | naehrstoffueberschuss | bewaesserung | schaedlinge | krankheit | umwelt | unbekannt\n\n"

    "WICHTIGE ENTSCHEIDUNGSREGEL (sehr wichtig):\n"
    "- Verwechsele Nährstoff-MANGEL NICHT mit Nährstoff-ÜBERSCHUSS.\n"
    "- MANGEL:\n"
    "  * eher hellgrün / gelblich\n"
    "  * Chlorosen\n"
    "  * beginnt oft an unteren Blättern\n"
    "- ÜBERSCHUSS / TOXIZITÄT:\n"
    "  * sehr dunkles Grün\n"
    "  * glänzende, ledrige Blätter\n"
    "  * Clawing (Blätter haken nach unten)\n"
    "  * gehemmtes oder gestautes Wachstum\n"
    "- Wenn Symptome für BEIDES passen:\n"
    "  -> markiere die Diagnose als UNSICHER\n"
    "  -> liefere ZWEI Diagnosen (primary + secondary)\n\n"

    "3) Gib eine Wahrscheinlichkeit (0–100) für die Diagnose an.\n"
    "   - Bei unsicherer Diagnose: Wahrscheinlichkeiten für primary + secondary angeben.\n"
    "   - Die Summe aller Wahrscheinlichkeiten MUSS 100 ergeben.\n\n"

    "4) Liste sichtbare Symptome und mögliche Ursachen.\n"
    "   - Nur das, was auf dem Bild sichtbar ist.\n"
    "   - Keine Vermutungen ohne Bildbezug.\n\n"

    "5) Gib eine kurze, sichere Empfehlung:\n"
    "   - KEINE detaillierten Anbau- oder Düngeanleitungen.\n"
    "   - Nur nächste sinnvolle Schritte (z. B. prüfen, beobachten, Bild nachreichen).\n\n"

    "6) Bildqualität prüfen:\n"
    "   - Wenn das Foto unscharf, zu dunkel, zu weit weg oder unvollständig ist:\n"
    "     * setze qualitaet_ok=false\n"
    "     * erkläre kurz warum\n"
    "     * gib konkrete Foto-Tipps (z. B. Blattunterseite, Gesamtpflanze, Nähe)\n\n"

    "7) SICHERHEIT & HAFTUNG:\n"
    "   - Wenn starke Probleme, Gefahren oder hohe Unsicherheit bestehen:\n"
    "     * setze hinweis_experte=true\n"
    "     * formuliere einen kurzen Haftungsausschluss\n"
    "     * empfehle einen erfahrenen Grower oder Fachperson hinzuzuziehen\n\n"

    "GIB AUSSCHLIESSLICH JSON ZURÜCK.\n"
    "KEIN Markdown. KEIN Freitext. KEINE zusätzlichen Erklärungen.\n\n"

    "JSON-SCHEMA (exakt diese Keys verwenden):\n"
    "{\n"
    "  \"ist_cannabis\": boolean,\n"
    "  \"sicherheit\": {\n"
    "    \"haertung\": \"low|medium|high\",\n"
    "    \"hinweis_experte\": boolean,\n"
    "    \"haftungsausschluss_kurz\": string\n"
    "  },\n"
    "  \"qualitaet\": {\n"
    "    \"qualitaet_ok\": boolean,\n"
    "    \"gruende\": [string],\n"
    "    \"foto_tipps\": [string]\n"
    "  },\n"
    "  \"analyse\": {\n"
    "    \"hauptproblem\": string,\n"
    "    \"kategorie\": string,\n"
    "    \"wahrscheinlichkeit\": number,\n"
    "    \"symptome\": [string],\n"
    "    \"moegliche_ursachen\": [string]\n"
    "  },\n"
    "  \"unsicherheit\": {\n"
    "    \"ist_unsicher\": boolean,\n"
    "    \"primary\": {\n"
    "      \"kategorie\": string,\n"
    "      \"hauptproblem\": string,\n"
    "      \"wahrscheinlichkeit\": number\n"
    "    },\n"
    "    \"secondary\": {\n"
    "      \"kategorie\": string,\n"
    "      \"hauptproblem\": string,\n"
    "      \"wahrscheinlichkeit\": number\n"
    "    },\n"
    "    \"benoetigte_fotos\": [string]\n"
    "  },\n"
    "  \"empfehlung\": {\n"
    "    \"kurz\": string,\n"
    "    \"naechste_schritte\": [string],\n"
    "    \"wann_experte\": string\n"
    "  }\n"
    "}\n"
)


    return system_prompt, user_prompt


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
    photo_position: str = Form("unknown"),  # top|middle|bottom|underside|unknown
    shot_type: str = Form("unknown"),       # whole_plant|closeup|unknown
    client_id: Optional[str] = Form(None),  # anonymous client id from app (optional)
    force: bool = Form(False),              # reanalyze even if already analyzed
):
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
        "result": result_json,
        "legal": {
            "disclaimer_title": t(lang, "disclaimer_title"),
            "disclaimer_body": t(lang, "disclaimer_body"),
            "privacy_title": t(lang, "privacy_title"),
            "privacy_body": t(lang, "privacy_body"),
        },
    }
