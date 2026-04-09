"""Tests for the middleware system — Middleware and MiddlewareStack.

Tests verify the context-based middleware pipeline: ordering,
short-circuiting, and stack utility methods.
"""

from __future__ import annotations

from nakama_framework.core.context import Context
from nakama_framework.core.types import Channel, Message, Session, User
from nakama_framework.middleware.base import (
    Middleware,
    MiddlewareStack,
    NextFn,
)


# --- Helpers ---


def _make_ctx() -> Context:
    """Create a minimal Context for testing middleware."""
    user = User(id="u1", name="Test", channel=Channel.MESSENGER)
    session = Session(user_id="u1")
    message = Message(text="test")
    return Context(user=user, session=session, message=message)


async def _noop_final() -> None:
    """A no-op final step for middleware chain tests."""
    pass


# --- MiddlewareStack Tests ---


async def test_stack_empty_calls_final_handler() -> None:
    """An empty stack should call the final handler directly."""
    called = False

    async def final() -> None:
        nonlocal called
        called = True

    ctx = _make_ctx()
    stack = MiddlewareStack()
    chain = stack.build(ctx, final)

    await chain()

    assert called


async def test_stack_single_middleware() -> None:
    """A single middleware should wrap the final handler."""
    calls: list[str] = []

    class TrackingMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            calls.append("before")
            await next()
            calls.append("after")

    ctx = _make_ctx()
    stack = MiddlewareStack()
    stack.add(TrackingMiddleware())
    chain = stack.build(ctx, _noop_final)

    await chain()

    assert calls == ["before", "after"]


async def test_stack_order_preserved() -> None:
    """Middlewares should execute in insertion order."""
    order: list[int] = []

    class OrderedMiddleware(Middleware):
        def __init__(self, index: int):
            self.index = index

        async def process(self, ctx: Context, next: NextFn) -> None:
            order.append(self.index)
            await next()

    ctx = _make_ctx()
    stack = MiddlewareStack()
    stack.add(OrderedMiddleware(1))
    stack.add(OrderedMiddleware(2))
    stack.add(OrderedMiddleware(3))
    chain = stack.build(ctx, _noop_final)

    await chain()

    assert order == [1, 2, 3]


async def test_stack_middleware_can_short_circuit() -> None:
    """A middleware can return early without calling next."""
    final_called = False

    class BlockingMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            return  # Don't call next — short circuit

    async def tracking_final() -> None:
        nonlocal final_called
        final_called = True

    ctx = _make_ctx()
    stack = MiddlewareStack()
    stack.add(BlockingMiddleware())
    chain = stack.build(ctx, tracking_final)

    await chain()

    assert not final_called


async def test_stack_middleware_receives_context() -> None:
    """Middleware should receive the correct context object."""
    received_ctx: Context | None = None

    class CapturingMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            nonlocal received_ctx
            received_ctx = ctx
            await next()

    ctx = _make_ctx()
    stack = MiddlewareStack()
    stack.add(CapturingMiddleware())
    chain = stack.build(ctx, _noop_final)

    await chain()

    assert received_ctx is ctx
    assert received_ctx.user.id == "u1"


async def test_stack_len() -> None:
    """len(stack) should return the number of middlewares."""
    stack = MiddlewareStack()
    assert len(stack) == 0

    class DummyMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            await next()

    stack.add(DummyMiddleware())
    assert len(stack) == 1

    stack.add(DummyMiddleware())
    assert len(stack) == 2


async def test_stack_middlewares_property() -> None:
    """The middlewares property should return a copy."""

    class DummyMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            await next()

    stack = MiddlewareStack()
    mw = DummyMiddleware()
    stack.add(mw)

    result = stack.middlewares
    assert len(result) == 1
    assert result[0] is mw

    # Modifying the returned list should not affect the stack
    result.clear()
    assert len(stack) == 1


async def test_stack_middleware_can_modify_context() -> None:
    """A middleware can modify content before passing to the next handler."""
    final_message: str | None = None

    class UppercaseMiddleware(Middleware):
        async def process(self, ctx: Context, next: NextFn) -> None:
            # Modify the message text to uppercase
            ctx.message = Message(
                text=ctx.message.text.upper(),
                payload=ctx.message.payload,
                id=ctx.message.id,
            )
            await next()

    async def capturing_final() -> None:
        nonlocal final_message
        final_message = ctx.message.text

    ctx = _make_ctx()  # text = "test"
    stack = MiddlewareStack()
    stack.add(UppercaseMiddleware())
    chain = stack.build(ctx, capturing_final)

    await chain()

    assert final_message == "TEST"


async def test_nested_middleware_execution_order() -> None:
    """Verify the onion-ring execution pattern (before/after ordering)."""
    events: list[str] = []

    class LogMiddleware(Middleware):
        def __init__(self, name: str):
            self._name = name

        async def process(self, ctx: Context, next: NextFn) -> None:
            events.append(f"{self._name}:before")
            await next()
            events.append(f"{self._name}:after")

    ctx = _make_ctx()
    stack = MiddlewareStack()
    stack.add(LogMiddleware("A"))
    stack.add(LogMiddleware("B"))
    chain = stack.build(ctx, _noop_final)

    await chain()

    # Onion pattern: A wraps B
    assert events == ["A:before", "B:before", "B:after", "A:after"]
