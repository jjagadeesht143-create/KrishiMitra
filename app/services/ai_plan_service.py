"""Structured AI rescue-plan generation (Phase C).

Takes one RescueReport (+ optional crop-photo analysis) and returns a
personalised 8-key AI plan through the EXISTING Muse Spark service
(app.ai_service). No new Meta integration is created here.

8 keys: detected_issue, possible_causes, confidence, explanation,
organic_treatment, recommended_actions, prevention_tips,
expert_referral. A fixed safety_note is always added.

Safety (always enforced, real or mock):
- Organic and cultural methods are asked for FIRST.
- Never a certain diagnosis (confidence defaults to low).
- Never pesticide names/doses: dosage-like text from the model is
  replaced with a safe expert-referral sentence.
- Never invented weather or mandi prices (the prompt forbids them
  and no such keys exist).
- Mock fallback (USE_MOCK_AI=true or unconfigured) returns safe
  generic guidance with low confidence, for development only.
"""

from __future__ import annotations

import json

from ..ai_service import ai_service
from .rescue_plan_service import SUPPORTED_PLAN_LANGUAGES, build_rescue_prompt

AI_PLAN_KEYS = (
    "detected_issue",
    "possible_causes",
    "confidence",
    "explanation",
    "organic_treatment",
    "recommended_actions",
    "prevention_tips",
    "expert_referral",
)

BANNED_TOKENS = ("ml/l", "mg/l", "g/l", "ml per", "pesticide dose")

_JSON_SHAPE = """Reply with ONLY one JSON object, no other text, in exactly this shape:
{
  "detected_issue": "main visible problem in one short sentence",
  "possible_causes": ["possible cause 1", "possible cause 2"],
  "confidence": "low",
  "explanation": "2-3 short simple sentences for a beginner farmer",
  "organic_treatment": ["organic or cultural step 1", "organic or cultural step 2"],
  "recommended_actions": ["safe action 1", "safe action 2", "safe action 3"],
  "prevention_tips": ["prevention tip 1", "prevention tip 2"],
  "expert_referral": "when to visit the local agricultural expert"
}
Rules: organic and cultural methods FIRST, before anything else.
Describe only VISIBLE symptoms and call causes only POSSIBLE.
NEVER claim a certain disease diagnosis. NEVER name pesticides and
NEVER give any dose or quantity. NEVER invent weather or mandi
prices; if the report has none, say nothing about them."""

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

_SCRUB_FALLBACK = {
    "en": "Ask your local agricultural expert for the exact treatment - do not guess any dose.",
    "ta": "சரியான சிகிச்சைக்கு உங்கள் பகுதி வேளாண் நிபுணரைக் கேளுங்கள் - அளவை யூகிக்க வேண்டாம்.",
    "hi": "सही इलाज के लिए अपने स्थानीय कृषि विशेषज्ञ से पूछें - खुराक का अंदाज़ा न लगाएं।",
}

