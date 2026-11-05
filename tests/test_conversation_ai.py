"""Phase 2-3: AI replies on POST /farmers/{id}/conversations (Mock Mode)."""

from __future__ import annotations

import os

os.environ["USE_MOCK_AI"] = "true"

from fastapi.testclient import TestClient

import main
from app import models
from app.ai_service import ai_service

from .conftest import TestSession

client = TestClient(main.app)

_phone_counter = 9400000000


def _make_farmer() -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    resp = client.post(
        "/farmers/", json={"name": "AI Farmer", "phone": str(_phone_counter)}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _history(farmer_id: int) -> list:
    db = TestSession()
    try:
        return (
            db.query(models.Conversation)
            .filter(models.Conversation.farmer_id == farmer_id)
            .order_by(models.Conversation.id)
            .all()
        )
    finally:
        db.close()


def test_default_post_is_unchanged_no_ai() -> None:
    """Without ?ai_reply=true: same as before, no assistant row added."""
    farmer_id = _make_farmer()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations",
        json={"role": "farmer", "content": "my leaves are yellow"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "farmer"
    assert [m.role for m in _history(farmer_id)] == ["farmer"]


def test_ai_reply_tamil_message_gets_tamil_reply() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations?ai_reply=true",
        json={"role": "farmer", "content": "வணக்கம், தக்காளி இலை மஞ்சள்"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "assistant"
    assert body["language"] == "ta"
    assert "நன்றி" in body["content"]
    assert [m.role for m in _history(farmer_id)] == ["farmer", "assistant"]


def test_ai_reply_english_message_gets_english_reply() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations?ai_reply=true",
        json={"role": "farmer", "content": "my tomato leaves are yellow"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "assistant"
    assert body["language"] == "en"
    assert "Thank you" in body["content"]


def test_ai_language_overrides_detection() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations?ai_reply=true&ai_language=hi",
        json={"role": "farmer", "content": "my tomato leaves are yellow"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["language"] == "hi"
    assert "धन्यवाद" in resp.json()["content"]


def test_ai_reply_rejects_bad_language() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/farmers/{farmer_id}/conversations?ai_reply=true&ai_language=fr",
        json={"role": "farmer", "content": "hello"},
    )
    assert resp.status_code == 400


def test_ai_reply_unknown_farmer_is_404() -> None:
    resp = client.post(
        "/farmers/999999/conversations?ai_reply=true",
        json={"role": "farmer", "content": "hello"},
    )
    assert resp.status_code == 404


def test_ai_service_falls_back_when_real_call_fails(monkeypatch) -> None:
    """Broken real-mode config must fall back, never raise, no key leak."""
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.setenv("META_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("META_API_BASE_URL", "http://127.0.0.1:9/unreachable")
    result = ai_service.generate_reply("my leaves are yellow", "en")
    assert result["used_fallback"] is True
    assert result["mode"] == "fallback"
    assert "Thank you" in result["reply"]
    assert "dummy-key" not in str(result)


def test_ai_service_status_never_shows_key(monkeypatch) -> None:
    monkeypatch.setenv("META_API_KEY", "super-secret-key")
    status = ai_service.get_status()
    assert "super-secret-key" not in str(status)
    assert status["key_configured"] is True
