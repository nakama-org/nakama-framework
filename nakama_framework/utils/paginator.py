"""Nakama V3 Framework — Paginator Utility.

A helper class to paginate long lists of items with Messenger quick replies.
Supports single-direction forward navigation ("Next", "Last").
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from nakama_framework.core.context import Context
from nakama_framework.core.types import Button





class Paginator:
    """Utility to paginate lists and send navigation quick replies.

    The state is saved inside the user's session data. Navigation only
    goes forward (Next/Last) because past messages remain visible in chat.
    """

    SESSION_PREFIX = "__pag_"

    def __init__(
        self,
        items: list[Any],
        per_page: int = 10,
        key: str = "default",
        icon_next: str | None = "https://res.cloudinary.com/dqpyf5nzd/image/upload/v1771590095/next-quickrep-icon_dcijbm.png",
        icon_last: str | None = "https://res.cloudinary.com/dqpyf5nzd/image/upload/v1771591230/lastp-quickrep-icon_lp9h6x.png",
    ) -> None:
        """Initialize a new Paginator.

        Args:
            items: The full list of items to paginate.
            per_page: Number of items per page.
            key: Unique identifier for this paginator instance in session data.
        """
        self.items = items
        self.per_page = per_page
        self.key = key
        self.icon_next = icon_next
        self.icon_last = icon_last

    @property
    def total_pages(self) -> int:
        """Total number of pages required."""
        return max(1, -(-len(self.items) // self.per_page))

    def get_page(self, page: int) -> list[Any]:
        """Get the items for a specific page (0-indexed)."""
        start = page * self.per_page
        return self.items[start : start + self.per_page]

    @classmethod
    def from_session(cls, ctx: Context, key: str = "default") -> Paginator:
        """Reconstruct a Paginator from session data.

        Args:
            ctx: The current request context.
            key: The unique identifier used when creating the original paginator.

        Returns:
            A new Paginator instance with the saved state.
        """
        items = ctx.session.data.get(f"{cls.SESSION_PREFIX}{key}", [])
        per_page = ctx.session.data.get(f"{cls.SESSION_PREFIX}{key}_pp", 10)
        return cls(items=items, per_page=per_page, key=key)

    @staticmethod
    def parse_page(payload: str | None) -> int:
        """Extract the page number from a navigation payload.

        Example payload: "NAV_CATALOG:2" -> page 2

        Args:
            payload: The postback payload string.

        Returns:
            The parsed page number (0-indexed), or 0 if parsing fails.
        """
        if not payload or ":" not in payload:
            return 0
        try:
            return int(payload.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            return 0

    async def send(
        self,
        ctx: Context,
        page: int,
        render: Callable[[Context, list[Any]], Awaitable[None]],
        extra_buttons: list[Button] | None = None,
    ) -> None:
        """Save state, render the current page, and send navigation buttons.

        Args:
            ctx: The current request context.
            page: The requested page number (0-indexed).
            render: An async callback that takes (ctx, items) and sends the UI.
            extra_buttons: Optional extra quick replies to append after
                the navigation buttons (e.g. "Menu", "Vider le panier").
        """
        # Save state to session
        ctx.session.data[f"{self.SESSION_PREFIX}{self.key}"] = self.items
        ctx.session.data[f"{self.SESSION_PREFIX}{self.key}_pp"] = self.per_page

        # Render current page
        await render(ctx, self.get_page(page))

        # Combine nav buttons + extra buttons and send if any
        nav = self._nav_buttons(page)
        if extra_buttons:
            nav.extend(extra_buttons)
        if nav:
            await ctx.send_quick_replies(f"📄 Page {page + 1}/{self.total_pages}", nav)

    def _nav_buttons(self, current: int) -> list[Button]:
        """Generate navigation quick replies for the given page."""
        if self.total_pages <= 1:
            return []

        buttons = []
        prefix = f"NAV_{self.key.upper()}"

        if current < self.total_pages - 1:
            buttons.append(
                Button(
                    title="Suivant",
                    payload=f"{prefix}:{current + 1}",
                    image_url=self.icon_next,
                )
            )

        if current < self.total_pages - 2:
            buttons.append(
                Button(
                    title="Fin",
                    payload=f"{prefix}:{self.total_pages - 1}",
                    image_url=self.icon_last,
                )
            )

        return buttons
