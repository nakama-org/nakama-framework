"""Nakama V3 Framework — Messenger Channel Package.

Provides the Messenger-specific components:
- MessengerClient: Sends messages via the Messenger Send API.
- MessengerProfile: Declarative profile config (Get Started, persistent menu).
- create_messenger_router: FastAPI router for Messenger webhooks.
- normalize_webhook_payload: Transforms Meta JSON into framework types.
- NativeQuickReply: Messenger-only quick reply requesting email/phone/location.
"""

from nakama_framework.channels.messenger.channel import MessengerChannel
from nakama_framework.channels.messenger.client import MessengerClient
from nakama_framework.channels.messenger.normalizer import (
    NormalizedEvent,
    normalize_webhook_payload,
)
from nakama_framework.channels.messenger.profile import (
    MenuItem,
    MenuItemType,
    MessengerProfile,
)
from nakama_framework.channels.messenger.types import NativeQuickReply
from nakama_framework.channels.messenger.webhook import create_webhook_router

__all__ = [
    "MessengerChannel",
    "MessengerClient",
    "MessengerProfile",
    "MenuItem",
    "MenuItemType",
    "NormalizedEvent",
    "normalize_webhook_payload",
    "create_webhook_router",
    "NativeQuickReply",
]
