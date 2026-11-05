"""Phase 2 + Phase 5: ai_service unit tests with mocked HTTP (never real).

Covers: mock mode in Tamil/Hindi/English, real-mode success, timeout,
invalid response, HTTP error, and missing key. httpx.post and
httpx.AsyncClient are always mocked, so no internet call can happen.
Phase 2 async API (get_ai_reply, get_mock_reply, call_real_meta_api)
is tested with run_sync (no event loop, no extra plugin). $0 cost.
"""

from __future__ import annotations

import json
import os

os.environ["USE_MOCK_AI"] = "true"

from unittest import mock

import httpx
import pytest

from app.ai_service import (
    FARMING_SAFETY_PROMPT,
    ai_service,
    call_real_meta_api,
    get_ai_reply,
    get_mock_reply,
)
from app.config import settings

EXPECTED_WORD = {"en": "Thank you", "ta": "நன்றி", "hi": "धन्यवाद"}
LANGUAGE_NAME = {"en": "English", "ta": "Tamil", "hi": "Hindi"}
NOT_CONFIGURED = (
    "Real Meta Model API endpoint not configured - "
    "missing official docs, staying in mock"
)


def run_sync(coro):
    """Drive a coroutine to completion without an event loop.

    Sandbox-safe: asyncio.run() needs sockets on Windows, which the
    sandbox blocks. Our coroutines only await mocked objects (pure
    coroutines), so one send() finishes them. No internet call here.
    """
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    raise RuntimeError("coroutine needs a real event loop (unexpected)")


def _real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend real mode is configured (key is a dummy, HTTP is mocked)."""
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("META_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("META_API_BASE_URL", "https://example.invalid/v1")


def _clear_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both key names so Mock Mode is forced (no real call)."""
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)


def _ok_response(text: str) -> mock.Mock:
    """Fake Chat Completions HTTP response carrying one reply."""
    resp = mock.Mock()
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    resp.raise_for_status.return_value = None
    return resp


def _async_client_mock(post_result=None, post_error=None):
    """Fake httpx.AsyncClient context manager (no internet call).

    Returns (client_manager_mock, client_mock). Set post_result to a
    fake response, or post_error to an exception for post() to raise.
    """
    fake_resp = post_result
    client = mock.AsyncMock()
    if post_error is not None:
        client.post = mock.AsyncMock(side_effect=post_error)
    else:
        client.post = mock.AsyncMock(return_value=fake_resp)
    manager = mock.AsyncMock()
    manager.__aenter__ = mock.AsyncMock(return_value=client)
    manager.__aexit__ = mock.AsyncMock(return_value=False)
    return manager, client


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_mock_mode_replies_in_same_language_without_http(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "true")
    _clear_keys(monkeypatch)
    with mock.patch("app.ai_service.httpx.post") as fake_post:
        result = ai_service.generate_reply("my leaves are yellow", language)
    assert result["mode"] == "mock"
    assert result["language"] == language
    assert result["used_fallback"] is False
    assert EXPECTED_WORD[language] in result["reply"]
    fake_post.assert_not_called()


def test_real_mode_success_extracts_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    with mock.patch(
        "app.ai_service.httpx.post", return_value=_ok_response("Live Meta answer")
    ) as fake_post:
        result = ai_service.generate_reply("my leaves are yellow", "en")
    assert result == {
        "reply": "Live Meta answer",
        "language": "en",
        "mode": "real",
        "used_fallback": False,
    }
    _, kwargs = fake_post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer dummy-key-for-test"}
    assert kwargs["timeout"] == 30
    assert kwargs["json"]["model"] == "muse-spark-1.3"
    roles = [m["role"] for m in kwargs["json"]["messages"]]
    assert roles == ["developer", "user"]


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_real_mode_tells_model_the_reply_language(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    _real_env(monkeypatch)
    with mock.patch(
        "app.ai_service.httpx.post", return_value=_ok_response("ok")
    ) as fake_post:
        ai_service.generate_reply("hello", language)
    user_text = fake_post.call_args[1]["json"]["messages"][1]["content"]
    assert LANGUAGE_NAME[language] in user_text


def test_real_mode_timeout_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    with mock.patch(
        "app.ai_service.httpx.post",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        result = ai_service.generate_reply("my leaves are yellow", "en")
    assert result["mode"] == "fallback"
    assert result["used_fallback"] is True
    assert "Thank you" in result["reply"]


def test_real_mode_http_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    bad = mock.Mock()
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad key", request=mock.Mock(), response=mock.Mock()
    )
    with mock.patch("app.ai_service.httpx.post", return_value=bad):
        result = ai_service.generate_reply("my leaves are yellow", "ta")
    assert result["mode"] == "fallback"
    assert result["language"] == "ta"
    assert "நன்றி" in result["reply"]


@pytest.mark.parametrize(
    "bad_body",
    [
        {},
        {"choices": []},
        "not-a-dict",
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "   "}}]},
    ],
)
def test_real_mode_invalid_response_falls_back(
    monkeypatch: pytest.MonkeyPatch, bad_body: object
) -> None:
    _real_env(monkeypatch)
    resp = mock.Mock()
    resp.json.return_value = bad_body
    resp.raise_for_status.return_value = None
    with mock.patch("app.ai_service.httpx.post", return_value=resp):
        result = ai_service.generate_reply("my leaves are yellow", "hi")
    assert result["mode"] == "fallback"
    assert result["used_fallback"] is True
    assert "धन्यवाद" in result["reply"]
    assert "dummy-key-for-test" not in str(result)


