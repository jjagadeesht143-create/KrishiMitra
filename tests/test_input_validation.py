"""Phase 13 Fix #2: input validation for farmer/chat/AI/weather/mandi."""

from __future__ import annotations

import os

os.environ["USE_MOCK_AI"] = "true"

from fastapi.testclient import TestClient

import main
from app import models

from .conftest import TestSession

client = TestClient(main.app)

_phone_counter = 9600000000


def _make_farmer(**extra):
    """POST /farmers/ with a unique phone; return the raw response."""
    global _phone_counter
    _phone_counter += 1
    payload = {"name": "Validation Velan", "phone": str(_phone_counter)}
    payload.update(extra)
    return client.post("/farmers/", json=payload)


def _make_farmer_id(**extra) -> int:
    resp = _make_farmer(**extra)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_farmer_rejects_empty_name() -> None:
    assert _make_farmer(name="").status_code == 422
    assert _make_farmer(name="   ").status_code == 422


def test_farmer_rejects_overlong_name() -> None:
    assert _make_farmer(name="x" * 101).status_code == 422


def test_farmer_rejects_bad_phone() -> None:
    for bad in ("", "   ", "abc", "12", "98-76-543210", "++1234567"):
        assert _make_farmer(phone=bad).status_code == 422, bad
    assert _make_farmer(phone="1" * 16).status_code == 422


def test_farmer_accepts_international_phone() -> None:
    resp = _make_farmer(phone="+919600099901")
    assert resp.status_code == 201, resp.text
    assert resp.json()["phone"] == "+919600099901"


def test_farmer_trims_whitespace() -> None:
    resp = _make_farmer(name="  Spaced Out  ")
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Spaced Out"


def test_conversation_rejects_empty_content() -> None:
    farmer_id = _make_farmer_id()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations",
        json={"role": "farmer", "content": "   "},
    )
    assert resp.status_code == 422


def test_conversation_rejects_bad_language() -> None:
    farmer_id = _make_farmer_id()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations",
        json={"role": "farmer", "content": "hi", "language": "fr"},
    )
    assert resp.status_code == 422


def test_conversation_accepts_tamil_language() -> None:
    farmer_id = _make_farmer_id()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations",
        json={"role": "farmer", "content": "வணக்கம்", "language": "ta"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["language"] == "ta"


def test_chat_rejects_overlong_message() -> None:
    farmer_id = _make_farmer_id()
    resp = client.post(
        "/chat", json={"farmer_id": farmer_id, "message": "x" * 2001}
    )
    assert resp.status_code == 400


def test_chat_accepts_max_length_message() -> None:
    farmer_id = _make_farmer_id()
    resp = client.post(
        "/chat", json={"farmer_id": farmer_id, "message": "x" * 2000}
    )
    assert resp.status_code == 200, resp.text


def test_ai_rejects_empty_message() -> None:
    resp = client.post("/ai/test", json={"message": "   ", "language": "en"})
    assert resp.status_code == 400


def test_ai_rejects_overlong_message() -> None:
    resp = client.post("/ai/test", json={"message": "x" * 2001, "language": "en"})
    assert resp.status_code == 400


def test_ai_accepts_valid_message() -> None:
    resp = client.post("/ai/test", json={"message": "hello", "language": "en"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "mock"


def test_weather_rejects_overlong_location() -> None:
    assert client.get("/weather", params={"location": "x" * 121}).status_code == 400


def test_mandi_rejects_overlong_inputs() -> None:
    assert client.get("/mandi", params={"crop": "x" * 81}).status_code == 400
    resp = client.get(
        "/mandi", params={"crop": "Tomato", "market": "x" * 121}
    )
    assert resp.status_code == 400


def test_list_farmers_includes_legacy_row_with_short_phone() -> None:
    """Legacy rows (saved before phone rules) must still serialize (200)."""
    db = TestSession()
    try:
        legacy = models.Farmer(name="Legacy", phone="123456")
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
    finally:
        db.close()
    resp = client.get("/farmers/")
    assert resp.status_code == 200, resp.text
    assert any(f["id"] == legacy_id for f in resp.json())
