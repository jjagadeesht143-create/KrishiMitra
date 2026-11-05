"""Phase 8: crop image upload + safe analysis (Meta-only Mock Mode)."""

from __future__ import annotations

import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="krishimitra_image_")
os.environ["UPLOAD_DIR"] = _tmpdir

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services.image_service import analyse_crop_image, image_service  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _isolate_upload_dir():
    """Point UPLOAD_DIR at this module's dir (import order must not matter)."""
    os.environ["UPLOAD_DIR"] = _tmpdir
    yield

# Minimal magic-byte headers only (content checks, not real photos).
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes-for-testing-only"
FAKE_JPG = b"\xff\xd8\xff\xe0" + b"fake-jpg-bytes-for-testing-only"
NOT_IMAGE = b"this is plain text, not an image"


def test_image_status_is_ready() -> None:
    resp = client.get("/image/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["module"] == "image"
    assert body["mode"] == "mock"


def test_analyse_english_crop_photo() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("leaf_en.png", FAKE_PNG, "image/png")},
        data={"language": "en"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["language"] == "en"
    assert body["confidence"] == "low"
    assert body["needs_clearer_photo"] is True
    assert "not clear enough to confirm any disease" in body["observation"]
    assert "not a confirmed disease diagnosis" in body["safety_note"]
    assert isinstance(body["possible_issues"], list) and body["possible_issues"]
    assert os.path.isfile(os.path.join(_tmpdir, body["filename"]))


def test_analyse_tamil_crop_photo() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("leaf_ta.jpg", FAKE_JPG, "image/jpeg")},
        data={"language": "ta"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["confidence"] == "low"
    assert "உறுதியாகச் சொல்ல முடியாது" in body["observation"]


def test_analyse_hindi_crop_photo() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("leaf_hi.png", FAKE_PNG, "image/png")},
        data={"language": "hi"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["confidence"] == "low"
    assert "पक्का रोग निदान नहीं" in body["safety_note"]


def test_analyse_rejects_bad_extension() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("leaf.txt", NOT_IMAGE, "text/plain")},
        data={"language": "en"},
    )
    assert resp.status_code == 400


def test_analyse_rejects_non_image_content() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("fake.png", NOT_IMAGE, "image/png")},
        data={"language": "en"},
    )
    assert resp.status_code == 400


def test_analyse_rejects_empty_file() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("empty.png", b"", "image/png")},
        data={"language": "en"},
    )
    assert resp.status_code == 400


def test_analyse_rejects_bad_language() -> None:
    resp = client.post(
        "/image/analyse",
        files={"file": ("leaf.png", FAKE_PNG, "image/png")},
        data={"language": "fr"},
    )
    assert resp.status_code == 400


def test_service_helper_returns_safe_mock_result() -> None:
    assert image_service.is_mock is True
    result = analyse_crop_image(os.path.join(_tmpdir, "sample.png"), "en")
    assert result["confidence"] == "low"
    assert result["needs_clearer_photo"] is True


def test_analyse_rejects_oversize_file() -> None:
    big = b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024)
    resp = client.post(
        "/image/analyse",
        files={"file": ("big.png", big, "image/png")},
        data={"language": "en"},
    )
    assert resp.status_code == 400