# Safe generic mock content (development fallback only). No diagnosis,
# no products, no doses: cultural practices + expert referral.
MOCK_PLAN = {
    "en": {
        "detected_issue": "Crop problem reported - needs closer inspection.",
        "possible_causes": [
            "Possible nutrient stress",
            "Possible pest damage",
            "Possible water stress",
        ],
        "confidence": "low",
        "explanation": (
            "Your crop shows signs of stress. The exact cause is not "
            "certain from this information alone, so follow only safe "
            "general steps for now."
        ),
        "organic_treatment": [
            "Remove badly affected leaves by hand and throw them away from the field.",
            "Improve air flow by spacing plants and clearing weeds.",
            "Water only at the soil in the morning; avoid wetting the leaves.",
        ],
        "recommended_actions": [
            "Watch the crop every morning and evening.",
            "Take a clear daylight photo of one affected leaf.",
            "Keep the field edges clean of weeds.",
        ],
        "prevention_tips": [
            "Give water only when the topsoil feels dry.",
            "Remove fallen leaves from the field.",
            "Do not spray any chemical yet.",
        ],
        "expert_referral": (
            "Show your crop and photos to your local agricultural "
            "expert within 2-3 days."
        ),
    },
    "ta": {
        "detected_issue": "பயிர் பிரச்சனை தெரிவிக்கப்பட்டது - நெருக்கமான பரிசோதனை தேவை.",
        "possible_causes": [
            "ஊட்டச்சத்து குறைபாடு இருக்கலாம்",
            "பூச்சி தாக்கம் இருக்கலாம்",
            "தண்ணீர் பற்றாக்குறை இருக்கலாம்",
        ],
        "confidence": "low",
        "explanation": (
            "உங்கள் பயிரில் பாதிப்பு தெரிகிறது. இந்த தகவலில் "
            "சரியான காரணம் உறுதியாகத் தெரியவில்லை, எனவே இப்போது "
            "பாதுகாப்பான பொது நடவடிக்கைகளை மட்டும் பின்பற்றுங்கள்."
        ),
        "organic_treatment": [
            "மிகவும் பாதித்த இலைகளை கையால் அகற்றி வயலுக்கு வெளியே எறியுங்கள்.",
            "செடிகளுக்கு இடைவெளி விட்டு, களைகளை அகற்றி காற்றோட்டம் கொடுங்கள்.",
            "காலையில் மண்ணில் மட்டும் தண்ணீர் விடுங்கள்; இலைகளை நனைக்க வேண்டாம்.",
        ],
        "recommended_actions": [
            "காலையும் மாலையும் பயிரை கவனியுங்கள்.",
            "பாதித்த ஒரு இலையை பகல் வெளிச்சத்தில் தெளிவாகப் புகைப்படம் எடுங்கள்.",
            "வயல் ஓரங்களை களை இல்லாமல் சுத்தமாக வையுங்கள்.",
        ],
        "prevention_tips": [
            "மேல் மண் காய்ந்திருந்தால் மட்டும் தண்ணீர் விடுங்கள்.",
            "உதிர்ந்த இலைகளை வயலில் இருந்து அகற்றுங்கள்.",
            "இப்போது எந்த மருந்தும் தெளிக்க வேண்டாம்.",
        ],
        "expert_referral": "2-3 நாட்களில் உங்கள் பயிரையும் புகைப்படங்களையும் பகுதி வேளாண் நிபுணரிடம் காட்டுங்கள்.",
    },
    "hi": {
        "detected_issue": "फसल की समस्या बताई गई - नज़दीकी जांच ज़रूरी है।",
        "possible_causes": [
            "पोषण की कमी हो सकती है",
            "कीट का असर हो सकता है",
            "पानी की कमी हो सकती है",
        ],
        "confidence": "low",
        "explanation": (
            "आपकी फसल में तकलीफ दिख रही है। इस जानकारी से सही "
            "कारण पक्का नहीं है, इसलिए अभी सिर्फ सुरक्षित सामान्य "
            "कदम अपनाएं।"
        ),
        "organic_treatment": [
            "बहुत खराब पत्तियों को हाथ से तोड़कर खेत से दूर फेंक दें।",
            "पौधों में दूरी रखें और खरपतवार हटाकर हवा आने दें।",
            "सुबह सिर्फ मिट्टी में पानी दें; पत्तियों को न भिगोएं।",
        ],
        "recommended_actions": [
            "सुबह और शाम फसल को ध्यान से देखें।",
            "प्रभावित एक पत्ती की दिन के उजाले में साफ फोटो लें।",
            "खेत की मेड़ों को खरपतवार से साफ रखें।",
        ],
        "prevention_tips": [
            "ऊपर की मिट्टी सूखी लगे तभी पानी दें।",
            "गिरी हुई पत्तियों को खेत से हटाएं।",
            "अभी कोई दवा न छिड़कें।",
        ],
        "expert_referral": "2-3 दिन में अपनी फसल और फोटो स्थानीय कृषि विशेषज्ञ को दिखाएं।",
    },
}


def _clean_language(language: str | None) -> str:
    """Keep only en/ta/hi; anything else becomes English."""
    return language if language in SUPPORTED_PLAN_LANGUAGES else "en"


