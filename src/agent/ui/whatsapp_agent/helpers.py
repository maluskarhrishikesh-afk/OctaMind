"""
Asset helpers and browser-watchdog for the WhatsApp Agent UI.
(Same pattern as email_agent/helpers.py)
"""
from __future__ import annotations

import base64 as _base64
import threading
import time as _t
from pathlib import Path

import streamlit as st


@st.cache_resource
def _logo_b64() -> str:
    """Return the base64 data-URL for octopus.png.  Cached for the process lifetime."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "octopus.png"
    data = img_path.read_bytes()
    return "data:image/png;base64," + _base64.b64encode(data).decode()


def _logo_path() -> str:
    """Return the absolute file path for octopus.png."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "octopus.png"
    return str(img_path) if img_path.exists() else "🐙"


def _logo_pinkraven() -> str:
    """Return the absolute file path for pinkRaven.png for user chat avatar."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "pinkRaven.png"
    return str(img_path) if img_path.exists() else "🐦"


def _logo_icon():
    """Return a PIL Image of octopus.png for page_icon, or emoji fallback."""
    try:
        from PIL import Image as _PILImage  # type: ignore
        return _PILImage.open(
            Path(__file__).parent.parent.parent / "assets" / "octopus.png"
        )
    except Exception:
        return "💬"


@st.cache_resource
def _start_browser_watchdog(agent_id: str) -> bool:
    """
    Background thread that detects browser disconnection and exits the process.
    @st.cache_resource ensures this only starts once per process lifetime.
    """
    def _watch() -> None:
        _t.sleep(20)
        while True:
            _t.sleep(8)
            try:
                from streamlit.runtime import get_instance
                rt = get_instance()
                if rt is None:
                    break
                sessions = rt._session_mgr.list_active_sessions()
                if not sessions:
                    import os
                    os._exit(0)
            except Exception:
                break

    t = threading.Thread(target=_watch, daemon=True, name=f"watchdog-{agent_id}")
    t.start()
    return True
