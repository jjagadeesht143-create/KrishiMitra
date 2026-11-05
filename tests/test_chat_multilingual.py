"""Phase 5: /chat multilingual tests with mocked Meta AI (never a real call).

Covers the real-mode chat path (USE_MOCK_AI=false) with a mocked Meta
response: success in Tamil/Hindi/English, invalid JSON, AI exception,
and missing key. The mock replaces generate_farming_response, so no
internet call can happen here.
"""

from __future__ import annotations

import json
import os

os.environ["USE_MOCK_AI"] = "true"

from unittest import mock

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

CHAT_KEYS = {"reply", "topic", "needs_follow_up", "follow_up_questions", "safety_note"}

TAMIL_MSG = "வணக்கம், தக்காளி இலை மஞ்சள்"
HINDI_MSG = "नमस्ते, टमाटर की पत्तियां पीली हो रही हैं"
ENGLISH_MSG = "Hello, my tomato leaves are turning yellow"

_phone_counter = 9510000000


def _make_farmer() -> int:
    """Register one farmer through the public API; return its id."""
    global _phone_counter
    _phone_counter += 1
    resp = client.post(
        "/farmers/", json={"name": "Chat Lang Farmer", "phone": str(_phone_counter)}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _ai_json(reply: str) -> str:
    """Fake Meta answer in the 5-key shape the chat parser expects."""
    return json.dumps(
        {
            "reply": reply,
            "topic": "crop_health",
            "needs_follow_up": False,
            "follow_up_questions": [],
            "safety_note": "Show your crop to a local expert.",
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    ("message", "reply"),
    [
        (TAMIL_MSG, "தமிழ் பதில்: இலை மஞ்சள் பற்றிய ஆலோசனை"),
        (HINDI_MSG, "हिंदी जवाब: पीली पत्तियों पर सलाह"),
        (ENGLISH_MSG, "English answer: advice about yellow leaves"),
    ],
)
def test_chat_real_mode_replies_in_same_language(
    monkeypatch: pytest.MonkeyPatch, message: str, reply: str
) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        fake_ai.generate_farming_response.return_value = _ai_json(reply)
        resp = client.post("/chat", json={"farmer_id": farmer_id, "message": message})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    assert body["reply"] == reply
    assert body["topic"] == "crop_health"


def test_chat_invalid_ai_json_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        fake_ai.generate_farming_response.return_value = "not json {{{"
        resp = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": ENGLISH_MSG}
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    assert body["needs_follow_up"] is True
    assert body["safety_note"]


def test_chat_ai_exception_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        fake_ai.generate_farming_response.side_effect = Exception("boom")
        resp = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": ENGLISH_MSG}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["needs_follow_up"] is True


def test_chat_missing_key_never_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real mode without a key: mock text is not JSON, so safe fallback."""
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.delenv("META_API_KEY", raising=False)
    farmer_id = _make_farmer()
    resp = client.post("/chat", json={"farmer_id": farmer_id, "message": TAMIL_MSG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    assert body["needs_follow_up"] is True


EXPECTED_REPLY_WORD = {"en": "Thank you", "ta": "நன்றி", "hi": "धन्यवाद"}


def _history_via_api(farmer_id: int) -> list:
    """Read saved chat history through the public API, oldest first."""
    resp = client.get(f"/farmers/{farmer_id}/conversations")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_chat_tamil_message_saved_and_replied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock Mode: Tamil POST /chat saves farmer + assistant rows in Tamil."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        resp = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": TAMIL_MSG}
        )
        fake_ai.generate_farming_response.assert_not_called()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    assert EXPECTED_REPLY_WORD["ta"] in body["reply"]
    assert body["safety_note"]
    history = _history_via_api(farmer_id)
    assert [m["role"] for m in history] == ["farmer", "assistant"]
    assert history[0]["content"] == TAMIL_MSG
    assert history[1]["content"] == body["reply"]
    assert [m["language"] for m in history] == ["ta", "ta"]


def test_chat_hindi_message_saved_and_replied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock Mode: Hindi POST /chat saves farmer + assistant rows in Hindi."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        resp = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": HINDI_MSG}
        )
        fake_ai.generate_farming_response.assert_not_called()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    assert EXPECTED_REPLY_WORD["hi"] in body["reply"]
    assert body["safety_note"]
    history = _history_via_api(farmer_id)
    assert [m["role"] for m in history] == ["farmer", "assistant"]
    assert history[0]["content"] == HINDI_MSG
    assert history[1]["content"] == body["reply"]
    assert [m["language"] for m in history] == ["hi", "hi"]


def test_chat_english_message_saved_and_replied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock Mode: English POST /chat saves farmer + assistant rows in English."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        resp = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": ENGLISH_MSG}
        )
        fake_ai.generate_farming_response.assert_not_called()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    assert EXPECTED_REPLY_WORD["en"] in body["reply"]
    assert body["safety_note"]
    history = _history_via_api(farmer_id)
    assert [m["role"] for m in history] == ["farmer", "assistant"]
    assert history[0]["content"] == ENGLISH_MSG
    assert history[1]["content"] == body["reply"]
    assert [m["language"] for m in history] == ["en", "en"]


def test_chat_conversation_history_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two /chat turns save 4 rows; GET history returns them in order."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    farmer_id = _make_farmer()
    with mock.patch(
        "app.services.chatbot.meta_ai_service"
    ) as fake_ai:
        first = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": ENGLISH_MSG}
        )
        second = client.post(
            "/chat", json={"farmer_id": farmer_id, "message": TAMIL_MSG}
        )
        fake_ai.generate_farming_response.assert_not_called()
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    reply1 = first.json()["reply"]
    reply2 = second.json()["reply"]
    assert EXPECTED_REPLY_WORD["en"] in reply1
    assert EXPECTED_REPLY_WORD["ta"] in reply2
    history = _history_via_api(farmer_id)
    assert len(history) == 4
    assert [m["role"] for m in history] == [
        "farmer",
        "assistant",
        "farmer",
        "assistant",
    ]
    assert history[0]["content"] == ENGLISH_MSG
    assert history[1]["content"] == reply1
    assert history[2]["content"] == TAMIL_MSG
    assert history[3]["content"] == reply2
    assert [m["language"] for m in history] == ["en", "en", "ta", "ta"]
