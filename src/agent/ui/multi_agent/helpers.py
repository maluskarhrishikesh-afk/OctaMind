"""
Helpers for the Multi-Agent UI.

Provides:
- Logo utilities (shared from assets)
- Browser watchdog (exits process when browser disconnects)
- Utilities for querying the status of running agents
"""
from __future__ import annotations

import base64 as _base64
import os
import threading
import time as _t
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st


# ---------------------------------------------------------------------------
# Logo helpers (shared asset path)
# ---------------------------------------------------------------------------

@st.cache_resource
def _logo_b64() -> str:
    """Return base64 data-URL for octopus.png."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "octopus.png"
    try:
        data = img_path.read_bytes()
        return "data:image/png;base64," + _base64.b64encode(data).decode()
    except Exception:
        return ""


def _logo_path() -> str:
    """Return the absolute file path for octopus.png for use as st.chat_message avatar."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "octopus.png"
    return str(img_path) if img_path.exists() else "🐙"


def _logo_pinkraven() -> str:
    """Return the absolute file path for pinkRaven.png for user chat avatar."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "pinkRaven.png"
    return str(img_path) if img_path.exists() else "🐦"


def _logo_icon():
    """Return PIL Image of octopus.png, or emoji fallback."""
    try:
        from PIL import Image as _PILImage  # type: ignore
        return _PILImage.open(
            Path(__file__).parent.parent.parent / "assets" / "octopus.png"
        )
    except Exception:
        return "⚡"


# ---------------------------------------------------------------------------
# Browser watchdog
# ---------------------------------------------------------------------------

@st.cache_resource
def _start_browser_watchdog(agent_id: str) -> bool:
    """
    Background thread — exits the process when the browser disconnects.
    Cached so it only starts once per process lifetime.
    """

    def _watch() -> None:
        _t.sleep(20)
        while True:
            _t.sleep(8)
            try:
                from streamlit.runtime import get_instance
                rt = get_instance()
                if rt is not None:
                    active = list(rt._session_mgr.list_active_session_info())
                    if len(active) == 0:
                        try:
                            from src.agent.core.process_manager import remove_agent_from_state
                            remove_agent_from_state(agent_id)
                        except Exception:
                            pass
                        os._exit(0)
            except Exception:
                pass

    t = threading.Thread(target=_watch, daemon=True)
    t.start()
    return True


# ---------------------------------------------------------------------------
# Running agent helpers
# ---------------------------------------------------------------------------

def get_running_agents() -> List[Dict]:
    """
    Return list of currently running agents from agents.json / running_agents.json.
    Each dict has at minimum: id, name, type, url.
    """
    try:
        from src.agent.core.process_manager import get_all_agent_statuses
        statuses = get_all_agent_statuses()
        return [s for s in statuses if s.get("running")]
    except Exception:
        return []


def get_agent_url(agent_type: str) -> Optional[str]:
    """Return the URL for a running agent of the given type, or None."""
    running = get_running_agents()
    for a in running:
        if a.get("type") == agent_type or a.get("agent_type") == agent_type:
            return a.get("url")
    return None