def test_missing_key_stays_in_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    _clear_keys(monkeypatch)
    with mock.patch("app.ai_service.httpx.post") as fake_post:
        result = ai_service.generate_reply("my leaves are yellow", "en")
    assert result["mode"] == "mock"
    fake_post.assert_not_called()


def test_status_never_shows_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("META_API_KEY", "super-secret-key")
    status = ai_service.get_status()
    assert "super-secret-key" not in str(status)
    assert status["key_configured"] is True
    _clear_keys(monkeypatch)
    assert ai_service.get_status()["key_configured"] is False


def test_empty_message_and_bad_language_still_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "true")
    result = ai_service.generate_reply("   ", "xx")
    assert result["language"] == "en"
    assert "Thank you" in result["reply"]


# --- Phase 2 async API: safety prompt, mock replies, no real network ---


def test_farming_safety_prompt_has_required_rules() -> None:
    """Safety prompt must carry every Phase 2 rule (no invented advice)."""
    text = FARMING_SAFETY_PROMPT.lower()
    assert "pesticide" in text
    assert "dose" in text
    assert "disease" in text
    assert "crop" in text
    assert "age" in text
    assert "symptom" in text
    assert "soil" in text
    assert "location" in text
    assert "expert" in text
    assert "weather" in text
    assert "mandi" in text
    assert "invent" in text
    assert "tamil" in text and "hindi" in text and "english" in text


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_get_mock_reply_same_language_safety_followup(language: str) -> None:
    """Mock reply is a safe follow-up in the same language, no HTTP."""
    with mock.patch("app.ai_service.httpx.AsyncClient") as fake_client:
        with mock.patch("app.ai_service.httpx.post") as fake_post:
            reply = get_mock_reply("my leaves are yellow", language)
    assert isinstance(reply, str)
    assert EXPECTED_WORD[language] in reply
    fake_client.assert_not_called()
    fake_post.assert_not_called()


def test_call_real_raises_when_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Mode never calls HTTP; it raises the exact staying-in-mock error."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    monkeypatch.setenv("META_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("META_API_BASE_URL", "https://example.invalid/v1")
    with mock.patch("app.ai_service.httpx.AsyncClient") as fake_client:
        with pytest.raises(RuntimeError) as info:
            run_sync(call_real_meta_api("hello", "en"))
    assert str(info.value) == NOT_CONFIGURED
    fake_client.assert_not_called()


def test_call_real_raises_when_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    _clear_keys(monkeypatch)
    monkeypatch.setenv("META_API_BASE_URL", "https://example.invalid/v1")
    with mock.patch("app.ai_service.httpx.AsyncClient") as fake_client:
        with pytest.raises(RuntimeError) as info:
            run_sync(call_real_meta_api("hello", "en"))
    assert str(info.value) == NOT_CONFIGURED
    fake_client.assert_not_called()


