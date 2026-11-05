"""Database tables for KrishiMitra.

Three tables: farmers (who), conversations (what was said), and
rescue_reports (structured crop-problem reports from the Rescue
Plan form). Existing tables are unchanged.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class Farmer(Base):
    """One row per farmer. Phone number must be unique."""

    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    village = Column(String, nullable=True)
    district = Column(String, nullable=True)
    state = Column(String, default="Tamil Nadu")
    preferred_language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.now)

    # One farmer -> many conversation messages.
    conversations = relationship(
        "Conversation", back_populates="farmer", cascade="all, delete-orphan"
    )


class Conversation(Base):
    """One row per chat message from a farmer or the assistant."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    role = Column(String, nullable=False)  # farmer, assistant, or system
    message_type = Column(String, default="text")
    content = Column(Text, nullable=False)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.now)

    # Many messages -> one farmer.
    farmer = relationship("Farmer", back_populates="conversations")


class RescueReport(Base):
    """One structured crop-problem report from the Rescue Plan form.

    Phase B: stores the farmer's own field values so the Rescue Plan
    can be personalised without re-asking. crop_name and symptoms are
    required; everything else is optional. image_filename is the safe
    local name under uploads/ (None when no photo was sent).
    """

    __tablename__ = "rescue_reports"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False, index=True)
    crop_name = Column(String(80), nullable=False)
    growth_stage = Column(String(100), nullable=True)
    symptoms = Column(Text, nullable=False)
    affected_area_pct = Column(Float, nullable=True)
    days_affected = Column(Integer, nullable=True)
    soil_type = Column(String(100), nullable=True)
    irrigation_method = Column(String(100), nullable=True)
    location = Column(String(120), nullable=True)
    recent_weather = Column(String(500), nullable=True)
    image_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
