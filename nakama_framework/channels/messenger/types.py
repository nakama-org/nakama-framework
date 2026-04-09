"""Nakama Framework — Messenger-specific types.

These types extend the generic framework types with Messenger
Platform-specific features that have no cross-channel equivalent.

Reference:
    https://developers.facebook.com/docs/messenger-platform/send-messages/quick-replies
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# Messenger "content_type" values for native quick replies.
# These trigger Messenger to pre-fill the input with data from the user's
# profile (email) or phone number, without the user having to type it.
NativeQuickReplyType = Literal["user_email", "user_phone_number", "user_location"]


class NativeQuickReply(BaseModel):
    """A Messenger-native quick reply that requests profile data from the user.

    Unlike ``Button``, this type has no ``title`` or ``payload`` — Messenger
    fills the reply text automatically from the user's profile (email, phone,
    or location). The bot receives the value via ``ctx.message.text``.

    This type is **Messenger-only** and has no equivalent on other channels.
    Other channel adapters should raise ``NotImplementedError`` if they receive
    instances of this class.

    Attributes:
        content_type: The type of native data to request.

    Example::

        from nakama_framework.channels.messenger.types import NativeQuickReply

        buttons = [
            NativeQuickReply(content_type="user_email"),
            NativeQuickReply(content_type="user_phone_number"),
        ]
        await ctx.send_quick_replies("Quel est ton email ?", buttons)
    """

    content_type: NativeQuickReplyType
