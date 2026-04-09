"""Tests for the Messenger normalizer — normalize_webhook_payload().

Covers text messages, postbacks, quick replies, media attachments,
echo filtering, edge cases, and multi-event payloads.
"""

from __future__ import annotations

import pytest

from nakama_framework.channels.messenger.normalizer import (
    NormalizedEvent,
    normalize_webhook_payload,
)
from nakama_framework.core.types import Channel, MediaType


# --- Helpers ---


def _make_webhook_payload(messaging_events: list[dict]) -> dict:
    """Build a minimal Facebook webhook payload wrapping messaging events."""
    return {
        "object": "page",
        "entry": [
            {
                "id": "PAGE_ID",
                "time": 1700000000000,
                "messaging": messaging_events,
            }
        ],
    }


def _text_event(sender_id: str = "USER_1", text: str = "hello") -> dict:
    """Build a text message event."""
    return {
        "sender": {"id": sender_id},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.123",
            "text": text,
        },
    }


# --- Text Messages ---


async def test_normalize_text_message() -> None:
    """A plain text message should normalize to User + Message."""
    body = _make_webhook_payload([_text_event("USER_1", "Bonjour")])
    events = normalize_webhook_payload(body)

    assert len(events) == 1
    assert events[0].user.id == "USER_1"
    assert events[0].user.channel == Channel.MESSENGER
    assert events[0].message.text == "Bonjour"
    assert events[0].message.payload is None
    assert events[0].message.media_type is None


async def test_normalize_preserves_raw() -> None:
    """The raw event dict should be stored in message.raw."""
    event = _text_event("USER_1", "test")
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert events[0].message.raw == event


# --- Postback Events ---


async def test_normalize_postback() -> None:
    """A postback (button click) should set payload and title as text."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "postback": {
            "title": "Get Started",
            "payload": "GET_STARTED",
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert len(events) == 1
    assert events[0].message.payload == "GET_STARTED"
    assert events[0].message.text == "Get Started"


async def test_normalize_postback_without_title() -> None:
    """A postback with no title should default text to empty string."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "postback": {
            "payload": "MENU_ACTION",
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert events[0].message.text == ""
    assert events[0].message.payload == "MENU_ACTION"


# --- Quick Replies ---


async def test_normalize_quick_reply() -> None:
    """A quick reply should set payload from quick_reply.payload."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.456",
            "text": "Yes",
            "quick_reply": {
                "payload": "CONFIRM_YES",
            },
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert len(events) == 1
    assert events[0].message.text == "Yes"
    assert events[0].message.payload == "CONFIRM_YES"


# --- Media Attachments ---


async def test_normalize_image_attachment() -> None:
    """An image attachment should set media_type and media_url."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.789",
            "attachments": [
                {
                    "type": "image",
                    "payload": {
                        "url": "https://example.com/photo.jpg",
                    },
                }
            ],
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert len(events) == 1
    assert events[0].message.media_type == MediaType.IMAGE
    assert events[0].message.media_url == "https://example.com/photo.jpg"
    assert events[0].message.text == ""


async def test_normalize_video_attachment() -> None:
    """A video attachment should map to MediaType.VIDEO."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.v1",
            "attachments": [
                {
                    "type": "video",
                    "payload": {
                        "url": "https://example.com/clip.mp4",
                    },
                }
            ],
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert events[0].message.media_type == MediaType.VIDEO
    assert events[0].message.media_url == "https://example.com/clip.mp4"


async def test_normalize_audio_attachment() -> None:
    """An audio attachment should map to MediaType.AUDIO."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.a1",
            "attachments": [
                {
                    "type": "audio",
                    "payload": {
                        "url": "https://example.com/voice.mp3",
                    },
                }
            ],
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert events[0].message.media_type == MediaType.AUDIO


async def test_normalize_file_attachment() -> None:
    """A file attachment should map to MediaType.FILE."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.f1",
            "attachments": [
                {
                    "type": "file",
                    "payload": {
                        "url": "https://example.com/doc.pdf",
                    },
                }
            ],
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert events[0].message.media_type == MediaType.FILE


async def test_normalize_unknown_attachment_type() -> None:
    """An unknown attachment type should leave media_type as None."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.u1",
            "attachments": [
                {
                    "type": "sticker",
                    "payload": {
                        "url": "https://example.com/sticker.png",
                    },
                }
            ],
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert events[0].message.media_type is None


# --- Filtering ---


async def test_skip_echo_messages() -> None:
    """Echo messages (sent by the page) should be filtered out."""
    event = {
        "sender": {"id": "PAGE_ID"},
        "recipient": {"id": "USER_1"},
        "timestamp": 1700000000000,
        "message": {
            "mid": "mid.echo1",
            "is_echo": True,
            "text": "Auto-reply",
        },
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert len(events) == 0


async def test_skip_event_without_sender() -> None:
    """Events missing sender.id should be skipped."""
    event = {
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "message": {"mid": "mid.no_sender", "text": "ghost"},
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert len(events) == 0


async def test_skip_event_without_message_or_postback() -> None:
    """Events with neither 'message' nor 'postback' should be skipped."""
    event = {
        "sender": {"id": "USER_1"},
        "recipient": {"id": "PAGE_ID"},
        "timestamp": 1700000000000,
        "delivery": {"mids": ["mid.123"]},
    }
    body = _make_webhook_payload([event])
    events = normalize_webhook_payload(body)

    assert len(events) == 0


# --- Non-page payloads ---


async def test_non_page_object_returns_empty() -> None:
    """Payloads with object != 'page' should return empty list."""
    body = {"object": "instagram", "entry": []}
    events = normalize_webhook_payload(body)

    assert events == []


# --- Multiple events ---


async def test_multiple_events_in_single_entry() -> None:
    """Multiple messaging events in one entry should all be normalized."""
    events_data = [
        _text_event("USER_1", "First"),
        _text_event("USER_2", "Second"),
        _text_event("USER_3", "Third"),
    ]
    body = _make_webhook_payload(events_data)
    events = normalize_webhook_payload(body)

    assert len(events) == 3
    assert events[0].user.id == "USER_1"
    assert events[1].user.id == "USER_2"
    assert events[2].user.id == "USER_3"


async def test_multiple_entries() -> None:
    """Multiple entries should all be processed."""
    body = {
        "object": "page",
        "entry": [
            {
                "id": "PAGE_1",
                "time": 1700000000000,
                "messaging": [_text_event("USER_A", "A")],
            },
            {
                "id": "PAGE_2",
                "time": 1700000001000,
                "messaging": [_text_event("USER_B", "B")],
            },
        ],
    }
    events = normalize_webhook_payload(body)

    assert len(events) == 2
    assert events[0].user.id == "USER_A"
    assert events[1].user.id == "USER_B"


async def test_empty_entry_list() -> None:
    """An empty entry list should return empty events."""
    body = {"object": "page", "entry": []}
    events = normalize_webhook_payload(body)

    assert events == []


async def test_entry_without_messaging() -> None:
    """An entry without messaging key should be handled gracefully."""
    body = {
        "object": "page",
        "entry": [{"id": "PAGE_ID", "time": 1700000000000}],
    }
    events = normalize_webhook_payload(body)

    assert events == []
