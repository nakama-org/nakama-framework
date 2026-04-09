"""Nakama V3 Framework — Database Models (Schema).

Defines the database schema as Python classes using SQLAlchemy's
Declarative API. These models are the source of truth for Alembic
migrations.

Framework Tables:
    - SystemConfig: Internal key-value storage (profile hashes, etc.)
    - UserSession: Conversational state per user.

Bot developers can add their own tables by importing Base:
    from nakama_framework.database import Base
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all models.

    Both framework and bot models inherit from this class.
    Alembic auto-discovers all subclasses for migrations.
    """

    pass


# ── Framework Tables ─────────────────────────────────────────


class SystemConfig(Base):
    """Internal key-value store for framework configuration.

    Used for storing deployment artifacts like the Messenger
    profile hash to avoid unnecessary API calls on restart.

    Attributes:
        key: Configuration key (e.g. "messenger_profile_hash").
        value: Configuration value (string).
    """

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class UserSession(Base):
    """Conversational state for a user.

    Stores the session data as JSON, allowing flexible
    key-value storage for cart, preferences, flow state, etc.

    Attributes:
        user_id: Channel-specific user ID (e.g. PSID for Messenger).
        data: Arbitrary JSON session data.
        state: Active state handler and its data (JSON).
        created_at: When the session was first created.
        updated_at: Last activity timestamp (auto-updated).
    """

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
