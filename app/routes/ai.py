"""Meta AI test routes (Phase 3).

Simple version:
- GET /ai/status  -> shows "mock" or "real" mode.
- POST /ai/test   -> send one test message, get one safe AI reply.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.meta_ai_service import meta_ai_service

router = APIRouter(prefix="/ai", tags=["Meta AI"])

ALLOWED_LANGUAGES = ("en", "ta", "hi")
MAX_MESSAGE_LENGTH = 2000  # characters per test message


class AITestRequest(BaseModel):
    """What the tester sends: a message + a language code."""

    message: str
    language: str = "en"


@router.get("/status")
def ai_status() -> dict:
    """Show whether Meta AI runs in mock mode or real mode."""
    return meta_ai_service.get_status()


@router.post("/test")
def ai_test(payload: AITestRequest) -> dict:
    """Send one test message to the Meta AI adapter, get one reply."""
    if payload.language not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: en, ta, hi.",
        )
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message must not be empty.",
        )
    if len(payload.message.strip()) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="Message is too long (max 2000 characters).",
        )
    reply = meta_ai_service.generate_farming_response(
        payload.message, payload.language
    )
    return {
        "farmer_message": payload.message,
        "language": payload.language,
        "ai_reply": reply,
        "mode": meta_ai_service.get_status()["mode"],
    }
