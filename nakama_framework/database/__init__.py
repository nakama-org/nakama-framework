"""Nakama V3 Framework — Database Layer.

Provides async SQLAlchemy integration with SQLite (dev) and
PostgreSQL (production) support via Alembic migrations.

Usage::

    from nakama_framework.database import Base, Database

    # Framework models are auto-registered.
    # Bot models just inherit from Base:
    class Product(Base):
        __tablename__ = "products"
        ...
"""

from nakama_framework.database.models import Base
from nakama_framework.database.connection import Database

__all__ = ["Base", "Database"]
