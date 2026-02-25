"""
Telegram → PA legacy router (used only by the global shared poller).

When each PA has its own bot token the per-PA poller sets PA_ID in the
process env and auto_responder.py uses it directly — this file is not
involved in that path.

This file is retained only as a fallback for the global single-bot setup.
"""
from __future__ import annotations

from typing import Optional


def get_pa_for_chat(chat_id: int | str) -> Optional[dict]:
    """
    Return the first available PA (legacy fallback for global single-bot mode).
    Used only when PA_ID env var is not set in the poller process.
    """
    try:
        from src.agent.hub.pa_manager import load_assistants
        assistants = load_assistants()
        return assistants[0] if assistants else None
    except Exception:
        return None
