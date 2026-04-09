"""Nakama V3 Framework — Channel adapters.

Each channel lives in its own subpackage under channels/:
- channels/messenger/ — Facebook Messenger
- channels/whatsapp/ — WhatsApp (future)
- channels/instagram/ — Instagram (future)
"""

from nakama_framework.channels.messenger.client import MessengerClient

__all__ = ["MessengerClient"]
