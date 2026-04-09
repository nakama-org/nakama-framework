"""Nakama V3 Framework — Messenger Profile Configuration.

Declarative models for the Messenger Profile API. These let bot
developers describe their desired Messenger profile (Get Started
button, persistent menu) as Python objects. The framework syncs
the profile to Meta's API automatically on startup.

Reference:
    https://developers.facebook.com/docs/messenger-platform/reference/messenger-profile-api
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, model_validator


class MenuItemType(str, Enum):
    """Supported menu item types."""

    POSTBACK = "postback"
    WEB_URL = "web_url"


class MenuItem(BaseModel):
    """A single item in the persistent menu.

    Attributes:
        type: The action type — ``postback`` triggers a webhook
            event, ``web_url`` opens a browser.
        title: Display label (max 30 characters).
        payload: Postback payload string (required for ``postback``).
        url: URL to open (required for ``web_url``).
    """

    type: MenuItemType = MenuItemType.POSTBACK
    title: str
    payload: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def _validate_type_fields(self) -> MenuItem:
        if self.type == MenuItemType.POSTBACK and not self.payload:
            msg = "MenuItem with type 'postback' requires a 'payload'"
            raise ValueError(msg)
        if self.type == MenuItemType.WEB_URL and not self.url:
            msg = "MenuItem with type 'web_url' requires a 'url'"
            raise ValueError(msg)
        return self

    def to_api_dict(self) -> dict:
        """Convert to the Facebook Graph API format."""
        result: dict = {"type": self.type.value, "title": self.title}
        if self.type == MenuItemType.POSTBACK:
            result["payload"] = self.payload
        else:
            result["url"] = self.url
        return result


class MessengerProfile(BaseModel):
    """Declarative configuration for the Messenger Profile API.

    Describes the desired state of the bot's Messenger profile.
    Pass this to ``NakamaApp`` and it will be synced automatically
    on startup.

    Attributes:
        get_started_payload: Payload sent when user taps the
            "Get Started" button (first interaction only).
            Required for the persistent menu to appear.
        persistent_menu: Up to 3 top-level menu items shown
            permanently in the conversation.

    Example::

        profile = MessengerProfile(
            get_started_payload="GET_STARTED",
            persistent_menu=[
                MenuItem(title="🛒 Commander", payload="START_ORDER"),
                MenuItem(title="📞 Support", payload="CONTACT_SUPPORT"),
                MenuItem(
                    title="🌐 Site web",
                    type=MenuItemType.WEB_URL,
                    url="https://azplus.mg",
                ),
            ],
        )
    """

    get_started_payload: str | None = None
    persistent_menu: list[MenuItem] | None = None

    @model_validator(mode="after")
    def _validate_menu_requires_get_started(self) -> MessengerProfile:
        if self.persistent_menu and not self.get_started_payload:
            msg = (
                "Messenger requires a 'get_started_payload' to be set "
                "before the persistent menu can appear."
            )
            raise ValueError(msg)
        return self

    def to_api_payload(self) -> dict:
        """Build the JSON payload for ``POST me/messenger_profile``.

        Returns:
            A dict ready to be sent to the Messenger Profile API.
        """
        payload: dict = {}

        if self.get_started_payload:
            payload["get_started"] = {"payload": self.get_started_payload}

        if self.persistent_menu:
            payload["persistent_menu"] = [
                {
                    "locale": "default",
                    "composer_input_disabled": False,
                    "call_to_actions": [
                        item.to_api_dict() for item in self.persistent_menu
                    ],
                }
            ]

        return payload
