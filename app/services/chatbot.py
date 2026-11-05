"""Chatbot brain for KrishiMitra (Phase 4 + Phase 6 languages).

Simple version of what happens for every chat message:
1. Language (Phase 6): explicit en/ta/hi wins, else auto-detect the
   message script (Tamil/Hindi/English only). Reply in that language.
2. Memory: read the farmer's last few messages from SQLite.
3. Mock Mode (USE_MOCK_AI=true): answer with safe built-in logic.
   No internet call, free testing.
4. Real Mode (USE_MOCK_AI=false): send the prompt through the
   EXISTING Phase 3 Meta AI service. No new Meta integration here.
5. The answer is always 5 keys: reply, topic, needs_follow_up,
   follow_up_questions, safety_note. Bad AI output can never crash us.
6. Save the farmer's message + our reply + preferred_language in SQLite.
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from .. import models
from .language_service import normalize_language
from .meta_ai_service import meta_ai_service
from .prompts import build_chat_prompt

load_dotenv()

ALLOWED_TOPICS = ("crop_health", "fertilizer", "irrigation", "pest", "general_farming")
HISTORY_LIMIT = 6  # how many old messages the bot remembers

# Words that tell us the farmer already gave this detail.
CROP_WORDS = (
    "tomato", "tamatar", "thakkali", "paddy", "rice", "nel", "wheat",
    "gothumai", "cotton", "paruthi", "onion", "vengayam", "potato",
    "urulai", "aloo", "chilli", "milagai", "mirch", "maize", "sorghum",
    "sugarcane", "karumbu", "banana", "vazhai", "kela", "mango", "mangai",
    "groundnut", "kadalai", "soybean", "soya", "brinjal", "kathiri",
    "baingan", "okra", "vendai", "bhindi", "coconut", "thengai",
    "turmeric", "manjal", "haldi", "ginger", "inji", "garlic",
    "sunflower", "mustard", "kadugu", "sarson",
)
AGE_WORDS = (
    "days old", "day old", "weeks old", "months old", "old crop",
    "sown", "sowed", "sowing", "planted", "planting", "transplant",
    "age of", "age is", "vitait", "vitai", "nadavu",
    "buvai", "bovai", "bue hue", "din ki", "din ka",
)
START_WORDS = (
    "days ago", "day ago", "ago", "since", "started", "starting",
    "begun", "began", "yesterday", "last week", "few days",
    "thodangiyathu", "thodangi", "aachu", "mun",
    "shuru", "pehle", "pichle", "kal se",
)
SYMPTOM_WORDS = (
    "yellow", "yellowing", "spot", "spots", "wilt", "wilting", "dry",
    "drying", "curl", "curling", "rot", "rotting", "white", "black",
    "brown", "patch", "hole", "falling", "drop", "burn", "sticky",
    "powder", "mold", "manjal", "pullli", "vadal", "karuppu",
    "peela", "peele", "dhabba", "daag", "sukha", "murjha",
)

TOPIC_KEYWORDS = {
    "pest": ("insect", "pest", "worm", "caterpillar", "aphid", "whitefly",
             "thrips", "mite", "bug", "beetle", "poochi", "puzhu",
             "keet", "keeda", "sundi", "illaipen"),
    "irrigation": ("water", "irrigation", "watering", "drip", "dry field",
                   "no water", "thanneer", "neer", "pasnam",
                   "paani", "pani", "sinchai", "sinchaai"),
    "fertilizer": ("fertilizer", "fertiliser", "urea", "manure", "compost",
                   "nutrient", "dap ", "potash", "uram", "eruvu",
                   "khaad", "urvarak"),
    "crop_health": ("yellow", "disease", "spot", "wilt", "rot", "curl",
                    "fungus", "virus", "leaves", "leaf", "stem", "root",
                    "flower", "fruit", "ilai", "manjal",
                    "patta", "patti", "paudha", "fasal"),
}

FOLLOW_UP_QUESTIONS = {
    "en": {
        "crop": "What is your crop name?",
        "age": "How old is your crop (how many days since sowing)?",
        "start": "How many days ago did this problem start?",
        "symptoms": "Can you describe the symptoms in more detail (color, spots, wilting)?",
    },
    "ta": {
        "crop": "உங்கள் பயிரின் பெயர் என்ன?",
        "age": "உங்கள் பயிர் எத்தனை நாட்கள் ஆனது (விதைத்த நாள் முதல்)?",
        "start": "இந்த பிரச்சனை எத்தனை நாட்களுக்கு முன் தொடங்கியது?",
        "symptoms": "அறிகுறிகளை இன்னும் விரிவாக சொல்ல முடியுமா (நிறம், புள்ளிகள், வாடல்)?",
    },
    "hi": {
        "crop": "आपकी फसल का नाम क्या है?",
        "age": "आपकी फसल कितने दिन की है (बुवाई के कितने दिन बाद)?",
        "start": "यह समस्या कितने दिन पहले शुरू हुई?",
        "symptoms": "लक्षणों को और विस्तार से बताएं (रंग, धब्बे, मुरझाना)?",
    },
}

SAFETY_NOTES = {
    "en": "I am not certain about the exact problem. Please show your crop to a local agricultural expert before spraying anything.",
    "ta": "சரியான பிரச்சனை என்னவென்று எனக்கு உறுதியாகத் தெரியவில்லை. எதையும் தெளிப்பதற்கு முன் உங்கள் பகுதி வேளாண் நிபுணரை அணுகவும்.",
    "hi": "मुझे सही समस्या के बारे में निश्चित रूप से नहीं पता। कुछ भी छिड़कने से पहले कृपया अपने स्थानीय कृषि विशेषज्ञ से संपर्क करें।",
}

MOCK_REPLY_NEEDS_INFO = {
    "en": "Thank you. I understand: '{message}'. To help you safely, please answer my follow-up questions.",
    "ta": "நன்றி. புரிந்துகொண்டேன்: '{message}'. உங்களுக்கு பாதுகாப்பாக உதவ, என் தொடர் கேள்விகளுக்கு பதில் சொல்லுங்கள்.",
    "hi": "धन्यवाद। मैं समझ गया: '{message}'। आपकी सुरक्षित मदद के लिए, कृपया मेरे अगले सवालों के जवाब दें।",
}

MOCK_REPLY_COMPLETE = {
    "en": "Thank you for the details. Safe general guidance: watch your crop daily, remove badly affected leaves by hand, give water only if the soil is dry, and do not spray any chemical yet.",
    "ta": "விவரங்களுக்கு நன்றி. பாதுகாப்பான பொது ஆலோசனை: தினமும் பயிரை கவனியுங்கள், மிகவும் பாதித்த இலைகளை கையால் அகற்றுங்கள், மண் காய்ந்திருந்தால் மட்டும் தண்ணீர் விடுங்கள், இப்போது எந்த மருந்தும் தெளிக்க வேண்டாம்.",
    "hi": "जानकारी के लिए धन्यवाद। सुरक्षित सामान्य सलाह: रोज अपनी फसल देखें, बहुत खराब पत्तियों को हाथ से हटाएं, मिट्टी सूखी हो तभी पानी दें, और अभी कोई दवा न छिड़कें।",
}


def use_mock_ai() -> bool:
    """True = safe Mock Mode. Read fresh each time so .env edits apply."""
    return (os.getenv("USE_MOCK_AI", "true") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def get_recent_history(
    db: Session, farmer_id: int, limit: int = HISTORY_LIMIT
) -> list[tuple[str, str]]:
    """Memory: last few (role, content) messages, oldest first."""
    rows = (
        db.query(models.Conversation)
        .filter(models.Conversation.farmer_id == farmer_id)
        .order_by(
            models.Conversation.created_at.desc(), models.Conversation.id.desc()
        )
        .limit(limit)
        .all()
    )
    return [(row.role, row.content) for row in reversed(rows)]


def save_exchange(
    db: Session,
    farmer_id: int,
    farmer_message: str,
    ai_reply: str,
    language: str = "en",
) -> None:
    """Save both sides of one chat turn so we remember next time."""
    db.add(
        models.Conversation(
            farmer_id=farmer_id,
            role="farmer",
            content=farmer_message,
            language=language,
        )
    )
    db.add(
        models.Conversation(
            farmer_id=farmer_id,
            role="assistant",
            content=ai_reply,
            language=language,
        )
    )
    db.commit()


def detect_topic(text: str) -> str:
    """Guess the farming topic from simple keywords (mock helper)."""
    lowered = (text or "").lower()
    for topic, words in TOPIC_KEYWORDS.items():
        if any(word in lowered for word in words):
            return topic
    return "general_farming"


def find_missing_info(farmer_texts: list[str]) -> list[str]:
    """Check which details the farmer has NOT given yet.

    Only farmer messages are checked, never our own old questions.
    Returns keys like ["age", "start"] in a fixed order.
    """
    combined = " ".join(farmer_texts or []).lower()
    missing = []
    if not any(word in combined for word in CROP_WORDS):
        missing.append("crop")
    if not any(word in combined for word in AGE_WORDS):
        missing.append("age")
    if not any(word in combined for word in START_WORDS):
        missing.append("start")
    if not any(word in combined for word in SYMPTOM_WORDS):
        missing.append("symptoms")
    return missing


def parse_ai_json(raw: str, language: str = "en") -> dict | None:
    """Read the 5-key JSON from AI text. Returns None if it is broken.

    Never raises: broken text simply gives None and the caller
    uses a safe fallback reply instead.
    """
    try:
        if not raw or not raw.strip():
            return None
        text = raw.strip()
        if text.startswith("```"):  # strip Markdown code fences
            lines = [ln for ln in text.splitlines()
                     if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            return None
        reply = str(data.get("reply", "")).strip()
        if not reply:
            return None
        topic = str(data.get("topic", "general_farming")).strip()
        if topic not in ALLOWED_TOPICS:
            topic = "general_farming"
        questions = data.get("follow_up_questions", [])
        if not isinstance(questions, list):
            questions = []
        questions = [str(q).strip() for q in questions if str(q).strip()][:4]
        needs_follow_up = bool(data.get("needs_follow_up", bool(questions)))
        safety_note = str(data.get("safety_note", "")).strip()
        if not safety_note:
            safety_note = SAFETY_NOTES.get(language, SAFETY_NOTES["en"])
        return {
            "reply": reply,
            "topic": topic,
            "needs_follow_up": needs_follow_up,
            "follow_up_questions": questions,
            "safety_note": safety_note,
        }
    except (ValueError, AttributeError, TypeError):
        return None


def _fallback_reply(raw: str, language: str = "en") -> dict:
    """Safe reply used when the AI output is not valid JSON."""
    lang = language if language in SAFETY_NOTES else "en"
    reply = (raw or "").strip().replace("```", "")[:600]
    if not reply:
        reply = MOCK_REPLY_NEEDS_INFO[lang].format(message="")
    return {
        "reply": reply,
        "topic": detect_topic(reply),
        "needs_follow_up": True,
        "follow_up_questions": [
            FOLLOW_UP_QUESTIONS[lang]["crop"],
            FOLLOW_UP_QUESTIONS[lang]["symptoms"],
        ],
        "safety_note": SAFETY_NOTES[lang],
    }


def _mock_chat_reply(
    message: str, history: list[tuple[str, str]], language: str = "en"
) -> dict:
    """Safe built-in answer. No internet call happens here."""
    lang = language if language in SAFETY_NOTES else "en"
    farmer_texts = [content for role, content in (history or [])
                    if role == "farmer"] + [message]
    missing = find_missing_info(farmer_texts)
    questions = [FOLLOW_UP_QUESTIONS[lang][key] for key in missing[:3]]
    if missing:
        reply = MOCK_REPLY_NEEDS_INFO[lang].format(message=message)
    else:
        reply = MOCK_REPLY_COMPLETE[lang]
    return {
        "reply": reply,
        "topic": detect_topic(" ".join(farmer_texts)),
        "needs_follow_up": bool(missing),
        "follow_up_questions": questions,
        "safety_note": SAFETY_NOTES[lang],
    }


def get_chat_reply(
    db: Session, farmer_id: int, message: str, language: str | None = None
) -> dict:
    """One full chatbot turn: detect -> remember -> think -> answer -> save.

    Phase 6: language None/unknown = auto-detect from the message script
    (Tamil/Hindi/English only); the reply uses that language and the
    farmer's preferred_language is stored in SQLite.
    Always returns the 5 keys. Never crashes on bad AI output.
    """
    lang = normalize_language(language, message)
    history = get_recent_history(db, farmer_id)
    if use_mock_ai():
        result = _mock_chat_reply(message, history, lang)
    else:
        try:
            prompt = build_chat_prompt(message, history, lang)
            # Reuse Phase 3 only. No new Meta integration is created here.
            raw = meta_ai_service.generate_farming_response(prompt, lang)
            result = parse_ai_json(raw, lang) or _fallback_reply(raw, lang)
        except Exception:
            result = _fallback_reply("", lang)
    farmer = (
        db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
    )
    if farmer is not None:
        farmer.preferred_language = lang
    save_exchange(db, farmer_id, message, result["reply"], lang)
    return result
