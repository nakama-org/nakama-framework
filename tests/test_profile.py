"""Tests for Messenger Profile API — models and sync.

Tests the declarative profile configuration (MessengerProfile, MenuItem)
and the sync_profile() method on MessengerClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from nakama_framework.channels.messenger.client import MessengerClient
from nakama_framework.channels.messenger.profile import (
    MenuItem,
    MenuItemType,
    MessengerProfile,
)


# ─── Profile Model Tests ───────────────────────────────────────────


class TestMenuItem:
    """Tests for MenuItem model validation."""

    def test_postback_item_requires_payload(self) -> None:
        with pytest.raises(ValueError, match="payload"):
            MenuItem(title="Test", type=MenuItemType.POSTBACK)

    def test_web_url_item_requires_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            MenuItem(title="Test", type=MenuItemType.WEB_URL)

    def test_postback_item_valid(self) -> None:
        item = MenuItem(title="Order", payload="START_ORDER")
        assert item.type == MenuItemType.POSTBACK
        assert item.payload == "START_ORDER"

    def test_web_url_item_valid(self) -> None:
        item = MenuItem(
            title="Website", type=MenuItemType.WEB_URL, url="https://example.com"
        )
        assert item.type == MenuItemType.WEB_URL
        assert item.url == "https://example.com"

    def test_to_api_dict_postback(self) -> None:
        item = MenuItem(title="Order", payload="START_ORDER")
        result = item.to_api_dict()
        assert result == {
            "type": "postback",
            "title": "Order",
            "payload": "START_ORDER",
        }

    def test_to_api_dict_web_url(self) -> None:
        item = MenuItem(title="Site", type=MenuItemType.WEB_URL, url="https://x.com")
        result = item.to_api_dict()
        assert result == {
            "type": "web_url",
            "title": "Site",
            "url": "https://x.com",
        }


class TestMessengerProfile:
    """Tests for MessengerProfile model validation."""

    def test_menu_requires_get_started(self) -> None:
        with pytest.raises(ValueError, match="get_started_payload"):
            MessengerProfile(
                persistent_menu=[MenuItem(title="X", payload="Y")],
            )

    def test_get_started_only(self) -> None:
        profile = MessengerProfile(get_started_payload="GET_STARTED")
        payload = profile.to_api_payload()
        assert payload == {"get_started": {"payload": "GET_STARTED"}}

    def test_full_profile(self) -> None:
        profile = MessengerProfile(
            get_started_payload="GET_STARTED",
            persistent_menu=[
                MenuItem(title="Order", payload="ORDER"),
                MenuItem(title="Web", type=MenuItemType.WEB_URL, url="https://x.com"),
            ],
        )
        payload = profile.to_api_payload()

        assert "get_started" in payload
        assert payload["get_started"]["payload"] == "GET_STARTED"

        menu = payload["persistent_menu"]
        assert len(menu) == 1  # single locale entry
        assert menu[0]["locale"] == "default"
        assert menu[0]["composer_input_disabled"] is False

        actions = menu[0]["call_to_actions"]
        assert len(actions) == 2
        assert actions[0]["title"] == "Order"
        assert actions[0]["type"] == "postback"
        assert actions[1]["title"] == "Web"
        assert actions[1]["type"] == "web_url"

    def test_empty_profile(self) -> None:
        profile = MessengerProfile()
        payload = profile.to_api_payload()
        assert payload == {}


# ─── sync_profile() Tests ──────────────────────────────────────────


class TestSyncProfile:
    """Tests for MessengerClient.sync_profile()."""

    @pytest.fixture()
    def mock_client(self) -> MessengerClient:
        """Create a MessengerClient with a mocked httpx client."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(
            return_value=httpx.Response(200, json={"result": "success"})
        )
        return MessengerClient(
            page_access_token="test-token",
            http_client=mock_http,
        )

    @pytest.mark.asyncio()
    async def test_sync_profile_posts_to_profile_api(
        self, mock_client: MessengerClient
    ) -> None:
        profile = MessengerProfile(get_started_payload="GET_STARTED")
        await mock_client.sync_profile(profile)

        mock_http = mock_client._client
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args

        # Verify URL
        assert "me/messenger_profile" in call_args.args[0]

        # Verify payload
        json_payload = call_args.kwargs["json"]
        assert json_payload == {"get_started": {"payload": "GET_STARTED"}}

    @pytest.mark.asyncio()
    async def test_sync_profile_skips_empty_profile(
        self, mock_client: MessengerClient
    ) -> None:
        profile = MessengerProfile()
        await mock_client.sync_profile(profile)

        # Should NOT post anything
        mock_http = mock_client._client
        mock_http.post.assert_not_called()

    @pytest.mark.asyncio()
    async def test_sync_profile_sends_access_token(
        self, mock_client: MessengerClient
    ) -> None:
        profile = MessengerProfile(get_started_payload="START")
        await mock_client.sync_profile(profile)

        mock_http = mock_client._client
        call_args = mock_http.post.call_args
        assert call_args.kwargs["params"]["access_token"] == "test-token"

    @pytest.mark.asyncio()
    async def test_sync_profile_raises_on_api_error(
        self, mock_client: MessengerClient
    ) -> None:
        mock_http = mock_client._client
        error_response = httpx.Response(400, json={"error": {"message": "Bad request"}})
        error_response.request = httpx.Request("POST", "https://example.com")
        mock_http.post = AsyncMock(return_value=error_response)

        profile = MessengerProfile(get_started_payload="START")
        with pytest.raises(httpx.HTTPStatusError):
            await mock_client.sync_profile(profile)
