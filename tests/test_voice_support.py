"""Phase 7: voice upload + transcription flow (Meta-only Mock Mode)."""

from __future__ import annotations

import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="krishimitra_voice_")
os.environ["UPLOAD_DIR"] = _tmpdir

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services.voice_service import transcribe_audio, voice_service  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _isolate_upload_dir():
    """Point UPLOAD_DIR at this module's dir (import order must not matter)."""
    os.environ["UPLOAD_DIR"] = _tmpdir
    yield

FAKE_AUDIO = b"RIFF....fake-audio-bytes-for-testing-only"


def test_voice_status_is_ready() -> None:
    resp = client.get("/voice/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["module"] == "voice"
    assert body["mode"] == "mock"


def test_transcribe_english_voice_note() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("note_en.mp3", FAKE_AUDIO, "audio/mpeg")},
        data={"language": "en"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["language"] == "en"
    assert "Mock Mode - English" in body["transcript"]
    assert os.path.isfile(os.path.join(_tmpdir, body["filename"]))


def test_transcribe_tamil_voice_note() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("note_ta.wav", FAKE_AUDIO, "audio/wav")},
        data={"language": "ta"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "குரல் கோப்பு" in body["transcript"]


def test_transcribe_hindi_voice_note() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("note_hi.m4a", FAKE_AUDIO, "audio/mp4")},
        data={"language": "hi"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "आवाज़ फ़ाइल" in body["transcript"]


def test_transcribe_rejects_bad_extension() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("note.txt", b"not audio", "text/plain")},
        data={"language": "en"},
    )
    assert resp.status_code == 400


def test_transcribe_rejects_empty_file() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("empty.mp3", b"", "audio/mpeg")},
        data={"language": "en"},
    )
    assert resp.status_code == 400


def test_transcribe_rejects_bad_language() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("note.mp3", FAKE_AUDIO, "audio/mpeg")},
        data={"language": "fr"},
    )
    assert resp.status_code == 400


def test_service_helper_returns_mock_text() -> None:
    assert voice_service.is_mock is True
    text = transcribe_audio(os.path.join(_tmpdir, "sample.mp3"), "en")
    assert "Mock Mode - English" in text


def test_transcribe_rejects_oversize_file() -> None:
    resp = client.post(
        "/voice/transcribe",
        files={"file": ("big.mp3", b"x" * (10 * 1024 * 1024 + 1), "audio/mpeg")},
        data={"language": "en"},
    )
    assert resp.status_code == 400
