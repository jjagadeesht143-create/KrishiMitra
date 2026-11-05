"""Chatbot routes for KrishiMitra (Phase 4 + Phase 6 languages).

Simple version:
- POST /chat -> send farmer_id + message (+ optional language en/ta/hi),
  get a safe structured reply in the same language. Omit language to
  auto-detect Tamil/Hindi/English. Preference is stored in SQLite.
  The bot remembers this farmer's old messages from SQLite.
- GET /chat/status -> quick check that the chat module is ready.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services.chatbot import get_chat_reply

router = APIRouter(prefix="/chat", tags=["chat"])

ALLOWED_LANGUAGES = ("en", "ta", "hi")
MAX_MESSAGE_LENGTH = 2000  # characters per chat message


class ChatRequest(BaseModel):
    """What the app sends: who is talking, what they said, which language."""

    farmer_id: int
    message: str
    language: str | None = None


class ChatReply(BaseModel):
    """The bot's structured, safe reply (always these 5 keys)."""

    reply: str
    topic: str
    needs_follow_up: bool
    follow_up_questions: list[str]
    safety_note: str


@router.get("/status")
def chat_status() -> dict:
    """Simple status check for the chat module."""
    return {"module": "chat", "status": "ready - Phase 6 multilingual active"}


@router.post("", response_model=ChatReply)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    """Talk to the KrishiMitra farming chatbot (remembers this farmer)."""
    if payload.language is not None and payload.language not in ALLOWED_LANGUAGES:
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
    farmer = (
        db.query(models.Farmer).filter(models.Farmer.id == payload.farmer_id).first()
    )
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return get_chat_reply(
        db, payload.farmer_id, payload.message.strip(), payload.language
    )
