"""
Channel Registry — single source of truth for all PA communication channels.

To add a new channel (e.g. WhatsApp, WeChat, Discord):
  1. Create src/agent/hub/channels/your_channel.py  subclassing BaseChannel
  2. Add an entry to CHANNEL_REGISTRY below — nothing else needs changing.
"""
from __future__ import annotations

from typing import Dict, List

from .channels import DashboardChannel, TelegramChannel
from .channels.base import BaseChannel

# ── Registry ────────────────────────────────────────────────────────────────
# Note: APIChannel (REST API on port 8502) has been removed from the active
# registry.  It was a FastAPI endpoint for external bot integrations which is
# not used in the current Personal Assistant workflow.  The channel code is
# preserved in src/agent/hub/channels/api.py and can be re-enabled here if
# external HTTP integrations are needed in the future.
CHANNEL_REGISTRY: Dict[str, BaseChannel] = {
    "dashboard": DashboardChannel(),
    "telegram":  TelegramChannel(),
}


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_channel(name: str) -> BaseChannel:
    """Return a channel by its registry key.  Raises KeyError if not found."""
    return CHANNEL_REGISTRY[name]


def get_enabled_channels() -> List[BaseChannel]:
    """All channels whose `enabled` flag is True."""
    return [ch for ch in CHANNEL_REGISTRY.values() if ch.enabled]


def start_all_channels() -> None:
    """
    Start every enabled channel.

    Calling code no longer needs to know *how* each channel launches —
    it just calls this one function.

    Usage in start.py::

        from src.agent.hub.channel_registry import start_all_channels
        start_all_channels()
    """
    for channel in get_enabled_channels():
        try:
            print(f"  {channel.icon}  Starting {channel.display_name}…")
            channel.start()
        except Exception as exc:
            print(f"  ⚠️  Failed to start {channel.display_name}: {exc}")


def stop_all_channels() -> None:
    """Gracefully stop every channel that is currently running."""
    for channel in CHANNEL_REGISTRY.values():
        try:
            if channel.is_running():
                channel.stop()
        except Exception as exc:
            print(f"  ⚠️  Error stopping {channel.display_name}: {exc}")
