"""Meta AI replies for KrishiMitra (Phase 2, Mock-only, $0 cost).

Simple version:
- USE_MOCK_AI=true (default) = safe pre-written replies, no internet call.
- Empty MODEL_API_KEY/META_API_KEY or empty META_API_BASE_URL = Mock Mode.
- Real call runs ONLY when USE_MOCK_AI=false AND key AND base URL are
  all officially configured. Base URL is used as-is from .env.
  NO invented endpoint, URL, path, header, or request format here.
- If the real call fails for ANY reason, we return a safe fallback
  reply instead. This module never crashes the app and never prints
  the API key.

Phase 2 API (async, mock-first):
- FARMING_SAFETY_PROMPT: standing safety rules for the model.
- get_mock_reply(prompt, language): safe follow-up in ta/hi/en.
- call_real_meta_api(prompt, language): real call or RuntimeError.
- get_ai_reply(prompt, language): real, mock, or fallback string.

Sync AIService.generate_reply is kept for existing callers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "ta", "hi")

# Standing safety rules for the real model (Phase 2).
FARMING_SAFETY_PROMPT = (
    "You are KrishiMitra, a farming assistant for Indian farmers. "
    "Reply in the farmer's language only (Tamil, Hindi, or English). "
    "Use short, easy sentences. "
    "NEVER give pesticide names or doses; give only general info and "
    "tell the farmer to consult a local agricultural expert. "
    "NEVER confirm a crop disease as 100% certain; describe it only as "
    "a possible issue and ask follow-up questions. "
    "If crop name, crop age, symptoms, soil type, or location is missing, "
    "ask follow-up questions about crop, age, symptoms, soil, and location. "
    "When risk is high or you are uncertain, recommend a local "
    "agricultural expert. "
    "NEVER invent weather or mandi prices; if not available, say so clearly."
)

# Old name kept for existing code. Same rules.
DEVELOPER_PROMPT = FARMING_SAFETY_PROMPT

LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}

# Safe pre-written replies (Mock Mode + fallback). No internet call here.
MOCK_REPLIES = {
    "en": (
        "Thank you, I got your message. To help you safely: "
        "what is your crop name, how old is the crop, "
        "how many days ago did the problem start, "
        "and what symptoms do you see (colour, spots, wilting)?"
    ),
    "ta": (
        "நன்றி, உங்கள் செய்தி கிடைத்தது. பாதுகாப்பாக உதவ: "
        "உங்கள் பயிரின் பெயர் என்ன, பயிர் எத்தனை நாட்கள் ஆனது, "
        "பிரச்சனை எத்தனை நாட்களுக்கு முன் தொடங்கியது, "
        "அறிகுறிகள் என்ன (நிறம், புள்ளிகள், வாடல்)?"
    ),
    "hi": (
        "धन्यवाद, मुझे आपका संदेश मिला। सुरक्षित मदद के लिए: "
        "आपकी फसल का नाम क्या है, फसल कितने दिन की है, "
        "समस्या कितने दिन पहले शुरू हुई, "
        "और लक्षण क्या हैं (रंग, धब्बे, मुरझाना)?"
    ),
}

NOT_CONFIGURED_MESSAGE = (
    "Real Meta Model API endpoint not configured - "
    "missing official docs, staying in mock"
)


def _clean_language(language: str | None) -> str:
    """Keep only en/ta/hi; anything else becomes English."""
    return language if language in SUPPORTED_LANGUAGES else "en"


def _mock_reply(language: str) -> str:
    """Safe pre-written reply in the farmer's language."""
    return MOCK_REPLIES[_clean_language(language)]


def get_mock_reply(prompt: str, language: str = "en") -> str:
    """Safe mock follow-up in the same language. No internet call."""
    _ = (prompt or "").strip()  # Prompt kept for signature; reply is fixed safe text.
    return _mock_reply(language)


def _extract_text(data: Any) -> str:
    """Read the reply text from a Chat Completions JSON body.

    Expected shape: choices[0].message.content.
    Raises ValueError when the shape is unusable (caller falls back).
    """
    if not isinstance(data, dict):
        raise ValueError("bad API response")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("bad API response")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("bad API response")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("bad API response")
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("bad API response")
    return text.strip()


