"""Nakama V3 Framework — Module (Blueprint/Router).

A Module is a logical grouping of handlers, similar to
Flask Blueprints or FastAPI routers. Each module declares
its handlers using decorators, and the framework collects
them at registration time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from nakama_framework.core.types import MediaType
from nakama_framework.logging import get_module_logger


# Type alias for async handler functions
Handler = Callable[..., Awaitable[Any]]


@dataclass
class TextRoute:
    """A text handler paired with its compiled regex pattern.

    Attributes:
        pattern: The compiled regex pattern.
        handler: The async handler function.
        raw_pattern: The original regex string (for debugging).
    """

    pattern: re.Pattern[str]
    handler: Handler
    raw_pattern: str


class Module:
    """A logical grouping of message handlers (Blueprint pattern).

    Handlers are registered via decorators and grouped by type.
    The framework's Dispatcher inspects these registries to route
    incoming messages.

    Example::

        module = Module("orders")

        @module.on_payload("ADD_CART")
        async def add_to_cart(ctx: Context):
            await ctx.reply("Added!")

    Attributes:
        name: A unique identifier for this module.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = get_module_logger(name)

        # Handler registries by type
        self._payload_handlers: dict[str, Handler] = {}
        self._prefix_handlers: dict[str, Handler] = {}
        self._state_handlers: dict[str, Handler] = {}
        self._command_handlers: dict[str, Handler] = {}
        self._media_handlers: dict[str, Handler] = {}
        self._text_routes: list[TextRoute] = []

    def on_payload(self, payload_id: str) -> Callable[[Handler], Handler]:
        """Register a handler for a button click (Postback/QuickReply).

        Priority Level 1 (MAX).

        Args:
            payload_id: The exact payload string to match.

        Returns:
            Decorator that registers the handler.
        """

        def decorator(func: Handler) -> Handler:
            self._payload_handlers[payload_id] = func
            return func

        return decorator

    def on_payload_prefix(self, prefix: str) -> Callable[[Handler], Handler]:
        """Register a handler for payloads starting with a prefix.

        Priority Level 1b (MAX).

        Args:
            prefix: The payload prefix to match.

        Returns:
            Decorator that registers the handler.
        """

        def decorator(func: Handler) -> Handler:
            self._prefix_handlers[prefix] = func
            return func

        return decorator

    def on_state(self, state_name: str) -> Callable[[Handler], Handler]:
        """Register a handler for a pending query/state.

        Priority Level 2 (HIGH). Triggered when
        session.state.name matches state_name.

        Args:
            state_name: The state identifier set by ctx.ask().

        Returns:
            Decorator that registers the handler.
        """

        def decorator(func: Handler) -> Handler:
            self._state_handlers[state_name] = func
            return func

        return decorator

    def on_command(self, command: str) -> Callable[[Handler], Handler]:
        """Register a handler for a slash command.

        Priority Level 3 (MEDIUM). Triggered when the message
        text starts with /<command>.

        Args:
            command: The command name without the leading slash.

        Returns:
            Decorator that registers the handler.
        """

        def decorator(func: Handler) -> Handler:
            self._command_handlers[command] = func
            return func

        return decorator

    def on_media(self, media_type: MediaType) -> Callable[[Handler], Handler]:
        """Register a handler for media messages.

        Priority Level 4 (MEDIUM). Triggered when the message
        contains a media attachment of the given type.

        Args:
            media_type: The media type to match (MediaType enum).

        Returns:
            Decorator that registers the handler.
        """

        def decorator(func: Handler) -> Handler:
            self._media_handlers[media_type.value] = func
            return func

        return decorator

    def on_text(self, pattern: str) -> Callable[[Handler], Handler]:
        """Register a handler for free text matching a regex.

        Priority Level 5 (LOW / Fallback). The pattern is tested
        against the full message text. Captured groups are passed
        as positional arguments to the handler after ctx.

        Args:
            pattern: A regex pattern string.

        Returns:
            Decorator that registers the handler.
        """

        def decorator(func: Handler) -> Handler:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._text_routes.append(
                TextRoute(pattern=compiled, handler=func, raw_pattern=pattern)
            )
            return func

        return decorator

    def __repr__(self) -> str:
        counts = (
            f"payloads={len(self._payload_handlers)}, "
            f"prefixes={len(self._prefix_handlers)}, "
            f"states={len(self._state_handlers)}, "
            f"commands={len(self._command_handlers)}, "
            f"media={len(self._media_handlers)}, "
            f"text={len(self._text_routes)}"
        )
        return f"Module({self.name!r}, {counts})"
