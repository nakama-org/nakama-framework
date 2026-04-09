"""Nakama V3 Framework — Message Dispatcher.

The Dispatcher is the brain's routing engine. It applies a strict
5-level priority hierarchy to determine which handler should
process each incoming message.

Priority Levels:
    1. Payload   (MAX)  — Button clicks (Postback/QuickReply)
    2. State     (HIGH) — Pending query (session.current_query)
    3. Command   (MED)  — Slash commands (/reset, /ping)
    4. Media     (MED)  — Media attachments (image, video, file)
    5. Text/NLU  (LOW)  — Free text (regex matching)
"""

from __future__ import annotations


from dataclasses import dataclass
from typing import Any, Callable, Awaitable, Optional

from nakama_framework.core.context import Context
from nakama_framework.core.module import Handler, Module, TextRoute
from nakama_framework.logging import get_logger

logger = get_logger("dispatcher")

# Type for the optional fallback handler
FallbackHandler = Optional[Callable[[Context], Awaitable[Any]]]


@dataclass
class DispatchResult:
    """Result of a dispatch operation.

    Attributes:
        matched: Whether a handler was found and invoked.
        handler_name: Qualified name of the matched handler (for logging).
        level: The priority level that matched (1-5, or 0 for fallback).
    """

    matched: bool
    handler_name: str = ""
    level: int = 0


