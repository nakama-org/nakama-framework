"""Nakama V3 Framework — Context-based middleware system.

Middlewares intercept the processing pipeline AFTER the request
has been normalized into a Context object and BEFORE the Dispatcher
routes to a handler. This gives middleware full access to the user,
session, message, and the ability to reply.

The pipeline follows the "chain of responsibility" pattern:
each middleware calls ``await next()`` to pass control to the
next middleware (or the dispatcher).

Example::

    from nakama_framework.middleware.base import Middleware, MiddlewareStack

    class MaintenanceMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            if os.environ.get("MAINTENANCE"):
                await ctx.reply("🚧 Bot en maintenance.")
                return  # Stop the chain
            await next()  # Continue

    stack = MiddlewareStack()
    stack.add(MaintenanceMiddleware())
"""

from __future__ import annotations

import abc
from typing import Callable, Awaitable

from nakama_framework.core.context import Context

# Type alias: a zero-arg async callable that invokes the next step
NextFn = Callable[[], Awaitable[None]]


class Middleware(abc.ABC):
    """Abstract base class for all context middlewares.

    Subclasses must implement ``process``. Call ``await next()``
    to pass control to the next middleware in the chain.
    If ``next()`` is NOT called, the chain stops (the dispatcher
    never runs) — useful for blocking requests.

    Example::

        class AuthMiddleware(Middleware):
            async def process(self, ctx: Context, next: NextFn) -> None:
                if ctx.user.id in BANNED_USERS:
                    return  # Silently block
                await next()
    """

    @abc.abstractmethod
    async def process(self, ctx: Context, next: NextFn) -> None:
        """Process the context before dispatch.

        Args:
            ctx: The full conversation context (user, message, session).
            next: Call this to continue to the next middleware or
                the dispatcher. If not called, the chain stops.
        """
        ...


class MiddlewareStack:
    """Composes context middlewares into an ordered processing pipeline.

    Middlewares are executed in the order they are added.
    The final step (the dispatcher logic) is wrapped at the
    end of the chain.

    Example::

        stack = MiddlewareStack()
        stack.add(MaintenanceMiddleware())
        stack.add(AuthMiddleware())

        # Build the chain with the dispatcher as final step
        chain = stack.build(final_step)

        # Execute: Maintenance -> Auth -> final_step
        await chain()
    """

    def __init__(self) -> None:
        self._middlewares: list[Middleware] = []

    def add(self, middleware: Middleware) -> None:
        """Add a middleware to the end of the stack.

        Middlewares execute in insertion order (first added =
        first to process the context).

        Args:
            middleware: The middleware instance to add.
        """
        self._middlewares.append(middleware)

    def build(self, ctx: Context, final_step: NextFn) -> NextFn:
        """Build the middleware chain for a given context.

        Creates a nested chain of callables where each middleware
        wraps the next one, with the final step (dispatcher) at
        the innermost level.

        Args:
            ctx: The context to pass through the chain.
            final_step: The async function to call after all
                middlewares have run (typically the dispatcher).

        Returns:
            A zero-arg async callable representing the full chain.
        """
        chain = final_step

        # Build in reverse so first-added middleware is outermost
        for middleware in reversed(self._middlewares):
            chain = _wrap_middleware(middleware, ctx, chain)

        return chain

    @property
    def middlewares(self) -> list[Middleware]:
        """List of registered middlewares (read-only)."""
        return list(self._middlewares)

    def __len__(self) -> int:
        return len(self._middlewares)


def _wrap_middleware(middleware: Middleware, ctx: Context, next_fn: NextFn) -> NextFn:
    """Wrap a middleware around a next function, creating a closure.

    Args:
        middleware: The middleware to wrap.
        ctx: The context to pass to the middleware.
        next_fn: The function to call from within the middleware.

    Returns:
        A new NextFn that invokes the middleware with ``next``
        bound to ``next_fn``.
    """

    async def wrapped() -> None:
        await middleware.process(ctx, next_fn)

    return wrapped
