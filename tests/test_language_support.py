"""Phase 6: Tamil/Hindi/English auto-detect, same-language reply, SQLite storage."""

from __future__ import annotations

import os

os.environ["USE_MOCK_AI"] = "true"

from fastapi.testclient import TestClient

import main
from app import models
from app.services.language_service import detect_language

from .conftest import TestSession as _TestSession

client = TestClient(main.app)

TAMIL_MSG = "வணக்கம், என் தக்காளி பயிரில் இலைகள் மஞ்சளாகின்றன"
HINDI_MSG = "नमस्ते, मेरी टमाटर की फसल में पत्तियां पीली हो रही हैं"
ENGLISH_MSG = "Hello, my tomato crop leaves are turning yellow"

_phone_counter = 9000000000


def _make_farmer() -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    resp = client.post(
        "/farmers/",
        json={"name": "Lang Farmer", "phone": str(_phone_counter)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _stored_preference(farmer_id: int) -> str:
    db = _TestSession()
    try:
        farmer = db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
        assert farmer is not None
        return farmer.preferred_language
    finally:
        db.close()


def _stored_conversation_languages(farmer_id: int) -> list[str]:
    db = _TestSession()
    try:
        rows = (
            db.query(models.Conversation)
            .filter(models.Conversation.farmer_id == farmer_id)
            .order_by(models.Conversation.id)
            .all()
        )
        return [row.language for row in rows]
    finally:
        db.close()


def test_detect_tamil_script() -> None:
    assert detect_language(TAMIL_MSG) == "ta"


def test_detect_hindi_script() -> None:
    assert detect_language(HINDI_MSG) == "hi"


def test_detect_english_defaults_to_en() -> None:
    assert detect_language(ENGLISH_MSG) == "en"
    assert detect_language("") == "en"


def test_tamil_message_gets_tamil_reply_and_stored_preference() -> None:
    farmer_id = _make_farmer()
    resp = client.post("/chat", json={"farmer_id": farmer_id, "message": TAMIL_MSG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "நன்றி" in body["reply"]
    assert _stored_preference(farmer_id) == "ta"
    assert _stored_conversation_languages(farmer_id) == ["ta", "ta"]


def test_hindi_message_gets_hindi_reply_and_stored_preference() -> None:
    farmer_id = _make_farmer()
    resp = client.post("/chat", json={"farmer_id": farmer_id, "message": HINDI_MSG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "धन्यवाद" in body["reply"]
    assert _stored_preference(farmer_id) == "hi"
    assert _stored_conversation_languages(farmer_id) == ["hi", "hi"]


def test_english_message_gets_english_reply_and_stored_preference() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        "/chat", json={"farmer_id": farmer_id, "message": ENGLISH_MSG}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Thank you" in body["reply"]
    assert _stored_preference(farmer_id) == "en"
    assert _stored_conversation_languages(farmer_id) == ["en", "en"]


def test_explicit_language_overrides_detection() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        "/chat",
        json={"farmer_id": farmer_id, "message": ENGLISH_MSG, "language": "ta"},
    )
    assert resp.status_code == 200, resp.text
    assert "நன்றி" in resp.json()["reply"]
    assert _stored_preference(farmer_id) == "ta"


def test_invalid_language_rejected() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        "/chat",
        json={"farmer_id": farmer_id, "message": ENGLISH_MSG, "language": "fr"},
    )
    assert resp.status_code == 400


def test_empty_message_rejected() -> None:
    farmer_id = _make_farmer()
    resp = client.post("/chat", json={"farmer_id": farmer_id, "message": "   "})
    assert resp.status_code == 400


def test_unknown_farmer_is_404() -> None:
    resp = client.post("/chat", json={"farmer_id": 999999, "message": ENGLISH_MSG})
    assert resp.status_code == 404
