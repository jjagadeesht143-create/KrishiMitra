"""Real Meta Model API paths with mocked HTTP (never real calls).

Covers the verified shapes (dev.meta.ai docs, checked 2026-11-04):
chat completions for MetaAIService and image understanding for
MetaImageService. httpx.post is always mocked with dummy keys, so no
internet call can happen. $0 cost.
"""

from __future__ import annotations

import json
from unittest import mock

import httpx
import pytest

from app.services.image_service import MetaImageService
from app.services.meta_ai_service import MetaAIService

LANGUAGE_NAME = {"en": "English", "ta": "Tamil", "hi": "Hindi"}
MOCK_WORD = {"en": "Mock Mode", "ta": "Mock Mode", "hi": "Mock Mode"}


def _chat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend chat credentials exist (dummy key, HTTP is mocked)."""
    monkeypatch.setenv("META_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("META_API_BASE_URL", "https://example.invalid/v1/chat")
    monkeypatch.setenv("META_MODEL_NAME", "muse-spark-1.3")


def _image_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend vision credentials exist (dummy key, HTTP is mocked)."""
    monkeypatch.setenv("META_IMAGE_API_KEY", "dummy-key-for-test")
    monkeypatch.setenv("META_IMAGE_API_BASE_URL", "https://example.invalid/v1/chat")
    monkeypatch.setenv("META_IMAGE_MODEL_NAME", "muse-spark-1.3")


def _clear_chat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.delenv("META_API_BASE_URL", raising=False)
    monkeypatch.delenv("META_MODEL_NAME", raising=False)


def _clear_image_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("META_IMAGE_API_BASE_URL", raising=False)
    monkeypatch.delenv("META_IMAGE_MODEL_NAME", raising=False)


