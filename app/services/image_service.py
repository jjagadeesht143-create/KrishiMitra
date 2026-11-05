"""Crop image understanding service adapter with safe Mock Mode (Phase 8).

How it works (simple version):
- The app reads 3 values from the .env file: META_IMAGE_API_KEY,
  META_IMAGE_API_BASE_URL, META_IMAGE_MODEL_NAME. Each empty value
  falls back to the shared chat credentials (MODEL_API_KEY else
  META_API_KEY, META_API_BASE_URL, META_MODEL_NAME), because Meta
  image understanding uses the SAME verified chat-completions
  endpoint, key, and model (verified live 2026-11-04).
- If a value is empty in BOTH places, the app runs in Mock Mode.
  Mock Mode returns a safe, pre-written test analysis. No internet call.
- To use different vision credentials, fill the 3 META_IMAGE_*
  values in .env (from official Meta docs only); they always win.

Verified against the official Meta Model API docs (dev.meta.ai,
image understanding + chat completions, checked 2026-11-04,
NOT invented):
- Same base https://api.meta.ai/v1, Bearer MODEL_API_KEY auth.
- Image goes in the content array of a user message as
  {"type": "image_url", "image_url": {"url": ...}} where the url
  is a public URL or a base64 data: URL (data:image/jpeg;base64,…).
  Local crop photos are sent as base64 data: URLs, no hosting needed.
- Reply text lives at choices[0].message.content.

SAM: checked 2026-11-01, no official Meta-hosted SAM endpoint docs
could be verified (only third-party wrappers and self-hosted code).
So SAM is NOT wired here. Revisit only with official Meta docs.

STRICT RULE: values still come only from .env. The key is never
printed, logged, or returned.

SAFETY RULE: Never claim a certain disease diagnosis from an unclear
image. Mock output always reports low confidence, lists only possible
observations, asks for a clearer photo, and suggests a local expert.
Real output is asked for JSON with the same safe shape; the safety
note is always our own fixed text, confidence defaults to low, and
any pesticide-dosage-like text from the model is replaced with a
safe "ask your local expert" sentence.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_LANGUAGES = ("en", "ta", "hi")

IMAGE_REQUEST_TIMEOUT_SECONDS = 60

_EXTENSION_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}

_VISION_PROMPT = """You are KrishiMitra, a farming assistant for Indian farmers.
Look at the crop photo and reply with ONLY one JSON object, no other text:
{
  "observation": "what you can see in 1-2 short sentences",
  "possible_issues": ["possible issue 1", "possible issue 2"],
  "confidence": "low",
  "guidance": "one safe next step (clearer photo, daily watch, expert visit)"
}
Rules: describe only VISIBLE symptoms and call them only POSSIBLE issues.
NEVER claim a certain disease diagnosis. NEVER name pesticides and NEVER
give any dose or quantity. If the photo is unclear, keep confidence low."""

# Dosage-like text (digit + unit per unit) must never reach the farmer.
_DOSAGE_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ml|mg|g|kg|l|litre|liter)\s*(?:/|per)\s*"
    r"(?:l|litre|liter|acre|hectare|ha|water)",
    re.IGNORECASE,
)

_SAFE_DOSE_FALLBACK = {
    "en": "Ask your local agricultural expert for the exact treatment - do not guess any dose.",
    "ta": "சரியான சிகிச்சைக்கு உங்கள் பகுதி வேளாண் நிபுணரைக் கேளுங்கள் - அளவை யூகிக்க வேண்டாம்.",
    "hi": "सही इलाज के लिए अपने स्थानीय कृषि विशेषज्ञ से पूछें - खुराक का अंदाज़ा न लगाएं।",
}

_FIXED_SAFETY_NOTE = {
    "en": (
        "This is not a confirmed disease diagnosis. Please show "
        "your crop to a local agricultural expert before spraying "
        "anything."
    ),
    "ta": (
        "இது உறுதியான நோய் கண்டறிதல் அல்ல. எந்த மருந்தும் "
        "தெளிப்பதற்கு முன் உங்கள் பகுதி வேளாண் நிபுணரை அணுகவும்."
    ),
    "hi": (
        "यह पक्का रोग निदान नहीं है। कोई दवा छिड़कने से पहले "
        "अपने स्थानीय कृषि विशेषज्ञ से संपर्क करें।"
    ),
}

_DEFAULT_GUIDANCE = {
    "en": "Take a close-up photo of the affected leaf in daylight and show it to your local expert.",
    "ta": "பாதித்த இலையை பகல் வெளிச்சத்தில் நெருக்கமாகப் புகைப்படம் எடுத்து உங்கள் பகுதி நிபுணரிடம் காட்டுங்கள்.",
    "hi": "प्रभावित पत्ती की दिन के उजाले में नज़दीकी फोटो लेकर अपने स्थानीय विशेषज्ञ को दिखाएं।",
}


def _data_url_for(file_path: str) -> str:
    """Encode a saved photo as a base64 data: URL (no hosting needed)."""
    ext = os.path.splitext(file_path or "")[1].lower()
    mime = _EXTENSION_MIME.get(ext, "image/jpeg")
    with open(file_path, "rb") as handle:
        raw = handle.read()
    if not raw:
        raise ValueError("empty image file")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_reply_text(data: object) -> str:
    """Read choices[0].message.content; raise ValueError when unusable."""
    if not isinstance(data, dict):
        raise ValueError("bad API response")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("bad API response")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("bad API response")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("bad API response")
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("bad API response")
    return text.strip()


def _scrub_field(text: str, language: str) -> str:
    """Replace dosage-like text with a safe expert-referral sentence."""
    if _DOSAGE_PATTERN.search(text or ""):
        return _SAFE_DOSE_FALLBACK[language]
    return text


def _vision_result_from_text(raw: str, language: str) -> dict:
    """Build the safe result dict from the model's reply text.

    Expects the JSON shape from _VISION_PROMPT; broken output still
    yields a safe result (raw text as observation, low confidence,
    clearer photo requested). The safety note is always our fixed
    text. Never raises on model output.
    """
    lang = language if language in ALLOWED_IMAGE_LANGUAGES else "en"
    data: dict = {}
    try:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                data = parsed
    except (ValueError, TypeError):
        data = {}
    observation = str(data.get("observation", "") or "").strip()[:1000]
    if not observation:
        observation = (raw or "").strip().replace("```", "")[:1000]
    issues = data.get("possible_issues", [])
    if not isinstance(issues, list):
        issues = []
    issues = [str(i).strip()[:300] for i in issues if str(i).strip()][:4]
    confidence = str(data.get("confidence", "low") or "low").strip().lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "low"
    guidance = str(data.get("guidance", "") or "").strip()[:1000]
    if not guidance:
        guidance = _DEFAULT_GUIDANCE[lang]
    return {
        "observation": _scrub_field(observation, lang),
        "possible_issues": [_scrub_field(i, lang) for i in issues],
        "confidence": confidence,
        "needs_clearer_photo": bool(data.get("needs_clearer_photo", True)),
        "guidance": _scrub_field(guidance, lang),
        "safety_note": _FIXED_SAFETY_NOTE[lang],
    }


class MetaImageService:
    """Adapter for Meta vision analysis with a safe Mock Mode fallback."""

    def __init__(self) -> None:
        """Read Meta vision settings, falling back to shared chat credentials.

        Each META_IMAGE_* value wins when set; otherwise the shared
        chat value is used (same verified endpoint/key/model).
        Mock Mode only when a value is missing in BOTH places.
        """
        self.api_key = (
            (os.getenv("META_IMAGE_API_KEY") or "").strip()
            or (os.getenv("MODEL_API_KEY") or "").strip()
            or (os.getenv("META_API_KEY") or "").strip()
        )
        self.base_url = (os.getenv("META_IMAGE_API_BASE_URL") or "").strip() or (
            os.getenv("META_API_BASE_URL") or ""
        ).strip()
        self.model_name = (os.getenv("META_IMAGE_MODEL_NAME") or "").strip() or (
            os.getenv("META_MODEL_NAME") or ""
        ).strip()
        # Mock Mode when any one of the 3 effective values is missing.
        self.is_mock = not (self.api_key and self.base_url and self.model_name)

    def get_status(self) -> dict:
        """Tell the caller if we run in mock mode or real mode."""
        if self.is_mock:
            return {
                "mode": "mock",
                "message": (
                    "Meta vision API not configured. "
                    "Running in safe Mock Mode for development."
                ),
            }
        return {
            "mode": "real",
            "model": self.model_name,
            "message": "Meta vision API configured.",
        }

    def analyse_crop_image(self, file_path: str, language: str = "en") -> dict:
        """Analyse one saved crop photo; return a safe structured result."""
        lang = language if language in ALLOWED_IMAGE_LANGUAGES else "en"
        if self.is_mock:
            result = self._mock_response(file_path, lang)
            result["mode"] = "mock"
            return result
        try:
            result = self._real_analyse(file_path, lang)
        except Exception as exc:
            # Real call failed: honest mock content labeled as mock.
            logger.warning("Meta vision call failed, using mock: %s", type(exc).__name__)
            result = self._mock_response(file_path, lang)
            result["mode"] = "mock"
            return result
        result["mode"] = "real"
        return result

    def _mock_response(self, file_path: str, language: str) -> dict:
        """Safe pre-written test analysis. No internet call happens here."""
        name = (file_path or "").replace("\\", "/").rsplit("/", 1)[-1]
        if language == "ta":
            return {
                "observation": (
                    "[Mock Mode - Tamil] "
                    f"பயிர் புகைப்படம் கிடைத்தது: '{name}'. "
                    "படம் தெளிவாக இல்லாததால் நோயை உறுதியாகச் சொல்ல முடியாது."
                ),
                "possible_issues": [
                    "இலை நிறம் மாறியிருக்கலாம் - தெளிவான படம் தேவை",
                    "பூச்சி தாக்கம் இருக்கலாம் - நெருக்கமான படம் தேவை",
                ],
                "confidence": "low",
                "needs_clearer_photo": True,
                "guidance": (
                    "பகல் வெளிச்சத்தில், பாதித்த இலையை நெருக்கமாகப் "
                    "புகைப்படம் எடுத்து மீண்டும் அனுப்புங்கள்."
                ),
                "safety_note": (
                    "இது உறுதியான நோய் கண்டறிதல் அல்ல. எந்த மருந்தும் "
                    "தெளிப்பதற்கு முன் உங்கள் பகுதி வேளாண் நிபுணரை அணுகவும்."
                ),
            }
        if language == "hi":
            return {
                "observation": (
                    "[Mock Mode - Hindi] "
                    f"फसल की फोटो मिली: '{name}'. "
                    "तस्वीर साफ न होने से बीमारी पक्की तौर पर नहीं बता सकते।"
                ),
                "possible_issues": [
                    "पत्तियों का रंग बदला हो सकता है - साफ फोटो चाहिए",
                    "कीट का असर हो सकता है - नज़दीकी फोटो चाहिए",
                ],
                "confidence": "low",
                "needs_clearer_photo": True,
                "guidance": (
                    "दिन के उजाले में प्रभावित पत्ती की नज़दीकी फोटो "
                    "लेकर दोबारा भेजें।"
                ),
                "safety_note": (
                    "यह पक्का रोग निदान नहीं है। कोई दवा छिड़कने से पहले "
                    "अपने स्थानीय कृषि विशेषज्ञ से संपर्क करें।"
                ),
            }
        return {
            "observation": (
                "[Mock Mode - English] "
                f"Crop photo received: '{name}'. "
                "The image is not clear enough to confirm any disease."
            ),
            "possible_issues": [
                "Leaf colour may have changed - clearer photo needed",
                "Possible insect damage - close-up photo needed",
            ],
            "confidence": "low",
            "needs_clearer_photo": True,
            "guidance": (
                "Please take a close-up photo of the affected leaf in "
                "daylight and send it again."
            ),
            "safety_note": (
                "This is not a confirmed disease diagnosis. Please show "
                "your crop to a local agricultural expert before spraying "
                "anything."
            ),
        }

    def _real_analyse(self, file_path: str, language: str) -> dict:
        """Real Meta image-understanding call (verified shape).

        Sends the photo as a base64 data: URL in a user content array
        (see module docstring). Raises on any failure so the caller
        can fall back to honest mock content.
        """
        data_url = _data_url_for(file_path)
        resp = httpx.post(
            self.base_url,  # Full endpoint from .env, used as-is.
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "developer", "content": _VISION_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Farmer's language: "
                                    f"{_LANGUAGE_NAMES[language]}. Reply ONLY in "
                                    f"{_LANGUAGE_NAMES[language]}. Analyse this crop photo."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    },
                ],
            },
            timeout=IMAGE_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return _vision_result_from_text(_extract_reply_text(resp.json()), language)


# One shared object used by the whole app.
image_service = MetaImageService()


def analyse_crop_image(file_path: str, language: str = "en") -> dict:
    """Analyse one crop photo; return the safe structured result."""
    return image_service.analyse_crop_image(file_path, language)
