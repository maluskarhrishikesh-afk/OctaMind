"""
Asset helpers shared by dashboard modules.
"""
from __future__ import annotations

import base64 as _base64
from pathlib import Path

import streamlit as st


@st.cache_resource
def _logo_b64() -> str:
    """Return the base64 data-URL for octopus.png. Cached for the process lifetime."""
    img_path = Path(__file__).parent.parent.parent / "assets" / "octopus.png"
    data = img_path.read_bytes()
    return "data:image/png;base64," + _base64.b64encode(data).decode()


def _logo_icon():
    """Return a PIL Image of octopus.png for page_icon, or emoji fallback."""
    try:
        from PIL import Image as _PILImage  # type: ignore
        return _PILImage.open(
            Path(__file__).parent.parent.parent / "assets" / "octopus.png"
        )
    except Exception:
        return "\U0001f419"
