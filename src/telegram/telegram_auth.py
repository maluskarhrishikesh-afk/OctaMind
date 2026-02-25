"""
Telegram Bot credentials loader.

Each Personal Assistant has its own bot token stored in data/assistants.json.
The per-PA poller (pa_poller_runner.py) sets the TELEGRAM_BOT_TOKEN env var
before starting the polling loop, so all downstream code just reads the env var.

Get a bot token by messaging @BotFather on Telegram:
  /newbot  → follow the prompts → copy the token it gives you.
Then paste it in the PA's Configure tab.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("telegram_agent")


def get_bot_token() -> str:
    """Return the Telegram bot token from the TELEGRAM_BOT_TOKEN env var.

    This env var is set by pa_poller_runner.py for each per-PA poller process.
    Returns an empty string if not running inside a poller process.
    """
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def credentials_configured() -> bool:
    """Return True if a non-empty bot token is available."""
    return bool(get_bot_token())