class Dispatcher:
    """Routes incoming messages to the appropriate handler.

    The Dispatcher collects handlers from all registered Modules
    and applies the 5-level priority hierarchy on each dispatch.

    After a state handler executes, the pending query is automatically
    cleared from the session to prevent infinite loops.
    """

    def __init__(self) -> None:
        # Aggregated handler registries (from all modules)
        self._payload_handlers: dict[str, Handler] = {}
        self._prefix_handlers: dict[str, Handler] = {}
        self._state_handlers: dict[str, Handler] = {}
        self._command_handlers: dict[str, Handler] = {}
        self._media_handlers: dict[str, Handler] = {}
        self._text_routes: list[TextRoute] = []
        self._fallback: FallbackHandler = None

    @staticmethod
    def _merge_handlers(
        target: dict[str, Handler],
        source: dict[str, Handler],
        label: str,
        module_name: str,
    ) -> None:
        """Merge handlers from a module into the dispatcher registry.

        Args:
            target: The dispatcher's handler dict to merge into.
            source: The module's handler dict to merge from.
            label: Human-readable handler type (for error messages).
            module_name: Name of the source module (for error messages).

        Raises:
            ValueError: If a handler key already exists in target.
        """
        for key, handler in source.items():
            if key in target:
                raise ValueError(
                    f"Duplicate {label} handler for '{key}': "
                    f"already registered, conflict from module '{module_name}'"
                )
            target[key] = handler

    def register_module(self, module: Module) -> None:
        """Register all handlers from a Module into the dispatcher.

        Args:
            module: The module whose handlers should be registered.

        Raises:
            ValueError: If a handler ID conflicts with an already
                registered handler (duplicate payload, state, etc.).
        """
        self._merge_handlers(
            self._payload_handlers, module._payload_handlers, "payload", module.name
        )
        self._merge_handlers(
            self._prefix_handlers, module._prefix_handlers, "prefix", module.name
        )
        self._merge_handlers(
            self._state_handlers, module._state_handlers, "state", module.name
        )
        self._merge_handlers(
            self._command_handlers, module._command_handlers, "command", module.name
        )
        self._merge_handlers(
            self._media_handlers, module._media_handlers, "media", module.name
        )

        # Text routes (order matters — first match wins)
        self._text_routes.extend(module._text_routes)

        logger.info("Registered module '%s': %s", module.name, module)

    def set_fallback(self, handler: FallbackHandler) -> None:
        """Set a fallback handler invoked when no route matches.

        Args:
            handler: Async function receiving a Context, or None to clear.
        """
        self._fallback = handler

    async def dispatch(self, ctx: Context) -> DispatchResult:
        """Route a message through the 5-level priority hierarchy.

        Args:
            ctx: The context for the current message.

        Returns:
            A DispatchResult indicating whether a handler matched.
        """
        msg = ctx.message
        session = ctx.session

        # --- Level 1: Payload (button click) ---
        if msg.payload and msg.payload in self._payload_handlers:
            handler = self._payload_handlers[msg.payload]
            logger.debug("L1 Payload match: %s", msg.payload)
            await handler(ctx)
            return DispatchResult(
                matched=True,
                handler_name=handler.__qualname__,
                level=1,
            )

        # --- Level 1b: Prefix Payload match ---
        if msg.payload:
            for prefix, handler in self._prefix_handlers.items():
                if msg.payload.startswith(prefix):
                    logger.debug("L1b Prefix match: %s -> %s", prefix, msg.payload)
                    await handler(ctx)
                    return DispatchResult(
                        matched=True,
                        handler_name=handler.__qualname__,
                        level=1,
                    )

        # --- Guard: Unrecognized Payload ---
        # If the message has a payload (user clicked a button) but NO handler
        # was found at L1 or L1b, this is a developer error (missing handler).
        # We MUST NOT let the active state "absorb" the unrecognized click,
        # as that would trap the user inside a form they can't escape.
        # Action: log the error, clear any active state, continue to L3+.
        if msg.payload:
            if session.state:
                logger.error(
                    "Unhandled payload '%s' from user %s — no handler registered. "
                    "Active state '%s' has been cleared to avoid trapping the user.",
                    msg.payload,
                    ctx.user.id,
                    session.state.name,
                )
                session.state = None
            else:
                logger.error(
                    "Unhandled payload '%s' from user %s — no handler registered.",
                    msg.payload,
                    ctx.user.id,
                )
            # Fall through to L3+ (command/media/text) or no-match fallback

        # --- Level 2: State (pending query) ---
        if session.state:
            state_name = session.state.name

            if state_name not in self._state_handlers:
                # Orphan state: the session has a state but no handler is registered
                # for it. This is always a developer error (typo, module not included,
                # or handler removed after a refactoring).
                # Clear the state to unblock the user and surface the bug via ERROR log.
                logger.error(
                    "Orphan state '%s' for user %s — no @on_state handler registered. "
                    "State has been cleared to avoid trapping the user.",
                    state_name,
                    ctx.user.id,
                )
                session.state = None
                # Fall through to L3+ (command/media/text) or no-match fallback

            else:
                handler = self._state_handlers[state_name]
                logger.debug("L2 State match: %s", state_name)

                # Since the handler might access ctx.state_data, and ctx.state_data
                # is a property that reads from session.state.data, we don't
                # need to manually clear state before calling the handler.
                # However, if the handler does NOT call ctx.ask() or ctx.set_state()
                # to set a NEW state, we clear the state AFTER execution to prevent
                # infinite loops.

                await handler(ctx)

                # If the state hasn't changed (meaning the handler didn't call ctx.ask),
                # clear the state so we don't get stuck in the same state.
                if session.state and session.state.name == state_name:
                    session.state = None

                return DispatchResult(
                    matched=True,
                    handler_name=handler.__qualname__,
                    level=2,
                )

        # --- Level 3: Command (/slash) ---
        if msg.text and msg.text.startswith("/"):
            parts = msg.text[1:].split(maxsplit=1)
            cmd = parts[0].lower() if parts else ""
            if cmd in self._command_handlers:
                handler = self._command_handlers[cmd]
                logger.debug("L3 Command match: /%s", cmd)
                await handler(ctx)
                return DispatchResult(
                    matched=True,
                    handler_name=handler.__qualname__,
                    level=3,
                )

        # --- Level 4: Media ---
        if msg.media_type:
            media_key = (
                msg.media_type.value
                if hasattr(msg.media_type, "value")
                else str(msg.media_type)
            )
            if media_key in self._media_handlers:
                handler = self._media_handlers[media_key]
                logger.debug("L4 Media match: %s", media_key)
                await handler(ctx)
                return DispatchResult(
                    matched=True,
                    handler_name=handler.__qualname__,
                    level=4,
                )

        # --- Level 5: Text/NLU (regex) ---
        if msg.text:
            for route in self._text_routes:
                match = route.pattern.search(msg.text)
                if match:
                    handler = route.handler
                    groups = match.groups()
                    logger.debug(
                        "L5 Text match: %s (groups=%s)",
                        route.raw_pattern,
                        groups,
                    )
                    await handler(ctx, *groups)
                    return DispatchResult(
                        matched=True,
                        handler_name=handler.__qualname__,
                        level=5,
                    )

        # --- Fallback ---
        if self._fallback:
            logger.debug("Fallback handler invoked")
            await self._fallback(ctx)
            return DispatchResult(
                matched=True,
                handler_name=self._fallback.__qualname__,
                level=0,
            )

        logger.warning(
            "No handler matched for message from user %s: %s",
            ctx.user.id,
            msg.text[:50] if msg.text else "(no text)",
        )
        return DispatchResult(matched=False)
