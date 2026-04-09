"""Nakama V3 Framework — NestJS-inspired logging.

Output::

    [Nakama] 42548 - 02/16/2026, 02:39:08 PM   INFO  [Server]       Starting bot
    [Nakama] 42548 - 02/16/2026, 02:39:08 PM   WARN  [Webhook]      Slow response
    [Nakama] 42548 - 02/16/2026, 02:39:08 PM   INFO  [PingModule]   Pong sent
    [Nakama] 42548 - 02/16/2026, 02:39:08 PM   ERROR [OrdersModule] Payment failed
"""

import logging
import os
import sys

# ── Colorama (optional) ──────────────────────────────────────

try:
    from colorama import Fore, Style, init as colorama_init

    colorama_init()
    _COLORS = {
        logging.DEBUG: Fore.MAGENTA,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }
    _RESET = Style.RESET_ALL
    _CTX_COLOR = Fore.YELLOW
except ImportError:
    _COLORS = {}
    _RESET = ""
    _CTX_COLOR = ""

# Shorter level names for alignment
_SHORT = {"WARNING": "WARN", "CRITICAL": "FATAL"}

_PID = os.getpid()


# ── Formatter ─────────────────────────────────────────────────


class _Formatter(logging.Formatter):
    """Formats: [Nakama] PID - timestamp   LEVEL [Context] message"""

    def format(self, record: logging.LogRecord) -> str:
        # Context: NAKAMA.server → Server, PingModule → PingModule
        name = record.name
        if name.startswith("NAKAMA."):
            part = name.split(".", 1)[1]
            ctx = part[0].upper() + part[1:]
        elif name == "NAKAMA":
            ctx = "Nakama"
        else:
            ctx = name

        level = _SHORT.get(record.levelname, record.levelname)
        ts = self.formatTime(record, "%m/%d/%Y, %I:%M:%S %p")
        color = _COLORS.get(record.levelno, "")

        line = (
            f"{color}[Nakama] {_PID}{_RESET} - {ts}   "
            f"{color}{level:<5s}{_RESET} "
            f"{_CTX_COLOR}[{ctx}]{_RESET} "
            f"{color}{record.getMessage()}{_RESET}"
        )

        # Append traceback for errors
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line += f"\n{record.exc_text}"
        if record.stack_info:
            line += f"\n{record.stack_info}"

        return line


# ── Shared handler ────────────────────────────────────────────

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_Formatter())


def _make_logger(name: str) -> logging.Logger:
    """Create a logger with the Nakama formatter."""
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        log.propagate = False
        log.addHandler(_handler)
    return log


# ── Public API ────────────────────────────────────────────────

# Root logger (initialized once at import)
logger = _make_logger("NAKAMA")


def get_logger(name: str) -> logging.Logger:
    """Framework logger → displays as [Server], [Webhook], etc."""
    return logging.getLogger(f"NAKAMA.{name}")


def get_module_logger(module_name: str) -> logging.Logger:
    """Module logger → displays as [PingModule], [OrdersModule], etc."""
    return logging.getLogger(f"NAKAMA.{module_name.capitalize()}Module")


# Suppress noisy external loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
