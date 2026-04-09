"""Nakama V3 Framework — HTTP Server and runner.

Provides the ``run()`` function that creates a FastAPI server
with health check and webhook endpoints, then starts uvicorn.

This is the main entry point for running a bot in production.

Usage::

    from nakama_framework import run
    from bot import app

    run(app)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from nakama_framework.app import NakamaApp
from nakama_framework.logging import get_logger

logger = get_logger("server")


def run(
    app: NakamaApp,
    host: str = "0.0.0.0",
    port: int | None = None,
) -> None:
    """Start the bot server.

    Creates a FastAPI application with:
    - GET  /health   — Docker / load balancer health check
    - GET  /webhook  — Meta verification handshake
    - POST /webhook  — Incoming messages (fire-and-forget)

    Then starts uvicorn to serve it.

    Args:
        app: The assembled NakamaApp instance.
        host: Bind address (default: 0.0.0.0).
        port: Bind port. Falls back to PORT env var,
            then defaults to 8000.

    Example::

        run(app)              # port 8000
        run(app, port=3000)   # port 3000
    """
    import uvicorn

    resolved_port = port or int(os.environ.get("PORT", "8000"))

    # --- Lifespan (startup/shutdown hooks) ---
    @asynccontextmanager
    async def lifespan(server: FastAPI) -> AsyncGenerator[None, None]:
        await app.on_startup()
        yield
        await app.on_shutdown()

    # --- Build FastAPI server ---
    server = FastAPI(
        title="Nakama Bot",
        version="0.1.0",
        lifespan=lifespan,
    )

    @server.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # --- Register channel webhook routes ---
    channel = app.channel
    if channel is not None:
        webhook_router = channel.create_router(app)
        server.include_router(webhook_router)
    elif channel is None:
        logger.warning("No channel registered — no webhook endpoints available.")

    # --- Start ---
    logger.info(
        "Starting bot on %s:%d (%d modules, %d middlewares)",
        host,
        resolved_port,
        len(app.modules),
        app.middleware_count,
    )
    uvicorn.run(server, host=host, port=resolved_port)
