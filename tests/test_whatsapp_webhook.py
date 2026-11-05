"""Phase 5 step 1: WhatsApp webhook GET verify + POST receiver (Meta only)."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

import main


def _client() -> TestClient:
    return TestClient(main.app)


def test_verify_ok_returns_challenge() -> None:
    os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify-123"
    resp = _client().get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "test-verify-123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "1158201444"


def test_verify_wrong_token_is_403() -> None:
    os.environ["WHATSAPP_VERIFY_TOKEN"] = "correct-token"
    resp = _client().get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "1158201444",
            "hub.verify_token": "wrong-token",
        },
    )
    assert resp.status_code == 403


def test_receiver_accepts_official_payload_shape() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550783881",
                                "phone_number_id": "106540352242922",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test Farmer"},
                                    "wa_id": "16505551234",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "16505551234",
                                    "id": "wamid.test123",
                                    "timestamp": "1749416383",
                                    "type": "text",
                                    "text": {"body": "Vanakkam"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    resp = _client().post("/whatsapp/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}


def test_receiver_ignores_non_whatsapp_object() -> None:
    resp = _client().post("/whatsapp/webhook", json={"object": "other"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
