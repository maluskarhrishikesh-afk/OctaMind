"""
Telegram channel — metadata-only entry in the Channel Registry.

There is no single global Telegram poller.  Each Personal Assistant
runs its own dedicated bot via pa_poller_manager / pa_poller_runner.
This class exists so "telegram" appears as a valid channel option
when configuring a PA, and reports aggregate running status.
"""
from __future__ import annotations

from .base import BaseChannel, ChannelStatus


class TelegramChannel(BaseChannel):
    name = "telegram"
    display_name = "Telegram Bot"
    icon = "✈️"
    description = "Telegram bot — users send messages via the Telegram app."
    enabled = True
    supports_markdown = True
    max_message_length = 4_096   # Telegram hard limit
    is_external = True

    def start(self) -> None:
        """No-op: Telegram bots are started per-PA from the Configure tab."""
        pass

    def stop(self) -> None:
        """No-op: Telegram bots are stopped per-PA from the Configure tab."""
        pass

    def is_running(self) -> bool:
        """True if at least one per-PA Telegram poller is currently alive."""
        try:
            from src.agent.hub.pa_manager import load_assistants
            from src.telegram.pa_poller_manager import get_pa_poller_status
            return any(
                get_pa_poller_status(pa["id"]) is not None
                for pa in load_assistants()
            )
        except Exception:
            return False

    def status(self) -> ChannelStatus:
        running = self.is_running()
        return ChannelStatus(
            running=running,
            pid=None,
            detail="Per-PA bots active" if running else "No PA bots running",
        )
