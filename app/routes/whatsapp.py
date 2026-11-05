"""WhatsApp webhook + send + AI routes (Meta WhatsApp Cloud API only, no Twilio).

- GET /whatsapp/webhook (+ alias GET /webhook): Meta verification.
- POST /whatsapp/webhook (+ alias POST /webhook): receive messages, always
  200 fast. Verifies X-Hub-Signature-256 when WHATSAPP_APP_SECRET is set,
  dedupes by message id, replies with AI in the farmer's language, and
  saves both sides to the conversations table.
- POST /whatsapp/send (+ alias POST /api/whatsapp/send): test send endpoint.
- GET /whatsapp/status (+ alias GET /api/whatsapp/status): status check.

Official Meta WhatsApp Cloud API only:
- Send: POST https://graph.facebook.com/v21.0/{phone-number-id}/messages
- Media: GET https://graph.facebook.com/v21.0/{media-id} -> {"url": ...},
  then GET that url. Both with "Authorization: Bearer <token>".
No token is ever printed, logged, or returned to any caller.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..ai_service import get_ai_reply
from ..config import settings, whatsapp_configured
from ..database import get_db
from ..services.image_service import image_service
from ..services.voice_service import voice_service
from ..services.whatsapp_service import parse_webhook_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Alias for Meta dashboard compatibility: GET/POST /webhook + /api aliases
# call the same functions. No main.py change needed (alias_router is mounted).
alias_router = APIRouter(tags=["whatsapp"])

GRAPH_BASE_URL = "https://graph.facebook.com"
SEND_TIMEOUT_SECONDS = 15
MEDIA_TIMEOUT_SECONDS = 15
MAX_MEDIA_BYTES = 5 * 1024 * 1024  # WhatsApp media limit for this receiver
MAX_TEXT_LENGTH = 2000  # matches POST /chat limit
MAX_SEND_LENGTH = 4096  # WhatsApp text message limit

WELCOME_MESSAGE = "Welcome to KrishiMitra! Choose 1.Tamil 2.Hindi 3.English"
MENU_MESSAGE = (
    "KrishiMitra menu:\n"
    "1. Ask a question\n"
    "2. Crop photo\n"
    "3. Weather\n"
    "4. Mandi price\n"
    "5. Voice question\n"
    "6. Rescue plan\n"
    "Reply with your question."
)

LANGUAGE_CHOICES = {
    "1": "ta",
    "2": "hi",
    "3": "en",
    "tamil": "ta",
    "tamilnadu": "ta",
    "hindi": "hi",
    "english": "en",
    "angilam": "en",
}

UNSUPPORTED_TYPE_MESSAGE = {
    "en": "Sorry, I can read text, photos and voice notes only. Please send your question as text.",
    "ta": "மன்னிக்கவும், என்னால் உரை, புகைப்படம், குரல் செய்திகளை மட்டுமே படிக்க முடியும். உங்கள் கேள்வியை உரையாக அனுப்புங்கள்.",
    "hi": "क्षमा करें, मैं केवल टेक्स्ट, फोटो और वॉइस नोट पढ़ सकता हूँ। कृपया अपना सवाल टेक्स्ट में भेजें।",
}

PHOTO_NOT_CONFIGURED_MESSAGE = {
    "en": "Photo received, but photo download is not configured yet. Please send a clear close-up photo in daylight.",
    "ta": "புகைப்படம் கிடைத்தது, ஆனால் பதிவிறக்கம் இன்னும் அமைக்கப்படவில்லை. பகல் வெளிச்சத்தில் தெளிவான நெருக்கமான புகைப்படம் அனுப்புங்கள்.",
    "hi": "फोटो मिली, लेकिन फोटो डाउनलोड अभी सेट नहीं है। कृपया दिन के उजाले में साफ नज़दीकी फोटो भेजें।",
}

VOICE_NOT_CONFIGURED_MESSAGE = {
    "en": "Voice note received, but voice download is not configured yet. Please type your question as text.",
    "ta": "குரல் செய்தி கிடைத்தது, ஆனால் பதிவிறக்கம் இன்னும் அமைக்கப்படவில்லை. உங்கள் கேள்வியை உரையாக அனுப்புங்கள்.",
    "hi": "वॉइस नोट मिला, लेकिन वॉइस डाउनलोड अभी सेट नहीं है। कृपया अपना सवाल टेक्स्ट में लिखें।",
}

# Dedupe cache: Meta may retry webhooks; ignore repeats by message id.
_SEEN_MESSAGE_IDS: set[str] = set()
_SEEN_CAP = 5000


def _reset_seen_message_ids() -> None:
    """Test helper: clear the webhook dedupe cache."""
    _SEEN_MESSAGE_IDS.clear()


def _upload_dir() -> str:
    """Folder for WhatsApp media (UPLOAD_DIR env override for tests)."""
    folder = os.getenv("UPLOAD_DIR", "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder


def _signature_ok(raw_body: bytes, header: str | None, secret: str) -> bool:
    """Check X-Hub-Signature-256 ("sha256=<hex>") with hmac. Never raises."""
    try:
        if not header or not header.startswith("sha256="):
            return False
        given = header.split("=", 1)[1].strip()
        if not given:
            return False
        expected = hmac.new(
            secret.encode("utf-8"), raw_body or b"", hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, given)
    except Exception:
        return False


def _parse_language_choice(text: str) -> str | None:
    """Map 1/2/3 or language name to ta/hi/en; None when not a choice."""
    return LANGUAGE_CHOICES.get((text or "").strip().lower())


def _send_url(phone_number_id: str, version: str) -> str:
    """Official send URL for one business phone number id."""
    return f"{GRAPH_BASE_URL}/{version}/{phone_number_id}/messages"


def _build_text_payload(to: str, text: str) -> dict[str, Any]:
    """Official text-message JSON body (required fields only)."""
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }


def _do_send_text(to: str, text: str) -> dict[str, Any]:
    """Send one WhatsApp text message. Mock when credentials are missing.

    Real path uses the official endpoint with a 15s timeout and maps
    401/404/429 to structured failures. Never raises, never leaks the token.
    """
    clean_to = (to or "").strip()
    clean_text = (text or "").strip()
    if not clean_to or not clean_text:
        return {"status": "rejected", "detail": "to and text must not be empty"}
    if not whatsapp_configured():
        logger.info(
            "WhatsApp mock send to=%s chars=%d", clean_to, len(clean_text)
        )
        return {
            "status": "mock",
            "Detail": "missing credentials",
            "detail": "missing credentials",
            "to": clean_to,
            "mode": "mock",
        }
    url = _send_url(settings.whatsapp_phone_number_id, settings.whatsapp_api_version)
    try:
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.whatsapp_token}",
                "Content-Type": "application/json",
            },
            json=_build_text_payload(clean_to, clean_text),
            timeout=SEND_TIMEOUT_SECONDS,
        )
        if resp.status_code == 401:
            logger.warning("WhatsApp send failed: unauthorized")
            return {
                "status": "failed",
                "error": "unauthorized",
                "code": 401,
                "detail": "WhatsApp token rejected (401). Check WHATSAPP_TOKEN.",
            }
        if resp.status_code == 404:
            logger.warning("WhatsApp send failed: not found")
            return {
                "status": "failed",
                "error": "not_found",
                "code": 404,
                "detail": "Phone number id not found (404). Check WHATSAPP_PHONE_NUMBER_ID.",
            }
        if resp.status_code == 429:
            logger.warning("WhatsApp send failed: rate limited")
            return {
                "status": "failed",
                "error": "rate_limited",
                "code": 429,
                "detail": "WhatsApp rate limited (429). Try again later.",
            }
        resp.raise_for_status()
        message_id: str | None = None
        try:
            data = resp.json()
            items = data.get("messages") if isinstance(data, dict) else None
            if isinstance(items, list) and items and isinstance(items[0], dict):
                raw_id = items[0].get("id")
                message_id = raw_id if isinstance(raw_id, str) else None
        except Exception:
            message_id = None
        logger.info("WhatsApp sent to=%s", clean_to)
        return {
            "status": "sent",
            "to": clean_to,
            "mode": "real",
            "message_id": message_id,
        }
    except httpx.TimeoutException:
        logger.warning("WhatsApp send failed: timeout")
        return {"status": "failed", "error": "timeout", "detail": "WhatsApp send timed out."}
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp send failed: %s", type(exc).__name__)
        return {"status": "failed", "error": type(exc).__name__}
    except Exception as exc:  # Any failure -> safe failed result, never raise.
        logger.warning("WhatsApp send failed: %s", type(exc).__name__)
        return {"status": "failed", "error": type(exc).__name__}


def _get_or_create_farmer(db: Session, phone: str) -> tuple[models.Farmer, bool]:
    """Find a farmer by phone, or create one with language choice pending."""
    farmer = db.query(models.Farmer).filter(models.Farmer.phone == phone).first()
    if farmer is not None:
        return farmer, False
    farmer = models.Farmer(
        name=f"WhatsApp {phone}"[:100],
        phone=phone,
        preferred_language="",  # "" = language not chosen yet
    )
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return farmer, True


def _save_exchange(
    db: Session,
    farmer_id: int,
    farmer_text: str,
    assistant_text: str,
    language: str,
    message_type: str = "text",
) -> None:
    """Save BOTH sides of one turn to the conversations table."""
    lang = language if language in ("en", "ta", "hi") else "en"
    db.add(
        models.Conversation(
            farmer_id=farmer_id,
            role="farmer",
            message_type=message_type,
            content=(farmer_text or "")[:5000],
            language=lang,
        )
    )
    db.add(
        models.Conversation(
            farmer_id=farmer_id,
            role="assistant",
            message_type="text",
            content=(assistant_text or "")[:5000],
            language=lang,
        )
    )
    db.commit()


def _download_media_bytes(media_id: str) -> tuple[bytes | None, str]:
    """Download one media object. Returns (bytes, mime) or (None, "").

    Official flow only: GET /{media-id} -> {"url": ...}, then GET the url.
    Both calls use the Bearer token with a 15s timeout. Never raises,
    never logs the token or url. Returns (None, "") on any failure.
    """
    try:
        settings.refresh()
        token = settings.whatsapp_token
        version = settings.whatsapp_api_version
        meta_resp = httpx.get(
            f"{GRAPH_BASE_URL}/{version}/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=MEDIA_TIMEOUT_SECONDS,
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        if not isinstance(meta, dict):
            return None, ""
        url = meta.get("url")
        mime = meta.get("mime_type") or ""
        if not isinstance(url, str) or not url:
            return None, ""
        try:
            declared = int(meta.get("file_size") or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared and declared > MAX_MEDIA_BYTES:
            return None, ""
        file_resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=MEDIA_TIMEOUT_SECONDS,
        )
        file_resp.raise_for_status()
        data = file_resp.content
        if not data or len(data) > MAX_MEDIA_BYTES:
            return None, ""
        return data, mime if isinstance(mime, str) else ""
    except Exception as exc:
        logger.warning("WhatsApp media download failed: %s", type(exc).__name__)
        return None, ""


def _format_image_reply(result: dict[str, Any]) -> str:
    """Build the WhatsApp reply from the existing image analysis result."""
    observation = str(result.get("observation", "") or "")
    issues = result.get("possible_issues") or []
    if isinstance(issues, list):
        issues_text = "; ".join(str(i) for i in issues[:4])
    else:
        issues_text = str(issues)
    confidence = str(result.get("confidence", "low") or "low")
    safety_note = str(result.get("safety_note", "") or "")
    parts = [observation]
    if issues_text:
        parts.append(f"Possible issues: {issues_text}")
    parts.append(f"Confidence: {confidence}")
    if safety_note:
        parts.append(safety_note)
    return "\n".join(part for part in parts if part)[:3500]


async def _handle_image(
    db: Session, farmer: models.Farmer, sender: str, lang: str, raw: dict
) -> None:
    """Download a WhatsApp photo, analyse it, save both sides, reply."""
    language = lang if lang in ("en", "ta", "hi") else "en"
    image_obj = raw.get("image")
    media_id = image_obj.get("id") if isinstance(image_obj, dict) else None
    if not media_id or not isinstance(media_id, str):
        reply = PHOTO_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[photo]", reply, language, "image")
        _do_send_text(sender, reply)
        return
    if not whatsapp_configured():
        reply = PHOTO_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[photo]", reply, language, "image")
        _do_send_text(sender, reply)
        return
    data, mime = _download_media_bytes(media_id)
    if data is None or mime not in ("image/jpeg", "image/png", "image/jpg"):
        reply = PHOTO_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[photo]", reply, language, "image")
        _do_send_text(sender, reply)
        return
    ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
    saved_name = f"wa_{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(_upload_dir(), saved_name)
    try:
        with open(saved_path, "wb") as handle:
            handle.write(data)
    except OSError:
        reply = PHOTO_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[photo]", reply, language, "image")
        _do_send_text(sender, reply)
        return
    try:
        result = image_service.analyse_crop_image(saved_path, language)
    except Exception:
        result = image_service.analyse_crop_image(saved_path, language)
    reply = _format_image_reply(result if isinstance(result, dict) else {})
    if not reply:
        reply = PHOTO_NOT_CONFIGURED_MESSAGE[language]
    _save_exchange(db, farmer.id, f"[photo {saved_name}]", reply, language, "image")
    _do_send_text(sender, reply)


async def _handle_voice(
    db: Session, farmer: models.Farmer, sender: str, lang: str, raw: dict
) -> None:
    """Download a WhatsApp voice note, transcribe it, answer with AI."""
    language = lang if lang in ("en", "ta", "hi") else "en"
    audio_obj = raw.get("audio")
    media_id = audio_obj.get("id") if isinstance(audio_obj, dict) else None
    if not media_id or not isinstance(media_id, str):
        reply = VOICE_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[voice note]", reply, language, "audio")
        _do_send_text(sender, reply)
        return
    if not whatsapp_configured():
        reply = VOICE_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[voice note]", reply, language, "audio")
        _do_send_text(sender, reply)
        return
    data, mime = _download_media_bytes(media_id)
    if data is None:
        reply = VOICE_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[voice note]", reply, language, "audio")
        _do_send_text(sender, reply)
        return
    ext = ".ogg"
    if "mpeg" in mime or "mp3" in mime:
        ext = ".mp3"
    elif "mp4" in mime or "m4a" in mime:
        ext = ".m4a"
    elif "wav" in mime:
        ext = ".wav"
    elif "webm" in mime:
        ext = ".webm"
    saved_name = f"wa_{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(_upload_dir(), saved_name)
    try:
        with open(saved_path, "wb") as handle:
            handle.write(data)
    except OSError:
        reply = VOICE_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[voice note]", reply, language, "audio")
        _do_send_text(sender, reply)
        return
    try:
        transcript = voice_service.transcribe_audio_file(saved_path, language).get(
            "transcript", ""
        )
    except Exception:
        transcript = ""
    transcript = (transcript or "").strip()
    if not transcript:
        reply = VOICE_NOT_CONFIGURED_MESSAGE[language]
        _save_exchange(db, farmer.id, "[voice note]", reply, language, "audio")
        _do_send_text(sender, reply)
        return
    answer = await get_ai_reply(transcript, language)
    reply = f"{transcript}\n\n{answer}"[:3500]
    _save_exchange(db, farmer.id, transcript[:2000], reply, language, "audio")
    _do_send_text(sender, reply)


async def _handle_message(db: Session, msg: dict[str, Any]) -> None:
    """Route one incoming WhatsApp message: dedupe, AI, save, reply."""
    msg_id = msg.get("id")
    if isinstance(msg_id, str) and msg_id:
        if msg_id in _SEEN_MESSAGE_IDS:
            return
        _SEEN_MESSAGE_IDS.add(msg_id)
        if len(_SEEN_MESSAGE_IDS) > _SEEN_CAP:
            _SEEN_MESSAGE_IDS.clear()
    sender = (msg.get("from") or "").strip()
    if not sender:
        return
    msg_type = (msg.get("type") or "").strip()
    raw = msg.get("raw")
    raw_dict = raw if isinstance(raw, dict) else {}
    farmer, _ = _get_or_create_farmer(db, sender)
    lang = farmer.preferred_language or ""
    if lang not in ("en", "ta", "hi"):
        lang = ""

    if msg_type == "text":
        text = ((msg.get("text") or "").strip())[:MAX_TEXT_LENGTH]
        if not text:
            return
        if not lang:
            choice = _parse_language_choice(text)
            if choice:
                farmer.preferred_language = choice
                db.commit()
                _save_exchange(db, farmer.id, text, MENU_MESSAGE, choice)
                _do_send_text(sender, MENU_MESSAGE)
            else:
                _save_exchange(db, farmer.id, text, WELCOME_MESSAGE, "en")
                _do_send_text(sender, WELCOME_MESSAGE)
            return
        reply = await get_ai_reply(text, lang)
        _save_exchange(db, farmer.id, text, reply, lang)
        _do_send_text(sender, reply)
    elif msg_type == "image":
        await _handle_image(db, farmer, sender, lang, raw_dict)
    elif msg_type in ("audio", "voice"):
        await _handle_voice(db, farmer, sender, lang, raw_dict)
    else:
        reply = WELCOME_MESSAGE if not lang else UNSUPPORTED_TYPE_MESSAGE[lang]
        _save_exchange(
            db, farmer.id, f"[{msg_type or 'unknown'} message]", reply,
            lang or "en", message_type="text",
        )
        _do_send_text(sender, reply)


@router.get("/status")
@alias_router.get("/api/whatsapp/status")
def whatsapp_status() -> dict:
    """Status check: receiver state plus honest credential state.

    configured is True only when WHATSAPP_TOKEN and
    WHATSAPP_PHONE_NUMBER_ID are both set; mode is real-ready or
    mock. Values are never included.
    """
    ready = whatsapp_configured()
    return {
        "module": "whatsapp",
        "status": "Phase 5 - webhook receiver active",
        "configured": ready,
        "mode": "real-ready" if ready else "mock",
    }


@router.get("/webhook")
@alias_router.get("/webhook")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
) -> Response:
    """Meta webhook verification (official GET contract, see module docstring)."""
    settings.refresh()
    expected = settings.whatsapp_verify_token
    if (
        hub_mode == "subscribe"
        and hub_challenge is not None
        and expected
        and hub_verify_token == expected
    ):
        try:
            return PlainTextResponse(content=str(int(hub_challenge)), status_code=200)
        except (TypeError, ValueError):
            return PlainTextResponse(content=hub_challenge, status_code=200)
    return Response(status_code=403)


@router.post("/webhook")
@alias_router.post("/webhook")
async def receive_webhook(
    request: Request, db: Session = Depends(get_db)
) -> JSONResponse:
    """Receive Meta webhook events; always acknowledge fast with HTTP 200."""
    try:
        raw_body = await request.body()
    except Exception:
        raw_body = b""
    try:
        payload = json.loads((raw_body or b"").decode("utf-8")) if raw_body else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    settings.refresh()
    secret = settings.whatsapp_app_secret
    if secret:
        signature = request.headers.get("X-Hub-Signature-256")
        if not _signature_ok(raw_body, signature, secret):
            logger.warning("WhatsApp webhook bad signature; event ignored")
            return JSONResponse({"status": "received"}, status_code=200)
    elif (os.getenv("APP_ENV", "development") or "").strip().lower() == "production":
        logger.warning(
            "WhatsApp APP_SECRET missing in production; signature check skipped"
        )

    try:
        parsed = parse_webhook_payload(payload)
    except Exception:
        parsed = {"messages": [], "statuses": []}
    for msg in parsed.get("messages", []) or []:
        if not isinstance(msg, dict):
            continue
        logger.info(
            "WhatsApp incoming from=%s type=%s text=%s",
            msg.get("from"),
            msg.get("type"),
            (msg.get("text") or "")[:200],
        )
        try:
            await _handle_message(db, msg)
        except Exception as exc:
            logger.warning("WhatsApp handler failed: %s", type(exc).__name__)
    return JSONResponse({"status": "received"}, status_code=200)


class SendRequest(BaseModel):
    """Test-send body: recipient, text, and language tag."""

    to: str
    message: str
    language: str = "en"


@router.post("/send")
@alias_router.post("/api/whatsapp/send")
def send_whatsapp_text(payload: SendRequest) -> dict[str, Any]:
    """Send one WhatsApp text message (mock when credentials are missing)."""
    to = (payload.to or "").strip()
    text = (payload.message or "").strip()
    language = (payload.language or "en").strip()
    if not to or not text:
        raise HTTPException(
            status_code=400, detail="to and message must not be empty."
        )
    if language not in ("en", "ta", "hi"):
        raise HTTPException(
            status_code=400, detail="Language must be one of: en, ta, hi."
        )
    if len(text) > MAX_SEND_LENGTH:
        raise HTTPException(
            status_code=400, detail="message must be at most 4096 characters."
        )
    return _do_send_text(to, text)
