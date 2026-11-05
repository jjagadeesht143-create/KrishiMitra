"""Phase 6: weather verification with mocked HTTP (never real network).

Covers: city success (geocode + forecast), lat/lon success (no geocode),
timeout, invalid JSON, lat/lon validation, and Tamil/Hindi/English
guidance. httpx.get is always mocked, so no internet call happens.
"""

from __future__ import annotations

from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from app.services import weather_service

client = TestClient(main.app)

GEOCODE_BODY = {
    "results": [
        {
            "name": "Madurai",
            "latitude": 9.91966,
            "longitude": 78.11939,
            "country": "India",
        }
    ]
}

FORECAST_BODY = {
    "current": {
        "time": "2026-11-03T10:00",
        "temperature_2m": 31.5,
        "relative_humidity_2m": 62,
        "apparent_temperature": 34.1,
        "precipitation": 0.0,
        "weather_code": 2,
        "wind_speed_10m": 12.4,
    },
    "daily": {
        "time": ["2026-11-03", "2026-11-04"],
        "temperature_2m_max": [33.0, 32.0],
        "temperature_2m_min": [24.0, 23.5],
        "precipitation_sum": [0.0, 1.5],
        "weather_code": [2, 63],
    },
}

FALLBACK_PHRASE = "weather not available, check local source"


def _resp(body: object) -> mock.Mock:
    """Fake httpx response carrying one JSON body."""
    resp = mock.Mock()
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


def test_status_is_200() -> None:
    resp = client.get("/weather/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["module"] == "weather"
    assert body["source"] == "open-meteo"


def test_city_success_returns_full_shape() -> None:
    """City path calls geocode first, then forecast, with timeout 15."""
    with mock.patch(
        "app.services.weather_service.httpx.get",
        side_effect=[_resp(GEOCODE_BODY), _resp(FORECAST_BODY)],
    ) as fake_get:
        resp = client.get("/weather", params={"city": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["source"] == "open-meteo"
    assert body["location"] == "Madurai"
    assert body["resolved_name"] == "Madurai"
    assert body["timestamp"]  # UTC stamp present
    assert body["temperature_c"] == 31.5
    assert body["precipitation_mm"] == 0.0
    assert body["wind_kph"] == 12.4
    assert len(body["daily"]) == 2
    assert body["daily"][0]["date"] == "2026-11-03"
    assert body["daily"][0]["temp_max_c"] == 33.0
    assert body["guidance"]  # farming guidance present
    assert body["language"] == "en"
    assert fake_get.call_count == 2
    first_url = fake_get.call_args_list[0][0][0]
    second_url = fake_get.call_args_list[1][0][0]
    assert "geocoding-api.open-meteo.com" in first_url
    assert "api.open-meteo.com" in second_url
    for call in fake_get.call_args_list:
        assert call[1]["timeout"] == 15


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_guidance_in_same_language(language: str) -> None:
    markers = {"en": "field work", "ta": "வயல்", "hi": "खेत"}
    with mock.patch(
        "app.services.weather_service.httpx.get",
        side_effect=[_resp(GEOCODE_BODY), _resp(FORECAST_BODY)],
    ):
        resp = client.get("/weather", params={"city": "Madurai", "language": language})
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == language
    assert markers[language] in body["guidance"]


def test_lat_lon_success_skips_geocode() -> None:
    """Coords path makes ONE call: forecast only, no geocode."""
    with mock.patch(
        "app.services.weather_service.httpx.get",
        return_value=_resp(FORECAST_BODY),
    ) as fake_get:
        resp = client.get("/weather", params={"lat": 9.9, "lon": 78.1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["source"] == "open-meteo"
    assert body["temperature_c"] == 31.5
    assert len(body["daily"]) == 2
    fake_get.assert_called_once()
    url = fake_get.call_args[0][0]
    assert "api.open-meteo.com" in url
    assert "geocoding" not in url
    assert fake_get.call_args[1]["timeout"] == 15


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 100, "lon": 78},   # lat too high
        {"lat": -91, "lon": 78},   # lat too low
        {"lat": 9, "lon": 181},    # lon too high
        {"lat": 9, "lon": -181},   # lon too low
        {"lat": 9},                # lon missing
        {"lon": 78},               # lat missing
    ],
)
def test_lat_lon_validation_is_400(params: dict) -> None:
    with mock.patch("app.services.weather_service.httpx.get") as fake_get:
        resp = client.get("/weather", params=params)
    assert resp.status_code == 400
    fake_get.assert_not_called()


def test_missing_place_is_400() -> None:
    resp = client.get("/weather")
    assert resp.status_code == 400


def test_timeout_returns_safe_fallback() -> None:
    with mock.patch(
        "app.services.weather_service.httpx.get",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        resp = client.get("/weather", params={"city": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert FALLBACK_PHRASE in body["note"]
    assert "temperature_c" not in body  # never invent numbers


def test_invalid_json_returns_safe_fallback() -> None:
    bad = mock.Mock()
    bad.raise_for_status.return_value = None
    bad.json.return_value = {"unexpected": "shape"}
    # Bad geocode body -> honest unavailable, nothing invented.
    with mock.patch("app.services.weather_service.httpx.get", return_value=bad):
        resp = client.get("/weather", params={"city": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert "unavailable" in body["note"].lower()
    assert "temperature_c" not in body
    # Good geocode + bad forecast body -> generic safe fallback phrase.
    with mock.patch(
        "app.services.weather_service.httpx.get",
        side_effect=[_resp(GEOCODE_BODY), bad],
    ):
        resp = client.get("/weather", params={"city": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert FALLBACK_PHRASE in body["note"]


def test_daily_parser_skips_bad_rows() -> None:
    rows = weather_service.parse_daily_response({"daily": {"time": []}})
    assert rows == []
    assert weather_service.parse_daily_response({}) == []
    assert weather_service.parse_daily_response("nope") == []
    rows = weather_service.parse_daily_response(FORECAST_BODY)
    assert [r["date"] for r in rows] == ["2026-11-03", "2026-11-04"]
    assert rows[1]["condition"] == "rain"


def test_guidance_picks_rain_when_wet() -> None:
    current = {"precipitation_mm": 5.0, "wind_kph": 5.0}
    assert "Rain" in weather_service.farming_guidance(current, [], "en")
    assert "மழை" in weather_service.farming_guidance(current, [], "ta")
    assert "बारिश" in weather_service.farming_guidance(current, [], "hi")
