"""Tests for the webhook endpoint — GET verification and POST message handling.

Uses FastAPI TestClient for integration tests of the full pipeline:
webhook → middleware → normalize → dispatch.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nakama_framework import Context, Module, NakamaApp
from nakama_framework.core.context import StubSender
from nakama_framework.middleware.base import MiddlewareStack
from nakama_framework.channels.messenger.webhook import create_webhook_router


# --- Fixtures ---

VERIFY_TOKEN = "test-verify-token"
APP_SECRET = "test-app-secret"


def _make_app() -> tuple[NakamaApp, list[str]]:
    """Create a NakamaApp with a test module that tracks calls."""
    handled_messages: list[str] = []

    nakama_app = NakamaApp()

    module = Module("test")

    @module.on_command("ping")
    async def ping_handler(ctx: Context) -> None:
        handled_messages.append(f"cmd:ping:{ctx.user.id}")

    @module.on_text(r"^hello$")
    async def hello_handler(ctx: Context) -> None:
        handled_messages.append(f"text:hello:{ctx.user.id}")

    nakama_app.include_module(module)

    @nakama_app.on_fallback
    async def fallback(ctx: Context) -> None:
        handled_messages.append(f"fallback:{ctx.message.text}:{ctx.user.id}")

    return nakama_app, handled_messages


def _create_test_client(
    with_signature: bool = False,
) -> tuple[TestClient, list[str]]:
    """Create a FastAPI TestClient with the webhook router mounted."""
    nakama_app, handled = _make_app()

    if with_signature:
        router = create_webhook_router(
            app=nakama_app,
            verify_token=VERIFY_TOKEN,
            app_secret=APP_SECRET,
        )
    else:
        # No signature verification for simpler tests
        router = create_webhook_router(
            app=nakama_app,
            verify_token=VERIFY_TOKEN,
            app_secret=None,
        )

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)

    return TestClient(fastapi_app), handled


def _compute_signature(body: bytes) -> str:
    """Compute X-Hub-Signature-256 for test payloads."""
    digest = hmac.new(APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _webhook_payload(
    sender_id: str = "USER_1",
    text: str = "hello",
) -> dict:
    """Build a minimal Messenger webhook payload."""
    return {
        "object": "page",
        "entry": [
            {
                "id": "PAGE_ID",
                "time": 1700000000000,
                "messaging": [
                    {
                        "sender": {"id": sender_id},
                        "recipient": {"id": "PAGE_ID"},
                        "timestamp": 1700000000000,
                        "message": {
                            "mid": "mid.test",
                            "text": text,
                        },
                    }
                ],
            }
        ],
    }


# --- GET /webhook: Verification Tests ---


class TestWebhookVerification:
    """Tests for the GET /webhook Meta verification endpoint."""

    def test_valid_verification(self) -> None:
        """Valid verify_token should return the challenge."""
        client, _ = _create_test_client()
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "CHALLENGE_123",
            },
        )

        assert response.status_code == 200
        assert response.text == "CHALLENGE_123"

    def test_wrong_verify_token(self) -> None:
        """Wrong verify_token should return 403."""
        client, _ = _create_test_client()
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "CHALLENGE_123",
            },
        )

        assert response.status_code == 403

    def test_wrong_mode(self) -> None:
        """Non-subscribe mode should return 403."""
        client, _ = _create_test_client()
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "unsubscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "CHALLENGE_123",
            },
        )

        assert response.status_code == 403

    def test_missing_params(self) -> None:
        """Missing parameters should return 403."""
        client, _ = _create_test_client()
        response = client.get("/webhook")

        assert response.status_code == 403


# --- POST /webhook: Message Handling Tests ---


class TestWebhookPost:
    """Tests for the POST /webhook message handling pipeline."""

    def test_text_message_dispatched(self) -> None:
        """A text message matching a regex should trigger the handler."""
        client, handled = _create_test_client()
        payload = _webhook_payload("USER_1", "hello")

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "text:hello:USER_1" in handled

    def test_command_dispatched(self) -> None:
        """A /ping command should trigger the command handler."""
        client, handled = _create_test_client()
        payload = _webhook_payload("USER_1", "/ping")

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert "cmd:ping:USER_1" in handled

    def test_fallback_for_unknown_text(self) -> None:
        """Unmatched text should trigger the fallback handler."""
        client, handled = _create_test_client()
        payload = _webhook_payload("USER_1", "random gibberish")

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert any("fallback:" in h for h in handled)

    def test_postback_dispatched(self) -> None:
        """A postback event should be dispatched correctly."""
        client, handled = _create_test_client()
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE_ID",
                    "time": 1700000000000,
                    "messaging": [
                        {
                            "sender": {"id": "USER_1"},
                            "recipient": {"id": "PAGE_ID"},
                            "timestamp": 1700000000000,
                            "postback": {
                                "title": "Start",
                                "payload": "GET_STARTED",
                            },
                        }
                    ],
                }
            ],
        }

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        # Postback with payload "GET_STARTED" won't match our test module
        # (no payload handler registered), so it hits fallback
        assert any("fallback:" in h for h in handled)

    def test_multiple_events_all_processed(self) -> None:
        """Multiple events in one payload should all be dispatched."""
        client, handled = _create_test_client()
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE_ID",
                    "time": 1700000000000,
                    "messaging": [
                        {
                            "sender": {"id": "USER_A"},
                            "recipient": {"id": "PAGE_ID"},
                            "timestamp": 1700000000000,
                            "message": {"mid": "m1", "text": "hello"},
                        },
                        {
                            "sender": {"id": "USER_B"},
                            "recipient": {"id": "PAGE_ID"},
                            "timestamp": 1700000000001,
                            "message": {"mid": "m2", "text": "/ping"},
                        },
                    ],
                }
            ],
        }

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert len(handled) == 2

    def test_echo_message_ignored(self) -> None:
        """Echo messages should be filtered out by the normalizer."""
        client, handled = _create_test_client()
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "PAGE_ID",
                    "time": 1700000000000,
                    "messaging": [
                        {
                            "sender": {"id": "PAGE_ID"},
                            "recipient": {"id": "USER_1"},
                            "timestamp": 1700000000000,
                            "message": {
                                "mid": "m.echo",
                                "is_echo": True,
                                "text": "auto-reply",
                            },
                        }
                    ],
                }
            ],
        }

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert len(handled) == 0

    def test_non_page_object_returns_ok(self) -> None:
        """Non-page payloads should return 200 (ack) with no processing."""
        client, handled = _create_test_client()
        payload = {"object": "instagram", "entry": []}

        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        assert len(handled) == 0

    def test_invalid_json_returns_400(self) -> None:
        """Invalid JSON should return 400."""
        client, _ = _create_test_client()

        response = client.post(
            "/webhook",
            content=b"not-json{{{",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 400

    def test_session_persistence_across_requests(self) -> None:
        """Sessions should persist between requests for the same user."""
        client, handled = _create_test_client()

        # First request
        client.post("/webhook", json=_webhook_payload("USER_1", "hello"))
        # Second request from same user
        client.post("/webhook", json=_webhook_payload("USER_1", "/ping"))

        assert len(handled) == 2
        assert "text:hello:USER_1" in handled
        assert "cmd:ping:USER_1" in handled


# --- POST /webhook with Signature Verification ---


class TestWebhookWithSignature:
    """Tests for the webhook with signature verification enabled."""

    def test_valid_signature_passes(self) -> None:
        """A correctly signed request should be processed."""
        client, handled = _create_test_client(with_signature=True)
        payload = _webhook_payload("USER_1", "hello")
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(body)

        response = client.post(
            "/webhook",
            content=body,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": sig,
            },
        )

        assert response.status_code == 200
        assert "text:hello:USER_1" in handled

    def test_missing_signature_rejected(self) -> None:
        """A request without signature should be rejected (403)."""
        client, handled = _create_test_client(with_signature=True)
        payload = _webhook_payload("USER_1", "hello")

        response = client.post("/webhook", json=payload)

        assert response.status_code == 403
        assert len(handled) == 0

    def test_invalid_signature_rejected(self) -> None:
        """A request with wrong signature should be rejected (403)."""
        client, handled = _create_test_client(with_signature=True)
        payload = _webhook_payload("USER_1", "hello")
        body = json.dumps(payload).encode("utf-8")

        response = client.post(
            "/webhook",
            content=body,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": "sha256=deadbeef",
            },
        )

        assert response.status_code == 403
        assert len(handled) == 0