async def call_real_meta_api(prompt: str, language: str = "en") -> str:
    """Real Meta Model API call. Raises RuntimeError when not configured.

    Raises RuntimeError(NOT_CONFIGURED_MESSAGE) when USE_MOCK_AI is true
    or when the key or base URL is empty. Uses httpx.AsyncClient with
    the configured timeout ONLY when officially configured. The base
    URL from .env is used as-is; NO path or endpoint is invented here.
    """
    settings.refresh()  # Pick up .env edits without a restart.
    lang = _clean_language(language)
    text = (prompt or "").strip()
    if settings.use_mock_ai or not settings.meta_api_key or not settings.meta_api_base_url:
        raise RuntimeError(NOT_CONFIGURED_MESSAGE)
    url = settings.meta_api_base_url  # Full endpoint from official docs. No invented suffix.
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.meta_api_key}"},
            json={
                "model": settings.meta_model_name,
                "messages": [
                    {"role": "developer", "content": FARMING_SAFETY_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Farmer's language: {LANGUAGE_NAMES[lang]}. "
                            f"Reply ONLY in {LANGUAGE_NAMES[lang]}.\n"
                            f"Farmer's message: {text}"
                        ),
                    },
                ],
            },
        )
        resp.raise_for_status()
        return _extract_text(resp.json())


async def get_ai_reply(prompt: str, language: str = "en") -> str:
    """One AI reply string. Never raises on network errors; falls back.

    Mock Mode (or missing key/base URL) returns the safe mock reply
    with no httpx call. Real mode tries call_real_meta_api and on
    Timeout, HTTPError, JSONError, or bad response returns the safe
    fallback instead. Always returns an assistant message string.
    """
    settings.refresh()  # Pick up .env edits without a restart.
    lang = _clean_language(language)
    text = (prompt or "").strip()
    if settings.use_mock_ai or not settings.meta_api_key or not settings.meta_api_base_url:
        return get_mock_reply(text, lang)
    try:
        return await call_real_meta_api(text, lang)
    except httpx.TimeoutException as exc:
        logger.warning("Meta API call failed, using safe fallback: %s", type(exc).__name__)
        return get_mock_reply(text, lang)
    except httpx.HTTPError as exc:
        logger.warning("Meta API call failed, using safe fallback: %s", type(exc).__name__)
        return get_mock_reply(text, lang)
    except json.JSONDecodeError as exc:
        logger.warning("Meta API call failed, using safe fallback: %s", type(exc).__name__)
        return get_mock_reply(text, lang)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Meta API call failed, using safe fallback: %s", type(exc).__name__)
        return get_mock_reply(text, lang)
    except Exception as exc:  # Any other failure -> safe fallback.
        logger.warning("Meta API call failed, using safe fallback: %s", type(exc).__name__)
        return get_mock_reply(text, lang)


class AIService:
    """One place for all Meta AI text replies (mock-first, fail-safe)."""

    def generate_reply(self, message: str, language: str = "en") -> dict:
        """Make one AI reply in the farmer's language. Never raises.

        Returns {"reply": str, "language": str, "mode": str,
        "used_fallback": bool}. Mode is mock/real/fallback.
        """
        settings.refresh()  # Pick up .env edits without a restart.
        lang = _clean_language(language)
        text = (message or "").strip()
        if settings.use_real_ai and settings.meta_api_base_url:
            try:
                reply = self._real_reply(text, lang)
                return {"reply": reply, "language": lang, "mode": "real", "used_fallback": False}
            except Exception as exc:  # Any failure -> safe fallback below.
                logger.warning("Meta API call failed, using safe fallback: %s", type(exc).__name__)
                return {
                    "reply": _mock_reply(lang),
                    "language": lang,
                    "mode": "fallback",
                    "used_fallback": True,
                }
        if settings.use_real_ai and not settings.meta_api_base_url:
            # Key present but endpoint missing: safe fallback, no invented URL.
            logger.warning("Meta API call failed, using safe fallback: %s", "RuntimeError")
            return {
                "reply": _mock_reply(lang),
                "language": lang,
                "mode": "fallback",
                "used_fallback": True,
            }
        return {"reply": _mock_reply(lang), "language": lang, "mode": "mock", "used_fallback": False}

    def _real_reply(self, message: str, language: str) -> str:
        """Real Meta Model API call (only runs when fully configured)."""
        if not settings.meta_api_base_url:
            raise RuntimeError(NOT_CONFIGURED_MESSAGE)
        url = settings.meta_api_base_url  # Full endpoint from official docs. No invented suffix.
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.meta_api_key}"},
            json={
                "model": settings.meta_model_name,
                "messages": [
                    {"role": "developer", "content": DEVELOPER_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Farmer's language: {LANGUAGE_NAMES[language]}. "
                            f"Reply ONLY in {LANGUAGE_NAMES[language]}.\n"
                            f"Farmer's message: {message}"
                        ),
                    },
                ],
            },
            timeout=settings.ai_timeout_seconds,
        )
        resp.raise_for_status()
        return _extract_text(resp.json())

    def get_status(self) -> dict:
        """Safe status (never includes the key)."""
        settings.refresh()
        return settings.safe_status()


# One shared object used by the whole app.
ai_service = AIService()
