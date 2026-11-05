"""Voice service adapter with safe Mock Mode (Phase 7).

How it works (simple version):
- The app reads 3 values from the .env file: META_VOICE_API_KEY,
  META_VOICE_API_BASE_URL, META_VOICE_MODEL_NAME.
- If ANY of those 3 is empty, the app runs in Mock Mode.
  Mock Mode returns a safe, pre-written test transcript. No internet call.
- When official Meta Muse Voice Transcribe API access is verified,
  fill those 3 values in .env (from official Meta docs only).

STRICT RULE: This file invents NO Meta API endpoint, URL, model name,
header, or request format. The real API call is wired only after
verifying the official Meta Developer Documentation.
Do NOT use OpenAI Whisper or any non-Meta speech model here.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

ALLOWED_VOICE_LANGUAGES = ("en", "ta", "hi")


class MetaVoiceService:
    """Adapter for Meta Muse Voice Transcribe with Mock Mode fallback."""

    def __init__(self) -> None:
        """Read Meta voice settings from .env. Empty value = Mock Mode."""
        self.api_key = (os.getenv("META_VOICE_API_KEY") or "").strip()
        self.base_url = (os.getenv("META_VOICE_API_BASE_URL") or "").strip()
        self.model_name = (os.getenv("META_VOICE_MODEL_NAME") or "").strip()
        # Mock Mode when any one of the 3 values is missing.
        self.is_mock = not (self.api_key and self.base_url and self.model_name)

    def get_status(self) -> dict:
        """Tell the caller if we run in mock mode or real mode."""
        if self.is_mock:
            return {
                "mode": "mock",
                "message": (
                    "Meta Voice Transcribe not configured. "
                    "Running in safe Mock Mode for development."
                ),
            }
        return {
            "mode": "real",
            "model": self.model_name,
            "message": "Meta Voice Transcribe configured.",
        }

    def transcribe_audio_file(
        self, file_path: str, language: str = "en"
    ) -> dict:
        """Transcribe one saved audio file; return transcript + mode."""
        lang = language if language in ALLOWED_VOICE_LANGUAGES else "en"
        if self.is_mock:
            return {
                "transcript": self._mock_response(file_path, lang),
                "language": lang,
                "mode": "mock",
            }
        return {
            "transcript": self._real_transcribe(file_path, lang),
            "language": lang,
            "mode": "real",
        }

    def _mock_response(self, file_path: str, language: str) -> str:
        """Safe pre-written test transcripts. No internet call happens here."""
        name = (file_path or "").replace("\\", "/").rsplit("/", 1)[-1]
        if language == "ta":
            return (
                "[Mock Mode - Tamil] "
                f"குரல் கோப்பு கிடைத்தது: '{name}'. "
                "உங்கள் பயிரின் பெயரையும் அறிகுறிகளையும் சொல்லுங்கள்."
            )
        if language == "hi":
            return (
                "[Mock Mode - Hindi] "
                f"मुझे आपकी आवाज़ फ़ाइल मिली: '{name}'. "
                "कृपया अपनी फसल का नाम और लक्षण बताएं।"
            )
        return (
            "[Mock Mode - English] "
            f"I received your voice file: '{name}'. "
            "Please tell me your crop name and symptoms."
        )

    def _real_transcribe(self, file_path: str, language: str) -> str:
        """Real Meta Muse Voice Transcribe call (wired later)."""
        # TODO: Replace this only after verifying the official Meta
        # Developer Documentation for Muse Voice Transcribe. Do NOT invent
        # any endpoint, URL, model name, header, or request format here.
        _ = (file_path, language)  # Used once the real API is wired.
        # Temporary safe fallback until the real format is verified.
        return self._mock_response(file_path, language) + (
            " [Real Voice API format pending verification]"
        )


# One shared object used by the whole app.
voice_service = MetaVoiceService()


def transcribe_audio(file_path: str, language: str = "en") -> str:
    """Transcribe one audio file; return the transcript text (mock-safe)."""
    return voice_service.transcribe_audio_file(file_path, language)["transcript"]
