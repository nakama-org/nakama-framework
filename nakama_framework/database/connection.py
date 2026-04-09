"""Nakama V3 Framework — Database Connection Management.

Manages the async SQLAlchemy engine and session factory.
This module is the "plumbing" — it creates connections and
provides transaction scopes to the rest of the application.

Usage::

    db = Database("sqlite+aiosqlite:///bot.db")
    await db.connect()

    async with db.transaction() as tx:
        result = await tx.execute(select(UserSession))

    await db.close()
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nakama_framework.database.models import Base
from nakama_framework.logging import get_logger

logger = get_logger("Database")

# Default SQLite database URL (file in current working directory)
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///bot.db"


class Database:
    """Async database connection manager.

    Creates an AsyncEngine and provides session factories
    for transactional database access.

    Args:
        url: SQLAlchemy connection URL.
            Default: ``sqlite+aiosqlite:///bot.db``
        echo: If True, log all SQL statements (useful for debugging).
    """

    def __init__(self, url: str = DEFAULT_DATABASE_URL, *, echo: bool = False):
        self.url = url
        self._echo = echo
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Whether connect() has been called successfully."""
        return self._connected

    async def connect(self) -> None:
        """Initialize the database engine and create all tables.

        In development, this creates tables directly from models.
        In production, use Alembic migrations instead.
        """
        self._engine = create_async_engine(self.url, echo=self._echo)
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._connected = True
        logger.info("Database connected and tables verified")

    async def close(self) -> None:
        """Close the database engine and release all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._connected = False
        logger.info("Database connection closed")

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope (auto-commit/rollback).

        Usage::

            async with db.transaction() as tx:
                user = await tx.get(UserSession, "user_123")
                tx.add(some_model)
                # auto-commits on exit, rolls back on exception
        """
        if self._session_factory is None:
            raise RuntimeError("Database.connect() must be called first")
        async with self._session_factory() as tx:
            try:
                yield tx
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise
