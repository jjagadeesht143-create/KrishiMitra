"""Phase B: RescueReport form API (multipart) + AI-guided plan.

Uses the shared isolated test DB (conftest) and its own temp upload
dir, so production data/ and uploads/ are never touched.
"""

from __future__ import annotations

import json
import os
import tempfile

os.environ["USE_MOCK_AI"] = "true"

_tmpdir = tempfile.mkdtemp(prefix="krishimitra_report_")
os.environ["UPLOAD_DIR"] = _tmpdir

import pytest
from fastapi.testclient import TestClient

import main
from app import models
from app.services.rescue_plan_service import build_rescue_prompt

client = TestClient(main.app)

BANNED_TOKENS = ("ml/l", "mg/l", "g/l", "ml per", "pesticide dose")

_phone_counter = 9700000000


@pytest.fixture(autouse=True)
def _isolate_upload_dir():
    """Point UPLOAD_DIR at this module's dir (import order must not matter)."""
    os.environ["UPLOAD_DIR"] = _tmpdir
    yield


def _make_farmer(name: str = "Report Ravi", **extra) -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    payload = {"name": name, "phone": str(_phone_counter)}
    payload.update(extra)
    resp = client.post("/farmers/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _png_bytes(size: int = 64) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(size)


def test_report_minimal_returns_plan_with_ai() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "Yellow spots on lower leaves"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body["report_id"], int)
    plan = body["plan"]
    assert plan["crop_display"] == "Tomato"
    assert plan["topic"] == "crop_health"
    assert plan["language"] == "en"
    assert plan["ai_guidance"]
    assert plan["ai_mode"] == "mock"
    assert plan["confidence"] == "low"


def test_report_all_fields_accepted() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={
            "crop_name": "Paddy",
            "growth_stage": "Flowering",
            "symptoms": "Leaves wilting even after watering",
            "affected_area_pct": "30",
            "days_affected": "7",
            "soil_type": "Clay soil",
            "irrigation_method": "Flood",
            "location": "Thanjavur",
            "recent_weather": "No rain for a week, very hot",
        },
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()["plan"]
    assert plan["crop_display"] == "Paddy"
    assert plan["report_id"] == resp.json()["report_id"]


def test_report_get_plan_uses_latest_report() -> None:
    farmer_id = _make_farmer()
    first = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Cotton", "symptoms": "White flies under leaves"},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Maize", "symptoms": "Brown patches on stem"},
    )
    assert second.status_code == 201, second.text
    resp = client.get(f"/plan/{farmer_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["crop_display"] == "Maize"
    assert body["report_id"] == second.json()["report_id"]


def test_report_missing_crop_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(f"/plan/{farmer_id}/report", data={"symptoms": "yellow leaves"})
    assert resp.status_code == 400


def test_report_missing_symptoms_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(f"/plan/{farmer_id}/report", data={"crop_name": "Tomato"})
    assert resp.status_code == 400


def test_report_blank_crop_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "   ", "symptoms": "yellow leaves"},
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("area", ["101", "150", "-5", "abc"])
def test_report_bad_area_is_400(area: str) -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={
            "crop_name": "Tomato",
            "symptoms": "yellow leaves",
            "affected_area_pct": area,
        },
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.parametrize("days", ["-1", "366", "1000", "seven"])
def test_report_bad_days_is_400(days: str) -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves", "days_affected": days},
    )
    assert resp.status_code == 400, resp.text


def test_report_overlong_crop_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "x" * 81, "symptoms": "yellow leaves"},
    )
    assert resp.status_code == 400


def test_report_overlong_symptoms_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "y" * 1001},
    )
    assert resp.status_code == 400


def test_report_blank_optional_fields_ok() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves", "soil_type": "   "},
    )
    assert resp.status_code == 201, resp.text


def test_report_unknown_farmer_is_404() -> None:
    resp = client.post(
        "/plan/999999/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
    )
    assert resp.status_code == 404


def test_report_bad_language_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report?language=fr",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
    )
    assert resp.status_code == 400


def test_report_tamil_input_and_language() -> None:
    farmer_id = _make_farmer(preferred_language="ta")
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={
            "crop_name": "தக்காளி",
            "growth_stage": "பூக்கும் பருவம்",
            "symptoms": "கீழ் இலைகளில் மஞ்சள் புள்ளிகள்",
            "soil_type": "செம்மண்",
            "location": "மதுரை",
        },
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()["plan"]
    assert plan["crop_display"] == "தக்காளி"
    assert plan["language"] == "ta"
    assert plan["title"] == "பயிர் மீட்புத் திட்டம்"
    assert plan["ai_guidance"]


def test_report_image_valid_png_is_saved() -> None:
    farmer_id = _make_farmer()
    before = set(os.listdir(_tmpdir))
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
        files={"file": ("leaf.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    new_files = [name for name in os.listdir(_tmpdir) if name not in before]
    assert len(new_files) == 1
    assert new_files[0].startswith("report_")
    assert new_files[0].endswith(".png")


def test_report_image_bad_extension_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
        files={"file": ("leaf.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 400


def test_report_image_non_image_bytes_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
        files={"file": ("leaf.png", b"this is not png data", "image/png")},
    )
    assert resp.status_code == 400


def test_report_image_empty_is_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
        files={"file": ("leaf.png", b"", "image/png")},
    )
    assert resp.status_code == 400


def test_report_image_oversize_is_400() -> None:
    farmer_id = _make_farmer()
    big = b"\x89PNG\r\n\x1a\n" + bytes(10 * 1024 * 1024)
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "yellow leaves"},
        files={"file": ("leaf.png", big, "image/png")},
    )
    assert resp.status_code == 400


def test_report_response_has_no_banned_tokens() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={
            "crop_name": "Tomato",
            "symptoms": "Yellow spots, some wilting",
            "affected_area_pct": "25",
            "days_affected": "5",
        },
    )
    assert resp.status_code == 201, resp.text
    blob = json.dumps(resp.json()).lower()
    for token in BANNED_TOKENS:
        assert token not in blob


def test_rescue_prompt_includes_structured_fields() -> None:
    report = models.RescueReport(
        farmer_id=1,
        crop_name="தக்காளி",
        growth_stage="பூக்கும் பருவம்",
        symptoms="மஞ்சள் புள்ளிகள்",
        affected_area_pct=30.0,
        days_affected=7,
        soil_type="செம்மண்",
        irrigation_method="சொட்டு நீர்",
        location="மதுரை",
        recent_weather="லேசான மழை",
    )
    prompt = build_rescue_prompt(report, "ta")
    for value in ("தக்காளி", "மஞ்சள் புள்ளிகள்", "30%", "7 days", "மதுரை", "Tamil"):
        assert value in prompt
    assert "pesticide" in prompt.lower()


def test_rescue_prompt_missing_fields_say_not_given() -> None:
    report = models.RescueReport(farmer_id=1, crop_name="Tomato", symptoms="spots")
    prompt = build_rescue_prompt(report, "en")
    assert "not given" in prompt
    assert "English" in prompt
