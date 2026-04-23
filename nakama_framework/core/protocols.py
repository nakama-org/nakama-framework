"""Nakama V3 Framework — Channel adapter protocol.

Defines the contract that every channel adapter must satisfy
to be registered with NakamaApp.register_channel().

Channel adapters (Messenger, WhatsApp, Telegram, etc.) implement
this protocol to provide message sending, webhook routing, and
lifecycle management.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter

from nakama_framework.core.types import Button, CarouselItem


@runtime_checkable
class Sender(Protocol):
    """Protocol for channel-specific message sending.

    Channel adapters implement this protocol to provide
    actual message delivery (Messenger, WhatsApp, etc.).
    """

    async def send_text(self, user_id: str, text: str) -> None:
        """Send a plain text message to a user."""
        ...

    async def send_image(self, user_id: str, source: str) -> None:
        """Send a standalone image (URL or local file path)."""
        ...

    async def send_file(
        self, user_id: str, data: bytes, filename: str, mime_type: str | None = None
    ) -> None:
        """Send a file attachment (PDF, docx, etc.) from in-memory bytes."""
        ...

    async def send_buttons(
        self, user_id: str, text: str, buttons: list[Button]
    ) -> None:
        """Send a message with interactive buttons."""
        ...

    async def send_carousel(self, user_id: str, items: list[CarouselItem]) -> None:
        """Send a carousel of cards to a user."""
        ...

    async def send_quick_replies(
        self, user_id: str, text: str, buttons: list[Button]
    ) -> None:
        """Send a message with quick reply buttons."""
        ...

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """Fetch user profile information from the channel.

        Returns a dictionary containing profile data (e.g. first_name, last_name, profile_pic)
        which varies depending on the channel constraints.
        """
        ...


@runtime_checkable
class ChannelAdapter(Protocol):
    """Contract for channel adapter implementations.

    Every channel must provide:
    - ``client``: A Sender for outgoing messages.
    - ``on_startup()``: Initialization tasks (e.g. profile sync).
    - ``create_router(app)``: Webhook endpoint registration.
    - ``close()``: Cleanup resources (HTTP clients, etc.).

    Example::

        class MessengerChannel:
            def __init__(self, ...):
                self.client = MessengerClient(...)

            async def on_startup(self) -> None:
                await self.client.sync_profile(self.profile)

            def create_router(self, app) -> APIRouter:
                return create_webhook_router(app, ...)

            async def close(self) -> None:
                await self.client.close()
    """

    client: Sender

    async def on_startup(self) -> None: ...
    def create_router(self, app: Any) -> APIRouter: ...
    async def close(self) -> None: ...
