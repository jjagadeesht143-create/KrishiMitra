"""Phase WhatsApp Config + Verify: alias GET /webhook + config defaults (Meta only)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main
from app.config import (
    DEFAULT_WHATSAPP_API_VERSION,
    DEFAULT_WHATSAPP_VERIFY_TOKEN,
    settings,
    whatsapp_configured,
)


def _client() -> TestClient:
    return TestClient(main.app)


def test_swagger_example_test123_12345(monkeypatch) -> None:
    """Swagger check: subscribe + test123 + 12345 -> 200 12345 on both routes."""
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test123")
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "12345",
        "hub.verify_token": "test123",
    }
    for path in ("/whatsapp/webhook", "/webhook"):
        resp = _client().get(path, params=params)
        assert resp.status_code == 200
        assert resp.text == "12345"


def test_alias_wrong_token_is_403(monkeypatch) -> None:
    """Alias uses the same verify logic: wrong token -> 403."""
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "correct-token")
    resp = _client().get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "12345",
            "hub.verify_token": "wrong-token",
        },
    )
    assert resp.status_code == 403


def test_status_still_200() -> None:
    resp = _client().get("/whatsapp/status")
    assert resp.status_code == 200
    assert resp.json()["module"] == "whatsapp"


def test_config_defaults_and_keys() -> None:
    """Code defaults: verify test123, API v21.0, 6 keys present, never logged."""
    assert DEFAULT_WHATSAPP_VERIFY_TOKEN == "test123"
    assert DEFAULT_WHATSAPP_API_VERSION == "v21.0"
    settings.refresh()
    for key in (
        "whatsapp_token",
        "whatsapp_phone_number_id",
        "whatsapp_business_account_id",
        "whatsapp_verify_token",
        "whatsapp_app_secret",
        "whatsapp_api_version",
    ):
        assert hasattr(settings, key)
    assert settings.whatsapp_api_version  # non-empty (default v21.0)
    assert "test123" not in repr(settings)
    assert settings.safe_status().get("whatsapp_token", None) is None


def test_whatsapp_configured_needs_token_and_phone(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_TOKEN", "")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "")
    assert whatsapp_configured() is False
    monkeypatch.setenv("WHATSAPP_TOKEN", "dummy-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
    assert whatsapp_configured() is True
