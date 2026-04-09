"""Nakama V3 Framework — Messenger Normalizer.

Transforms the complex Facebook Webhook JSON into canonical
framework types (User, Message). This is the "polyglot" layer
that shields the rest of the framework from Messenger-specific
JSON structures.

Reference:
    https://developers.facebook.com/docs/messenger-platform/reference/webhook-events/messages
    https://developers.facebook.com/docs/messenger-platform/reference/webhook-events/messaging_postbacks
"""

from __future__ import annotations


import re
from dataclasses import dataclass
from typing import Any

from nakama_framework.core.types import Channel, MediaType, Message, User
from nakama_framework.logging import get_logger

logger = get_logger("normalizer")

# Mapping from Facebook attachment types to our MediaType enum
_FB_MEDIA_TYPE_MAP: dict[str, MediaType] = {
    "image": MediaType.IMAGE,
    "video": MediaType.VIDEO,
    "audio": MediaType.AUDIO,
    "file": MediaType.FILE,
    "location": MediaType.LOCATION,
}


@dataclass
class NormalizedEvent:
    """Result of normalizing a Facebook webhook event.

    Attributes:
        user: The canonical User who sent the message.
        message: The canonical Message extracted from the event.
    """

    user: User
    message: Message


def normalize_webhook_payload(body: dict[str, Any]) -> list[NormalizedEvent]:
    """Extract normalized events from a Facebook webhook payload.

    A single webhook POST can contain multiple entries, each with
    multiple messaging events. This function flattens them all
    into a list of NormalizedEvent objects.

    Args:
        body: The raw JSON body from the Facebook webhook POST.

    Returns:
        A list of NormalizedEvent objects. May be empty if no
        valid messaging events are found.
    """
    events: list[NormalizedEvent] = []

    if body.get("object") != "page":
        logger.warning("Webhook payload is not for 'page': %s", body.get("object"))
        return events

    for entry in body.get("entry", []):
        for messaging in entry.get("messaging", []):
            event = _normalize_messaging_event(messaging)
            if event is not None:
                events.append(event)

    return events


def _normalize_messaging_event(
    event: dict[str, Any],
) -> NormalizedEvent | None:
    """Normalize a single messaging event from the webhook.

    Handles three event types:
    1. Text messages (with optional quick_reply)
    2. Messages with attachments (image, video, audio, file)
    3. Postback events (button clicks)

    Args:
        event: A single item from the 'messaging' array.

    Returns:
        A NormalizedEvent if the event is supported, None otherwise.
    """
    sender_id = event.get("sender", {}).get("id")
    if not sender_id:
        logger.debug("Skipping event without sender.id")
        return None

    user = User(
        id=sender_id,
        name="",  # Name requires a separate API call (Profile API)
        channel=Channel.MESSENGER,
    )

    # --- Case 1: Postback (button click) ---
    postback = event.get("postback")
    if postback is not None:
        message = Message(
            text=postback.get("title", ""),
            payload=postback.get("payload"),
            raw=event,
        )
        return NormalizedEvent(user=user, message=message)

    # --- Case 2: Message event ---
    msg_data = event.get("message")
    if msg_data is None:
        logger.debug("Skipping event without 'message' or 'postback'")
        return None

    # Check for echo (messages sent BY the page, not TO the page)
    if msg_data.get("is_echo"):
        logger.debug("Skipping echo message")
        return None

    text = msg_data.get("text", "")
    payload: str | None = None
    media_type: MediaType | None = None
    media_url: str | None = None

    # Quick reply payload (takes priority — it's a button click)
    quick_reply = msg_data.get("quick_reply")
    if quick_reply:
        payload = quick_reply.get("payload")
        
        # Detect NativeQuickReply responses (email, phone) — treat as text
        if payload:
            # Email pattern: something@something.something
            if re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', payload):
                text = payload
                payload = None
            # Phone pattern: digits with optional +, spaces, dashes (min 9 chars)
            elif re.match(r'^[\d\s+\-()]+$', payload) and len(payload.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")) >= 9:
                text = payload
                payload = None

    # Attachments (first attachment determines media type)
    attachments = msg_data.get("attachments", [])
    if attachments:
        first_att = attachments[0]
        att_type = first_att.get("type", "")
        media_type = _FB_MEDIA_TYPE_MAP.get(att_type)
        att_payload = first_att.get("payload", {})
        media_url = att_payload.get("url") if isinstance(att_payload, dict) else None

    message = Message(
        id=msg_data.get("mid"),
        text=text,
        payload=payload,
        media_type=media_type,
        media_url=media_url,
        raw=event,
    )

    return NormalizedEvent(user=user, message=message)
