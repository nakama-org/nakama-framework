"""Tests for nakama_framework.utils.paginator"""

import pytest

from nakama_framework.core.context import Context, StubSender
from nakama_framework.utils.paginator import Paginator
from nakama_framework.core.types import Channel, Message, Session, User


def make_ctx() -> Context:
    user = User(id="u1", channel=Channel.MESSENGER)
    session = Session(user_id="u1")
    message = Message(text="hello")
    return Context(user=user, session=session, message=message, sender=StubSender())


def test_total_pages() -> None:
    p = Paginator(items=list(range(50)), per_page=10)
    assert p.total_pages == 5


def test_total_pages_not_even() -> None:
    p = Paginator(items=list(range(53)), per_page=10)
    assert p.total_pages == 6


def test_total_pages_empty() -> None:
    p = Paginator(items=[], per_page=10)
    assert p.total_pages == 1  # Always at least 1 page


def test_get_page() -> None:
    p = Paginator(items=list(range(20)), per_page=10)
    assert p.get_page(0) == list(range(10))
    assert p.get_page(1) == list(range(10, 20))


def test_get_page_last_partial() -> None:
    p = Paginator(items=list(range(15)), per_page=10)
    assert p.get_page(1) == list(range(10, 15))


def test_parse_page_valid() -> None:
    assert Paginator.parse_page("NAV_CATALOG:3") == 3


def test_parse_page_invalid() -> None:
    assert Paginator.parse_page("ORDER_123") == 0
    assert Paginator.parse_page("NAV_CATALOG:ABC") == 0
    assert Paginator.parse_page(None) == 0


def test_from_session() -> None:
    ctx = make_ctx()
    ctx.session.data["__pag_catalog"] = ["a", "b"]
    ctx.session.data["__pag_catalog_pp"] = 5

    p = Paginator.from_session(ctx, key="catalog")
    assert p.items == ["a", "b"]
    assert p.per_page == 5
    assert p.key == "catalog"


def test_nav_first_page() -> None:
    p = Paginator(items=list(range(50)), per_page=10, key="cat")
    nav = p._nav_buttons(0)  # page 1
    assert len(nav) == 2
    assert nav[0].title == "Suivant"
    assert nav[0].payload == "NAV_CAT:1"
    assert nav[1].title == "Fin"
    assert nav[1].payload == "NAV_CAT:4"


def test_nav_before_last() -> None:
    p = Paginator(items=list(range(50)), per_page=10, key="cat")
    nav = p._nav_buttons(3)  # page 4 (out of 5)
    assert len(nav) == 1
    assert nav[0].title == "Suivant"
    assert nav[0].payload == "NAV_CAT:4"


def test_nav_last_page() -> None:
    p = Paginator(items=list(range(50)), per_page=10, key="cat")
    nav = p._nav_buttons(4)  # page 5 (out of 5)
    assert len(nav) == 0


def test_nav_single_page() -> None:
    p = Paginator(items=["a", "b"], per_page=10, key="cat")
    nav = p._nav_buttons(0)
    assert len(nav) == 0


async def test_send() -> None:
    ctx = make_ctx()
    p = Paginator(items=list(range(15)), per_page=10, key="cat")

    rendered_items = []

    async def render(context: Context, items: list) -> None:
        rendered_items.append(items)

    class MockSender(StubSender):
        def __init__(self):
            self.sent_replies = None

        async def send_quick_replies(self, user_id: str, text: str, buttons: list):
            self.sent_replies = (text, buttons)

    ctx.sender = MockSender()

    await p.send(ctx, page=0, render=render)

    # 1. Saved state correctly
    assert ctx.session.data["__pag_cat"] == list(range(15))
    assert ctx.session.data["__pag_cat_pp"] == 10

    # 2. Rendered the right page
    assert rendered_items == [list(range(10))]

    # 3. Sent nav buttons
    assert ctx.sender.sent_replies is not None
    text, buttons = ctx.sender.sent_replies
    assert text == "📄 Page 1/2"
    assert len(buttons) == 1
    assert buttons[0].title == "Suivant"
    assert buttons[0].payload == "NAV_CAT:1"


async def test_send_with_extra_buttons() -> None:
    """Extra buttons appear after nav buttons in the quick reply row."""
    from nakama_framework.core.types import Button

    ctx = make_ctx()
    p = Paginator(items=list(range(15)), per_page=10, key="cat")

    class MockSender(StubSender):
        def __init__(self):
            self.sent_replies = None

        async def send_quick_replies(self, user_id: str, text: str, buttons: list):
            self.sent_replies = (text, buttons)

    ctx.sender = MockSender()

    menu_btn = Button(title="🏠 Menu", payload="MAIN_MENU")

    async def render(context: Context, items: list) -> None:
        pass

    await p.send(ctx, page=0, render=render, extra_buttons=[menu_btn])

    assert ctx.sender.sent_replies is not None
    _, buttons = ctx.sender.sent_replies
    # Expected: [Suivant, Menu] (no "Fin" because only 2 pages)
    assert len(buttons) == 2
    assert buttons[0].title == "Suivant"
    assert buttons[1].title == "🏠 Menu"
    assert buttons[1].payload == "MAIN_MENU"


async def test_send_extra_buttons_on_last_page() -> None:
    """On the last page, no nav buttons — but extra buttons should still appear."""
    from nakama_framework.core.types import Button

    ctx = make_ctx()
    p = Paginator(items=list(range(5)), per_page=10, key="cat")  # 1 page only

    class MockSender(StubSender):
        def __init__(self):
            self.sent_replies = None

        async def send_quick_replies(self, user_id: str, text: str, buttons: list):
            self.sent_replies = (text, buttons)

    ctx.sender = MockSender()

    menu_btn = Button(title="🏠 Menu", payload="MAIN_MENU")

    async def render(context: Context, items: list) -> None:
        pass

    await p.send(ctx, page=0, render=render, extra_buttons=[menu_btn])

    # Even with a single page (no nav), extra buttons must still be sent
    assert ctx.sender.sent_replies is not None
    _, buttons = ctx.sender.sent_replies
    assert len(buttons) == 1
    assert buttons[0].title == "🏠 Menu"
