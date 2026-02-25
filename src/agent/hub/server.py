"""
OctaMind Hub API — FastAPI server.

Exposes the HubProcessor as an HTTP endpoint so any external bot
(WhatsApp, WeChat, custom integrations …) can reach the multi-agent brain.

Endpoints:
    POST /hub/chat        — send a message, get a response
    GET  /hub/health      — liveness check
    GET  /hub/session/{id} — inspect conversation history for a session

Default port: 8502  (Streamlit UI stays on 8501)

Start manually:
    uvicorn src.agent.hub.server:app --host 0.0.0.0 --port 8502 --reload

Or via start.py (launched automatically alongside the Streamlit dashboard).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path when run directly
_ROOT = Path(__file__).parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.agent.hub.processor import HubProcessor, _SESSION_HISTORY

logger = logging.getLogger("hub_api")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# Optional API-key auth
# Set HUB_API_KEY env-var to protect the endpoint.
# If unset, the endpoint is open (fine for localhost-only use).
# ---------------------------------------------------------------------------
_API_KEY = os.getenv("HUB_API_KEY", "")

app = FastAPI(
    title="OctaMind Hub API",
    description="Channel-agnostic multi-agent brain. Send messages from any bot.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

_processor = HubProcessor()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's text message")
    session_id: str = Field(..., description="Unique ID for the conversation (e.g. 'telegram_12345')")
    source: str = Field("api", description="Channel source: telegram | whatsapp | api | …")
    agent_id: Optional[str] = Field("__multi_agent__", description="OctaMind agent ID to use")
    agent_name: Optional[str] = Field("Personal Assistant", description="Display name of the agent")


class ChatResponse(BaseModel):
    response: str
    source: str
    status: str
    elapsed: float
    actions_taken: List[Dict[str, Any]] = []
    session_id: str


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _check_auth(authorization: Optional[str]) -> None:
    if not _API_KEY:
        return  # open — no key configured
    if authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/hub/health", response_model=HealthResponse, tags=["Meta"])
async def health():
    """Liveness check."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/hub/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Send a message to the multi-agent hub and receive a response.

    The hub automatically routes the message to:
    - A conversational LLM reply (no agents needed)
    - A single specialized agent (Drive / Email / Files)
    - A full multi-agent workflow (e.g. Drive → Email)
    """
    _check_auth(authorization)
    logger.info("[HubAPI] %s | session=%s | %.80s", body.source, body.session_id, body.message)

    result = _processor.process(
        message=body.message,
        session_id=body.session_id,
        source=body.source,
        agent_id=body.agent_id or "__multi_agent__",
        agent_name=body.agent_name or "Personal Assistant",
    )

    return ChatResponse(
        response=result.response,
        source=result.source,
        status=result.status,
        elapsed=result.elapsed,
        actions_taken=result.actions_taken,
        session_id=body.session_id,
    )


@app.get("/hub/session/{session_id}", tags=["Meta"])
async def get_session(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """Return the conversation history for a session."""
    _check_auth(authorization)
    history = _SESSION_HISTORY.get(session_id, [])
    return {"session_id": session_id, "message_count": len(history), "history": history}


@app.delete("/hub/session/{session_id}", tags=["Meta"])
async def clear_session(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """Clear the conversation history for a session."""
    _check_auth(authorization)
    _SESSION_HISTORY.pop(session_id, None)
    return {"session_id": session_id, "cleared": True}


# ---------------------------------------------------------------------------
# Run directly: python -m src.agent.hub.server
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HUB_PORT", "8502"))
    uvicorn.run("src.agent.hub.server:app", host="0.0.0.0", port=port, reload=False)
