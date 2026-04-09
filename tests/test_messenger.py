"""Tests for MessengerClient — verifies correct API payload construction.

All tests mock httpx to avoid real API calls and assert the exact
JSON payloads sent to the Graph API Send endpoint.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from nakama_framework.channels.messenger.client import MessengerClient
from nakama_framework.core.types import Button, CarouselItem


# --- Fixtures ---


@pytest.fixture
def mock_response() -> MagicMock:
    """Create a mock httpx Response with status 200."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "recipient_id": "USER_123",
        "message_id": "mid.123",
    }
    return resp


@pytest.fixture
def mock_client(mock_response: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_response
    return client


@pytest.fixture
def messenger(mock_client: AsyncMock) -> MessengerClient:
    """Create a MessengerClient with a mocked HTTP client.

    The client always performs auto sender actions (mark_seen,
    typing_on, typing_off) before each send. Tests account for
    the 4 total API calls per message send.
    """
    return MessengerClient(
        page_access_token="FAKE_TOKEN",
        http_client=mock_client,
    )


# --- Helpers ---


def _get_message_call(mock_client: AsyncMock) -> MagicMock:
    """Extract the final (message-sending) API call from the list.

    _send_message makes 4 calls:
      0: mark_seen
      1: typing_on
      2: typing_off
      3: actual message (the one we usually want to assert)
    """
    return mock_client.post.call_args_list[-1]


# --- Tests ---


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_text_payload(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_text should POST the correct JSON to the Send API."""
    await messenger.send_text("USER_123", "Hello!")

    send_call = _get_message_call(mock_client)
    assert send_call.kwargs["json"] == {
        "recipient": {"id": "USER_123"},
        "messaging_type": "RESPONSE",
        "message": {"text": "Hello!"},
    }
    assert send_call.kwargs["params"] == {"access_token": "FAKE_TOKEN"}


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_text_uses_correct_api_url(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_text should call the correct Graph API URL."""
    await messenger.send_text("USER_123", "Hi")

    url = _get_message_call(mock_client).args[0]
    assert "graph.facebook.com" in url
    assert "/me/messages" in url


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_buttons_payload(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_buttons should build a Button Template payload."""
    buttons = [
        Button(title="Option A", payload="OPT_A"),
        Button(title="Option B", payload="OPT_B"),
    ]
    await messenger.send_buttons("USER_123", "Choose one:", buttons)

    payload = _get_message_call(mock_client).kwargs["json"]
    attachment = payload["message"]["attachment"]
    assert attachment["type"] == "template"
    assert attachment["payload"]["template_type"] == "button"
    assert attachment["payload"]["text"] == "Choose one:"
    assert len(attachment["payload"]["buttons"]) == 2
    assert attachment["payload"]["buttons"][0] == {
        "type": "postback",
        "title": "Option A",
        "payload": "OPT_A",
    }


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_buttons_max_three(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_buttons should truncate to 3 buttons (Messenger limit)."""
    buttons = [Button(title=f"Btn {i}", payload=f"P{i}") for i in range(5)]
    await messenger.send_buttons("USER_123", "Pick:", buttons)

    payload = _get_message_call(mock_client).kwargs["json"]
    fb_buttons = payload["message"]["attachment"]["payload"]["buttons"]
    assert len(fb_buttons) == 3


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_buttons_text_truncation(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_buttons should truncate text to 640 chars."""
    long_text = "A" * 700
    await messenger.send_buttons(
        "USER_123", long_text, [Button(title="OK", payload="OK")]
    )

    payload = _get_message_call(mock_client).kwargs["json"]
    text = payload["message"]["attachment"]["payload"]["text"]
    assert len(text) == 640


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_carousel_payload(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_carousel should build a Generic Template payload."""
    items = [
        CarouselItem(
            title="Product A",
            subtitle="Best product",
            image_url="https://example.com/a.jpg",
            buttons=[Button(title="Buy", payload="BUY_A")],
        ),
        CarouselItem(
            title="Product B",
            subtitle="Second best",
        ),
    ]
    await messenger.send_carousel("USER_123", items)

    payload = _get_message_call(mock_client).kwargs["json"]
    attachment = payload["message"]["attachment"]
    assert attachment["type"] == "template"
    assert attachment["payload"]["template_type"] == "generic"

    elements = attachment["payload"]["elements"]
    assert len(elements) == 2

    # First element has all fields
    assert elements[0]["title"] == "Product A"
    assert elements[0]["subtitle"] == "Best product"
    assert elements[0]["image_url"] == "https://example.com/a.jpg"
    assert len(elements[0]["buttons"]) == 1

    # Second element: no image, no buttons
    assert elements[1]["title"] == "Product B"
    assert "image_url" not in elements[1]
    assert "buttons" not in elements[1]


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_carousel_max_ten(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_carousel should truncate to 10 items (Messenger limit)."""
    items = [CarouselItem(title=f"Item {i}") for i in range(15)]
    await messenger.send_carousel("USER_123", items)

    payload = _get_message_call(mock_client).kwargs["json"]
    elements = payload["message"]["attachment"]["payload"]["elements"]
    assert len(elements) == 10


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_carousel_title_truncation(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_carousel should truncate titles to 80 chars."""
    items = [CarouselItem(title="X" * 100)]
    await messenger.send_carousel("USER_123", items)

    payload = _get_message_call(mock_client).kwargs["json"]
    title = payload["message"]["attachment"]["payload"]["elements"][0]["title"]
    assert len(title) == 80


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_quick_replies_payload(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_quick_replies should build quick reply chips."""
    buttons = [
        Button(title="Yes", payload="YES"),
        Button(title="No", payload="NO"),
    ]
    await messenger.send_quick_replies("USER_123", "Continue?", buttons)

    payload = _get_message_call(mock_client).kwargs["json"]
    assert payload["message"]["text"] == "Continue?"
    qr = payload["message"]["quick_replies"]
    assert len(qr) == 2
    assert qr[0] == {
        "content_type": "text",
        "title": "Yes",
        "payload": "YES",
    }


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_quick_replies_max_thirteen(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_quick_replies should truncate to 13 buttons."""
    buttons = [Button(title=f"Q{i}", payload=f"Q{i}") for i in range(20)]
    await messenger.send_quick_replies("USER_123", "Pick:", buttons)

    payload = _get_message_call(mock_client).kwargs["json"]
    assert len(payload["message"]["quick_replies"]) == 13


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_send_quick_replies_title_truncation(
    mock_sleep: AsyncMock,
    messenger: MessengerClient,
    mock_client: AsyncMock,
) -> None:
    """send_quick_replies should truncate titles to 20 chars."""
    buttons = [Button(title="A" * 30, payload="P")]
    await messenger.send_quick_replies("USER_123", "Pick:", buttons)

    payload = _get_message_call(mock_client).kwargs["json"]
    title = payload["message"]["quick_replies"][0]["title"]
    assert len(title) == 20


async def test_close_client(mock_client: AsyncMock) -> None:
    """close() should close the underlying httpx client."""
    messenger = MessengerClient("TOKEN", http_client=mock_client)
    await messenger.close()

    mock_client.aclose.assert_called_once()
    assert messenger._client is None


async def test_close_noop_when_no_client() -> None:
    """close() should be safe to call even if no client was created."""
    messenger = MessengerClient("TOKEN")
    # _client is None by default — should not raise
    await messenger.close()


async def test_api_error_raises(mock_client: AsyncMock) -> None:
    """Non-200 responses should raise httpx.HTTPStatusError."""
    error_resp = MagicMock(spec=httpx.Response)
    error_resp.status_code = 400
    error_resp.text = '{"error": "Invalid token"}'
    error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=error_resp
    )
    mock_client.post.return_value = error_resp

    messenger = MessengerClient(
        "BAD_TOKEN",
        http_client=mock_client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await messenger.send_text("USER_123", "Hello")


# --- Sender Action Tests ---


async def test_send_action_mark_seen(
    messenger: MessengerClient, mock_client: AsyncMock
) -> None:
    """send_action('mark_seen') should send the correct payload."""
    await messenger.send_action("USER_123", "mark_seen")

    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload == {
        "recipient": {"id": "USER_123"},
        "sender_action": "mark_seen",
    }


async def test_send_action_typing_on(
    messenger: MessengerClient, mock_client: AsyncMock
) -> None:
    """send_action('typing_on') should send the correct payload."""
    await messenger.send_action("USER_123", "typing_on")

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload == {
        "recipient": {"id": "USER_123"},
        "sender_action": "typing_on",
    }


async def test_send_action_typing_off(
    messenger: MessengerClient, mock_client: AsyncMock
) -> None:
    """send_action('typing_off') should send the correct payload."""
    await messenger.send_action("USER_123", "typing_off")

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload == {
        "recipient": {"id": "USER_123"},
        "sender_action": "typing_off",
    }


# --- Auto Sender Actions Tests ---


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_auto_actions_before_send_text(
    mock_sleep: AsyncMock,
) -> None:
    """send_text should auto-fire mark_seen, typing_on, typing_off before the message."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"recipient_id": "USER_123", "message_id": "mid.1"}
    mock_client.post.return_value = mock_resp

    client = MessengerClient(
        "TOKEN",
        http_client=mock_client,
    )
    await client.send_text("USER_123", "Hello!")

    # 4 HTTP calls: mark_seen, typing_on, typing_off, message
    assert mock_client.post.call_count == 4

    calls = mock_client.post.call_args_list

    # Call 0: mark_seen
    assert calls[0].kwargs["json"]["sender_action"] == "mark_seen"
    # Call 1: typing_on
    assert calls[1].kwargs["json"]["sender_action"] == "typing_on"
    # Call 2: typing_off
    assert calls[2].kwargs["json"]["sender_action"] == "typing_off"
    # Call 3: the actual message
    assert calls[3].kwargs["json"]["message"] == {"text": "Hello!"}

    # Sleep was called with default typing_delay (0.2)
    mock_sleep.assert_awaited_once_with(0.2)


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_auto_actions_before_send_buttons(
    mock_sleep: AsyncMock,
) -> None:
    """Auto actions should also fire before send_buttons."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"recipient_id": "USER_123", "message_id": "mid.1"}
    mock_client.post.return_value = mock_resp

    client = MessengerClient(
        "TOKEN",
        http_client=mock_client,
    )
    buttons = [Button(title="OK", payload="OK")]
    await client.send_buttons("USER_123", "Pick:", buttons)

    # 4 HTTP calls: mark_seen, typing_on, typing_off, message
    assert mock_client.post.call_count == 4

    calls = mock_client.post.call_args_list
    # First 3 are sender actions
    assert calls[0].kwargs["json"]["sender_action"] == "mark_seen"
    assert calls[1].kwargs["json"]["sender_action"] == "typing_on"
    assert calls[2].kwargs["json"]["sender_action"] == "typing_off"
    # Last call is the actual message
    assert "message" in calls[3].kwargs["json"]


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_auto_actions_custom_delay(
    mock_sleep: AsyncMock,
) -> None:
    """typing_delay should be configurable."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"recipient_id": "USER_123", "message_id": "mid.1"}
    mock_client.post.return_value = mock_resp

    client = MessengerClient(
        "TOKEN",
        http_client=mock_client,
        typing_delay=1.0,
    )
    await client.send_text("USER_123", "Hello!")

    mock_sleep.assert_awaited_once_with(1.0)


@patch(
    "nakama_framework.channels.messenger.client.asyncio.sleep",
    new_callable=AsyncMock,
)
async def test_auto_actions_correct_recipient(
    mock_sleep: AsyncMock,
) -> None:
    """All sender action calls should target the correct recipient."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"recipient_id": "USER_456", "message_id": "mid.1"}
    mock_client.post.return_value = mock_resp

    client = MessengerClient(
        "TOKEN",
        http_client=mock_client,
    )
    await client.send_text("USER_456", "Hi!")

    for c in mock_client.post.call_args_list:
        assert c.kwargs["json"]["recipient"]["id"] == "USER_456"