def test_call_real_raises_when_missing_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("META_API_KEY", "dummy-key-for-test")
    monkeypatch.delenv("META_API_BASE_URL", raising=False)
    with mock.patch("app.ai_service.httpx.AsyncClient") as fake_client:
        with pytest.raises(RuntimeError) as info:
            run_sync(call_real_meta_api("hello", "en"))
    assert str(info.value) == NOT_CONFIGURED
    fake_client.assert_not_called()


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_get_ai_reply_mock_mode_no_http(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """Mock Mode returns safe follow-up with zero HTTP calls."""
    monkeypatch.setenv("USE_MOCK_AI", "true")
    _clear_keys(monkeypatch)
    with mock.patch("app.ai_service.httpx.AsyncClient") as fake_client:
        with mock.patch("app.ai_service.httpx.post") as fake_post:
            reply = run_sync(get_ai_reply("my leaves are yellow", language))
    assert isinstance(reply, str)
    assert EXPECTED_WORD[language] in reply
    fake_client.assert_not_called()
    fake_post.assert_not_called()


def test_get_ai_reply_missing_key_falls_back_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_MOCK_AI", "false")
    _clear_keys(monkeypatch)
    with mock.patch("app.ai_service.httpx.AsyncClient") as fake_client:
        reply = run_sync(get_ai_reply("my leaves are yellow", "en"))
    assert "Thank you" in reply
    fake_client.assert_not_called()


def test_get_ai_reply_mocked_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked AsyncClient success returns the live text (no real network)."""
    _real_env(monkeypatch)
    manager, client = _async_client_mock(post_result=_ok_response("Live Meta answer"))
    with mock.patch(
        "app.ai_service.httpx.AsyncClient", return_value=manager
    ) as fake_factory:
        reply = run_sync(get_ai_reply("my leaves are yellow", "en"))
    assert reply == "Live Meta answer"
    _, factory_kwargs = fake_factory.call_args
    assert factory_kwargs["timeout"] == 30
    _, post_kwargs = client.post.call_args
    assert post_kwargs["headers"] == {"Authorization": "Bearer dummy-key-for-test"}
    assert post_kwargs["json"]["model"] == "muse-spark-1.3"
    roles = [m["role"] for m in post_kwargs["json"]["messages"]]
    assert roles == ["developer", "user"]
    assert "English" in post_kwargs["json"]["messages"][1]["content"]


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_get_ai_reply_tells_model_the_language(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    _real_env(monkeypatch)
    manager, client = _async_client_mock(post_result=_ok_response("ok"))
    with mock.patch("app.ai_service.httpx.AsyncClient", return_value=manager):
        run_sync(get_ai_reply("hello", language))
    user_text = client.post.call_args[1]["json"]["messages"][1]["content"]
    assert LANGUAGE_NAME[language] in user_text


def test_get_ai_reply_timeout_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    manager, _ = _async_client_mock(
        post_error=httpx.TimeoutException("timed out")
    )
    with mock.patch("app.ai_service.httpx.AsyncClient", return_value=manager):
        reply = run_sync(get_ai_reply("my leaves are yellow", "en"))
    assert "Thank you" in reply


def test_get_ai_reply_http_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_env(monkeypatch)
    bad = mock.Mock()
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad key", request=mock.Mock(), response=mock.Mock()
    )
    manager, _ = _async_client_mock(post_result=bad)
    with mock.patch("app.ai_service.httpx.AsyncClient", return_value=manager):
        reply = run_sync(get_ai_reply("my leaves are yellow", "ta"))
    assert "நன்றி" in reply


@pytest.mark.parametrize(
    "bad_body",
    [
        {},
        {"choices": []},
        "not-a-dict",
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "   "}}]},
    ],
)
def test_get_ai_reply_invalid_response_falls_back(
    monkeypatch: pytest.MonkeyPatch, bad_body: object
) -> None:
    _real_env(monkeypatch)
    resp = mock.Mock()
    resp.json.return_value = bad_body
    resp.raise_for_status.return_value = None
    manager, _ = _async_client_mock(post_result=resp)
    with mock.patch("app.ai_service.httpx.AsyncClient", return_value=manager):
        reply = run_sync(get_ai_reply("my leaves are yellow", "hi"))
    assert "धन्यवाद" in reply
    assert "dummy-key-for-test" not in str(reply)


def test_get_ai_reply_bad_json_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid JSON from the API still returns a safe assistant message."""
    _real_env(monkeypatch)
    resp = mock.Mock()
    resp.json.side_effect = json.JSONDecodeError("bad", "doc", 0)
    resp.raise_for_status.return_value = None
    manager, _ = _async_client_mock(post_result=resp)
    with mock.patch("app.ai_service.httpx.AsyncClient", return_value=manager):
        reply = run_sync(get_ai_reply("my leaves are yellow", "en"))
    assert "Thank you" in reply


def test_model_api_key_fallback_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """MODEL_API_KEY wins, else META_API_KEY, else empty (Mock Mode)."""
    monkeypatch.setenv("MODEL_API_KEY", "model-key-1")
    monkeypatch.setenv("META_API_KEY", "meta-key-2")
    settings.refresh()
    assert settings.meta_api_key == "model-key-1"
    assert settings.model_api_key == "model-key-1"
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    settings.refresh()
    assert settings.meta_api_key == "meta-key-2"
    _clear_keys(monkeypatch)
    settings.refresh()
    assert settings.meta_api_key == ""
    assert settings.is_configured is False
