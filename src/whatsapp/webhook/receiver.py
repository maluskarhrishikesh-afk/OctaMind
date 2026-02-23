"""
WhatsApp Webhook Receiver — FastAPI server.

Meta sends all inbound messages to this endpoint as HTTP POST requests.
The GET endpoint handles the one-time webhook verification handshake.

Run this server with:
    python -m uvicorn src.whatsapp.webhook.receiver:app --host 0.0.0.0 --port 9001

For local development, expose it with ngrok:
    ngrok http 9001
Then register the HTTPS URL in Meta Developer Console:
    https://<your-ngrok-id>.ngrok-free.app/webhook

Environment / settings.json:
    WHATSAPP_VERIFY_TOKEN — must match what you put in Meta console
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("whatsapp_webhook")

try:
    from fastapi import FastAPI, HTTPException, Query, Request, Response  # type: ignore
    from fastapi.responses import PlainTextResponse  # type: ignore
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    logger.warning(
        "fastapi is not installed. "
        "Install it with: pip install fastapi uvicorn"
    )

from ..whatsapp_auth import get_verify_token, get_access_token
from .message_store import store_inbound_message

if _FASTAPI_AVAILABLE:
    app = FastAPI(title="OctaMind WhatsApp Webhook", version="1.0.0")
else:
    app = None  # type: ignore


def _ts_to_iso(unix_ts: Any) -> str:
    """Convert a Unix timestamp (int or str) to an ISO-8601 string."""
    try:
        return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(tz=timezone.utc).isoformat()


def _process_webhook_payload(payload: Dict[str, Any]) -> None:
    """
    Parse the Meta webhook payload and persist each message.

    Meta sends batched payloads.  This function handles all known message
    types: text, image, video, audio, document, sticker, location, contacts,
    reaction, and unsupported.
    """
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts_meta = {
                c.get("wa_id"): c.get("profile", {}).get("name")
                for c in value.get("contacts", [])
            }

            for msg in messages:
                msg_id = msg.get("id", "")
                from_number = msg.get("from", "")
                msg_type = msg.get("type", "text")
                timestamp = _ts_to_iso(msg.get("timestamp"))
                sender_name = contacts_meta.get(from_number)

                # Determine group_id (conversation context id for groups)
                conversation = msg.get("context", {})
                group_id: Optional[str] = None

                body = ""
                media_id = None
                media_type = None
                caption = None

                if msg_type == "text":
                    body = msg.get("text", {}).get("body", "")

                elif msg_type in ("image", "video", "audio", "document", "sticker"):
                    media_obj = msg.get(msg_type, {})
                    media_id = media_obj.get("id")
                    media_type = msg_type
                    caption = media_obj.get("caption")
                    body = caption or f"[{msg_type}]"

                elif msg_type == "location":
                    loc = msg.get("location", {})
                    body = (
                        f"📍 Location: {loc.get('name', '')} "
                        f"({loc.get('latitude')}, {loc.get('longitude')})"
                    ).strip()

                elif msg_type == "contacts":
                    shared = msg.get("contacts", [])
                    names = [
                        c.get("name", {}).get("formatted_name", "")
                        for c in shared
                    ]
                    body = f"[Shared contact(s): {', '.join(names)}]"

                elif msg_type == "reaction":
                    reaction = msg.get("reaction", {})
                    body = f"[Reaction: {reaction.get('emoji', '?')} on {reaction.get('message_id', '?')}]"

                else:
                    body = f"[Unsupported message type: {msg_type}]"

                logger.info(
                    "Inbound WhatsApp: from=%s type=%s body=%.60s",
                    from_number, msg_type, body,
                )

                store_inbound_message(
                    message_id=msg_id,
                    from_number=from_number,
                    message_type=msg_type,
                    body=body,
                    timestamp=timestamp,
                    group_id=group_id,
                    media_id=media_id,
                    media_type=media_type,
                    caption=caption,
                    sender_name=sender_name,
                )


if _FASTAPI_AVAILABLE:

    @app.get("/webhook", response_class=PlainTextResponse)
    async def verify_webhook(
        hub_mode: Optional[str] = Query(None, alias="hub.mode"),
        hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
        hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    ) -> str:
        """
        WhatsApp webhook verification handshake.

        Meta sends a GET request with these query params when you register
        or re-register the webhook URL.  We must echo back hub.challenge
        if the verify token matches.
        """
        expected_token = get_verify_token()
        if hub_mode == "subscribe" and hub_verify_token == expected_token:
            logger.info("Webhook verified successfully.")
            return hub_challenge or ""
        logger.warning(
            "Webhook verification failed: mode=%s token=%s",
            hub_mode, hub_verify_token,
        )
        raise HTTPException(status_code=403, detail="Verification token mismatch")

    @app.post("/webhook")
    async def receive_webhook(request: Request) -> Dict[str, str]:
        """
        Receive inbound WhatsApp messages and status updates.

        Meta sends a POST for every inbound message, delivery receipt,
        read receipt, and button click.  We persist inbound messages and
        ignore status updates (they have no "messages" key).
        """
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        logger.debug("Webhook payload received: %s", json.dumps(payload)[:200])

        # Only process message events; ignore delivery/read status updates silently
        if payload.get("object") == "whatsapp_business_account":
            _process_webhook_payload(payload)

        # Meta expects a 200 OK within 20 seconds — always return quickly
        return {"status": "ok"}

    @app.get("/health")
    async def health() -> Dict[str, str]:
        """Simple liveness check."""
        return {"status": "healthy", "service": "whatsapp-webhook"}


# ── Standalone entry point ────────────────────────────────────────────────────

def run_server(host: str = "0.0.0.0", port: int = 9001) -> None:
    """Start the webhook server (blocking call — run in a thread or process)."""
    if not _FASTAPI_AVAILABLE:
        logger.error("Cannot start webhook server: fastapi/uvicorn not installed.")
        return
    try:
        import uvicorn  # type: ignore
        uvicorn.run(app, host=host, port=port, log_level="info")
    except ImportError:
        logger.error("uvicorn is not installed. Run: pip install uvicorn")


def start_webhook_in_background(host: str = "0.0.0.0", port: int = 9001) -> None:
    """Launch the webhook server in a background daemon thread."""
    import threading
    t = threading.Thread(
        target=run_server, args=(host, port), daemon=True, name="whatsapp-webhook",
    )
    t.start()
    logger.info("WhatsApp webhook server started on %s:%d", host, port)
