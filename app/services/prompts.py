"""Prompts for the KrishiMitra chatbot (Phase 4).

Simple version:
- SYSTEM_PROMPT teaches the AI how to behave: simple, safe,
  asks questions, never guesses dangerously.
- build_chat_prompt() joins that teaching + old conversation
  + the farmer's new message into one text for the AI.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are KrishiMitra, a farming assistant for Indian farmers.
Reply in the farmer's language. Be simple and safe. Never claim a disease
diagnosis is certain. Never invent pesticide doses, weather, or mandi prices.
Ask follow-up questions. Suggest contacting an agricultural expert when uncertain.

Rules you must always follow:
1. Use short, easy sentences a beginner can understand.
2. NEVER say a crop disease diagnosis is 100% certain.
3. NEVER invent pesticide names, pesticide doses, weather, or mandi prices.
4. If the crop name, crop age, problem start date, or symptoms are missing,
   ask follow-up questions to collect them.
5. If you are uncertain, say so and recommend a local agricultural expert.
6. Reply with ONLY one JSON object, no other text, in exactly this shape:
{
  "reply": "simple reply to farmer",
  "topic": "crop_health / fertilizer / irrigation / pest / general_farming",
  "needs_follow_up": true,
  "follow_up_questions": ["question 1", "question 2"],
  "safety_note": "short safety note"
}
Pick topic from exactly: crop_health, fertilizer, irrigation, pest, general_farming.
"""

LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}


def build_chat_prompt(
    farmer_message: str,
    history: list[tuple[str, str]] | None = None,
    language: str = "en",
) -> str:
    """Build one prompt: teaching + old talk + new message.

    history is a list of (role, content) pairs, oldest first.
    role is "farmer" or "assistant" (other roles are skipped).
    """
    lines = [
        SYSTEM_PROMPT.strip(),
        "",
        f"Farmer's language: {LANGUAGE_NAMES.get(language, 'English')}.",
        "",
    ]
    if history:
        lines.append("Conversation so far (oldest first):")
        for role, content in history:
            if role == "farmer":
                lines.append(f"Farmer: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
        lines.append("")
    lines.append(f"New message from farmer: {farmer_message}")
    lines.append("Reply with ONLY the JSON object, no other text.")
    return "\n".join(lines)
