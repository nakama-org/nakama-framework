"""Tests for nakama_framework.core.dispatcher — 5-level routing engine."""

import pytest

from nakama_framework.core.context import Context
from nakama_framework.core.dispatcher import Dispatcher, DispatchResult
from nakama_framework.core.module import Module
from nakama_framework.core.types import (
    Channel,
    MediaType,
    Message,
    Session,
    User,
    State,
)


# --- Helpers ---


class RecordingSender:
    """Test sender that records messages."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_text(self, user_id: str, text: str) -> None:
        self.messages.append({"type": "text", "user_id": user_id, "text": text})

    async def send_buttons(self, user_id: str, text: str, buttons: list) -> None:
        self.messages.append({"type": "buttons"})

    async def send_carousel(self, user_id: str, items: list) -> None:
        self.messages.append({"type": "carousel"})


def make_ctx(
    text: str = "",
    payload: str | None = None,
    media_type: MediaType | None = None,
    current_query: str | None = None,
    sender: RecordingSender | None = None,
) -> Context:
    """Create a Context for testing dispatch."""
    s = sender or RecordingSender()
    user = User(id="user_1", name="Test", channel=Channel.MESSENGER)
    state = State(name=current_query) if current_query else None
    session = Session(user_id="user_1", state=state)
    message = Message(text=text, payload=payload, media_type=media_type)
    return Context(user=user, session=session, message=message, sender=s)


# --- Tests ---


class TestLevel1Payload:
    """Level 1: Payload dispatch (button clicks)."""

    async def test_payload_matches(self) -> None:
        m = Module("test")
        called_with: list[str] = []

        @m.on_payload("BUY")
        async def buy(ctx: Context) -> None:
            called_with.append("buy")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(payload="BUY")
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 1
        assert called_with == ["buy"]

    async def test_payload_not_registered(self) -> None:
        d = Dispatcher()
        ctx = make_ctx(payload="UNKNOWN")
        result = await d.dispatch(ctx)

        assert result.matched is False


class TestLevel1bPrefix:
    """Level 1b: Prefix Payload dispatch."""

    async def test_prefix_matches(self) -> None:
        m = Module("test")
        called_with: list[str] = []

        @m.on_payload_prefix("NAV_")
        async def nav(ctx: Context) -> None:
            called_with.append("nav")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(payload="NAV_CATALOG:2")
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 1
        assert called_with == ["nav"]

    async def test_prefix_not_registered(self) -> None:
        d = Dispatcher()
        ctx = make_ctx(payload="ORDER_123")
        result = await d.dispatch(ctx)

        assert result.matched is False

    async def test_exact_payload_overrides_prefix(self) -> None:
        """Level 1a (exact payload) beats Level 1b (prefix)."""
        m = Module("test")
        called: list[str] = []

        @m.on_payload("NAV_0")
        async def exact_handler(ctx: Context) -> None:
            called.append("exact")

        @m.on_payload_prefix("NAV_")
        async def prefix_handler(ctx: Context) -> None:
            called.append("prefix")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(payload="NAV_0")
        result = await d.dispatch(ctx)

        assert result.level == 1
        assert called == ["exact"]


class TestLevel2State:
    """Level 2: State/Query dispatch."""

    async def test_state_matches(self) -> None:
        m = Module("test")
        called_with: list[str] = []

        @m.on_state("handle_size")
        async def handle_size(ctx: Context) -> None:
            called_with.append("size")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="42", current_query="handle_size")
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 2
        assert called_with == ["size"]

    async def test_state_clears_query_after_dispatch(self) -> None:
        """After handling a state, current_query should be cleared."""
        m = Module("test")

        @m.on_state("step1")
        async def step1(ctx: Context) -> None:
            pass

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="answer", current_query="step1")
        await d.dispatch(ctx)

        assert ctx.session.state is None

    async def test_state_handler_can_set_new_query(self) -> None:
        """A state handler can chain to a new question via ctx.ask."""
        m = Module("test")

        @m.on_state("step1")
        async def step1(ctx: Context) -> None:
            await ctx.ask("Next question?", next_action="step2")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="answer", current_query="step1")
        await d.dispatch(ctx)

        # The handler set a NEW query
        assert ctx.session.state is not None and ctx.session.state.name == "step2"


class TestLevel3Command:
    """Level 3: Command dispatch (/slash)."""

    async def test_command_matches(self) -> None:
        m = Module("test")
        called_with: list[str] = []

        @m.on_command("ping")
        async def ping(ctx: Context) -> None:
            called_with.append("ping")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="/ping")
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 3
        assert called_with == ["ping"]

    async def test_command_case_insensitive(self) -> None:
        m = Module("test")
        called = []

        @m.on_command("ping")
        async def ping(ctx: Context) -> None:
            called.append(True)

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="/PING")
        result = await d.dispatch(ctx)

        assert result.matched is True

    async def test_command_with_args(self) -> None:
        """Commands with trailing text should still match."""
        m = Module("test")
        called = []

        @m.on_command("reset")
        async def reset(ctx: Context) -> None:
            called.append(True)

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="/reset all")
        result = await d.dispatch(ctx)

        assert result.matched is True


class TestLevel4Media:
    """Level 4: Media dispatch."""

    async def test_media_matches(self) -> None:
        m = Module("test")
        called = []

        @m.on_media(MediaType.IMAGE)
        async def handle_image(ctx: Context) -> None:
            called.append("image")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(media_type=MediaType.IMAGE)
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 4
        assert called == ["image"]


class TestLevel5Text:
    """Level 5: Text/NLU dispatch (regex)."""

    async def test_text_matches(self) -> None:
        m = Module("test")
        captured: list[str] = []

        @m.on_text(r"^i want (.*)")
        async def want(ctx: Context, item: str) -> None:
            captured.append(item)

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="i want pizza")
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 5
        assert captured == ["pizza"]

    async def test_text_case_insensitive(self) -> None:
        m = Module("test")
        called = []

        @m.on_text(r"^hello")
        async def hello(ctx: Context) -> None:
            called.append(True)

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="HELLO world")
        result = await d.dispatch(ctx)

        assert result.matched is True

    async def test_text_first_match_wins(self) -> None:
        """When multiple text routes match, the first registered wins."""
        m = Module("test")
        order: list[str] = []

        @m.on_text(r"hello")
        async def first(ctx: Context) -> None:
            order.append("first")

        @m.on_text(r"hello world")
        async def second(ctx: Context) -> None:
            order.append("second")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="hello world")
        await d.dispatch(ctx)

        assert order == ["first"]


class TestPriorityOrder:
    """Ensure higher priority levels always override lower ones."""

    async def test_payload_overrides_state(self) -> None:
        """Level 1 (payload) beats Level 2 (state)."""
        m = Module("test")
        called: list[str] = []

        @m.on_payload("ACTION")
        async def payload_handler(ctx: Context) -> None:
            called.append("payload")

        @m.on_state("some_state")
        async def state_handler(ctx: Context) -> None:
            called.append("state")

        d = Dispatcher()
        d.register_module(m)

        # Both payload AND active state — payload should win
        ctx = make_ctx(payload="ACTION", text="answer", current_query="some_state")
        result = await d.dispatch(ctx)

        assert result.level == 1
        assert called == ["payload"]

    async def test_state_overrides_command(self) -> None:
        """Level 2 (state) beats Level 3 (command)."""
        m = Module("test")
        called: list[str] = []

        @m.on_state("waiting")
        async def state_handler(ctx: Context) -> None:
            called.append("state")

        @m.on_command("ping")
        async def ping(ctx: Context) -> None:
            called.append("command")

        d = Dispatcher()
        d.register_module(m)

        # Text is /ping but state is active — state wins
        ctx = make_ctx(text="/ping", current_query="waiting")
        result = await d.dispatch(ctx)

        assert result.level == 2
        assert called == ["state"]

    async def test_command_overrides_text(self) -> None:
        """Level 3 (command) beats Level 5 (text)."""
        m = Module("test")
        called: list[str] = []

        @m.on_command("start")
        async def start_cmd(ctx: Context) -> None:
            called.append("command")

        @m.on_text(r"/start")
        async def start_text(ctx: Context) -> None:
            called.append("text")

        d = Dispatcher()
        d.register_module(m)

        ctx = make_ctx(text="/start")
        result = await d.dispatch(ctx)

        assert result.level == 3
        assert called == ["command"]


class TestFallback:
    """Tests for fallback handler."""

    async def test_fallback_called_when_no_match(self) -> None:
        d = Dispatcher()
        called = []

        async def fallback(ctx: Context) -> None:
            called.append(True)

        d.set_fallback(fallback)

        ctx = make_ctx(text="random gibberish")
        result = await d.dispatch(ctx)

        assert result.matched is True
        assert result.level == 0
        assert called == [True]

    async def test_no_fallback_returns_unmatched(self) -> None:
        d = Dispatcher()
        ctx = make_ctx(text="random gibberish")
        result = await d.dispatch(ctx)

        assert result.matched is False


class TestDuplicateRegistration:
    """Tests for duplicate handler detection."""

    def test_duplicate_payload_raises(self) -> None:
        m1 = Module("mod1")
        m2 = Module("mod2")

        @m1.on_payload("SAME")
        async def h1(ctx: Context) -> None:
            pass

        @m2.on_payload("SAME")
        async def h2(ctx: Context) -> None:
            pass

        d = Dispatcher()
        d.register_module(m1)

        with pytest.raises(ValueError, match="Duplicate payload"):
            d.register_module(m2)

    def test_duplicate_command_raises(self) -> None:
        m1 = Module("mod1")
        m2 = Module("mod2")

        @m1.on_command("ping")
        async def h1(ctx: Context) -> None:
            pass

        @m2.on_command("ping")
        async def h2(ctx: Context) -> None:
            pass

        d = Dispatcher()
        d.register_module(m1)

        with pytest.raises(ValueError, match="Duplicate command"):
            d.register_module(m2)

    def test_duplicate_prefix_raises(self) -> None:
        m1 = Module("mod1")
        m2 = Module("mod2")

        @m1.on_payload_prefix("PRE_")
        async def h1(ctx: Context) -> None:
            pass

        @m2.on_payload_prefix("PRE_")
        async def h2(ctx: Context) -> None:
            pass

        d = Dispatcher()
        d.register_module(m1)

        with pytest.raises(ValueError, match="Duplicate prefix"):
            d.register_module(m2)
