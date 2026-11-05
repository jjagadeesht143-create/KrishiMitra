"""Language detection for KrishiMitra (Phase 6).

Tamil, Hindi, and English only. Script-based detection:
- Any Tamil character (U+0B80-U+0BFF) -> "ta".
- Else any Devanagari character (U+0900-U+097F) -> "hi".
- Else -> "en" (includes plain English and romanized Tamil/Hindi
  typed in Latin letters; callers can override with an explicit
  language code when the farmer picks one in the UI).
"""

from __future__ import annotations

SUPPORTED_LANGUAGES = ("en", "ta", "hi")


def _has_codepoint_in(text: str, start: int, end: int) -> bool:
    """True if any character in text falls within [start, end]."""
    for char in text or "":
        if start <= ord(char) <= end:
            return True
    return False


def is_tamil_text(text: str) -> bool:
    """True if text contains any Tamil script character."""
    return _has_codepoint_in(text, 0x0B80, 0x0BFF)


def is_hindi_text(text: str) -> bool:
    """True if text contains any Devanagari script character."""
    return _has_codepoint_in(text, 0x0900, 0x097F)


def detect_language(text: str) -> str:
    """Detect one of en/ta/hi from message script. Never raises."""
    if is_tamil_text(text):
        return "ta"
    if is_hindi_text(text):
        return "hi"
    return "en"


def normalize_language(language: str | None, fallback_text: str = "") -> str:
    """Resolve the reply language: explicit code wins, else auto-detect.

    Returns one of en/ta/hi. Unknown codes fall back to detection.
    """
    if language in SUPPORTED_LANGUAGES:
        return language
    return detect_language(fallback_text)
