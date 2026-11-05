"""Central settings for KrishiMitra (Phase 2, Mock-only, $0 cost).

Simple version:
- Reads values from the .env file (never prints the secret key).
- USE_MOCK_AI=true (default) = free safe testing, no internet call.
- MODEL_API_KEY else META_API_KEY else "" (both empty = Mock Mode).
- META_API_BASE_URL else "" (empty = Mock Mode, NO invented URL).
- META_MODEL_NAME default muse-spark-1.3 (example name only, no call).
- AI_TIMEOUT_SECONDS default 30.
- No real httpx call happens while in Mock Mode.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Phase 2 defaults. No invented endpoint: empty base URL means Mock Mode.
DEFAULT_META_MODEL_NAME = "muse-spark-1.3"
DEFAULT_AI_TIMEOUT_SECONDS = 30

# Phase WhatsApp Config + Verify. Official Meta WhatsApp Cloud API only.
DEFAULT_WHATSAPP_VERIFY_TOKEN = "test123"
DEFAULT_WHATSAPP_API_VERSION = "v21.0"

TRUE_VALUES = ("1", "true", "yes", "on")


class Settings:
    """All KrishiMitra settings in one place. The key is never printed."""

    def __init__(self) -> None:
        """Read settings once at startup. Call refresh() to re-read .env."""
        self.refresh()

    def refresh(self) -> None:
        """Re-read every setting from the environment (cheap, safe)."""
        load_dotenv()
        self.use_mock_ai = (os.getenv("USE_MOCK_AI", "true") or "").strip().lower() in TRUE_VALUES
        # MODEL_API_KEY wins, else META_API_KEY, else "" (Mock Mode).
        combined_key = (os.getenv("MODEL_API_KEY") or "").strip() or (os.getenv("META_API_KEY") or "").strip()
        self.meta_api_key = combined_key
        # Keep an alias so new code can read either name. Same value.
        self.model_api_key = combined_key
        # Empty default on purpose: NO invented URL. Empty = Mock Mode.
        self.meta_api_base_url = (os.getenv("META_API_BASE_URL") or "").strip()
        self.meta_model_name = (
            (os.getenv("META_MODEL_NAME") or "").strip() or DEFAULT_META_MODEL_NAME
        )
        try:
            timeout = int((os.getenv("AI_TIMEOUT_SECONDS") or "").strip() or DEFAULT_AI_TIMEOUT_SECONDS)
        except ValueError:
            timeout = DEFAULT_AI_TIMEOUT_SECONDS
        self.ai_timeout_seconds = timeout if timeout > 0 else DEFAULT_AI_TIMEOUT_SECONDS
        # WhatsApp Cloud API config (ADD-only). Never logged. Empty = not configured,
        # except verify token (default test123) and API version (default v21.0).
        self.whatsapp_token = (os.getenv("WHATSAPP_TOKEN") or "").strip()
        self.whatsapp_phone_number_id = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
        self.whatsapp_business_account_id = (os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") or "").strip()
        self.whatsapp_verify_token = (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip() or DEFAULT_WHATSAPP_VERIFY_TOKEN
        self.whatsapp_app_secret = (os.getenv("WHATSAPP_APP_SECRET") or "").strip()
        self.whatsapp_api_version = (os.getenv("WHATSAPP_API_VERSION") or "").strip() or DEFAULT_WHATSAPP_API_VERSION

    @property
    def is_configured(self) -> bool:
        """True only when a real Meta API key is present."""
        return bool(self.meta_api_key)

    @property
    def use_real_ai(self) -> bool:
        """True only when mock mode is off AND a key is configured."""
        return (not self.use_mock_ai) and self.is_configured

    @property
    def whatsapp_configured(self) -> bool:
        """True only when WhatsApp token AND phone number id are present."""
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)

    def safe_status(self) -> dict:
        """Status info that is safe to show: never includes the key."""
        return {
            "mode": "mock" if not self.use_real_ai else "real",
            "model": self.meta_model_name,
            "base_url": self.meta_api_base_url,
            "timeout_seconds": self.ai_timeout_seconds,
            "key_configured": self.is_configured,
        }

    def __repr__(self) -> str:  # Never leak the key in logs.
        return (
            f"Settings(mode={'mock' if not self.use_real_ai else 'real'}, "
            f"model={self.meta_model_name!r}, key_configured={self.is_configured})"
        )


# One shared object used by the whole app.
settings = Settings()

# WhatsApp module-level config (ADD-only, mirrors Settings). Never log tokens.
WHATSAPP_TOKEN = (os.getenv("WHATSAPP_TOKEN") or "").strip()
WHATSAPP_PHONE_NUMBER_ID = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
WHATSAPP_BUSINESS_ACCOUNT_ID = (os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") or "").strip()
WHATSAPP_VERIFY_TOKEN = (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip() or DEFAULT_WHATSAPP_VERIFY_TOKEN
WHATSAPP_APP_SECRET = (os.getenv("WHATSAPP_APP_SECRET") or "").strip()
WHATSAPP_API_VERSION = (os.getenv("WHATSAPP_API_VERSION") or "").strip() or DEFAULT_WHATSAPP_API_VERSION


def whatsapp_configured() -> bool:
    """True only when WhatsApp token AND phone number id are present (live check)."""
    settings.refresh()
    return bool(settings.whatsapp_token and settings.whatsapp_phone_number_id)
