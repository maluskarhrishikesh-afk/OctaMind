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

# Skills are stateless executors — memory belongs to Personal Assistants only.


def handle_conversation(
    message: str,
    agent_id: str = None,
    agent_name: str = None,
) -> str | None:
    """
    Handle conversational messages.

    Returns a response string if the message is conversational,
    or None if it should be treated as a Drive command.

    Routing is done by the LLM (classify_intent) rather than brittle keyword
    matching, so natural phrasings are correctly identified as Drive commands.
    """
    # ── LLM-based intent routing ───────────────────────────────────────────
    _DRIVE_CONTEXT = (
        "listing, searching, uploading, downloading, creating, moving, deleting, "
        "sharing, organising, or otherwise interacting with the user's Google Drive "
        "files, folders, documents, storage quota, or permissions"
    )
    try:
        llm = get_llm_client()
        intent = llm.classify_intent(message, agent_context=_DRIVE_CONTEXT)
        logger.debug(f"[Router] intent={intent!r} for message={message[:60]!r}")
        if intent == "COMMAND":
            return None  # Let orchestrator handle it
    except Exception as e:
        logger.error(f"Intent classification failed, defaulting to COMMAND: {e}")
        return None  # safe default: try the drive orchestrator

    # Conversational — use LLM (stateless, no memory)
    try:
        # Skills are stateless — no memory context
        memory_context = ""

        # Conversation history for short-term continuity
        conversation_history = []
        if "chat_messages" in st.session_state:
            for m in st.session_state.chat_messages[-10:]:
                conversation_history.append(
                    {"role": m["role"], "content": m["content"]})

        if not agent_name:
            agent_name = os.getenv("AGENT_NAME", "Drive Assistant")

        llm = get_llm_client()
        response = llm.chat(
            user_message=message,
            agent_name=agent_name,
            agent_type="Google Drive Agent",
            memory_context=memory_context,
            conversation_history=conversation_history,
        )

        return response
    except Exception as e:
        logger.error("handle_conversation error: %s", e)
        return (
            "Hi! I'm your Drive Assistant. I can help you manage Google Drive "
            "files and folders. What would you like to do?"
        )
