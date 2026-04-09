"""Tests for nakama_framework.core.module — Module (Blueprint/Router)."""

import pytest

from nakama_framework.core.context import Context
from nakama_framework.core.module import Module
from nakama_framework.core.types import Channel, MediaType, Message, Session, User

# --- Helpers ---


async def dummy_handler(ctx: Context) -> None:
    """Placeholder handler for registration tests."""
    pass


async def dummy_text_handler(ctx: Context, match: str) -> None:
    """Placeholder text handler with a regex group."""
    pass


# --- Tests ---


class TestModulePayload:
    """Tests for @module.on_payload()."""

    def test_register_payload_handler(self) -> None:
        m = Module("test")

        @m.on_payload("ADD_CART")
        async def add_cart(ctx: Context) -> None:
            pass

        assert "ADD_CART" in m._payload_handlers
        assert m._payload_handlers["ADD_CART"] is add_cart

    def test_multiple_payload_handlers(self) -> None:
        m = Module("test")

        @m.on_payload("A")
        async def handler_a(ctx: Context) -> None:
            pass

        @m.on_payload("B")
        async def handler_b(ctx: Context) -> None:
            pass

        assert len(m._payload_handlers) == 2


class TestModulePrefix:
    """Tests for @module.on_payload_prefix()."""

    def test_register_prefix_handler(self) -> None:
        m = Module("test")

        @m.on_payload_prefix("NAV_")
        async def handle_nav(ctx: Context) -> None:
            pass

        assert "NAV_" in m._prefix_handlers
        assert m._prefix_handlers["NAV_"] is handle_nav

    def test_multiple_prefix_handlers(self) -> None:
        m = Module("test")

        @m.on_payload_prefix("A_")
        async def handler_a(ctx: Context) -> None:
            pass

        @m.on_payload_prefix("B_")
        async def handler_b(ctx: Context) -> None:
            pass

        assert len(m._prefix_handlers) == 2


class TestModuleState:
    """Tests for @module.on_state()."""

    def test_register_state_handler(self) -> None:
        m = Module("test")

        @m.on_state("handle_size")
        async def handle_size(ctx: Context) -> None:
            pass

        assert "handle_size" in m._state_handlers
        assert m._state_handlers["handle_size"] is handle_size


class TestModuleCommand:
    """Tests for @module.on_command()."""

    def test_register_command_handler(self) -> None:
        m = Module("test")

        @m.on_command("ping")
        async def ping(ctx: Context) -> None:
            pass

        assert "ping" in m._command_handlers


class TestModuleMedia:
    """Tests for @module.on_media()."""

    def test_register_media_handler(self) -> None:
        m = Module("test")

        @m.on_media(MediaType.IMAGE)
        async def handle_image(ctx: Context) -> None:
            pass

        assert "image" in m._media_handlers


class TestModuleText:
    """Tests for @module.on_text()."""

    def test_register_text_handler(self) -> None:
        m = Module("test")

        @m.on_text(r"^hello (.*)")
        async def greet(ctx: Context, name: str) -> None:
            pass

        assert len(m._text_routes) == 1
        assert m._text_routes[0].raw_pattern == r"^hello (.*)"
        assert m._text_routes[0].handler is greet

    def test_text_pattern_is_compiled(self) -> None:
        m = Module("test")

        @m.on_text(r"^test\d+")
        async def handler(ctx: Context) -> None:
            pass

        route = m._text_routes[0]
        assert route.pattern.match("test123") is not None
        assert route.pattern.match("nope") is None


class TestModuleRepr:
    """Tests for Module.__repr__."""

    def test_repr(self) -> None:
        m = Module("orders")
        assert "orders" in repr(m)
        assert "payloads=0" in repr(m)
