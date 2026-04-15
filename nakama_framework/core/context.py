"""Nakama V3 Framework — Context object.

The Context is the ONLY interface the bot uses to interact with
the framework and the outside world. It abstracts the underlying
channel API behind a unified, channel-agnostic interface.
"""

from __future__ import annotations

from typing import Any

from nakama_framework.core.protocols import Sender
from nakama_framework.core.types import (
    Button,
    CarouselItem,
    Message,
    Session,
    User,
    State,
)
from nakama_framework.logging import get_logger

logger = get_logger("context")


class StubSender:
    """Default sender that logs actions without sending.

    Used for testing and development when no channel is configured.
    """

    async def send_text(self, user_id: str, text: str) -> None:
        logger.info("[StubSender] -> %s: %s", user_id, text)

    async def send_image(self, user_id: str, source: str) -> None:
        logger.info("[StubSender] -> %s: image %s", user_id, source)

    async def send_buttons(
        self, user_id: str, text: str, buttons: list[Button]
    ) -> None:
        labels = [b.title for b in buttons]
        logger.info("[StubSender] -> %s: %s [buttons: %s]", user_id, text, labels)

    async def send_carousel(self, user_id: str, items: list[CarouselItem]) -> None:
        titles = [item.title for item in items]
        logger.info("[StubSender] -> %s: carousel %s", user_id, titles)

    async def send_quick_replies(
        self, user_id: str, text: str, buttons: list[Button]
    ) -> None:
        labels = [b.title for b in buttons]
        logger.info("[StubSender] -> %s: %s [quick_replies: %s]", user_id, text, labels)


class Context:
    """Unified interface for bot handlers to interact with the framework.

    Every handler receives a Context instance that provides:
    - Access to the sender (user), session, and message.
    - Methods to reply, ask questions, and send rich content.

    The Context is created fresh for each incoming message by the
    framework and is never reused across requests.

    Attributes:
        user: The message sender.
        session: Conversational state for this user.
        message: The normalized incoming message.
        sender: The channel adapter used to send responses.
    """

    __slots__ = ("user", "session", "message", "sender")

    def __init__(
        self,
        user: User,
        session: Session,
        message: Message,
        sender: Sender | None = None,
    ) -> None:
        self.user = user
        self.session = session
        self.message = message
        self.sender = sender or StubSender()

    @property
    def state_data(self) -> dict[str, Any]:
        """Shortcut to access the current session state data.

        Returns the data dict passed to `set_state` / `ask`, or `{}`
        if no state is active.

        Example::

            # In a state handler:
            name = ctx.state_data["name"]
        """
        if self.session.state:
            return self.session.state.data
        return {}

    async def reply(self, text: str) -> None:
        """Send a plain text response to the user.

        Args:
            text: The text message to send.
        """
        await self.sender.send_text(self.user.id, text)

    def set_state(self, state_name: str, **data: Any) -> None:
        """Set the session state without sending any message.

        Use this to prime the dispatcher so the next incoming message
        from the user is routed to the matching ``@module.on_state``
        handler.

        This is the low-level primitive. Prefer ``ask()`` when you also
        need to send a question to the user.

        Args:
            state_name: The state handler name (must match the argument passed
                to ``@module.on_state``).
            **data: Arbitrary key-value data to attach to the state,
                accessible via ``ctx.state_data`` in the next handler.

        .. warning::
            Do not use ``state_name`` as a data key — it is a reserved
            parameter of this method.

        Example::

            ctx.set_state("awaiting_confirm", order_id="42")
        """
        self.session.state = State(name=state_name, data=data)

    def clear_state(self) -> None:
        """Clear the session state.

        Removes any pending state, so the next incoming message
        will not be routed to a state handler and will follow the
        normal dispatch hierarchy (payload → command → media → text).

        Example::

            ctx.clear_state()
        """
        self.session.state = None

    async def ask(self, text: str, next_action: str, **data: Any) -> None:
        """Ask a question and register the next handler to process the reply.

        Convenience wrapper around ``set_state`` + ``reply``. Sets the
        session state so the user's next message is dispatched to the
        ``@module.on_state(next_action)`` handler.

        Args:
            text: The question text to send to the user.
            next_action: The state name that will handle the reply
                (must match ``@module.on_state`` argument).
            **data: Arbitrary data passed to the next handler
                (accessible via ``ctx.state_data``).

        Example::

            await ctx.ask("Quel est ton prénom ?", "awaiting_name")
        """
        self.set_state(next_action, **data)
        await self.sender.send_text(self.user.id, text)

    async def send_buttons(self, text: str, buttons: list[Button]) -> None:
        """Send a message with interactive buttons.

        Args:
            text: The message text displayed above the buttons.
            buttons: List of buttons to display.
        """
        await self.sender.send_buttons(self.user.id, text, buttons)

    async def send_carousel(self, items: list[CarouselItem]) -> None:
        """Send a carousel of interactive cards.

        Args:
            items: List of carousel items to display.
        """
        await self.sender.send_carousel(self.user.id, items)

    async def send_quick_replies(self, text: str, buttons: list[Button]) -> None:
        """Send a message with quick reply buttons.

        Args:
            text: The message text.
            buttons: List of quick reply buttons.
        """
        await self.sender.send_quick_replies(self.user.id, text, buttons)

    async def send_image(self, source: str) -> None:
        """Send a standalone image to the user.

        Args:
            source: Either a public HTTPS URL or a local file path.
        """
        await self.sender.send_image(self.user.id, source)
