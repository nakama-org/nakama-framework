"""Nakama V3 Framework — Messenger Channel Client.

Implements the Sender protocol for Facebook Messenger using the
Graph API Send API. Handles sending text messages, button
templates, generic template carousels, and quick replies.

Reference:
    https://developers.facebook.com/docs/messenger-platform/reference/send-api/
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from nakama_framework.channels.messenger.profile import MessengerProfile
from nakama_framework.channels.messenger.types import NativeQuickReply

from nakama_framework.core.types import Button, CarouselItem
from nakama_framework.logging import get_logger

logger = get_logger("messenger")

API_VERSION = "v25.0"
GRAPH_API_URL = "https://graph.facebook.com"
SEND_API_URL = f"{GRAPH_API_URL}/{API_VERSION}/me/messages"
PROFILE_API_URL = f"{GRAPH_API_URL}/{API_VERSION}/me/messenger_profile"
BATCH_API_URL = f"{GRAPH_API_URL}/{API_VERSION}/"


class MessengerClient:
    """Sends messages to Facebook Messenger via the Send API.

    Implements the Sender protocol expected by Context.
    Uses httpx for async HTTP requests.

    Attributes:
        page_access_token: The Facebook Page Access Token.
    """

    def __init__(
        self,
        page_access_token: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        typing_delay: float = 0.2,
    ) -> None:
        """Initialize the Messenger client.

        Args:
            page_access_token: Facebook Page Access Token for API auth.
            api_version: Graph API version (default: v24.0).
            http_client: Optional pre-configured httpx client (for testing).
            typing_delay: Seconds to wait between typing_on and the
                actual message (default: 0.2).
        """
        self.page_access_token = page_access_token
        self._api_url = SEND_API_URL
        self._profile_url = PROFILE_API_URL
        self._batch_url = BATCH_API_URL
        self._client = http_client
        self.typing_delay = typing_delay

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _send_batch(self, requests: list[dict[str, Any]]) -> list[Any]:
        """Send multiple requests via the Facebook Batch API.

        Args:
            requests: List of batch request objects, each with
                ``method``, ``relative_url``, and optional ``body``.

        Returns:
            The parsed batch response (list of response objects).

        Raises:
            httpx.HTTPStatusError: If the batch HTTP call fails.
        """
        client = await self._get_client()
        response = await client.post(
            self._batch_url,
            params={"access_token": self.page_access_token},
            data={
                "batch": json.dumps(requests),
                "include_headers": "false",
            },
        )

        if response.status_code != 200:
            logger.error(
                "Batch API error %d: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        data = response.json()
        logger.debug("Batch response: %s", data)
        return data

    async def _send_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Raw POST to the Messenger Send API. No auto actions.

        Args:
            payload: The full request body to send.

        Returns:
            The API response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        client = await self._get_client()
        response = await client.post(
            self._api_url,
            params={"access_token": self.page_access_token},
            json=payload,
        )

        if response.status_code != 200:
            logger.error(
                "Messenger API error %d: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        data = response.json()
        logger.debug(
            "Message sent: recipient=%s, message_id=%s",
            data.get("recipient_id"),
            data.get("message_id"),
        )
        return data

    async def _send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a message with auto sender actions (mark_seen, typing).

        Args:
            payload: The full request body to send.

        Returns:
            The API response as a dict.
        """
        user_id = payload["recipient"]["id"]

        await self.send_action(user_id, "mark_seen")
        await self.send_action(user_id, "typing_on")
        await asyncio.sleep(self.typing_delay)
        await self.send_action(user_id, "typing_off")
        data = await self._send_raw(payload)

        return data

    # --- Sender Actions ---

    async def send_action(self, user_id: str, action: str) -> dict[str, Any]:
        """Send a sender action (mark_seen, typing_on, typing_off).

        Uses ``_send_raw`` directly — no auto actions, no recursion.

        Args:
            user_id: The recipient's PSID.
            action: One of ``mark_seen``, ``typing_on``, ``typing_off``.

        Returns:
            The API response as a dict.
        """
        return await self._send_raw(
            {
                "recipient": {"id": user_id},
                "sender_action": action,
            }
        )

    async def react(self, user_id: str, message_id: str, emoji: str) -> dict[str, Any]:
        """React to a user's message with an emoji.

        Args:
            user_id: The recipient's PSID.
            message_id: The ID of the message to react to.
            emoji: The emoji character (e.g. "👍", "❤️").

        Returns:
            The API response as a dict.
        """
        return await self._send_raw(
            {
                "recipient": {"id": user_id},
                "sender_action": "react",
                "payload": {
                    "message_id": message_id,
                    "reaction": emoji,
                },
            }
        )

    async def unreact(self, user_id: str, message_id: str) -> dict[str, Any]:
        """Remove a reaction from a user's message.

        Args:
            user_id: The recipient's PSID.
            message_id: The ID of the message to unreact to.

        Returns:
            The API response as a dict.
        """
        return await self._send_raw(
            {
                "recipient": {"id": user_id},
                "sender_action": "unreact",
                "payload": {
                    "message_id": message_id,
                },
            }
        )

    # --- Sender Protocol Implementation ---

    async def send_text(self, user_id: str, text: str) -> None:
        """Send a plain text message.

        Args:
            user_id: The recipient's PSID.
            text: The text content (max 2000 chars).
        """
        await self._send_message(
            {
                "recipient": {"id": user_id},
                "messaging_type": "RESPONSE",
                "message": {"text": text},
            }
        )

    async def send_image(self, user_id: str, source: str) -> None:
        """Send a standalone image, by URL or from a local file path.

        Args:
            user_id: The recipient's PSID.
            source: Either an HTTPS URL or a path to a local file.
        """
        if source.startswith(("http://", "https://")):
            await self._send_message(
                {
                    "recipient": {"id": user_id},
                    "messaging_type": "RESPONSE",
                    "message": {
                        "attachment": {
                            "type": "image",
                            "payload": {
                                "url": source,
                                "is_reusable": True,
                            },
                        }
                    },
                }
            )
            return

        # Local file — upload via multipart/form-data
        path = Path(source)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        file_bytes = path.read_bytes()

        await self.send_action(user_id, "mark_seen")
        await self.send_action(user_id, "typing_on")
        await asyncio.sleep(self.typing_delay)
        await self.send_action(user_id, "typing_off")

        client = await self._get_client()
        response = await client.post(
            self._api_url,
            params={"access_token": self.page_access_token},
            data={
                "recipient": json.dumps({"id": user_id}),
                "message": json.dumps(
                    {
                        "attachment": {
                            "type": "image",
                            "payload": {"is_reusable": True},
                        }
                    }
                ),
            },
            files={"filedata": (path.name, file_bytes, mime_type)},
        )

        if response.status_code != 200:
            logger.error(
                "Messenger API error %d on image upload: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        logger.debug("Image sent: recipient=%s, file=%s", user_id, path.name)

    async def send_file(
        self,
        user_id: str,
        data: bytes,
        filename: str,
        mime_type: str | None = None,
    ) -> None:
        """Send a file attachment from in-memory bytes.

        Uses Messenger's multipart upload with ``attachment.type = "file"``
        so the recipient sees a native download card in the conversation.
        """
        mime = mime_type or (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )

        await self.send_action(user_id, "mark_seen")
        await self.send_action(user_id, "typing_on")
        await asyncio.sleep(self.typing_delay)
        await self.send_action(user_id, "typing_off")

        client = await self._get_client()
        response = await client.post(
            self._api_url,
            params={"access_token": self.page_access_token},
            data={
                "recipient": json.dumps({"id": user_id}),
                "message": json.dumps(
                    {
                        "attachment": {
                            "type": "file",
                            "payload": {"is_reusable": False},
                        }
                    }
                ),
            },
            files={"filedata": (filename, data, mime)},
        )

        if response.status_code != 200:
            logger.error(
                "Messenger API error %d on file upload: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        logger.debug("File sent: recipient=%s, filename=%s", user_id, filename)

    async def send_buttons(
        self, user_id: str, text: str, buttons: list[Button]
    ) -> None:
        """Send a message with postback buttons (Button Template).

        Uses the Button Template which supports 1-3 buttons
        and up to 640 characters of text above them.

        Args:
            user_id: The recipient's PSID.
            text: Text displayed above the buttons (max 640 chars).
            buttons: List of buttons (max 3).
        """
        fb_buttons = [
            {
                "type": "postback",
                "title": btn.title,
                "payload": btn.payload,
            }
            for btn in buttons[:3]  # Messenger limit: max 3 buttons
        ]

        await self._send_message(
            {
                "recipient": {"id": user_id},
                "messaging_type": "RESPONSE",
                "message": {
                    "attachment": {
                        "type": "template",
                        "payload": {
                            "template_type": "button",
                            "text": text[:640],
                            "buttons": fb_buttons,
                        },
                    }
                },
            }
        )

    async def send_carousel(self, user_id: str, items: list[CarouselItem]) -> None:
        """Send a carousel of cards (Generic Template).

        Uses the Generic Template which supports up to 10 elements,
        each with title, subtitle, image, and up to 3 buttons.

        Args:
            user_id: The recipient's PSID.
            items: List of carousel items (max 10).
        """
        elements = []
        for item in items[:10]:  # Messenger limit: max 10 elements
            element: dict[str, Any] = {
                "title": item.title[:80],  # Messenger limit: 80 chars
            }
            if item.subtitle:
                element["subtitle"] = item.subtitle[:80]
            if item.image_url:
                element["image_url"] = item.image_url
            if item.buttons:
                element["buttons"] = [
                    {
                        "type": "postback",
                        "title": btn.title,
                        "payload": btn.payload,
                    }
                    for btn in item.buttons[:3]
                ]
            elements.append(element)

        await self._send_message(
            {
                "recipient": {"id": user_id},
                "messaging_type": "RESPONSE",
                "message": {
                    "attachment": {
                        "type": "template",
                        "payload": {
                            "template_type": "generic",
                            "elements": elements,
                        },
                    }
                },
            }
        )

    async def send_quick_replies(
        self, user_id: str, text: str, buttons: list[Button | NativeQuickReply]
    ) -> None:
        """Send a message with quick reply chips.

        Supports both generic ``Button`` (converted to ``content_type: text``)
        and Messenger-native ``NativeQuickReply`` (e.g. email, phone) which
        have no title or payload.

        Args:
            user_id: The recipient's PSID.
            text: The message text.
            buttons: List of quick reply buttons (max 13). May mix ``Button``
                and ``NativeQuickReply`` instances.
        """
        quick_replies = []
        for btn in buttons[:13]:  # Messenger limit: max 13
            if isinstance(btn, NativeQuickReply):
                # Native quick replies only carry content_type — no title/payload.
                quick_replies.append({"content_type": btn.content_type})
            else:
                qr: dict[str, Any] = {
                    "content_type": "text",
                    "title": btn.title[:20],  # Messenger limit: 20 chars
                    "payload": btn.payload,
                }
                if btn.image_url:
                    qr["image_url"] = btn.image_url
                quick_replies.append(qr)

        await self._send_message(
            {
                "recipient": {"id": user_id},
                "messaging_type": "RESPONSE",
                "message": {
                    "text": text,
                    "quick_replies": quick_replies,
                },
            }
        )

    # --- Profile API ---

    async def sync_profile(self, profile: MessengerProfile) -> None:
        """Sync the Messenger Profile (Get Started, Persistent Menu).

        Posts the profile configuration to the Messenger Profile API.
        Should be called once on startup.

        Args:
            profile: The declarative profile configuration.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        payload = profile.to_api_payload()
        if not payload:
            logger.debug("No profile properties to sync")
            return

        client = await self._get_client()
        response = await client.post(
            self._profile_url,
            params={"access_token": self.page_access_token},
            json=payload,
        )

        if response.status_code != 200:
            logger.error(
                "Profile API error %d: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        logger.info(
            "Messenger profile synced: %s",
            list(payload.keys()),
        )

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """Fetch Messenger user profile (first_name, last_name, profile_pic)."""
        client = await self._get_client()
        response = await client.get(
            f"{GRAPH_API_URL}/{user_id}",
            params={
                "fields": "first_name,last_name,profile_pic",
                "access_token": self.page_access_token,
            },
        )
        if response.status_code != 200:
            logger.error("Failed to fetch user profile: %s", response.text)
            return {}
        return response.json()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
