"""
Router — decides whether a user command needs one or multiple agents.

Strategy:
1. Fast keyword scan (no LLM needed for obvious cases).
2. If only one agent's keywords are present → single-agent (return None).
3. If both Drive AND Email keywords present → multi-agent workflow.

Usage:
    agents = detect_agents_needed("download the Q3 report and email it to bob")
    # → ["drive", "email"]
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

logger = logging.getLogger("workflows")

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------
_DRIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "drive",
        "gdrive",
        "file",
        "files",
        "download",
        "folder",
        "folders",
        "document",
        "documents",
        "spreadsheet",
        "spreadsheets",
        "presentation",
        "pdf",
        "upload",
        "docs",
        "sheets",
        "slides",
        "storage",
        "gdoc",
        "gsheet",
    }
)

_EMAIL_KEYWORDS: frozenset[str] = frozenset(
    {
        "email",
        "emails",
        "send",
        "mail",
        "inbox",
        "attach",
        "attachment",
        "attachments",
        "message",
        "messages",
        "gmail",
        "compose",
        "reply",
        "forward",
        "recipient",
        "cc",
        "bcc",
        "subject",
        "smtp",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_agents_needed(command: str) -> Optional[List[str]]:
    """
    Analyse *command* and return the list of agents required.

    Returns:
        ["drive", "email"]  — if the command clearly needs both agents.
        None                — single-agent task; let the normal flow handle it.

    Note:
        The caller should inspect *which* agent is needed independently when
        this returns None.  This function's only job is to detect MULTI-agent
        commands.
    """
    lower = command.lower()
    words = set(re.findall(r"[a-z]+", lower))  # token-level, no punctuation

    has_drive = bool(_DRIVE_KEYWORDS & words)
    has_email = bool(_EMAIL_KEYWORDS & words)

    if has_drive and has_email:
        logger.info("Router: multi-agent detected — drive + email")
        return ["drive", "email"]

    agent = "drive" if has_drive else ("email" if has_email else None)
    if agent:
        logger.info("Router: single-agent detected — %s", agent)
    else:
        logger.info("Router: no agent keywords detected in command")
    return None


def describe_routing(command: str) -> dict:
    """Return a debug-friendly dict showing the routing decision."""
    lower = command.lower()
    words = set(re.findall(r"[a-z]+", lower))
    drive_hits = sorted(_DRIVE_KEYWORDS & words)
    email_hits = sorted(_EMAIL_KEYWORDS & words)
    agents = detect_agents_needed(command)
    return {
        "command": command,
        "drive_keywords_matched": drive_hits,
        "email_keywords_matched": email_hits,
        "routing_decision": agents or "single-agent",
    }
