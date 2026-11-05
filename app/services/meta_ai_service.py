"""Meta AI service adapter with safe Mock Mode (Phase 3).

How it works (simple version):
- The app reads 3 values from the .env file: META_API_KEY,
  META_API_BASE_URL, META_MODEL_NAME.
- If ANY of those 3 is empty, the app runs in Mock Mode.
  Mock Mode gives safe, pre-written test replies. No internet call.
- When you later get official Meta access, you only fill those
  3 values in .env (from official Meta docs). No code change needed.

Verified against the official Meta Model API docs (dev.meta.ai,
checked 2026-11-04, NOT invented):
- Base URL: https://api.meta.ai/v1 (full endpoint goes in .env as-is,
  e.g. https://api.meta.ai/v1/chat/completions)
- Auth: Authorization: Bearer MODEL_API_KEY
- Chat model: muse-spark-1.3
- Request: {"model", "messages": [{"role", "content"}]} with
  "developer" + "user" roles.
- Reply text lives at choices[0].message.content.

STRICT RULE: values still come only from .env. Empty key, base URL,
or model name = Mock Mode, no internet call. The key is never
printed, logged, or returned.
"""

from __future__ import annotations

import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

META_REQUEST_TIMEOUT_SECONDS = 30

_SYSTEM_PROMPT = (
    "You are KrishiMitra, a farming assistant for Indian farmers. "
    "Reply in the farmer's language. Be simple and safe. "
    "Never claim a disease diagnosis is certain. "
    "Never invent pesticide doses, weather, or mandi prices. "
    "Ask follow-up questions. "
    "Suggest contacting an agricultural expert when uncertain."
)


def _extract_reply_text(data: object) -> str:
    """Read choices[0].message.content; raise ValueError when unusable."""
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


class MetaAIService:
    """Adapter for the Meta Model API with a safe Mock Mode fallback."""

    def __init__(self) -> None:
        """Read Meta settings from .env. Empty value = Mock Mode."""
        self.api_key = (os.getenv("META_API_KEY") or "").strip()
        self.base_url = (os.getenv("META_API_BASE_URL") or "").strip()
        self.model_name = (os.getenv("META_MODEL_NAME") or "").strip()
        # Mock Mode when any one of the 3 values is missing.
        self.is_mock = not (self.api_key and self.base_url and self.model_name)

    def get_status(self) -> dict:
        """Tell the caller if we run in mock mode or real mode."""
        if self.is_mock:
            return {
                "mode": "mock",
                "message": (
                    "Meta API key not configured. "
                    "Running in safe Mock Mode for development."
                ),
            }
        return {
            "mode": "real",
            "model": self.model_name,
            "message": "Meta API configured. Running with the real Meta model.",
        }

    def generate_farming_response(
        self, farmer_message: str, language: str = "en"
    ) -> str:
        """Make one safe farming reply in the farmer's language."""
        if self.is_mock:
            return self._mock_response(farmer_message, language)
        return self._real_meta_response(farmer_message, language)

    def _mock_response(self, farmer_message: str, language: str) -> str:
        """Safe pre-written test replies. No internet call happens here."""
        if language == "ta":
            return (
                "[Mock Mode - Tamil] "
                f"உங்கள் செய்தி கிடைத்தது: '{farmer_message}'. "
                "உங்கள் பயிரின் பெயர் என்ன? "
                "இந்த அறிகுறிகள் எத்தனை நாட்களாக உள்ளன?"
            )
        if language == "hi":
            return (
                "[Mock Mode - Hindi] "
                f"मुझे आपका संदेश मिला: '{farmer_message}'. "
                "कृपया अपनी फसल का नाम बताएं और बताएं कि "
                "ये लक्षण कितने दिनों से दिख रहे हैं?"
            )
        return (
            "[Mock Mode - English] "
            f"I received your message: '{farmer_message}'. "
            "Please tell me your crop name and how many days "
            "you have seen these symptoms?"
        )

    def _real_meta_response(self, farmer_message: str, language: str) -> str:
        """Real Meta Model API call (verified shape, see module docstring).

        Runs only when key + base URL + model are all configured (else
        the caller uses Mock Mode and this never runs). Any failure
        returns the safe mock reply instead - never raises, never
        leaks the key.
        """
        lang = language if language in ("en", "ta", "hi") else "en"
        names = {"en": "English", "ta": "Tamil", "hi": "Hindi"}
        try:
            resp = httpx.post(
                self.base_url,  # Full endpoint from .env, used as-is.
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "developer", "content": _SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"Farmer's language: {names[lang]}. "
                                f"Reply ONLY in {names[lang]}.\n"
                                f"Farmer's message: {(farmer_message or '').strip()}"
                            ),
                        },
                    ],
                },
                timeout=META_REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return _extract_reply_text(resp.json())
        except Exception as exc:
            logger.warning("Meta API call failed, using mock: %s", type(exc).__name__)
            return self._mock_response(farmer_message, lang)


# One shared object used by the whole app.
meta_ai_service = MetaAIService()
