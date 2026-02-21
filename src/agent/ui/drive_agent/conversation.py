"""
Conversational handler for the Drive Agent.

handle_conversation() inspects the user message and either:
  - returns a natural-language response string (conversational intent), or
  - returns None to signal that execute_with_llm_orchestration() should handle it.
"""
from __future__ import annotations

import logging
import os

import streamlit as st
from src.agent.llm.llm_parser import get_llm_client

logger = logging.getLogger("drive_agent")

try:
    from src.agent.memory.agent_memory import get_agent_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False


def handle_conversation(
    message: str,
    agent_id: str = None,
    agent_name: str = None,
) -> str | None:
    """
    Handle conversational messages.

    Returns a response string if the message is conversational,
    or None if it should be treated as a Drive command.
    """
    msg = message.strip().lower()

    # Drive-specific action keywords
    has_action_word = any(word in msg for word in [
        "list", "show", "find", "search", "upload", "download", "create",
        "move", "copy", "trash", "delete", "restore", "star", "unstar",
        "rename", "organize", "share", "permission", "public", "private",
        "revoke", "folder", "file", "duplicate", "version", "history",
        "storage", "quota", "large", "old", "stale", "orphan", "report",
        "insight", "analytic", "summary", "summarize", "breakdown",
        "sort", "count", "how many", "size",
    ])
    has_drive_word = any(word in msg for word in [
        "drive", "file", "folder", "document", "gdrive", "google drive",
        "sheet", "doc", "slide", "pdf", "my drive",
        # Storage / quota terms — unambiguously Drive-specific
        "storage", "quota", "usage", "space", "gb", "mb",
        # Trash / bin
        "trash", "trashed", "bin", "deleted",
        # Starred
        "starred", "starred files",
    ])

    if has_action_word and has_drive_word:
        return None  # Let orchestrator handle it

    # Pure Drive action without explicit "drive" keyword (still pass to orchestrator)
    strong_drive_actions = any(word in msg for word in [
        "upload", "download", "share file", "list files", "find files",
        "search files", "create folder", "move file",
        "storage usage", "storage quota", "disk usage",
        "sharing report", "drive report", "drive health",
        "storage breakdown", "usage insights",
    ])
    if strong_drive_actions:
        return None

    # Conversational — use LLM
    try:
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
            except Exception:
                pass

        llm = get_llm_client()
        name = agent_name or "Drive Assistant"

        system = (
            f"You are {name}, an AI assistant specialising in Google Drive. "
            "You can list files, search, upload, organise folders, share, and analyse storage. "
            "Be concise and friendly."
        )
        if memory_context:
            system += f"\n\nContext about the user:\n{memory_context}"

        response = llm.chat(system_prompt=system, user_message=message)
        return response
    except Exception as e:
        logger.error("handle_conversation error: %s", e)
        return f"Hi! I'm your Drive Assistant. I can help you manage Google Drive files and folders. What would you like to do?"
