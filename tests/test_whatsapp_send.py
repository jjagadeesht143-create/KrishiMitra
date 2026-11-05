"""Phase WhatsApp Receiver + Send + AI: send endpoint, dedupe, no real network."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main
from app.routes import whatsapp as wa_routes


@pytest.fixture(autouse=True)
def _isolate_whatsapp(monkeypatch):
    """Clear dedupe cache, force mock AI + mock WhatsApp for every test."""
    wa_routes._reset_seen_message_ids()
    monkeypatch.setenv("USE_MOCK_AI", "true")
    monkeypatch.setenv("WHATSAPP_TOKEN", "")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "")
    yield
    wa_routes._reset_seen_message_ids()


def _client() -> TestClient:
    return TestClient(main.app)


def _text_payload(wamid: str, body: str = "Hello", sender: str = "16505559999") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": sender,
                                    "id": wamid,
                                    "timestamp": "1749416383",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_verify_ok_returns_challenge(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "send-phase-verify")
    resp = _client().get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "999",
            "hub.verify_token": "send-phase-verify",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "999"


def test_verify_wrong_token_is_403(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "correct-token")
    resp = _client().get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "999",
            "hub.verify_token": "wrong-token",
        },
    )
    assert resp.status_code == 403


def test_duplicate_webhook_ignored() -> None:
    """Same message id twice -> AI runs once, both replies stay 200."""
    ai_mock = AsyncMock(return_value="mocked ai reply")
    with (
        patch("app.routes.whatsapp.get_ai_reply", ai_mock),
        patch(
            "app.routes.whatsapp.httpx.post",
            side_effect=AssertionError("real network blocked"),
        ),
        patch(
            "app.routes.whatsapp.httpx.get",
            side_effect=AssertionError("real network blocked"),
        ),
    ):
        # First text picks language 3 (English) -> menu; use fresh sender.
        first = _text_payload("wamid.dedupe.1", "3", sender="16505550001")
        resp1 = _client().post("/whatsapp/webhook", json=first)
        resp2 = _client().post("/whatsapp/webhook", json=first)
    assert resp1.status_code == 200
    assert resp1.json() == {"status": "received"}
    assert resp2.status_code == 200
    assert resp2.json() == {"status": "received"}
    # Duplicate ignored before AI; language-choice turn needs no AI either.
    assert ai_mock.await_count == 0

    ai_mock2 = AsyncMock(return_value="mocked ai reply")
    with patch("app.routes.whatsapp.get_ai_reply", ai_mock2):
        question = _text_payload("wamid.dedupe.2", "My crop leaves are yellow", sender="16505550001")
        assert _client().post("/whatsapp/webhook", json=question).status_code == 200
        assert _client().post("/whatsapp/webhook", json=question).status_code == 200
    assert ai_mock2.await_count == 1


def test_alias_post_webhook_same_shape() -> None:
    resp = _client().post("/webhook", json=_text_payload("wamid.alias.post.1"))
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}


def test_alias_status_matches() -> None:
    for path in ("/whatsapp/status", "/api/whatsapp/status"):
        resp = _client().get(path)
        assert resp.status_code == 200
        assert resp.json()["module"] == "whatsapp"


def test_send_missing_credentials_mock() -> None:
    """No credentials -> mock result, and httpx is never touched."""
    with (
        patch(
            "app.routes.whatsapp.httpx.post",
            side_effect=AssertionError("real network blocked"),
        ),
    ):
        for path in ("/whatsapp/send", "/api/whatsapp/send"):
            resp = _client().post(
                path,
                json={"to": "16505551234", "message": "Hello", "language": "en"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "mock"
            assert body["Detail"] == "missing credentials"


def test_send_validation_400() -> None:
    assert (
        _client()
        .post("/whatsapp/send", json={"to": "", "message": "Hi", "language": "en"})
        .status_code
        == 400
    )
    assert (
        _client()
        .post(
            "/whatsapp/send",
            json={"to": "16505551234", "message": "Hi", "language": "xx"},
        )
        .status_code
        == 400
    )


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


def test_send_handles_provider_errors_without_network(monkeypatch) -> None:
    """401/404/429 are mapped to structured failures (mocked httpx)."""
    monkeypatch.setenv("WHATSAPP_TOKEN", "dummy-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "999")
    cases = {401: "unauthorized", 404: "not_found", 429: "rate_limited"}
    for code, error in cases.items():
        with patch(
            "app.routes.whatsapp.httpx.post",
            return_value=_FakeResponse(code),
        ) as mocked:
            resp = _client().post(
                "/whatsapp/send",
                json={"to": "16505551234", "message": "Hi", "language": "en"},
            )
            assert mocked.call_count == 1
            # Official URL shape only: base + v21.0 + phone id + /messages.
            called_url = mocked.call_args[0][0]
            assert called_url == "https://graph.facebook.com/v21.0/999/messages"
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error"] == error
        assert body["code"] == code
        assert "dummy-token" not in json.dumps(body)


def test_send_success_shape_without_network(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_TOKEN", "dummy-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "999")
    with patch(
        "app.routes.whatsapp.httpx.post",
        return_value=_FakeResponse(200, {"messages": [{"id": "wamid.abc"}]}),
    ):
        resp = _client().post(
            "/api/whatsapp/send",
            json={"to": "16505551234", "message": "Hi", "language": "en"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "sent"
    assert body["message_id"] == "wamid.abc"
    assert "dummy-token" not in json.dumps(body)


def test_bad_signature_still_200_but_ignored(monkeypatch) -> None:
    """Secret set + bad signature -> 200 received, message not processed."""
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    ai_mock = AsyncMock(return_value="should not run")
    with patch("app.routes.whatsapp.get_ai_reply", ai_mock):
        resp = _client().post(
            "/whatsapp/webhook",
            json=_text_payload("wamid.bad.sig.1"),
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
    assert ai_mock.await_count == 0


def test_good_signature_is_processed(monkeypatch) -> None:
    """Secret set + valid hmac -> message flows to the AI handler."""
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    payload = _text_payload("wamid.good.sig.1", "3", sender="16505550002")
    raw = json.dumps(payload).encode("utf-8")
    digest = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    ai_mock = AsyncMock(return_value="mocked ai reply")
    with patch("app.routes.whatsapp.get_ai_reply", ai_mock):
        resp = _client().post(
            "/whatsapp/webhook",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={digest}",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
    # "3" is a language choice (no AI call) but proves signature passed:
    # the sender farmer row must now exist in the isolated test DB.
    from app import models
    from tests.conftest import TestSession

    db = TestSession()
    try:
        row = (
            db.query(models.Farmer)
            .filter(models.Farmer.phone == "16505550002")
            .first()
        )
        assert row is not None
        assert row.preferred_language == "en"
    finally:
        db.close()
