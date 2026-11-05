"""Phase 10: weather + mandi use real APIs or honest 'unavailable'.

No test here touches the real internet: live shapes are checked with
doc-shaped samples, and failure paths use unroutable local URLs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import main
from app.services import mandi_service, weather_service

client = TestClient(main.app)

DEAD_URL = "http://127.0.0.1:9/unreachable"

GEOCODE_SAMPLE = {
    "results": [
        {
            "name": "Madurai",
            "latitude": 9.91966,
            "longitude": 78.11939,
            "country": "India",
        }
    ]
}

FORECAST_SAMPLE = {
    "current": {
        "time": "2026-11-01T10:00",
        "temperature_2m": 31.5,
        "relative_humidity_2m": 62,
        "apparent_temperature": 34.1,
        "precipitation": 0.0,
        "weather_code": 2,
        "wind_speed_10m": 12.4,
    }
}

MANDI_SAMPLE = {
    "records": [
        {
            "commodity": "Tomato",
            "market": "Madurai",
            "district": "Madurai",
            "state": "Tamil Nadu",
            "min_price": "1200",
            "max_price": "1800",
            "modal_price": "1500",
            "arrival_date": "01/11/2026",
        }
    ]
}


def test_weather_code_lookup() -> None:
    assert weather_service.describe_weather_code(0) == "clear sky"
    assert weather_service.describe_weather_code(63) == "rain"
    assert weather_service.describe_weather_code(999) == "unknown"
    assert weather_service.describe_weather_code(None) == "unknown"


def test_weather_parsers_read_doc_shaped_samples() -> None:
    geo = weather_service.parse_geocode_response(GEOCODE_SAMPLE)
    assert geo == (9.91966, 78.11939, "Madurai", "India")
    assert weather_service.parse_geocode_response({}) is None
    current = weather_service.parse_forecast_response(FORECAST_SAMPLE)
    assert current is not None
    assert current["temperature_c"] == 31.5
    assert current["condition"] == "partly cloudy"
    assert weather_service.parse_forecast_response({}) is None


def test_weather_unreachable_api_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_API_BASE_URL", DEAD_URL)
    monkeypatch.setenv("WEATHER_GEOCODE_URL", DEAD_URL)
    result = weather_service.get_weather("Madurai")
    assert result["status"] == "unavailable"
    assert "unavailable" in result["note"].lower()


def test_weather_route_unavailable_shape(monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_API_BASE_URL", DEAD_URL)
    monkeypatch.setenv("WEATHER_GEOCODE_URL", DEAD_URL)
    resp = client.get("/weather", params={"location": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["location"] == "Madurai"


def test_weather_route_validates_location() -> None:
    assert client.get("/weather", params={"location": "   "}).status_code == 400
    assert client.get("/weather").status_code == 400


def test_weather_status_is_ready() -> None:
    resp = client.get("/weather/status")
    assert resp.status_code == 200
    assert resp.json()["module"] == "weather"


def test_mandi_parser_reads_record_sample() -> None:
    record = mandi_service.parse_mandi_response(MANDI_SAMPLE)
    assert record is not None
    assert record["modal_price"] == 1500.0
    assert record["market"] == "Madurai"
    assert mandi_service.parse_mandi_response({"records": []}) is None
    assert mandi_service.parse_mandi_response({"records": [{"market": "x"}]}) is None


def test_mandi_without_key_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("MANDI_API_BASE_URL", raising=False)
    monkeypatch.delenv("MANDI_API_KEY", raising=False)
    assert mandi_service.is_configured() is False
    result = mandi_service.get_mandi_price("Tomato", "Madurai")
    assert result["status"] == "unavailable"
    assert "not configured" in result["note"]


def test_mandi_route_unavailable_shape(monkeypatch) -> None:
    monkeypatch.delenv("MANDI_API_BASE_URL", raising=False)
    monkeypatch.delenv("MANDI_API_KEY", raising=False)
    resp = client.get("/mandi", params={"crop": "Tomato", "market": "Madurai"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["crop"] == "Tomato"


def test_mandi_route_validates_crop() -> None:
    assert client.get("/mandi", params={"crop": "   "}).status_code == 400
    assert client.get("/mandi").status_code == 400


def test_mandi_status_never_leaks_key(monkeypatch) -> None:
    monkeypatch.setenv("MANDI_API_BASE_URL", "https://example.invalid/r")
    monkeypatch.setenv("MANDI_API_KEY", "secret-key-123")
    resp = client.get("/mandi/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert "secret-key-123" not in resp.text