def _ok_response(text: str) -> mock.Mock:
    """Fake Chat Completions HTTP response carrying one reply."""
    resp = mock.Mock()
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_chat_real_success_uses_verified_shape(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    _chat_env(monkeypatch)
    service = MetaAIService()
    assert service.is_mock is False
    with mock.patch(
        "app.services.meta_ai_service.httpx.post",
        return_value=_ok_response("Live Meta answer"),
    ) as fake_post:
        reply = service.generate_farming_response("leaves are yellow", language)
    assert reply == "Live Meta answer"
    url, kwargs = fake_post.call_args[0][0], fake_post.call_args[1]
    assert url == "https://example.invalid/v1/chat"
    assert kwargs["headers"] == {"Authorization": "Bearer dummy-key-for-test"}
    assert kwargs["json"]["model"] == "muse-spark-1.3"
    roles = [m["role"] for m in kwargs["json"]["messages"]]
    assert roles == ["developer", "user"]
    assert LANGUAGE_NAME[language] in kwargs["json"]["messages"][1]["content"]
    assert "dummy-key-for-test" not in reply


@pytest.mark.parametrize("language", ["en", "ta", "hi"])
def test_chat_real_failure_falls_back_to_mock(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    _chat_env(monkeypatch)
    service = MetaAIService()
    with mock.patch(
        "app.services.meta_ai_service.httpx.post",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        reply = service.generate_farming_response("leaves are yellow", language)
    assert MOCK_WORD[language] in reply


@pytest.mark.parametrize("bad_body", [{}, {"choices": []}, {"choices": [{"x": 1}]}])
def test_chat_real_bad_shape_falls_back_to_mock(
    monkeypatch: pytest.MonkeyPatch, bad_body: object
) -> None:
    _chat_env(monkeypatch)
    service = MetaAIService()
    resp = mock.Mock()
    resp.json.return_value = bad_body
    resp.raise_for_status.return_value = None
    with mock.patch("app.services.meta_ai_service.httpx.post", return_value=resp):
        reply = service.generate_farming_response("leaves are yellow", "en")
    assert "Mock Mode" in reply


def test_chat_missing_values_never_calls_http(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_chat_env(monkeypatch)
    service = MetaAIService()
    assert service.is_mock is True
    with mock.patch("app.services.meta_ai_service.httpx.post") as fake_post:
        reply = service.generate_farming_response("leaves are yellow", "ta")
    fake_post.assert_not_called()
    assert "Mock Mode" in reply


def _tiny_png(tmp_path) -> str:
    """Write a minimal PNG file and return its path."""
    path = tmp_path / "leaf.png"
    path.write_bytes(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + bytes(32))
    return str(path)


def test_image_real_success_parses_structured_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _image_env(monkeypatch)
    service = MetaImageService()
    assert service.is_mock is False
    model_json = json.dumps(
        {
            "observation": "Three lower leaves show yellow patches.",
            "possible_issues": ["Possible nutrient stress", "Needs closer look"],
            "confidence": "low",
            "guidance": "Send a daylight close-up photo.",
        }
    )
    with mock.patch(
        "app.services.image_service.httpx.post",
        return_value=_ok_response(model_json),
    ) as fake_post:
        result = service.analyse_crop_image(_tiny_png(tmp_path), "en")
    url, kwargs = fake_post.call_args[0][0], fake_post.call_args[1]
    assert url == "https://example.invalid/v1/chat"
    assert kwargs["headers"] == {"Authorization": "Bearer dummy-key-for-test"}
    user_msg = kwargs["json"]["messages"][1]
    blocks = {b["type"]: b for b in user_msg["content"]}
    assert blocks["image_url"]["image_url"]["url"].startswith("data:image/png;base64,")
    assert result["mode"] == "real"
    assert result["observation"] == "Three lower leaves show yellow patches."
    assert result["possible_issues"] == ["Possible nutrient stress", "Needs closer look"]
    assert result["confidence"] == "low"
    assert result["needs_clearer_photo"] is True
    assert "not a confirmed disease diagnosis" in result["safety_note"]
    assert "dummy-key-for-test" not in json.dumps(result)


def test_image_real_failure_falls_back_to_labeled_mock(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _image_env(monkeypatch)
    service = MetaImageService()
    with mock.patch(
        "app.services.image_service.httpx.post",
        side_effect=httpx.ConnectError("no network"),
    ):
        result = service.analyse_crop_image(_tiny_png(tmp_path), "hi")
    assert result["mode"] == "mock"
    assert "Mock Mode" in result["observation"]


def test_image_real_dosage_text_is_scrubbed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _image_env(monkeypatch)
    service = MetaImageService()
    model_json = json.dumps(
        {
            "observation": "Spray 10 ml/l of product X.",
            "possible_issues": [],
            "confidence": "low",
            "guidance": "Apply 5 g per litre twice.",
        }
    )
    with mock.patch(
        "app.services.image_service.httpx.post",
        return_value=_ok_response(model_json),
    ):
        result = service.analyse_crop_image(_tiny_png(tmp_path), "en")
    assert result["mode"] == "real"
    assert "ml/l" not in result["observation"]
    assert "per litre" not in result["guidance"]
    assert "local agricultural expert" in result["observation"]
    assert "local agricultural expert" in result["guidance"]


def test_image_real_non_json_text_stays_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _image_env(monkeypatch)
    service = MetaImageService()
    with mock.patch(
        "app.services.image_service.httpx.post",
        return_value=_ok_response("just some plain words"),
    ):
        result = service.analyse_crop_image(_tiny_png(tmp_path), "ta")
    assert result["mode"] == "real"
    assert result["observation"] == "just some plain words"
    assert result["confidence"] == "low"
    assert result["needs_clearer_photo"] is True
    assert result["safety_note"]


def test_image_missing_values_never_calls_http(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _clear_image_env(monkeypatch)
    service = MetaImageService()
    assert service.is_mock is True
    with mock.patch("app.services.image_service.httpx.post") as fake_post:
        result = service.analyse_crop_image(_tiny_png(tmp_path), "en")
    fake_post.assert_not_called()
    assert result["mode"] == "mock"


def _shared_chat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shared chat credentials only (image-specific values stay empty)."""
    monkeypatch.setenv("META_API_KEY", "dummy-chat-key")
    monkeypatch.setenv("META_API_BASE_URL", "https://example.invalid/v1/chat")
    monkeypatch.setenv("META_MODEL_NAME", "muse-spark-1.3")


def test_image_uses_shared_chat_credentials_when_image_keys_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _clear_image_env(monkeypatch)
    _shared_chat_env(monkeypatch)
    service = MetaImageService()
    assert service.is_mock is False
    body = json.dumps({"observation": "Shared-credential reply.", "confidence": "low"})
    with mock.patch(
        "app.services.image_service.httpx.post",
        return_value=_ok_response(body),
    ) as fake_post:
        result = service.analyse_crop_image(_tiny_png(tmp_path), "en")
    url, kwargs = fake_post.call_args[0][0], fake_post.call_args[1]
    assert url == "https://example.invalid/v1/chat"
    assert kwargs["headers"] == {"Authorization": "Bearer dummy-chat-key"}
    assert kwargs["json"]["model"] == "muse-spark-1.3"
    assert result["mode"] == "real"
    assert result["observation"] == "Shared-credential reply."


def test_image_own_keys_win_over_shared_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _image_env(monkeypatch)
    monkeypatch.setenv("META_API_KEY", "dummy-chat-key")
    service = MetaImageService()
    assert service.is_mock is False
    body = json.dumps({"observation": "Own-key reply.", "confidence": "low"})
    with mock.patch(
        "app.services.image_service.httpx.post",
        return_value=_ok_response(body),
    ) as fake_post:
        result = service.analyse_crop_image(_tiny_png(tmp_path), "ta")
    assert fake_post.call_args[1]["headers"] == {
        "Authorization": "Bearer dummy-key-for-test"
    }
    assert result["mode"] == "real"
