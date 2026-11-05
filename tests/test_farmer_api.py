"""Phase 11: farmer registry + conversation history API coverage."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main

from .conftest import TestSession

client = TestClient(main.app)

_phone_counter = 9300000000


def _make_farmer(**extra) -> dict:
    """Register one farmer through the public API; return its body."""
    global _phone_counter
    _phone_counter += 1
    payload = {"name": "Phase Eleven", "phone": str(_phone_counter)}
    payload.update(extra)
    resp = client.post("/farmers/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_read_farmer() -> None:
    created = _make_farmer(village="Testur", district="Madurai")
    assert created["village"] == "Testur"
    assert created["preferred_language"] == "en"
    resp = client.get(f"/farmers/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["phone"] == created["phone"]


def test_list_farmers_contains_newcomer() -> None:
    created = _make_farmer()
    resp = client.get("/farmers/")
    assert resp.status_code == 200
    assert any(f["id"] == created["id"] for f in resp.json())


def test_duplicate_phone_rejected() -> None:
    created = _make_farmer()
    resp = client.post(
        "/farmers/", json={"name": "Copycat", "phone": created["phone"]}
    )
    assert resp.status_code == 400


def test_unknown_farmer_is_404() -> None:
    assert client.get("/farmers/999999").status_code == 404
    assert client.get("/farmers/999999/conversations").status_code == 404
    resp = client.post(
        "/farmers/999999/conversations",
        json={"role": "farmer", "content": "hi"},
    )
    assert resp.status_code == 404


def test_bad_language_rejected() -> None:
    global _phone_counter
    _phone_counter += 1
    resp = client.post(
        "/farmers/",
        json={
            "name": "Bad Lang",
            "phone": str(_phone_counter),
            "preferred_language": "fr",
        },
    )
    assert resp.status_code == 422


def test_conversation_round_trip_in_order() -> None:
    created = _make_farmer()
    farmer_id = created["id"]
    for content in ("first message", "second message"):
        resp = client.post(
            f"/farmers/{farmer_id}/conversations",
            json={"role": "farmer", "content": content},
        )
        assert resp.status_code == 201, resp.text
    resp = client.get(f"/farmers/{farmer_id}/conversations")
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()]
    assert contents[-2:] == ["first message", "second message"]


def test_conversation_bad_role_rejected() -> None:
    created = _make_farmer()
    resp = client.post(
        f"/farmers/{created['id']}/conversations",
        json={"role": "alien", "content": "hi"},
    )
    assert resp.status_code == 422


def test_farmer_row_persists_in_sqlite() -> None:
    created = _make_farmer()
    db = TestSession()
    try:
        from app import models

        row = (
            db.query(models.Farmer)
            .filter(models.Farmer.id == created["id"])
            .first()
        )
        assert row is not None
        assert row.phone == created["phone"]
    finally:
        db.close()
