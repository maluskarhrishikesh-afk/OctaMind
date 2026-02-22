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

    Uses an LLM to understand natural language intent, with a keyword-based
    fallback if the LLM is unavailable.

    Returns:
        ["drive", "email"]  — if the command needs BOTH agents.
        None                — single-agent task; let the normal flow handle it.
    """
    # ── LLM-based detection ─────────────────────────────────────────────────
    try:
        from src.agent.llm.llm_parser import get_llm_client
        llm = get_llm_client()
        client = llm.client  # underlying openai.OpenAI instance
        prompt = (
            "You are a command router. Given a user command, decide which agents "
            "are needed.\n\n"
            "AGENTS:\n"
            "  DRIVE  — Google Drive file operations (upload, download, list files, "
            "create documents, share)\n"
            "  EMAIL  — Gmail operations (read emails, send mail, reply, count, "
            "search inbox)\n\n"
            "Reply with EXACTLY ONE of these four words:\n"
            "  BOTH     — command requires both Drive AND Email\n"
            "  DRIVE    — command requires only Drive\n"
            "  EMAIL    — command requires only Email\n"
            "  NEITHER  — unrelated to either agent\n\n"
            f"Command: {command}\n"
            "Answer:"
        )
        response = client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
        )
        verdict = response.choices[0].message.content.strip().upper()
        if verdict == "BOTH":
            logger.info("Router [LLM]: multi-agent — drive + email")
            return ["drive", "email"]
        if verdict == "DRIVE":
            logger.info("Router [LLM]: single-agent — drive only")
            return ["drive"]
        if verdict == "EMAIL":
            logger.info("Router [LLM]: single-agent — email only")
            return ["email"]
        # NEITHER or unrecognised
        logger.info("Router [LLM]: neither agent needed — %s", verdict)
        return None
    except Exception as exc:
        logger.warning("Router LLM classification failed (%s), falling back to keywords", exc)

    # ── Keyword fallback ────────────────────────────────────────────────────
    lower = command.lower()
    words = set(re.findall(r"[a-z]+", lower))
    has_drive = bool(_DRIVE_KEYWORDS & words)
    has_email = bool(_EMAIL_KEYWORDS & words)
    if has_drive and has_email:
        logger.info("Router [keywords]: multi-agent — drive + email")
        return ["drive", "email"]
    if has_drive:
        logger.info("Router [keywords]: single-agent — drive only")
        return ["drive"]
    if has_email:
        logger.info("Router [keywords]: single-agent — email only")
        return ["email"]
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