def build_ai_plan_prompt(
    report, language: str = "en", image_analysis: dict | None = None
) -> str:
    """Structured prompt: Phase B report block + photo notes + JSON schema.

    Pure function, no API call. Reuses build_rescue_prompt for the
    farmer's field values so both stay in sync.
    """
    lang = _clean_language(language)
    parts = [build_rescue_prompt(report, lang)]
    if isinstance(image_analysis, dict):
        observation = str(image_analysis.get("observation", "") or "").strip()
        issues = image_analysis.get("possible_issues") or []
        if isinstance(issues, list):
            issues_text = "; ".join(str(i).strip() for i in issues if str(i).strip())
        else:
            issues_text = str(issues).strip()
        if observation or issues_text:
            parts.append("")
            parts.append("Crop photo analysis (uncertain, treat as hints only):")
            if observation:
                parts.append(f"- Observation: {observation[:600]}")
            if issues_text:
                parts.append(f"- Possible issues: {issues_text[:600]}")
    parts.append("")
    parts.append(_JSON_SHAPE)
    return "\n".join(parts)


def _scrub(text: str, lang: str) -> str:
    """Replace dosage-like text with a safe expert-referral sentence."""
    if any(token in (text or "").lower() for token in BANNED_TOKENS):
        return _SCRUB_FALLBACK[lang]
    return text


def _as_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _as_list(value: object, limit: int = 4) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(i).strip()[:300] for i in value if str(i).strip()][:limit]


def parse_ai_plan(raw: str, language: str = "en") -> dict:
    """Parse the model's JSON into the safe 8-key plan. Never raises.

    Missing keys are filled from the safe mock content; broken output
    keeps the raw text as the detected issue with low confidence.
    The safety note is always our fixed text.
    """
    lang = _clean_language(language)
    mock = MOCK_PLAN[lang]
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
    detected = _as_text(data.get("detected_issue"), 500)
    if not detected:
        detected = (raw or "").strip().replace("```", "")[:500] or mock["detected_issue"]
    causes = _as_list(data.get("possible_causes")) or list(mock["possible_causes"])
    confidence = _as_text(data.get("confidence", "low"), 20).lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "low"
    explanation = _as_text(data.get("explanation"), 1000) or mock["explanation"]
    organic = _as_list(data.get("organic_treatment")) or list(mock["organic_treatment"])
    actions = _as_list(data.get("recommended_actions")) or list(mock["recommended_actions"])
    prevention = _as_list(data.get("prevention_tips")) or list(mock["prevention_tips"])
    referral = _as_text(data.get("expert_referral"), 500) or mock["expert_referral"]
    return {
        "detected_issue": _scrub(detected, lang),
        "possible_causes": [_scrub(c, lang) for c in causes],
        "confidence": confidence,
        "explanation": _scrub(explanation, lang),
        "organic_treatment": [_scrub(o, lang) for o in organic],
        "recommended_actions": [_scrub(a, lang) for a in actions],
        "prevention_tips": [_scrub(p, lang) for p in prevention],
        "expert_referral": _scrub(referral, lang),
        "safety_note": _FIXED_SAFETY_NOTE[lang],
    }


def generate_ai_plan(
    report, language: str = "en", image_analysis: dict | None = None
) -> dict:
    """One structured AI plan via the existing Muse Spark service.

    Returns {"mode", "plan", "guidance"}: mode is mock/real/fallback
    from ai_service, plan is the safe 8-key dict, guidance is a short
    derived summary string (kept for existing callers). Never raises:
    AI failure yields the safe mock-structured plan instead. Real API
    is used only when officially configured; mock otherwise.
    """
    lang = _clean_language(language)
    prompt = build_ai_plan_prompt(report, lang, image_analysis)
    try:
        ai = ai_service.generate_reply(prompt, lang)
    except Exception:
        ai = {"reply": "", "language": lang, "mode": "fallback", "used_fallback": True}
    plan = parse_ai_plan(ai.get("reply", ""), lang)
    summary = plan["explanation"]
    top_actions = " ".join(plan["recommended_actions"][:2])
    guidance = f"{summary} {top_actions}".strip()
    return {"mode": ai.get("mode", "fallback"), "plan": plan, "guidance": guidance}
