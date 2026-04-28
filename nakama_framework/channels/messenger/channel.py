"""Nakama V3 Framework — Messenger Channel Adapter.

Bundles all Messenger-specific configuration (credentials, profile)
into a single object so that NakamaApp stays channel-agnostic.

Usage::

    from nakama_framework.channels.messenger import MessengerChannel

    channel = MessengerChannel(
        page_access_token="EAA...",
        verify_token="my-verify-token",
        app_secret="abc123",
        profile=MessengerProfile(
            get_started_payload="GET_STARTED",
            persistent_menu=[...],
        ),
    )

    app = NakamaApp()
    app.register_channel(channel)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from nakama_framework.channels.messenger.client import MessengerClient
from nakama_framework.channels.messenger.profile import MessengerProfile
from nakama_framework.logging import get_logger

logger = get_logger("messenger.channel")


class MessengerChannel:
    """Messenger channel adapter.

    Encapsulates the Messenger client, webhook credentials, and
    profile configuration. Passed to ``NakamaApp.register_channel()``
    to wire everything up.

    Attributes:
        client: The MessengerClient used to send messages.
        verify_token: Token for Meta webhook verification handshake.
        app_secret: Facebook App Secret for signature verification.
        profile: Optional declarative Messenger profile config.
    """

    def __init__(
        self,
        page_access_token: str,
        verify_token: str = "",
        app_secret: str | None = None,
        profile: MessengerProfile | None = None,
        typing_indicator: bool = True,
    ) -> None:
        """Initialize the Messenger channel.

        Args:
            page_access_token: Facebook Page Access Token for API auth.
            verify_token: Webhook verification token (required for
                Meta webhook subscription).
            app_secret: Facebook App Secret for signature verification.
                If None, signature check is skipped (dev mode only).
            profile: Optional Messenger profile config (Get Started,
                persistent menu). Synced on startup if provided.
            typing_indicator: Whether to show the ``…typing`` bubble and
                ``mark_seen`` before replies. Set to False to skip the
                short delay (default: True).
        """
        self.client = MessengerClient(
            page_access_token, typing_indicator=typing_indicator
        )
        self.verify_token = verify_token
        self.app_secret = app_secret
        self.profile = profile

    async def on_startup(self) -> None:
        """Run channel-specific startup tasks.

        Called by NakamaApp.on_startup() after database init.
        Syncs the Messenger profile if configured.
        """
        if self.profile is not None:
            try:
                await self.client.sync_profile(self.profile)
            except Exception:
                logger.exception("Failed to sync Messenger profile")

    def create_router(self, app: Any) -> APIRouter:
        """Create the FastAPI webhook router for this channel.

        Args:
            app: The NakamaApp instance (used for message processing).

        Returns:
            A FastAPI APIRouter with GET/POST /webhook endpoints.
        """
        from nakama_framework.channels.messenger.webhook import create_webhook_router

        if not self.verify_token:
            logger.warning("No verify_token set — webhook verification will fail.")

        return create_webhook_router(
            app=app,
            verify_token=self.verify_token,
            app_secret=self.app_secret,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.close()
