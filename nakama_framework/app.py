"""Nakama V3 Framework — Main application class.

NakamaApp is the top-level assembler that wires together Modules,
the Dispatcher, the Middleware Stack, and a Sender. It provides
the high-level API for building and running a chatbot.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import asyncio

from nakama_framework.core.context import Context, Sender, StubSender
from nakama_framework.core.dispatcher import Dispatcher, DispatchResult
from nakama_framework.core.module import Module
from nakama_framework.core.types import Message, Session, User, State
from nakama_framework.core.protocols import ChannelAdapter
from nakama_framework.database.connection import DEFAULT_DATABASE_URL, Database
from nakama_framework.database.repository import Repository
from nakama_framework.logging import get_logger
from nakama_framework.middleware.base import Middleware, MiddlewareStack

logger = get_logger("app")


class NakamaApp:
    """Main application class for a Nakama-powered chatbot.

    Assembles modules, configures the dispatcher, manages the
    context middleware stack, and provides the entry point for
    processing incoming messages.

    Example::

        from nakama_framework import NakamaApp, run

        app = NakamaApp()
        app.include_module(ping)
        run(app)

    Attributes:
        sender: The channel adapter for sending responses.
        dispatcher: The message routing engine.
    """

    def __init__(
        self,
        database_url: str = DEFAULT_DATABASE_URL,
    ) -> None:
        """Initialize the application.

        Args:
            database_url: SQLAlchemy connection URL for persistence.
                Defaults to ``sqlite+aiosqlite:///bot.db``.
        """
        self.sender: Sender = StubSender()
        self.dispatcher = Dispatcher()
        self._modules: list[Module] = []
        self._middleware_stack = MiddlewareStack()
        self.db = Database(database_url)
        self.repo = Repository(self.db)
        self._channel: ChannelAdapter | None = None
        self._bg_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro: Awaitable[Any]) -> asyncio.Task:
        """Create a tracked fire-and-forget background task."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def register_channel(self, channel: ChannelAdapter) -> None:
        """Register a channel adapter with the application.

        The channel provides the sender (for outgoing messages),
        webhook credentials, and any channel-specific startup tasks.

        Args:
            channel: A channel adapter (e.g. ``MessengerChannel``).
                Must have a ``client`` attribute implementing the
                Sender protocol.

        Example::

            from nakama_framework.channels.messenger import MessengerChannel

            channel = MessengerChannel(
                page_access_token="EAA...",
                verify_token="my-token",
            )
            app.register_channel(channel)
        """
        self._channel = channel
        self.sender = channel.client
        logger.info("Channel registered: %s", type(channel).__name__)

    def include_module(self, module: Module) -> None:
        """Register a module's handlers with the application.

        Args:
            module: The module to include.

        Raises:
            ValueError: If handler IDs conflict with already
                registered handlers.
        """
        self.dispatcher.register_module(module)
        self._modules.append(module)
        logger.info("Included module: %s", module.name)

    def add_middleware(self, middleware: Middleware) -> None:
        """Add a context middleware to the processing pipeline.

        Middlewares execute in insertion order, AFTER the webhook
        has verified the signature and normalized the event into
        a Context, but BEFORE the Dispatcher routes to a handler.

        Args:
            middleware: A Middleware instance to add to the stack.

        Example::

            app.add_middleware(MaintenanceMiddleware())
            app.add_middleware(AuthMiddleware())
            # Execution order: Maintenance -> Auth -> Dispatcher
        """
        self._middleware_stack.add(middleware)
        logger.info("Added middleware: %s", type(middleware).__name__)

    def on_fallback(
        self, handler: Callable[[Context], Awaitable[Any]]
    ) -> Callable[[Context], Awaitable[Any]]:
        """Decorator to register a fallback handler.

        The fallback is invoked when no module handler matches
        the incoming message.

        Example::

            @app.on_fallback
            async def default_reply(ctx: Context):
                await ctx.reply("I don't understand.")

        Args:
            handler: The async fallback handler.

        Returns:
            The same handler (unmodified).
        """
        self.dispatcher.set_fallback(handler)
        return handler

    async def process(
        self,
        user: User,
        message: Message,
    ) -> DispatchResult:
        """Full message lifecycle — called by channel webhooks.

        Pipeline:
        1. Load (or create) the user's session from the database.
        2. Dispatch via handle() (middleware + routing).
        3. Persist the (potentially modified) session back to the DB.

        If the database has not been initialized (on_startup not called),
        sessions are ephemeral (in-memory only).

        Args:
            user: The sender of the message.
            message: The normalized incoming message.

        Returns:
            A DispatchResult indicating whether a handler matched.
        """
        db_ready = self.db.is_connected

        # 1. Auto-load session from DB (or create a fresh one)
        if db_ready:
            db_session = await self.repo.get_session(user.id)
            if db_session:
                state = None
                if db_session.state:
                    state = State(**db_session.state)

                session = Session(
                    user_id=user.id,
                    data=db_session.data,
                    state=state,
                )
            else:
                session = Session(user_id=user.id)
        else:
            session = Session(user_id=user.id)

        # 2. Dispatch
        result = await self.handle(user, session, message)

        # 3. Auto-save session to DB
        if db_ready:
            state_dict = None
            if session.state:
                state_dict = session.state.model_dump()

            await self.repo.save_session(
                user_id=user.id,
                data=session.data,
                state=state_dict,
            )

        return result

    async def handle(
        self,
        user: User,
        session: Session,
        message: Message,
    ) -> DispatchResult:
        """Pure routing — dispatch a message to the matching handler.

        This method does NOT touch the database. It is the ideal
        entry point for unit tests where you control the session.

        Args:
            user: The sender of the message.
            session: The user's conversational state.
            message: The normalized incoming message.

        Returns:
            A DispatchResult indicating whether a handler matched.
        """
        ctx = Context(
            user=user,
            session=session,
            message=message,
            sender=self.sender,
        )

        logger.debug(
            "Handling message from %s: text=%r, payload=%r",
            user.id,
            message.text[:50] if message.text else None,
            message.payload,
        )

        # Track dispatch result via typed mutable list.
        # NOTE: We use a list (not `nonlocal`) because Pyright cannot model
        # that `chain()` may or may not call `dispatch_step` at runtime.
        # Pyright correctly tracks `.append()` mutation, so this is the
        # idiomatic type-safe pattern for capturing results from async closures.
        dispatched: list[DispatchResult] = []

        async def dispatch_step() -> None:
            """The final step in the middleware chain: dispatch."""
            dispatched.append(await self.dispatcher.dispatch(ctx))

        # Build and execute the middleware chain -> dispatch
        chain = self._middleware_stack.build(ctx, dispatch_step)
        await chain()

        # If a middleware blocked execution, no dispatch happened
        if not dispatched:
            logger.info("Message from %s blocked by middleware", user.id)
            return DispatchResult(matched=False, handler_name="blocked_by_middleware")

        result = dispatched[0]
        if result.matched:
            logger.info(
                "Message from %s handled by %s (level %d)",
                user.id,
                result.handler_name,
                result.level,
            )
        else:
            logger.warning("No handler matched for message from %s", user.id)

        return result

    @property
    def modules(self) -> list[Module]:
        """List of registered modules."""
        return list(self._modules)

    @property
    def channel(self) -> ChannelAdapter | None:
        """The registered channel adapter (read-only)."""
        return self._channel

    @property
    def middleware_count(self) -> int:
        """Number of registered middlewares."""
        return len(self._middleware_stack)

    async def on_startup(self) -> None:
        """Initialize resources on application startup.

        Called by the server before accepting webhook requests.
        Creates database tables (dev) or verifies schema (prod).
        Runs channel-specific startup tasks (e.g. profile sync).
        """
        await self.db.connect()

        if self._channel is not None:
            await self._channel.on_startup()

        logger.info("Application started")

    async def on_shutdown(self) -> None:
        """Cleanup resources on application shutdown.

        Called by the server when shutting down gracefully.
        Closes database connections and channel resources.
        """
        for task in list(self._bg_tasks):
            task.cancel()

        if self._channel is not None:
            await self._channel.close()

        await self.db.close()
        logger.info("Application shut down")

    def __repr__(self) -> str:
        module_names = [m.name for m in self._modules]
        mw_count = len(self._middleware_stack)
        channel_name = type(self._channel).__name__ if self._channel else "None"
        return f"NakamaApp(channel={channel_name}, modules={module_names}, middlewares={mw_count})"
