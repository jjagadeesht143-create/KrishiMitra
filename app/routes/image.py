"""Crop image upload + analysis routes (Phase 8, Meta-only, mock-safe).

Simple version:
- POST /image/analyse -> upload one crop photo (multipart form field
  "file", optional form field "language" en/ta/hi), get back a safe
  structured analysis. Never a certain diagnosis from an unclear image.
  Runs on Mock Mode until official Meta vision access is in .env.
- GET /image/status -> quick check that the image module is ready.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.image_service import image_service

router = APIRouter(prefix="/image", tags=["image"])

ALLOWED_LANGUAGES = ("en", "ta", "hi")
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB photo limit


def _upload_dir() -> str:
    """Folder for saved crop photos (UPLOAD_DIR env override for tests)."""
    folder = os.getenv("UPLOAD_DIR", "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder


def _safe_filename(original: str) -> str:
    """Unique local filename; keeps only the validated extension."""
    ext = os.path.splitext(original or "")[1].lower()
    return f"crop_{uuid.uuid4().hex}{ext}"


def _looks_like_image(data: bytes) -> bool:
    """Magic-byte check for JPEG/PNG/WebP (no new dependency needed)."""
    if data[:3] == b"\xff\xd8\xff":  # JPEG
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":  # PNG
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WebP
        return True
    return False


@router.get("/status")
def image_status() -> dict:
    """Simple status check for the image module."""
    status = image_service.get_status()
    return {"module": "image", "status": "ready - Phase 8 image active", **status}


@router.post("/analyse")
async def analyse_image(
    file: UploadFile = File(...),
    language: str = Form("en"),
) -> dict:
    """Upload one crop photo and get its safe analysis (mock-safe)."""
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: en, ta, hi.",
        )
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Image file must be one of: jpg, jpeg, png, webp.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Image file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400, detail="Image file is larger than 10 MB."
        )
    if not _looks_like_image(data):
        raise HTTPException(
            status_code=400, detail="File content is not a valid image."
        )
    saved_name = _safe_filename(file.filename or f"crop{ext}")
    saved_path = os.path.join(_upload_dir(), saved_name)
    with open(saved_path, "wb") as handle:
        handle.write(data)
    result = image_service.analyse_crop_image(saved_path, language)
    return {"filename": saved_name, "language": language, **result}
