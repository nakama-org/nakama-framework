"""Nakama V3 Framework.

A developer-friendly chatbot framework built on FastAPI and SQLAlchemy.
Focuses on excellent Developer Experience (DX) for Messenger bots.
"""

from nakama_framework.app import NakamaApp
from nakama_framework.server import run
from nakama_framework.core import (
    Button,
    CarouselItem,
    Context,
    Message,
    Module,
    Session,
    User,
    State,
)
from nakama_framework.core.context import StubSender
from nakama_framework.utils.paginator import Paginator

__all__ = [
    "NakamaApp",
    "run",
    "Button",
    "CarouselItem",
    "Context",
    "Message",
    "Module",
    "Session",
    "State",
    "User",
    "Paginator",
    "StubSender",
]

# Version information
__version__ = "0.4.0"
