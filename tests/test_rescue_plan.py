"""Phase 9: personalised Crop Rescue Plan (JSON) + HTML Rescue Card."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

# Banned: pesticide doses / chemical dosages must never appear in a plan.
BANNED_TOKENS = ("ml/l", "mg/l", "g/l", "ml per", "pesticide dose")

_phone_counter = 9200000000


def _make_farmer(name: str = "Rescue Rani", **extra) -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    payload = {"name": name, "phone": str(_phone_counter)}
    payload.update(extra)
    resp = client.post("/farmers/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_farmer_message(farmer_id: int, content: str) -> None:
    resp = client.post(
        f"/farmers/{farmer_id}/conversations",
        json={"role": "farmer", "content": content},
    )
    assert resp.status_code == 201, resp.text


def test_plan_status_is_ready() -> None:
    resp = client.get("/plan/status")
    assert resp.status_code == 200
    assert resp.json()["module"] == "plan"


def test_plan_is_personalised_and_safe() -> None:
    farmer_id = _make_farmer(village="Keelavalavu")
    _add_farmer_message(farmer_id, "My tomato leaves are turning yellow")
    resp = client.get(f"/plan/{farmer_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["farmer_name"] == "Rescue Rani"
    assert "Keelavalavu" in body["village"]
    assert body["crop"] == "tomato"
    assert body["topic"] == "crop_health"
    assert body["confidence"] == "low"
    assert body["immediate_steps"] and body["watch_out_for"]
    assert body["questions_for_expert"], "missing details must raise questions"
    assert "not a confirmed diagnosis" in body["disclaimer"]
    blob = json.dumps(body).lower()
    for token in BANNED_TOKENS:
        assert token not in blob


def test_plan_uses_stored_language_preference() -> None:
    farmer_id = _make_farmer(preferred_language="ta")
    _add_farmer_message(farmer_id, "வணக்கம், தக்காளி இலை மஞ்சள்")
    resp = client.get(f"/plan/{farmer_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "ta"
    assert body["title"] == "பயிர் மீட்புத் திட்டம்"


def test_plan_explicit_language_overrides_preference() -> None:
    farmer_id = _make_farmer()
    resp = client.get(f"/plan/{farmer_id}", params={"language": "hi"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["language"] == "hi"


def test_plan_farmer_without_history_still_works() -> None:
    farmer_id = _make_farmer()
    resp = client.get(f"/plan/{farmer_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["crop"] is None
    assert body["crop_display"] == "Not known yet"
    assert body["questions_for_expert"]


def test_plan_rejects_bad_language() -> None:
    farmer_id = _make_farmer()
    resp = client.get(f"/plan/{farmer_id}", params={"language": "fr"})
    assert resp.status_code == 400


def test_plan_unknown_farmer_is_404() -> None:
    assert client.get("/plan/999999").status_code == 404
    assert client.get("/plan/999999/card").status_code == 404


def test_card_is_shareable_html() -> None:
    farmer_id = _make_farmer(village="Keelavalavu")
    _add_farmer_message(farmer_id, "My tomato leaves are turning yellow")
    resp = client.get(f"/plan/{farmer_id}/card")
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Rescue Rani" in html
    assert "Keelavalavu" in html
    assert "tomato" in html
    assert "<style>" in html, "card must be standalone-shareable"
    blob = html.lower()
    for token in BANNED_TOKENS:
        assert token not in blob


def test_card_escapes_farmer_name() -> None:
    farmer_id = _make_farmer(name="<script>alert(1)</script>")
    resp = client.get(f"/plan/{farmer_id}/card")
    assert resp.status_code == 200, resp.text
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text
