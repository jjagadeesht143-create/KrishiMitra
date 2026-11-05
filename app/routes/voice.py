"""Voice upload + transcription routes (Phase 7, Meta-only, no Whisper).

Simple version:
- POST /voice/transcribe -> upload one audio file (multipart form field
  "file", optional form field "language" en/ta/hi), get back a transcript.
  Runs on Mock Mode until official Meta Muse Voice Transcribe access
  is configured in .env.
- GET /voice/status -> quick check that the voice module is ready.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.voice_service import voice_service

router = APIRouter(prefix="/voice", tags=["voice"])

ALLOWED_LANGUAGES = ("en", "ta", "hi")
ALLOWED_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".webm")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB voice-note limit


def _upload_dir() -> str:
    """Folder for saved voice files (UPLOAD_DIR env override for tests)."""
    folder = os.getenv("UPLOAD_DIR", "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder


def _safe_filename(original: str) -> str:
    """Unique local filename; keeps only the validated extension."""
    ext = os.path.splitext(original or "")[1].lower()
    return f"voice_{uuid.uuid4().hex}{ext}"


@router.get("/status")
def voice_status() -> dict:
    """Simple status check for the voice module."""
    status = voice_service.get_status()
    return {"module": "voice", "status": "ready - Phase 7 voice active", **status}


@router.post("/transcribe")
async def transcribe_voice(
    file: UploadFile = File(...),
    language: str = Form("en"),
) -> dict:
    """Upload one voice file and get its transcript (mock-safe)."""
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: en, ta, hi.",
        )
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Audio file must be one of: mp3, wav, m4a, ogg, webm.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400, detail="Audio file is larger than 10 MB."
        )
    saved_name = _safe_filename(file.filename or f"voice{ext}")
    saved_path = os.path.join(_upload_dir(), saved_name)
    with open(saved_path, "wb") as handle:
        handle.write(data)
    result = voice_service.transcribe_audio_file(saved_path, language)
    return {
        "filename": saved_name,
        "language": result["language"],
        "transcript": result["transcript"],
        "mode": result["mode"],
    }
