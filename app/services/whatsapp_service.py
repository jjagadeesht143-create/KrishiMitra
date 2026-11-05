"""WhatsApp Cloud API service adapter (Meta only, no Twilio).

Webhook payload parsing + mock-safe text send, per official Meta docs:
- GET verification + POST receiver contract:
  https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint
- messages webhook payload shape (object/entry/changes/value/messages):
  https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages
- Send endpoint + auth (verified 2026-11-03, NOT invented):
  POST https://graph.facebook.com/{Version}/{Phone-Number-ID}/messages
  Headers: Authorization: Bearer <token>, Content-Type: application/json
  Source: https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-phone-number/message-api
- Text message body (verified 2026-11-03, NOT invented):
  {"messaging_product": "whatsapp", "recipient_type": "individual",
   "to": "<user phone>", "type": "text", "text": {"body": "<text>"}}
  Only doc-marked required fields are sent; nothing invented.
  Source: https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/text-messages

Mock-safe: when WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID is empty
(default), send_message() returns a mock result and makes NO internet
call. This module never prints or logs token values.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Official Graph base + version shown in the Meta docs sample (see above).
WHATSAPP_GRAPH_BASE_URL = "https://graph.facebook.com"
WHATSAPP_GRAPH_VERSION = "v26.0"
WHATSAPP_TIMEOUT_SECONDS = 30


def parse_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract incoming messages + statuses from a Meta webhook POST body.

    Returns {"messages": [...], "statuses": [...]} where each message is
    {"from": str, "id": str, "timestamp": str, "type": str, "text": str|None,
     "raw": dict}. Unknown shapes yield empty lists, never an exception.
    """
    messages: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return {"messages": messages, "statuses": statuses}
    if payload.get("object") != "whatsapp_business_account":
        return {"messages": messages, "statuses": statuses}

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return {"messages": messages, "statuses": statuses}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            raw_messages = value.get("messages")
            if isinstance(raw_messages, list):
                for item in raw_messages:
                    if not isinstance(item, dict):
                        continue
                    text_body = None
                    if item.get("type") == "text":
                        text_obj = item.get("text")
                        if isinstance(text_obj, dict):
                            body = text_obj.get("body")
                            if isinstance(body, str):
                                text_body = body
                    messages.append(
                        {
                            "from": item.get("from"),
                            "id": item.get("id"),
                            "timestamp": item.get("timestamp"),
                            "type": item.get("type"),
                            "text": text_body,
                            "raw": item,
                        }
                    )
            raw_statuses = value.get("statuses")
            if isinstance(raw_statuses, list):
                for item in raw_statuses:
                    if isinstance(item, dict):
                        statuses.append(item)

    return {"messages": messages, "statuses": statuses}


def _send_credentials() -> tuple[str, str]:
    """Read send credentials fresh from .env (never printed or logged)."""
    token = (os.getenv("WHATSAPP_TOKEN") or "").strip()
    phone_number_id = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    return token, phone_number_id


def build_text_payload(to: str, text: str) -> dict[str, Any]:
    """Build the official text-message JSON body (required fields only)."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }


def build_send_url(phone_number_id: str) -> str:
    """Build the official send URL for one business phone number id."""
    base = WHATSAPP_GRAPH_BASE_URL.rstrip("/")
    return f"{base}/{WHATSAPP_GRAPH_VERSION}/{phone_number_id}/messages"


def get_whatsapp_status() -> dict[str, Any]:
    """Safe status: tells if each value is set, never the values."""
    token, phone_number_id = _send_credentials()
    verify = (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip()
    return {
        "mode": "mock" if not (token and phone_number_id) else "real-ready",
        "token_configured": bool(token),
        "phone_number_id_configured": bool(phone_number_id),
        "verify_token_configured": bool(verify),
    }


def send_message(to: str, text: str) -> dict:
    """Send one WhatsApp text message (mock-safe, never raises).

    - Empty to/text -> rejected, no internet call.
    - Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID -> mock_sent,
      no internet call (default while .env is empty).
    - Configured -> one official POST (see module docstring). Any
      failure returns failed with the error type only. The token is
      never printed, logged, or included in any return value.
    """
    clean_to = (to or "").strip()
    clean_text = (text or "").strip()
    if not clean_to or not clean_text:
        return {
            "status": "rejected",
            "reason": "to and text must not be empty",
            "to": clean_to,
            "mode": "mock",
        }
    token, phone_number_id = _send_credentials()
    if not (token and phone_number_id):
        logger.info("WhatsApp mock send to=%s chars=%d", clean_to, len(clean_text))
        return {"status": "mock_sent", "to": clean_to, "text": clean_text, "mode": "mock"}
    try:
        resp = httpx.post(
            build_send_url(phone_number_id),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=build_text_payload(clean_to, clean_text),
            timeout=WHATSAPP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        message_id: str | None = None
        try:
            data = resp.json()
            items = data.get("messages") if isinstance(data, dict) else None
            if isinstance(items, list) and items and isinstance(items[0], dict):
                raw_id = items[0].get("id")
                message_id = raw_id if isinstance(raw_id, str) else None
        except Exception:
            message_id = None
        logger.info("WhatsApp sent to=%s", clean_to)
        return {
            "status": "sent",
            "to": clean_to,
            "text": clean_text,
            "mode": "real",
            "message_id": message_id,
        }
    except Exception as exc:  # Any failure -> safe failed result, never raise.
        logger.warning("WhatsApp send failed: %s", type(exc).__name__)
        return {"status": "failed", "to": clean_to, "mode": "real",
                "error": type(exc).__name__}
