"""Crop Rescue Plan generator service (Phase 9).

Builds a personalised plan from the farmer's own SQLite data: profile,
recent messages, detected topic, and still-missing details. Content is
always in the farmer's language (Tamil/Hindi/English only).

Safety rules (always apply, enforced by construction):
- Ask follow-up questions before final advice (questions_for_expert).
- Never claim a certain disease diagnosis (confidence is always "low",
  plus an explicit not-a-diagnosis disclaimer).
- Safe next steps only; always refer to a local expert.
- Never invent pesticide names/doses, weather, or prices: this module
  contains no chemical names, no dosages, no weather, and no prices.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import models
from .chatbot import (
    CROP_WORDS,
    FOLLOW_UP_QUESTIONS,
    SAFETY_NOTES,
    detect_topic,
    find_missing_info,
    get_recent_history,
)

SUPPORTED_PLAN_LANGUAGES = ("en", "ta", "hi")

CROP_UNKNOWN = {
    "en": "Not known yet",
    "ta": "இன்னும் தெரியவில்லை",
    "hi": "अभी पता नहीं",
}

TOPIC_DISPLAY = {
    "en": {
        "crop_health": "Crop health",
        "fertilizer": "Fertilizer / nutrition",
        "irrigation": "Water / irrigation",
        "pest": "Pests / insects",
        "general_farming": "General farming",
    },
    "ta": {
        "crop_health": "பயிர் நலம்",
        "fertilizer": "உரம் / ஊட்டச்சத்து",
        "irrigation": "தண்ணீர் / நீர்ப்பாசனம்",
        "pest": "பூச்சிகள்",
        "general_farming": "பொது விவசாயம்",
    },
    "hi": {
        "crop_health": "फसल स्वास्थ्य",
        "fertilizer": "उर्वरक / पोषण",
        "irrigation": "पानी / सिंचाई",
        "pest": "कीट",
        "general_farming": "सामान्य खेती",
    },
}

SUMMARY_KNOWN_CROP = {
    "en": "{name}, here is your personal Crop Rescue Plan for your {crop} crop ({topic}). This is general guidance only, not a confirmed diagnosis.",
    "ta": "{name}, உங்கள் {crop} பயிருக்கான ({topic}) தனிப்பட்ட பயிர் மீட்புத் திட்டம் இதோ. இது பொது ஆலோசனை மட்டுமே, உறுதியான நோய் கண்டறிதல் அல்ல.",
    "hi": "{name}, आपकी {crop} फसल ({topic}) के लिए आपकी व्यक्तिगत फसल बचाव योजना यह है। यह सिर्फ सामान्य सलाह है, पक्का निदान नहीं।",
}

SUMMARY_UNKNOWN_CROP = {
    "en": "{name}, here is your personal Crop Rescue Plan ({topic}). Tell me your crop name so the next plan can be more specific. This is general guidance only, not a confirmed diagnosis.",
    "ta": "{name}, உங்கள் தனிப்பட்ட பயிர் மீட்புத் திட்டம் ({topic}) இதோ. அடுத்த திட்டம் இன்னும் துல்லியமாக இருக்க உங்கள் பயிரின் பெயரைச் சொல்லுங்கள். இது பொது ஆலோசனை மட்டுமே, உறுதியான நோய் கண்டறிதல் அல்ல.",
    "hi": "{name}, आपकी व्यक्तिगत फसल बचाव योजना ({topic}) यह है। अगली योजना और सटीक बने, इसलिए अपनी फसल का नाम बताएं। यह सिर्फ सामान्य सलाह है, पक्का निदान नहीं।",
}

IMMEDIATE_STEPS = {
    "en": [
        "Look at your crop every morning and evening for 5 minutes.",
        "Remove badly affected leaves by hand and throw them away from the field.",
        "Give water only if the top soil feels dry; do not flood the field.",
        "Keep the field edges clean of weeds so air can move freely.",
        "Do not spray any chemical until a local expert sees your crop.",
    ],
    "ta": [
        "காலையும் மாலையும் 5 நிமிடம் பயிரை கவனியுங்கள்.",
        "மிகவும் பாதித்த இலைகளை கையால் அகற்றி வயலுக்கு வெளியே எறியுங்கள்.",
        "மேல் மண் காய்ந்திருந்தால் மட்டும் தண்ணீர் விடுங்கள்; வயலை மூழ்கடிக்க வேண்டாம்.",
        "காற்று நன்கு படும்படி வயல் ஓரங்களில் களைகளை அகற்றுங்கள்.",
        "உங்கள் பகுதி நிபுணர் பயிரைப் பார்க்கும் வரை எந்த மருந்தும் தெளிக்க வேண்டாம்.",
    ],
    "hi": [
        "सुबह और शाम 5 मिनट अपनी फसल को ध्यान से देखें।",
        "बहुत खराब पत्तियों को हाथ से तोड़कर खेत से दूर फेंक दें।",
        "ऊपर की मिट्टी सूखी लगे तभी पानी दें; खेत में पानी न भरें।",
        "हवा आने के लिए खेत की मेड़ों से खरपतवार हटाकर साफ रखें।",
        "स्थानीय विशेषज्ञ के फसल देखने तक कोई दवा न छिड़कें।",
    ],
}

WATCH_OUT_FOR = {
    "en": [
        "More leaves changing colour or getting spots.",
        "Leaves wilting even after watering.",
        "Small insects or a sticky coating under the leaves.",
        "The problem spreading to nearby plants.",
    ],
    "ta": [
        "மேலும் இலைகள் நிறம் மாறுவது அல்லது புள்ளிகள் தோன்றுவது.",
        "தண்ணீர் விட்டும் இலைகள் வாடுவது.",
        "இலைகளின் அடியில் சிறு பூச்சிகள் அல்லது ஒட்டும் படலம்.",
        "அருகிலுள்ள செடிகளுக்கும் பிரச்சனை பரவுவது.",
    ],
    "hi": [
        "और पत्तियों का रंग बदलना या धब्बे पड़ना।",
        "पानी देने के बाद भी पत्तियों का मुरझाना।",
        "पत्तियों के नीचे छोटे कीट या चिपचिपी परत।",
        "पास के पौधों में समस्या फैलना।",
    ],
}

FOLLOW_UP = {
    "en": [
        "Day 1-2: check the affected leaves morning and evening; note any spread.",
        "Day 3-4: if spots keep spreading, take fresh photos for the expert.",
        "Day 7: review the whole field; visit the expert if nothing improved.",
    ],
    "ta": [
        "நாள் 1-2: காலையும் மாலையும் பாதித்த இலைகளைப் பார்த்து பரவலைக் குறித்துக்கொள்ளுங்கள்.",
        "நாள் 3-4: புள்ளிகள் தொடர்ந்து பரவினால், நிபுணருக்காக புதிய புகைப்படம் எடுங்கள்.",
        "நாள் 7: முழு வயலையும் மதிப்பிடுங்கள்; முன்னேற்றம் இல்லையெனில் நிபுணரைப் பாருங்கள்.",
    ],
    "hi": [
        "दिन 1-2: सुबह-शाम प्रभावित पत्तियां देखें और फैलाव नोट करें।",
        "दिन 3-4: धब्बे फैलते रहें तो विशेषज्ञ के लिए नई फोटो लें।",
        "दिन 7: पूरा खेत देखें; सुधार न हो तो विशेषज्ञ से मिलें।",
    ],
}

DEFAULT_EXPERT_QUESTION = {
    "en": "What should be my next safe step for this crop?",
    "ta": "இந்த பயிருக்கு அடுத்த பாதுகாப்பான படி என்ன?",
    "hi": "इस फसल के लिए मेरा अगला सुरक्षित कदम क्या हो?",
}

EXPERT_REFERRAL = {
    "en": "Please visit your nearest agricultural extension officer or Krishi Vigyan Kendra with your crop photos within 2-3 days.",
    "ta": "உங்கள் பயிர் புகைப்படங்களுடன் 2-3 நாட்களில் அருகிலுள்ள வேளாண் விரிவாக்க அலுவலர் அல்லது கிருஷி விக்யான் கேந்திராவை அணுகவும்.",
    "hi": "अपनी फसल की फोटो के साथ 2-3 दिन में नज़दीकी कृषि विस्तार अधिकारी या कृषि विज्ञान केंद्र जाएं।",
}

DISCLAIMER = {
    "en": "KrishiMitra guidance is general information, not a confirmed diagnosis. No pesticide, dose, weather, or price data is included.",
    "ta": "கிருஷிமித்ரா ஆலோசனை பொது தகவல் மட்டுமே, உறுதியான நோய் கண்டறிதல் அல்ல. மருந்து, அளவு, வானிலை, விலை விவரங்கள் இதில் இல்லை.",
    "hi": "कृषिमित्रा सलाह सामान्य जानकारी है, पक्का निदान नहीं। इसमें कोई दवा, खुराक, मौसम या भाव की जानकारी नहीं है।",
}

LABELS = {
    "en": {
        "title": "Crop Rescue Plan",
        "farmer": "Farmer",
        "village": "Village",
        "crop": "Crop",
        "topic": "Focus area",
        "summary": "Summary",
        "steps": "Safe steps for this week",
        "watch": "Watch out for",
        "followup": "Follow-up schedule",
        "questions": "Questions for your local expert",
        "safety": "Safety note",
        "expert": "Next: meet an expert",
        "generated": "Plan made on",
    },
    "ta": {
        "title": "பயிர் மீட்புத் திட்டம்",
        "farmer": "விவசாயி",
        "village": "கிராமம்",
        "crop": "பயிர்",
        "topic": "கவனம்",
        "summary": "சுருக்கம்",
        "steps": "இந்த வார பாதுகாப்பான படிகள்",
        "watch": "கவனிக்க வேண்டியவை",
        "followup": "தொடர் கண்காணிப்பு",
        "questions": "உங்கள் பகுதி நிபுணரிடம் கேட்க",
        "safety": "பாதுகாப்பு குறிப்பு",
        "expert": "அடுத்து: நிபுணரை சந்தியுங்கள்",
        "generated": "திட்டம் தயாரான நாள்",
    },
    "hi": {
        "title": "फसल बचाव योजना",
        "farmer": "किसान",
        "village": "गांव",
        "crop": "फसल",
        "topic": "ध्यान का विषय",
        "summary": "सारांश",
        "steps": "इस हफ़्ते के सुरक्षित कदम",
        "watch": "इन पर नज़र रखें",
        "followup": "फॉलो-अप कार्यक्रम",
        "questions": "अपने स्थानीय विशेषज्ञ से पूछें",
        "safety": "सुरक्षा नोट",
        "expert": "अगला कदम: विशेषज्ञ से मिलें",
        "generated": "योजना बनी",
    },
}


def _find_crop(farmer_texts: list[str]) -> str | None:
    """First known crop word in the farmer's messages, if any."""
    combined = " ".join(farmer_texts or []).lower()
    for word in CROP_WORDS:
        if word in combined:
            return word
    return None


