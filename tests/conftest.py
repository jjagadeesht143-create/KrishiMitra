"""Shared test fixtures: one isolated SQLite DB for all DB-touching tests.

A single engine + get_db override avoids last-write-wins conflicts
between test modules (FastAPI dependency_overrides is global).
Production data/krishimitra.db is never touched by tests.
"""

from __future__ import annotations

import os
import tempfile

# Hermetic guard: tests must NEVER use real .env credentials, even when
# the developer has real keys configured (USE_MOCK_AI=false + keys).
# Empty strings (not deletion) so later load_dotenv() calls cannot
# restore real values (dotenv never overrides existing vars).
for _var in (
    "MODEL_API_KEY",
    "META_API_KEY",
    "META_VOICE_API_KEY",
    "META_IMAGE_API_KEY",
    "WHATSAPP_TOKEN",
    "MANDI_API_KEY",
):
    os.environ[_var] = ""
os.environ["USE_MOCK_AI"] = "true"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main

# Freeze dotenv in tests: settings.refresh() calls load_dotenv() at
# runtime, which would resurrect real .env keys right after a test
# deletes them to simulate "missing key". Neutralize it so deletion
# truly means missing. Production hot-reload is untouched.
import app.config


def _no_dotenv(*args, **kwargs) -> bool:
    return False


app.config.load_dotenv = _no_dotenv
from app import models
from app.database import get_db

_tmpdir = tempfile.mkdtemp(prefix="krishimitra_test_")
test_engine = create_engine(
    f"sqlite:///{_tmpdir}/test.db", connect_args={"check_same_thread": False}
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
models.Base.metadata.create_all(bind=test_engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[get_db] = _override_get_db
