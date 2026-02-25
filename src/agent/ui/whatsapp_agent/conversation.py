"""
Conversational handler for the WhatsApp Agent.

handle_conversation() inspects the user message and either:
  - returns a natural-language response string (conversational intent), or
  - returns None to signal that execute_with_llm_orchestration() should handle it.
"""
from __future__ import annotations

import logging
import os

import streamlit as st

from src.agent.llm.llm_parser import get_llm_client

logger = logging.getLogger("whatsapp_agent")

# Skills are stateless executors — memory belongs to Personal Assistants only.


def handle_conversation(
    message: str,
    agent_id: str = None,
    agent_name: str = None,
) -> str | None:
    """
    Handle general conversational messages using LLM with memory context.

    Returns a response string if the message is conversational, or None if it
    should be treated as a WhatsApp command (handoff to orchestrator).

    Intent routing is LLM-based — no brittle keyword matching.
    """
    try:
        llm = get_llm_client()
        intent = llm.classify_intent(message)
        logger.debug("[Router] intent=%r for message=%.60r", intent, message)
        if intent == "COMMAND":
            return None  # hand off to execute_with_llm_orchestration()
    except Exception as e:
        logger.error("Intent classification failed, defaulting to COMMAND: %s", e)
        return None

    # Conversational path — use LLM (stateless, no memory)
    try:
        # Skills are stateless — no memory context
        memory_context = ""

        conversation_history = []
        if "chat_messages" in st.session_state:
            for m in st.session_state.chat_messages[-10:]:
                conversation_history.append({
                    "role": m["role"],
                    "content": m["content"],
                })

        if not agent_name:
            agent_name = os.getenv("AGENT_NAME", "WhatsApp Assistant")

        response = llm.chat(
            user_message=message,
            agent_name=agent_name,
            agent_type="WhatsApp Agent",
            memory_context=memory_context,
            conversation_history=conversation_history,
        )

        return response

    except Exception as e:
        logger.error("LLM conversation error: %s", e)
        return (
            "I'm having trouble understanding that right now. "
            "Could you try rephrasing, or ask me to help with your WhatsApp messages?"
        )
