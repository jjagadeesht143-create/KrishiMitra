"""Final completion gaps: follow-up schedule, report history,
WhatsApp status flags, dashboard service keys."""

from __future__ import annotations

import os

os.environ["USE_MOCK_AI"] = "true"

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

_phone_counter = 9900000000


def _make_farmer(name: str = "Gap Gopi", **extra) -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    payload = {"name": name, "phone": str(_phone_counter)}
    payload.update(extra)
    resp = client.post("/farmers/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize(
    ("language", "word"),
    [(None, "Day 7"), ("ta", "நாள் 7"), ("hi", "दिन 7")],
)
def test_plan_has_follow_up_schedule(language, word: str) -> None:
    farmer_id = _make_farmer()
    params = {"language": language} if language else None
    resp = client.get(f"/plan/{farmer_id}", params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["follow_up"]) == 3
    assert any(word in item for item in body["follow_up"])


def test_card_shows_follow_up_schedule() -> None:
    farmer_id = _make_farmer()
    resp = client.get(f"/plan/{farmer_id}/card")
    assert resp.status_code == 200, resp.text
    assert "Follow-up schedule" in resp.text
    assert "Day 7" in resp.text


def test_reports_empty_list_for_new_farmer() -> None:
    farmer_id = _make_farmer()
    resp = client.get(f"/plan/{farmer_id}/reports")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_reports_lists_newest_first() -> None:
    farmer_id = _make_farmer()
    first = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Cotton", "symptoms": "white flies"},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Maize", "symptoms": "brown stem", "days_affected": "4"},
    )
    assert second.status_code == 201, second.text
    resp = client.get(f"/plan/{farmer_id}/reports")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["crop_name"] for r in rows] == ["Maize", "Cotton"]
    assert rows[0]["days_affected"] == 4
    assert rows[0]["id"] == second.json()["report_id"]


def test_reports_unknown_farmer_is_404() -> None:
    assert client.get("/plan/999999/reports").status_code == 404


def test_whatsapp_status_reports_mock_when_unconfigured() -> None:
    for path in ("/whatsapp/status", "/api/whatsapp/status"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        body = resp.json()
        assert body["module"] == "whatsapp"
        assert body["configured"] is False
        assert body["mode"] == "mock"


def test_whatsapp_status_reports_ready_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHATSAPP_TOKEN", "dummy-wa-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
    resp = client.get("/whatsapp/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["mode"] == "real-ready"
    assert "dummy-wa-token" not in resp.text


def test_dashboard_has_services_card_and_keys() -> None:
    home = client.get("/").text
    assert 'id="dash-services"' in home
    js = client.get("/static/js/i18n.js").text
    for key in (
        "dash_services",
        "svc_whatsapp",
        "svc_ai",
        "svc_ready",
        "svc_not_connected",
        "plan_followup",
    ):
        assert key in js, key
    app = client.get("/static/js/app.js").text
    assert "dashServices()" in app
    assert "renderAiPlan" in app
