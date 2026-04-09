"""Nakama V3 Framework — Webhook endpoint for Messenger.

Provides a FastAPI router with two endpoints:
- GET /webhook  — Meta verification challenge (subscription setup)
- POST /webhook — Receives incoming messages, verifies signature
  natively, normalizes events, runs context middlewares, and
  dispatches them.

The signature verification and request logging are handled
natively by the framework (not as pluggable middlewares).

Usage::

    from nakama_framework.webhook import create_webhook_router

    router = create_webhook_router(
        app=nakama_app,
        verify_token="my-verify-token",
        app_secret="my-app-secret",
    )
    fastapi_app.include_router(router)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json


from fastapi import APIRouter, Query, Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from nakama_framework.app import NakamaApp
from nakama_framework.channels.messenger.normalizer import (
    NormalizedEvent,
    normalize_webhook_payload,
)
from nakama_framework.logging import get_logger

logger = get_logger("webhook")


def _verify_signature(
    body: bytes, app_secret: str, signature_header: str | None
) -> str | None:
    """Verify the X-Hub-Signature-256 header (native framework security).

    Args:
        body: The raw request body bytes.
        app_secret: The Facebook App Secret.
        signature_header: The value of the X-Hub-Signature-256 header.

    Returns:
        An error message if verification fails, None if OK.
    """
    if not signature_header:
        return "Missing signature"

    if not signature_header.startswith("sha256="):
        return "Invalid signature format"

    received_hash = signature_header[7:]  # Strip "sha256=" prefix
    expected_hash = hmac.new(
        app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        return "Invalid signature"

    return None  # Signature is valid


async def _process_event(app: NakamaApp, event: NormalizedEvent) -> None:
    """Process a single webhook event in the background.

    This runs after the HTTP 200 has already been returned to Meta.
    Any exception here is logged but does NOT affect the webhook response.

    Args:
        app: The NakamaApp instance.
        event: The normalized event to process.
    """
    try:
        await app.process(event.user, event.message)
    except Exception:
        logger.exception("Error processing event from user %s", event.user.id)


def create_webhook_router(
    app: NakamaApp,
    verify_token: str,
    app_secret: str | None = None,
    prefix: str = "/webhook",
) -> APIRouter:
    """Create a FastAPI router for the Messenger webhook.

    Wires together native security, normalization, and background
    event processing into a complete request pipeline.

    Pipeline (synchronous — before returning 200):
    1. Signature verification (native, non-optional if app_secret set)
    2. JSON parsing & normalization

    Pipeline (asynchronous — after returning 200):
    3. Context creation
    4. Context middleware stack (business rules)
    5. Dispatcher routing (5-level priority)
    6. Response sent to user via channel adapter

    Args:
        app: The NakamaApp instance with registered modules.
        verify_token: The token Meta uses to verify the webhook
            during subscription setup.
        app_secret: Facebook App Secret for signature verification.
            If None, signature check is skipped (dev mode only).
        prefix: URL prefix for the webhook endpoints.

    Returns:
        A FastAPI APIRouter ready to be included in the app.
    """
    router = APIRouter(prefix=prefix, tags=["webhook"])

    # -- GET: Meta Verification Challenge --
    @router.get("")
    async def verify_webhook(
        hub_mode: str = Query(alias="hub.mode", default=""),
        hub_verify_token: str = Query(alias="hub.verify_token", default=""),
        hub_challenge: str = Query(alias="hub.challenge", default=""),
    ) -> Response:
        """Handle the Meta webhook verification handshake.

        Meta sends a GET request with hub.mode=subscribe,
        hub.verify_token=<your_token>, and hub.challenge=<challenge>.
        We must return the challenge value if the token matches.
        """
        if hub_mode == "subscribe" and hub_verify_token == verify_token:
            logger.info("Webhook verified successfully")
            return PlainTextResponse(hub_challenge)

        logger.warning(
            "Webhook verification failed: mode=%s, token=%s",
            hub_mode,
            hub_verify_token[:10] + "..." if hub_verify_token else "(empty)",
        )
        return JSONResponse(
            {"error": "Verification failed"},
            status_code=403,
        )

    # -- POST: Incoming Messages --
    @router.post("")
    async def receive_webhook(request: Request) -> Response:
        """Receive and process incoming Messenger webhook events.

        Returns 200 immediately after validating the request
        (signature + JSON). Event processing runs in background
        tasks to respect Meta's 5-second timeout.
        """
        body = await request.body()

        # --- Step 1: Native Signature Verification (Sync) ---
        if app_secret:
            sig_header = request.headers.get("x-hub-signature-256")
            error = _verify_signature(body, app_secret, sig_header)
            if error:
                logger.warning("Signature check failed: %s", error)
                return JSONResponse({"error": error}, status_code=403)

        # --- Step 2: Parse & Normalize (Sync) ---
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Invalid JSON in webhook body: %s", e)
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        # logger.debug("Raw webhook payload: %s", json.dumps(payload, ensure_ascii=False))
        events = normalize_webhook_payload(payload)
        logger.info("Received %d event(s), dispatching to background", len(events))

        # --- Step 3: Fire-and-Forget (Async Background) ---
        for event in events:
            app._spawn(_process_event(app, event))

        # --- Return 200 IMMEDIATELY ---
        # Meta gets its acknowledgement in ~2ms.
        # The actual processing continues in the background.
        return JSONResponse({"status": "ok"})

    return router