REPORT_LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}


def _latest_report(db: Session, farmer_id: int):
    """Newest RescueReport for a farmer, or None when there is none."""
    return (
        db.query(models.RescueReport)
        .filter(models.RescueReport.farmer_id == farmer_id)
        .order_by(
            models.RescueReport.created_at.desc(), models.RescueReport.id.desc()
        )
        .first()
    )


def _report_texts(report) -> list[str]:
    """Free-text fields of a report for topic/gap analysis."""
    if report is None:
        return []
    values = [
        report.crop_name,
        report.growth_stage,
        report.symptoms,
        report.soil_type,
        report.irrigation_method,
        report.location,
        report.recent_weather,
    ]
    return [str(v).strip() for v in values if v and str(v).strip()]


def build_rescue_prompt(report, language: str = "en") -> str:
    """Structured AI prompt from one RescueReport (Phase B).

    Pure function: formats the farmer's own field values for the
    existing Muse Spark AI service. No API call happens here; the
    caller sends this through ai_service (mock-safe) and the model
    replies in the farmer's language.
    """
    lang = language if language in SUPPORTED_PLAN_LANGUAGES else "en"
    name = REPORT_LANGUAGE_NAMES[lang]

    def _or_given(value) -> str:
        text = str(value).strip() if value is not None else ""
        return text if text else "not given"

    area = (
        f"{report.affected_area_pct:g}%"
        if report.affected_area_pct is not None
        else "not given"
    )
    days = (
        f"{report.days_affected} days" if report.days_affected is not None else "not given"
    )
    lines = [
        "Crop Rescue Plan request (structured farmer report):",
        f"- Crop: {_or_given(report.crop_name)}",
        f"- Growth stage: {_or_given(report.growth_stage)}",
        f"- Symptoms: {_or_given(report.symptoms)}",
        f"- Affected area: {area}",
        f"- Days affected: {days}",
        f"- Soil: {_or_given(report.soil_type)}",
        f"- Irrigation: {_or_given(report.irrigation_method)}",
        f"- Location: {_or_given(report.location)}",
        f"- Recent weather: {_or_given(report.recent_weather)}",
        "",
        f"Farmer's language: {name}. Reply ONLY in {name}.",
        "Give short safe guidance a beginner can follow: what the visible "
        "symptoms may mean (only as possibilities), immediate safe steps, "
        "what to watch daily, and questions for a local agricultural expert. "
        "Never claim a certain disease diagnosis. Never name pesticides and "
        "never give any dose or quantity.",
    ]
    return "\n".join(lines)


