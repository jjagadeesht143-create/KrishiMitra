"""Farmer + conversation history API (SQLite storage).

No AI here. These endpoints only save and read farmer data.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..ai_service import ai_service
from ..database import get_db
from ..services.language_service import detect_language

router = APIRouter(prefix="/farmers", tags=["farmers"])

AI_LANGUAGES = ("en", "ta", "hi")


def _get_farmer_or_404(farmer_id: int, db: Session) -> models.Farmer:
    """Find a farmer or stop with a 404 error."""
    farmer = db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return farmer


@router.post("/", response_model=schemas.FarmerResponse, status_code=201)
def create_farmer(payload: schemas.FarmerCreate, db: Session = Depends(get_db)):
    """Register a new farmer. Phone number must be unique."""
    exists = db.query(models.Farmer).filter(models.Farmer.phone == payload.phone).first()
    if exists is not None:
        raise HTTPException(
            status_code=400, detail="Farmer with this phone already exists"
        )
    farmer = models.Farmer(**payload.model_dump())
    db.add(farmer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Farmer with this phone already exists"
        )
    db.refresh(farmer)
    return farmer


@router.get("/", response_model=list[schemas.FarmerResponse])
def list_farmers(db: Session = Depends(get_db)):
    """Get all farmers, oldest first."""
    return db.query(models.Farmer).order_by(models.Farmer.id).all()


@router.get("/{farmer_id}", response_model=schemas.FarmerResponse)
def get_farmer(farmer_id: int, db: Session = Depends(get_db)):
    """Get one farmer by id, or 404 if missing."""
    return _get_farmer_or_404(farmer_id, db)


@router.post(
    "/{farmer_id}/conversations",
    response_model=schemas.ConversationResponse,
    status_code=201,
)
def add_conversation(
    farmer_id: int,
    payload: schemas.ConversationCreate,
    ai_reply: bool = False,
    ai_language: str | None = None,
    db: Session = Depends(get_db),
):
    """Save one chat message for a farmer.

    Default (ai_reply=false): saves and returns the farmer's message,
    exactly as before. Nothing changes for existing callers.

    With ?ai_reply=true on a farmer message: also asks Meta AI for a
    reply in the same language (ai_language wins, else auto-detected
    Tamil/Hindi/English), saves BOTH messages, and returns the AI
    reply (role=assistant). If AI fails, a safe fallback reply is
    saved instead - never an error, never invented advice.
    """
    _get_farmer_or_404(farmer_id, db)
    if ai_language is not None and ai_language not in AI_LANGUAGES:
        raise HTTPException(
            status_code=400, detail="ai_language must be one of: en, ta, hi."
        )
    message = models.Conversation(farmer_id=farmer_id, **payload.model_dump())
    db.add(message)
    db.commit()
    db.refresh(message)
    if not (ai_reply and payload.role == "farmer"):
        return message
    reply_lang = ai_language or detect_language(payload.content)
    result = ai_service.generate_reply(payload.content, reply_lang)
    ai_message = models.Conversation(
        farmer_id=farmer_id,
        role="assistant",
        message_type="text",
        content=result["reply"],
        language=result["language"],
    )
    db.add(ai_message)
    db.commit()
    db.refresh(ai_message)
    return ai_message


@router.get(
    "/{farmer_id}/conversations",
    response_model=list[schemas.ConversationResponse],
)
def get_conversations(farmer_id: int, db: Session = Depends(get_db)):
    """Get a farmer's chat history in date order, oldest first."""
    _get_farmer_or_404(farmer_id, db)
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.farmer_id == farmer_id)
        .order_by(models.Conversation.created_at.asc(), models.Conversation.id.asc())
        .all()
    )
