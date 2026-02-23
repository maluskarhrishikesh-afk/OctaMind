"""
Conversational handler for the Files Agent.

handle_conversation() inspects the user message and either:
  - returns a natural-language response string (conversational intent), or
  - returns None to signal that execute_with_llm_orchestration() should handle it.
"""
from __future__ import annotations

import logging
import os

import streamlit as st

from src.agent.llm.llm_parser import get_llm_client

logger = logging.getLogger("files_agent")

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
    Handle general conversational messages using LLM with memory context.

    Returns a response string if the message is conversational, or None if it
    should be treated as a file system command (handoff to orchestrator).
    """
    try:
        llm = get_llm_client()
        intent = llm.classify_intent(message)
        logger.debug("[Router] intent=%r for message=%.60r", intent, message)
        if intent == "COMMAND":
            return None
    except Exception as e:
        logger.error("Intent classification failed, defaulting to COMMAND: %s", e)
        return None

    # Conversational path — use LLM with memory context
    try:
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
                recalled = memory.recall_for_llm(message)
                if recalled:
                    memory_context += f"\n\n{recalled}"
                    logger.debug("[Memory] Injected episodic recall (%d chars)", len(recalled))
            except Exception as exc:
                logger.warning("Memory load failed: %s", exc)

        history = st.session_state.get("history", [])

        system_prompt = (
            f"You are {agent_name or 'Files Agent'}, an AI assistant that helps users "
            "manage their local files, folders, and drives on their computer. "
            "You can zip files, organise folders, search for files, analyse disk usage, "
            "read file contents, and integrate with Gmail and Google Drive.\n\n"
            + (f"User context:\n{memory_context}" if memory_context else "")
        )

        response = llm.chat(message, system_prompt=system_prompt, history=history)

        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory.add_interaction(message, response)
            except Exception:
                pass

        return response
    except Exception as exc:
        logger.error("handle_conversation failed: %s", exc)
        return None
