"""Mandi price routes (Phase 10, real data.gov.in API or honest unavailable).

Simple version:
- GET /mandi?crop=Tomato&market=Madurai -> latest mandi price record.
  Always HTTP 200; the body says status "ok" or "unavailable".
  Without MANDI_API_BASE_URL + MANDI_API_KEY in .env the answer is
  always "unavailable" - no prices are ever invented.
- GET /mandi/status -> quick check that the mandi module is ready.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..services.mandi_service import get_mandi_price, is_configured

router = APIRouter(prefix="/mandi", tags=["mandi"])

MAX_CROP_LENGTH = 80  # characters per crop name
MAX_MARKET_LENGTH = 120  # characters per market name


@router.get("/status")
def mandi_status() -> dict:
    """Simple status check for the mandi module (never leaks the key)."""
    return {
        "module": "mandi",
        "status": "ready - Phase 10 mandi active",
        "source": "data.gov.in",
        "configured": is_configured(),
    }


@router.get("")
def mandi(
    crop: str = Query(default=""),
    market: str = Query(default=""),
) -> dict:
    """Latest mandi price for a crop (or honest 'unavailable')."""
    crop_name = (crop or "").strip()
    market_name = (market or "").strip()
    if not crop_name:
        raise HTTPException(status_code=400, detail="Crop must not be empty.")
    if len(crop_name) > MAX_CROP_LENGTH:
        raise HTTPException(
            status_code=400, detail="Crop is too long (max 80 characters)."
        )
    if len(market_name) > MAX_MARKET_LENGTH:
        raise HTTPException(
            status_code=400, detail="Market is too long (max 120 characters)."
        )
    return get_mandi_price(crop_name, market_name)
