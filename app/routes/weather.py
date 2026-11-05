"""Weather routes (Phase 6 verification, real Open-Meteo API).

Simple version:
- GET /weather/status -> quick check that the weather module is ready.
- GET /weather?lat=9.9&lon=78.1 -> weather for coordinates (no geocode).
- GET /weather?city=Madurai -> geocode the city first, then forecast.
- GET /weather?location=Madurai -> same as city (old name, still works).
- Add &language=ta or hi for Tamil/Hindi farming guidance.
Always HTTP 200 on success or honest "unavailable"; 400 when the
request itself is bad (missing place, bad lat/lon range, too long).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..services.weather_service import get_weather, get_weather_by_coords

router = APIRouter(prefix="/weather", tags=["weather"])

MAX_LOCATION_LENGTH = 120  # characters per place name


@router.get("/status")
def weather_status() -> dict:
    """Simple status check for the weather module."""
    return {
        "module": "weather",
        "status": "ready - Phase 6 weather verified",
        "source": "open-meteo",
    }


@router.get("")
def weather(
    location: str | None = Query(default=None),
    city: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lon: float | None = Query(default=None),
    language: str | None = Query(default=None),
) -> dict:
    """Current + daily weather with farming guidance (or 'unavailable').

    Give lat AND lon together, or a city/location name. Coordinates
    skip geocoding; a name is geocoded first, then forecast.
    """
    if lat is not None or lon is not None:
        if lat is None or lon is None:
            raise HTTPException(
                status_code=400, detail="Both lat and lon are required together."
            )
        if not -90 <= lat <= 90:
            raise HTTPException(
                status_code=400, detail="lat must be between -90 and 90."
            )
        if not -180 <= lon <= 180:
            raise HTTPException(
                status_code=400, detail="lon must be between -180 and 180."
            )
        return get_weather_by_coords(lat, lon, language or "en")
    place = (city or "").strip() or (location or "").strip()
    if not place:
        raise HTTPException(
            status_code=400,
            detail="Provide lat and lon, or a city name.",
        )
    if len(place) > MAX_LOCATION_LENGTH:
        raise HTTPException(
            status_code=400, detail="Location is too long (max 120 characters)."
        )
    return get_weather(place, language or "en")
