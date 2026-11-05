"""Phase C: structured AI rescue-plan generation (mocked HTTP only).

Covers the prompt builder, the defensive JSON parser, mock + real
(via mocked httpx) generation paths, Tamil output, image-hint flow,
and the report API integration. No internet call can happen.
"""

from __future__ import annotations

import json
import os
import tempfile

os.environ["USE_MOCK_AI"] = "true"

_tmpdir = tempfile.mkdtemp(prefix="krishimitra_aiplan_")
os.environ["UPLOAD_DIR"] = _tmpdir

from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from app import models
from app.services.ai_plan_service import (
    AI_PLAN_KEYS,
    build_ai_plan_prompt,
    generate_ai_plan,
    parse_ai_plan,
)

client = TestClient(main.app)

BANNED_TOKENS = ("ml/l", "mg/l", "g/l", "ml per", "pesticide dose")

_phone_counter = 9800000000


@pytest.fixture(autouse=True)
def _isolate_upload_dir():
    """Point UPLOAD_DIR at this module's dir (import order must not matter)."""
    os.environ["UPLOAD_DIR"] = _tmpdir
    yield


def _make_farmer(name: str = "AI Plan Priya", **extra) -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    payload = {"name": name, "phone": str(_phone_counter)}
    payload.update(extra)
    resp = client.post("/farmers/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _report(**extra) -> models.RescueReport:
    values = {
        "farmer_id": 1,
        "crop_name": "Tomato",
        "growth_stage": "Flowering",
        "symptoms": "Yellow spots on lower leaves",
        "affected_area_pct": 30.0,
        "days_affected": 7,
        "soil_type": "Red soil",
        "irrigation_method": "Drip",
        "location": "Madurai",
        "recent_weather": "Light rain, 2 days",
    }
    values.update(extra)
    return models.RescueReport(**values)


def _ok_response(text: str) -> mock.Mock:
    """Fake Chat Completions HTTP response carrying one reply."""
    resp = mock.Mock()
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    resp.raise_for_status.return_value = None
    return resp


def _real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend real mode is configured (dummy key, HTTP is mocked)."""
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("META_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("META_API_BASE_URL", "https://example.invalid/v1")


def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "true")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)


def _full_json(**extra) -> str:
    body = {
        "detected_issue": "Yellow spots spreading on lower leaves.",
        "possible_causes": ["Possible early blight", "Possible nutrient deficiency"],
        "confidence": "medium",
        "explanation": "The spots match several common issues, so this is uncertain.",
        "organic_treatment": ["Remove spotted leaves by hand", "Mulch the soil bed"],
        "recommended_actions": ["Inspect daily", "Photo one leaf", "Clean field edges"],
        "prevention_tips": ["Water at soil level", "Space plants well"],
        "expert_referral": "Visit the local expert this week with photos.",
    }
    body.update(extra)
    return json.dumps(body)


# ---------- prompt builder ----------


def test_prompt_includes_fields_and_safety_rules() -> None:
    prompt = build_ai_plan_prompt(_report(), "ta")
    for value in ("Tomato", "Yellow spots", "30%", "7 days", "Madurai", "Tamil"):
        assert value in prompt
    for key in AI_PLAN_KEYS:
        assert key in prompt
    lowered = prompt.lower()
    assert "organic" in lowered
    assert "never claim a certain" in lowered
    assert "never" in lowered and "dose" in lowered
    assert "mandi" in lowered and "weather" in lowered


def test_prompt_includes_image_hints_when_given() -> None:
    analysis = {
        "observation": "Pale patches visible on two leaves.",
        "possible_issues": ["Colour change", "Possible insect damage"],
    }
    prompt = build_ai_plan_prompt(_report(), "en", analysis)
    assert "Pale patches visible" in prompt
    assert "Possible insect damage" in prompt


def test_prompt_without_image_has_no_photo_block() -> None:
    prompt = build_ai_plan_prompt(_report(), "en", None)
    assert "photo analysis" not in prompt.lower()


# ---------- parser ----------


def test_parse_valid_json_returns_8_keys() -> None:
    plan = parse_ai_plan(_full_json(), "en")
    for key in AI_PLAN_KEYS:
        assert plan[key]
    assert plan["confidence"] == "medium"
    assert plan["safety_note"]
    assert len(plan["organic_treatment"]) == 2


def test_parse_broken_text_falls_back_safely() -> None:
    plan = parse_ai_plan("not json at all {{{", "en")
    assert plan["detected_issue"] == "not json at all {{{"
    assert plan["confidence"] == "low"
    assert plan["possible_causes"]
    assert plan["organic_treatment"]
    assert plan["expert_referral"]
    assert plan["safety_note"]


def test_parse_bad_confidence_becomes_low() -> None:
    plan = parse_ai_plan(_full_json(confidence="certain"), "en")
    assert plan["confidence"] == "low"


def test_parse_missing_keys_are_filled() -> None:
    plan = parse_ai_plan(json.dumps({"detected_issue": "spots seen"}), "hi")
    assert plan["detected_issue"] == "spots seen"
    for key in ("possible_causes", "organic_treatment", "recommended_actions"):
        assert plan[key]
    assert plan["safety_note"]


def test_parse_dosage_text_is_scrubbed() -> None:
    plan = parse_ai_plan(_full_json(explanation="Spray 10 ml/l twice weekly."), "en")
    assert "ml/l" not in plan["explanation"]
    assert "local agricultural expert" in plan["explanation"]


def test_parse_tamil_fallback_is_tamil() -> None:
    plan = parse_ai_plan("plain words", "ta")
    assert "உறுதியான நோய் கண்டறிதல் அல்ல" in plan["safety_note"]
    assert plan["expert_referral"]


# ---------- generator ----------


def test_generate_mock_makes_no_http_call(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_env(monkeypatch)
    with mock.patch("app.ai_service.httpx.post") as fake_post:
        result = generate_ai_plan(_report(), "en")
    fake_post.assert_not_called()
    assert result["mode"] == "mock"
    for key in AI_PLAN_KEYS:
        assert result["plan"][key]
    assert result["guidance"]


def test_generate_mock_tamil_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_env(monkeypatch)
    result = generate_ai_plan(_report(crop_name="தக்காளி"), "ta")
    assert result["mode"] == "mock"
    assert "உறுதியான நோய் கண்டறிதல் அல்ல" in result["plan"]["safety_note"]
    assert result["guidance"]


def test_generate_real_mode_parses_structured_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _real_env(monkeypatch)
    with mock.patch(
        "app.ai_service.httpx.post", return_value=_ok_response(_full_json())
    ):
        result = generate_ai_plan(_report(), "en")
    assert result["mode"] == "real"
    assert result["plan"]["detected_issue"].startswith("Yellow spots")
    assert result["plan"]["confidence"] == "medium"
    assert "dummy-key-for-test" not in json.dumps(result)


def test_generate_real_bad_shape_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    bad = mock.Mock()
    bad.json.return_value = {"choices": []}
    bad.raise_for_status.return_value = None
    with mock.patch("app.ai_service.httpx.post", return_value=bad):
        result = generate_ai_plan(_report(), "en")
    assert result["mode"] == "fallback"
    for key in AI_PLAN_KEYS:
        assert result["plan"][key]


def test_generate_real_timeout_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    with mock.patch(
        "app.ai_service.httpx.post",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        result = generate_ai_plan(_report(), "hi")
    assert result["mode"] == "fallback"
    assert result["plan"]["confidence"] == "low"
    assert result["plan"]["safety_note"]


def test_generate_never_raises_on_ai_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_env(monkeypatch)
    with mock.patch("app.services.ai_plan_service.ai_service") as fake_ai:
        fake_ai.generate_reply.side_effect = Exception("boom")
        result = generate_ai_plan(_report(), "en")
    assert result["mode"] == "fallback"
    for key in AI_PLAN_KEYS:
        assert result["plan"][key]


# ---------- API integration ----------


def test_api_report_returns_structured_ai_plan() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "Yellow spots on lower leaves"},
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()["plan"]
    assert plan["ai_mode"] == "mock"
    assert plan["ai_guidance"]
    for key in AI_PLAN_KEYS:
        assert plan["ai_plan"][key], key
    assert plan["ai_plan"]["safety_note"]


def test_api_report_with_photo_returns_ai_plan() -> None:
    farmer_id = _make_farmer()
    png = b"\x89PNG\r\n\x1a\n" + bytes(64)
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "symptoms": "Yellow spots"},
        files={"file": ("leaf.png", png, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()["plan"]
    for key in AI_PLAN_KEYS:
        assert plan["ai_plan"][key], key


def test_api_report_tamil_ai_plan_is_tamil() -> None:
    farmer_id = _make_farmer(preferred_language="ta")
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "தக்காளி", "symptoms": "மஞ்சள் புள்ளிகள்"},
    )
    assert resp.status_code == 201, resp.text
    plan = resp.json()["plan"]
    assert plan["language"] == "ta"
    assert "உறுதியான நோய் கண்டறிதல் அல்ல" in plan["ai_plan"]["safety_note"]


def test_api_report_ai_plan_has_no_banned_tokens() -> None:
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


def test_api_report_invalid_input_still_400() -> None:
    farmer_id = _make_farmer()
    resp = client.post(
        f"/plan/{farmer_id}/report",
        data={"crop_name": "Tomato", "affected_area_pct": "999"},
    )
    assert resp.status_code == 400
