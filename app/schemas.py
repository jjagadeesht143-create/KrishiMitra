"""Request/response shapes for KrishiMitra (Pydantic).

These check every API input: language must be en/ta/hi,
role must be farmer/assistant/system, names/phones/content must be
non-empty and within length limits.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

ALLOWED_LANGUAGES = ("en", "ta", "hi")
ALLOWED_ROLES = ("farmer", "assistant", "system")


class FarmerBase(BaseModel):
    """Shared farmer fields without validators.

    Input is checked by FarmerCreate. FarmerResponse reuses these fields
    WITHOUT validators so reading older database rows never fails.
    """

    name: str
    phone: str
    village: str | None = None
    district: str | None = None
    state: str = "Tamil Nadu"
    preferred_language: str = "en"


class FarmerCreate(FarmerBase):
    """Data needed to register a farmer. Validators check INPUT only."""

    @field_validator("preferred_language")
    @classmethod
    def check_language(cls, value: str) -> str:
        if value not in ALLOWED_LANGUAGES:
            raise ValueError("preferred_language must be one of: en, ta, hi")
        return value

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        if len(cleaned) > 100:
            raise ValueError("name must be at most 100 characters")
        return cleaned

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        cleaned = (value or "").strip()
        digits = cleaned[1:] if cleaned.startswith("+") else cleaned
        if not digits.isdigit() or not 7 <= len(digits) <= 15:
            raise ValueError("phone must be 7-15 digits, optional leading +")
        return cleaned

    @field_validator("village", "district", "state")
    @classmethod
    def check_place(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) > 100:
            raise ValueError("must be at most 100 characters")
        return cleaned


# NOTE: inherits FarmerBase (no validators) so legacy rows always serialize.
class FarmerResponse(FarmerBase):
    """Farmer data sent back, including id and created time."""

    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    """One chat message to save for a farmer."""

    role: str
    content: str
    message_type: str = "text"
    language: str = "en"

    @field_validator("role")
    @classmethod
    def check_role(cls, value: str) -> str:
        if value not in ALLOWED_ROLES:
            raise ValueError("role must be one of: farmer, assistant, system")
        return value

    @field_validator("content")
    @classmethod
    def check_content(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("content must not be empty")
        if len(cleaned) > 5000:
            raise ValueError("content must be at most 5000 characters")
        return cleaned

    @field_validator("language")
    @classmethod
    def check_conversation_language(cls, value: str) -> str:
        if value not in ALLOWED_LANGUAGES:
            raise ValueError("language must be one of: en, ta, hi")
        return value

    @field_validator("message_type")
    @classmethod
    def check_message_type(cls, value: str) -> str:
        cleaned = (value or "").strip() or "text"
        if len(cleaned) > 20:
            raise ValueError("message_type must be at most 20 characters")
        return cleaned


class ConversationResponse(ConversationCreate):
    """Chat message sent back, including id, farmer_id and created time."""

    id: int
    farmer_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RescueReportCreate(BaseModel):
    """Structured crop-problem input from the Rescue Plan form.

    Phase B: crop_name and symptoms are required. All text accepts
    Tamil, Hindi, and English (any script). Numbers are range-checked.
    """

    crop_name: str
    growth_stage: str | None = None
    symptoms: str
    affected_area_pct: float | None = None
    days_affected: int | None = None
    soil_type: str | None = None
    irrigation_method: str | None = None
    location: str | None = None
    recent_weather: str | None = None

    @field_validator("crop_name")
    @classmethod
    def check_crop_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("crop_name must not be empty")
        if len(cleaned) > 80:
            raise ValueError("crop_name must be at most 80 characters")
        return cleaned

    @field_validator("symptoms")
    @classmethod
    def check_symptoms(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("symptoms must not be empty")
        if len(cleaned) > 1000:
            raise ValueError("symptoms must be at most 1000 characters")
        return cleaned

    @field_validator("growth_stage", "soil_type", "irrigation_method")
    @classmethod
    def check_short_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > 100:
            raise ValueError("must be at most 100 characters")
        return cleaned

    @field_validator("location")
    @classmethod
    def check_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > 120:
            raise ValueError("must be at most 120 characters")
        return cleaned

    @field_validator("recent_weather")
    @classmethod
    def check_recent_weather(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > 500:
            raise ValueError("must be at most 500 characters")
        return cleaned

    @field_validator("affected_area_pct")
    @classmethod
    def check_area_pct(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not 0 <= value <= 100:
            raise ValueError("affected_area_pct must be between 0 and 100")
        return value

    @field_validator("days_affected")
    @classmethod
    def check_days_affected(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not 0 <= value <= 365:
            raise ValueError("days_affected must be between 0 and 365")
        return value


class RescueReportResponse(RescueReportCreate):
    """Stored report sent back, including id, farmer_id and created time."""

    id: int
    farmer_id: int
    image_filename: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
