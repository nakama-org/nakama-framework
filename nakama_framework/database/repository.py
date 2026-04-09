"""Nakama V3 Framework — Data Access Repository.

Provides a clean interface for database operations, hiding
SQLAlchemy query complexity behind simple async methods.

The Repository is the ONLY place where SQL queries live.
The rest of the application uses these methods instead of
writing raw queries.

Usage::

    repo = Repository(db)

    # Store a config value
    await repo.set_config("messenger_profile_hash", "abc123")

    # Load a session
    session = await repo.get_session("user_123")
"""

from __future__ import annotations

from typing import Any


from nakama_framework.database.models import SystemConfig, UserSession
from nakama_framework.database.connection import Database


class Repository:
    """Data access layer for framework operations.

    Abstracts all SQL queries behind async methods.
    Bot developers can create their own repositories
    following the same pattern.

    Args:
        db: The Database instance to use for connections.
    """

    def __init__(self, db: Database):
        self._db = db

    # ── System Config ────────────────────────────────────────

    async def get_config(self, key: str) -> str | None:
        """Get a system configuration value by key.

        Returns:
            The config value, or None if not found.
        """
        async with self._db.transaction() as tx:
            result = await tx.get(SystemConfig, key)
            return result.value if result else None

    async def set_config(self, key: str, value: str) -> None:
        """Set a system configuration value (upsert)."""
        async with self._db.transaction() as tx:
            existing = await tx.get(SystemConfig, key)
            if existing:
                existing.value = value
            else:
                tx.add(SystemConfig(key=key, value=value))

    # ── User Sessions ────────────────────────────────────────

    async def get_session(self, user_id: str) -> UserSession | None:
        """Load a user's session from the database.

        Returns:
            The UserSession model, or None if user has no session.
        """
        async with self._db.transaction() as tx:
            return await tx.get(UserSession, user_id)

    async def save_session(
        self,
        user_id: str,
        data: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> None:
        """Save or update a user's session (upsert)."""
        async with self._db.transaction() as tx:
            existing = await tx.get(UserSession, user_id)
            if existing:
                existing.data = data
                existing.state = state
            else:
                tx.add(
                    UserSession(
                        user_id=user_id,
                        data=data,
                        state=state,
                    )
                )
