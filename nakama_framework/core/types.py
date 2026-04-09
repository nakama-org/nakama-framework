"""Nakama V3 Framework — Core type definitions.

Canonical data models that flow through the entire framework.
These types are channel-agnostic and represent the normalized
form of messages, users, and conversational state.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Channel(str, Enum):
    """Supported messaging channels."""

    MESSENGER = "messenger"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class MediaType(str, Enum):
    """Types of media attachments."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    LOCATION = "location"


class User(BaseModel):
    """Represents the message sender.

    Attributes:
        id: Unique user identifier (channel-specific).
        name: Display name (may be empty if unavailable).
        channel: The channel the user is communicating from.
    """

    id: str
    name: str = ""
    channel: Channel


class Message(BaseModel):
    """Normalized representation of an incoming message.

    The framework normalizes raw channel-specific payloads into
    this canonical form before routing.

    Attributes:
        text: Text content of the message (empty string if media-only).
        payload: Postback/QuickReply payload ID (None if not a button click).
        media_type: Type of media attachment (None if text-only).
        media_url: URL of the media attachment (None if text-only).
        raw: Original channel-specific payload for escape-hatch access.
    """

    id: str | None = None
    text: str = ""
    payload: str | None = None
    media_type: MediaType | None = None
    media_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class State(BaseModel):
    """Represents a conversational state.

    Used to track which part of a flow the user is in and
    keep track of data specific to that flow.
    """

    name: str
    data: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """Conversational state for a user.

    Tracks the current conversation flow, pending states,
    and arbitrary key-value data across message exchanges.

    Attributes:
        user_id: The user this session belongs to.
        data: Arbitrary session storage (cart, preferences, etc.).
        state: The current state handler awaiting a response.
            None when no question is pending.
    """

    user_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    state: State | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from session data."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in session data."""
        self.data[key] = value

    def clear(self) -> None:
        """Clear all session data and pending states."""
        self.data.clear()
        self.state = None

    def clear_state(self) -> None:
        """Clear the pending state without touching session data."""
        self.state = None


class Button(BaseModel):
    """Interactive button sent to the user.

    This is a channel-agnostic type. Each channel adapter maps it
    to its own wire format (postback, reply button, inline button, etc.).

    Attributes:
        title: Display text on the button.
        payload: Hidden payload ID sent back when clicked.
        image_url: URL of an image to display on the button (optional).
    """

    title: str
    payload: str
    image_url: str | None = None


class CarouselItem(BaseModel):
    """A single item in a carousel/card display.

    Attributes:
        title: Item title.
        subtitle: Item description.
        image_url: URL of the item image (optional).
        buttons: Action buttons attached to this item.
    """

    title: str
    subtitle: str = ""
    image_url: str | None = None
    buttons: list[Button] = Field(default_factory=list)
