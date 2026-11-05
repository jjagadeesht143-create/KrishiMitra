"""Database setup for KrishiMitra (SQLite + SQLAlchemy).

Supporting infrastructure: SQLite + SQLAlchemy only store data.
They are NOT Meta services. All AI comes in later phases.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/krishimitra.db")

# Auto-create the folder for a file-based SQLite database (e.g. ./data/).
if DATABASE_URL.startswith("sqlite:///"):
    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

# check_same_thread=False is needed because FastAPI serves many requests
# in different threads but SQLite allows one thread by default.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# SessionLocal makes one database chat session per request.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class every table model inherits from.
Base = declarative_base()


def get_db():
    """Give one request its own database session, then close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
