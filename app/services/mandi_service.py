"""Indian mandi price info service (Phase 10).

Real API path: Government of India data.gov.in Data API (Agmarknet
daily prices), which needs a free user key. On 2026-11-01 the official
data.gov.in API help page could NOT be reached (page not found), so the
exact resource endpoint is NOT treated as verified: this module ships
with NO default URL. Fill MANDI_API_BASE_URL + MANDI_API_KEY in .env by
hand from data.gov.in. Anything missing or failing returns an honest
"data unavailable" result.

Honesty rule: this module never invents prices. Parsing is fully
defensive: a record counts only when it carries a real numeric modal
price; anything else is "unavailable".
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

REQUEST_TIMEOUT = 8.0  # seconds per API call


def _config() -> tuple[str, str]:
    """Read (base_url, api_key) fresh each call. Empty = unavailable."""
    base_url = (os.getenv("MANDI_API_BASE_URL") or "").strip()
    api_key = (os.getenv("MANDI_API_KEY") or "").strip()
    return base_url, api_key


def is_configured() -> bool:
    """True only when both the mandi URL and key are set in .env."""
    base_url, api_key = _config()
    return bool(base_url and api_key)


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_mandi_response(data: object) -> dict | None:
    """First usable price record; None when the response has no real price."""
    if not isinstance(data, dict):
        return None
    records = data.get("records")
    if not isinstance(records, list) or not records:
        return None
    for record in records:
        if not isinstance(record, dict):
            continue
        modal = _as_float(record.get("modal_price"))
        if modal is None:
            continue
        out: dict[str, object] = {"modal_price": modal}
        for key in ("min_price", "max_price"):
            value = _as_float(record.get(key))
            if value is not None:
                out[key] = value
        for key in ("commodity", "market", "district", "state", "arrival_date"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                out[key] = value.strip()
        return out
    return None


def _unavailable(crop: str, market: str, reason: str) -> dict:
    """Honest 'data unavailable' result. No prices invented."""
    return {"status": "unavailable", "crop": crop, "market": market, "note": reason}


def get_mandi_price(crop: str, market: str = "") -> dict:
    """Real mandi price for a crop, or an honest 'unavailable' result."""
    crop_name = (crop or "").strip()
    market_name = (market or "").strip()
    if not crop_name:
        return _unavailable(crop, market, "Mandi data unavailable: empty crop name.")
    base_url, api_key = _config()
    if not base_url or not api_key:
        return _unavailable(
            crop_name,
            market_name,
            "Mandi data unavailable: mandi API key not configured.",
        )
    params: dict[str, object] = {
        "api-key": api_key,
        "format": "json",
        "limit": 5,
        "filters[commodity]": crop_name,
    }
    if market_name:
        params["filters[market]"] = market_name
    try:
        resp = httpx.get(base_url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        record = parse_mandi_response(resp.json())
        if record is None:
            return _unavailable(
                crop_name, market_name, "Mandi data unavailable: no price record found."
            )
    except (httpx.HTTPError, ValueError):
        return _unavailable(
            crop_name, market_name, "Mandi data unavailable: mandi API unreachable."
        )
    return {
        "status": "ok",
        "crop": crop_name,
        "market": market_name,
        "source": "data.gov.in",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        **record,
    }
