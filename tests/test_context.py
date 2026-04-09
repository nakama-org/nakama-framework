"""Tests for nakama_framework.core.context — Context object."""

import pytest

from nakama_framework.core.context import Context, StubSender
from nakama_framework.core.types import (
    Button,
    CarouselItem,
    Channel,
    Message,
    Session,
    User,
)


# --- Helpers ---


class RecordingSender:
    """Test sender that records all sent messages."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_text(self, user_id: str, text: str) -> None:
        self.messages.append({"type": "text", "user_id": user_id, "text": text})

    async def send_buttons(
        self, user_id: str, text: str, buttons: list[Button]
    ) -> None:
        self.messages.append(
            {
                "type": "buttons",
                "user_id": user_id,
                "text": text,
                "buttons": buttons,
            }
        )

    async def send_carousel(self, user_id: str, items: list[CarouselItem]) -> None:
        self.messages.append(
            {
                "type": "carousel",
                "user_id": user_id,
                "items": items,
            }
        )


def make_ctx(
    text: str = "",
    payload: str | None = None,
    sender: RecordingSender | None = None,
    user_name: str = "TestUser",
) -> tuple[Context, RecordingSender]:
    """Create a Context with a RecordingSender for testing."""
    s = sender or RecordingSender()
    user = User(id="user_123", name=user_name, channel=Channel.MESSENGER)
    session = Session(user_id="user_123")
    message = Message(text=text, payload=payload)
    ctx = Context(user=user, session=session, message=message, sender=s)
    return ctx, s


# --- Tests ---


class TestContextReply:
    """Tests for ctx.reply()."""

    async def test_reply_sends_text(self) -> None:
        ctx, sender = make_ctx()
        await ctx.reply("Hello!")

        assert len(sender.messages) == 1
        assert sender.messages[0]["type"] == "text"
        assert sender.messages[0]["text"] == "Hello!"
        assert sender.messages[0]["user_id"] == "user_123"

    async def test_reply_multiple(self) -> None:
        ctx, sender = make_ctx()
        await ctx.reply("First")
        await ctx.reply("Second")

        assert len(sender.messages) == 2
        assert sender.messages[0]["text"] == "First"
        assert sender.messages[1]["text"] == "Second"


class TestContextAsk:
    """Tests for ctx.ask()."""

    async def test_ask_sets_current_query(self) -> None:
        ctx, sender = make_ctx()
        await ctx.ask("What size?", next_action="handle_size")

        assert ctx.session.state is not None and ctx.session.state.name == "handle_size"

    async def test_ask_sends_text(self) -> None:
        ctx, sender = make_ctx()
        await ctx.ask("What size?", next_action="handle_size")

        assert len(sender.messages) == 1
        assert sender.messages[0]["text"] == "What size?"

    async def test_ask_passes_payload(self) -> None:
        ctx, sender = make_ctx()
        await ctx.ask(
            "What size?",
            next_action="handle_size",
            category="shoes",
            brand="nike",
        )

        assert ctx.session.state is not None and ctx.session.state.data == {
            "category": "shoes",
            "brand": "nike",
        }
        assert ctx.state_data == {"category": "shoes", "brand": "nike"}


class TestContextSendButtons:
    """Tests for ctx.send_buttons()."""

    async def test_send_buttons(self) -> None:
        ctx, sender = make_ctx()
        buttons = [
            Button(title="Yes", payload="YES"),
            Button(title="No", payload="NO"),
        ]
        await ctx.send_buttons("Confirm?", buttons)

        assert len(sender.messages) == 1
        assert sender.messages[0]["type"] == "buttons"
        assert sender.messages[0]["text"] == "Confirm?"
        assert len(sender.messages[0]["buttons"]) == 2


class TestContextSendCarousel:
    """Tests for ctx.send_carousel()."""

    async def test_send_carousel(self) -> None:
        ctx, sender = make_ctx()
        items = [
            CarouselItem(
                title="Nike Air",
                subtitle="Great shoes",
                buttons=[Button(title="Buy", payload="BUY_1")],
            ),
        ]
        await ctx.send_carousel(items)

        assert len(sender.messages) == 1
        assert sender.messages[0]["type"] == "carousel"
        assert len(sender.messages[0]["items"]) == 1


class TestContextDefaults:
    """Tests for default sender behavior."""

    async def test_default_sender_is_stub(self) -> None:
        user = User(id="u1", channel=Channel.MESSENGER)
        session = Session(user_id="u1")
        message = Message(text="hi")
        ctx = Context(user=user, session=session, message=message)

        assert isinstance(ctx.sender, StubSender)
        # Should not raise
        await ctx.reply("test")