def build_rescue_plan(
    db: Session, farmer_id: int, language: str | None = None
) -> dict | None:
    """Build one personalised Crop Rescue Plan from SQLite data.

    Phase B: when the farmer has a RescueReport, its field values are
    merged in (crop name used as-is, topic and gaps detected from the
    report text, days_affected covers the "when did it start" gap).
    With no report the result is exactly the history-based plan.
    Returns None when the farmer does not exist. Language resolution:
    explicit en/ta/hi wins, else the farmer's stored preferred_language.
    """
    farmer = db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
    if farmer is None:
        return None
    if language in SUPPORTED_PLAN_LANGUAGES:
        lang = language
    elif farmer.preferred_language in SUPPORTED_PLAN_LANGUAGES:
        lang = farmer.preferred_language
    else:
        lang = "en"

    history = get_recent_history(db, farmer_id, limit=20)
    farmer_texts = [content for role, content in history if role == "farmer"]
    report = _latest_report(db, farmer_id)
    report_texts = _report_texts(report)
    all_texts = farmer_texts + report_texts
    topic = detect_topic(" ".join(all_texts))
    missing = find_missing_info(all_texts)
    if report is not None and report.days_affected is not None and "start" in missing:
        missing.remove("start")
    crop = _find_crop(all_texts)

    topic_display = TOPIC_DISPLAY[lang].get(topic, TOPIC_DISPLAY[lang]["general_farming"])
    if report is not None:
        crop_display = report.crop_name.strip()
        summary = SUMMARY_KNOWN_CROP[lang].format(
            name=farmer.name, crop=crop_display, topic=topic_display
        )
    elif crop:
        summary = SUMMARY_KNOWN_CROP[lang].format(
            name=farmer.name, crop=crop, topic=topic_display
        )
        crop_display = crop
    else:
        summary = SUMMARY_UNKNOWN_CROP[lang].format(
            name=farmer.name, topic=topic_display
        )
        crop_display = CROP_UNKNOWN[lang]

    if missing:
        questions = [FOLLOW_UP_QUESTIONS[lang][key] for key in missing]
    else:
        questions = [DEFAULT_EXPERT_QUESTION[lang]]

    village = farmer.village or "-"
    if farmer.district:
        village = f"{village}, {farmer.district}"

    return {
        "farmer_id": farmer.id,
        "farmer_name": farmer.name,
        "report_id": report.id if report is not None else None,
        "village": village,
        "language": lang,
        "crop": crop,
        "crop_display": crop_display,
        "topic": topic,
        "topic_display": topic_display,
        "title": LABELS[lang]["title"],
        "summary": summary,
        "immediate_steps": list(IMMEDIATE_STEPS[lang]),
        "watch_out_for": list(WATCH_OUT_FOR[lang]),
        "follow_up": list(FOLLOW_UP[lang]),
        "questions_for_expert": questions,
        "safety_note": SAFETY_NOTES[lang],
        "expert_referral": EXPERT_REFERRAL[lang],
        "disclaimer": DISCLAIMER[lang],
        "confidence": "low",
        "labels": dict(LABELS[lang]),
        "generated_at": datetime.now().isoformat(timespec="minutes"),
    }
