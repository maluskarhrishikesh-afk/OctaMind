"""
BaseChannel — abstract contract every channel must implement.

A channel is how the user reaches the Personal Assistant:
  dashboard, telegram, whatsapp, slack, api, ...

To add a new channel:
  1. Create src/agent/hub/channels/my_channel.py implementing BaseChannel.
  2. Add one entry to CHANNEL_REGISTRY in channel_registry.py.
  3. That's it — start.py picks it up automatically.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChannelStatus:
    running: bool
    pid: Optional[int] = None
    port: Optional[int] = None
    detail: str = ""


class BaseChannel(ABC):
    """
    Abstract base for all PA communication channels.

    Subclasses must set class-level attributes and implement
    start() / stop() / is_running().
    """

    # ── Declare these in every subclass ──────────────────────────────────────
    name: str = ""                   # registry key, e.g. "telegram"
    display_name: str = ""           # human-readable, e.g. "Telegram Bot"
    icon: str = "📡"                 # emoji for dashboard display
    description: str = ""           # one-line summary shown in settings panel
    enabled: bool = True             # can be toggled without code changes
    supports_markdown: bool = True   # does the channel render markdown?
    max_message_length: int = 4096   # characters; longer responses get truncated
    is_external: bool = True         # False = dashboard (internal), True = bot/API

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def start(self) -> None:
        """Launch the channel's background process or thread."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Gracefully shut down the channel."""
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """Return True if the channel is currently active."""
        ...

    # ── Optional hooks ────────────────────────────────────────────────────────

    def status(self) -> ChannelStatus:
        """Return a rich status object. Override for more detail."""
        return ChannelStatus(running=self.is_running())

    def format_response(self, text: str) -> str:
        """
        Adapt a markdown response for this channel.

        Default: return as-is. Override for channels that don't support
        markdown (e.g. plain-SMS, WhatsApp without formatting).
        """
        if len(text) <= self.max_message_length:
            return text
        # Truncate gracefully at a sentence boundary
        truncated = text[: self.max_message_length - 20]
        last_break = max(truncated.rfind("\n"), truncated.rfind(". "))
        if last_break > self.max_message_length // 2:
            truncated = truncated[:last_break]
        return truncated + "\n\n_(message truncated)_"

    def __repr__(self) -> str:
        status = "✅" if self.is_running() else ("🔴" if self.enabled else "⚫")
        return f"<Channel {self.name} {status}>"
