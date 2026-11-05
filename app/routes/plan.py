"""Crop Rescue Plan routes (Phase 9 + Phase B report form).

Simple version:
- GET /plan/{farmer_id} -> personalised plan as JSON, built from the
  farmer's own SQLite data (chat history plus the newest RescueReport
  when one exists). Optional query ?language=en/ta/hi, else the
  farmer's stored preference.
- POST /plan/{farmer_id}/report -> save one structured RescueReport
  (multipart form: crop_name + symptoms required, 7 optional fields,
  optional crop photo) and get the fresh plan plus AI guidance back.
- GET /plan/{farmer_id}/reports -> list the farmer's saved reports,
  newest first.
- GET /plan/{farmer_id}/card -> the same plan as a shareable standalone
  HTML Crop Rescue Card (inline styles, no extra files needed).
- GET /plan/status -> quick check that the plan module is ready.

Safety: plans never claim a certain diagnosis and never contain
pesticide names/doses, weather, or prices.
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.ai_plan_service import generate_ai_plan
from ..services.image_service import image_service
from ..services.rescue_plan_service import build_rescue_plan

router = APIRouter(prefix="/plan", tags=["plan"])

ALLOWED_LANGUAGES = ("en", "ta", "hi")
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB photo limit (same as /image/analyse)

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
_jinja = Environment(
    loader=FileSystemLoader(os.path.abspath(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _get_plan_or_404(
    farmer_id: int, language: str | None, db: Session
) -> dict:
    """Build the farmer's plan or stop with a 404 error."""
    if language is not None and language not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: en, ta, hi.",
        )
    plan = build_rescue_plan(db, farmer_id, language)
    if plan is None:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return plan


@router.get("/status")
def plan_status() -> dict:
    """Simple status check for the plan module."""
    return {"module": "plan", "status": "ready - Phase 9 rescue plan active"}


def _report_upload_dir() -> str:
    """Folder for saved report photos (UPLOAD_DIR env override for tests)."""
    folder = os.getenv("UPLOAD_DIR", "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder


def _report_filename(original: str) -> str:
    """Unique local filename; keeps only the validated extension."""
    ext = os.path.splitext(original or "")[1].lower()
    return f"report_{uuid.uuid4().hex}{ext}"


def _looks_like_image(data: bytes) -> bool:
    """Magic-byte check for JPEG/PNG/WebP (same rule as /image/analyse)."""
    if data[:3] == b"\xff\xd8\xff":  # JPEG
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":  # PNG
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WebP
        return True
    return False


@router.post("/{farmer_id}/report", status_code=201)
async def submit_report(
    farmer_id: int,
    language: str | None = Query(default=None),
    crop_name: str = Form(""),
    growth_stage: str | None = Form(None),
    symptoms: str = Form(""),
    affected_area_pct: str | None = Form(None),
    days_affected: str | None = Form(None),
    soil_type: str | None = Form(None),
    irrigation_method: str | None = Form(None),
    location: str | None = Form(None),
    recent_weather: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> dict:
    """Save one structured RescueReport and return the fresh plan.

    crop_name + symptoms are required; the rest is optional, including
    the crop photo. The plan is built from the report plus history and
    enriched with a structured 8-key AI plan from the existing Muse
    Spark service (mock-safe: mock content only while real access is
    unconfigured). An uploaded photo is analysed first and its notes
    feed the AI prompt as uncertain hints.
    """
    if language is not None and language not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: en, ta, hi.",
        )
    farmer = (
        db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
    )
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")
    try:
        cleaned = schemas.RescueReportCreate(
            crop_name=crop_name,
            growth_stage=growth_stage,
            symptoms=symptoms,
            affected_area_pct=affected_area_pct,
            days_affected=days_affected,
            soil_type=soil_type,
            irrigation_method=irrigation_method,
            location=location,
            recent_weather=recent_weather,
        )
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())) or "field"
        raise HTTPException(
            status_code=400, detail=f"Invalid {field}: {first.get('msg', 'bad value')}"
        )
    saved_name: str | None = None
    if file is not None and (file.filename or "").strip():
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Image file must be one of: jpg, jpeg, png, webp.",
            )
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Image file is empty.")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=400, detail="Image file is larger than 10 MB."
            )
        if not _looks_like_image(data):
            raise HTTPException(
                status_code=400, detail="File content is not a valid image."
            )
        saved_name = _report_filename(file.filename or f"report{ext}")
        with open(os.path.join(_report_upload_dir(), saved_name), "wb") as handle:
            handle.write(data)
    report = models.RescueReport(
        farmer_id=farmer_id,
        image_filename=saved_name,
        **cleaned.model_dump(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    plan = build_rescue_plan(db, farmer_id, language)
    if plan is None:  # Cannot happen (farmer checked above); stay safe.
        raise HTTPException(status_code=404, detail="Farmer not found")
    image_analysis = None
    if saved_name is not None:
        try:
            image_analysis = image_service.analyse_crop_image(
                os.path.join(_report_upload_dir(), saved_name), plan["language"]
            )
        except Exception:
            image_analysis = None
    result = generate_ai_plan(report, plan["language"], image_analysis)
    plan["ai_plan"] = result["plan"]
    plan["ai_guidance"] = result["guidance"]
    plan["ai_mode"] = result["mode"]
    return {"report_id": report.id, "plan": plan}


@router.get("/{farmer_id}/reports", response_model=list[schemas.RescueReportResponse])
def list_reports(farmer_id: int, db: Session = Depends(get_db)):
    """List one farmer's RescueReports, newest first (plan history)."""
    farmer = db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return (
        db.query(models.RescueReport)
        .filter(models.RescueReport.farmer_id == farmer_id)
        .order_by(models.RescueReport.id.desc())
        .all()
    )


@router.get("/{farmer_id}")
def get_plan(
    farmer_id: int,
    language: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get one farmer's personalised Crop Rescue Plan as JSON."""
    return JSONResponse(_get_plan_or_404(farmer_id, language, db))


@router.get("/{farmer_id}/card")
def get_plan_card(
    farmer_id: int,
    language: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get one farmer's shareable Crop Rescue Card as standalone HTML."""
    plan = _get_plan_or_404(farmer_id, language, db)
    html = _jinja.get_template("rescue_card.html").render(plan=plan)
    return HTMLResponse(content=html)
