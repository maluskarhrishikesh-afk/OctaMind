"""
Conversational handler for the Email Agent.

handle_conversation() inspects the user message and either:
  - returns a natural-language response string (conversational intent), or
  - returns None to signal that execute_with_llm_orchestration() should handle it.
"""
from __future__ import annotations

import logging
import os

import streamlit as st

from src.agent.llm.llm_parser import get_llm_client

logger = logging.getLogger("email_agent")

# Optional memory integration
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
    should be treated as an email command.

    Routing is done by the LLM itself (classify_intent) rather than brittle
    keyword matching, so natural phrasings like "how many emails did I get
    today?" are correctly identified as email commands.
    """
    # ── LLM-based intent routing ───────────────────────────────────────────
    # The LLM understands natural language and won't miss synonyms or
    # paraphrases the way a fixed keyword list does.
    try:
        llm = get_llm_client()
        intent = llm.classify_intent(message)  # uses default email context
        logger.debug(f"[Router] intent={intent!r} for message={message[:60]!r}")
        if intent == "COMMAND":
            return None  # hand off to execute_with_llm_orchestration()
    except Exception as e:
        logger.error(f"Intent classification failed, defaulting to COMMAND: {e}")
        return None  # safe default: try the email orchestrator

    # For conversational messages, use LLM
    try:
        # Get memory context if available
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
                # On-demand recall: inject episodic hits so the LLM can answer
                recalled = memory.recall_for_llm(message)
                if recalled:
                    memory_context += f"\n\n{recalled}"
                    logger.debug(
                        f"[Memory] Injected episodic recall ({len(recalled)} chars)")
            except Exception:
                pass

        # Get conversation history from session state
        conversation_history = []
        if 'chat_messages' in st.session_state:
            for m in st.session_state.chat_messages[-10:]:
                conversation_history.append({
                    'role': m['role'],
                    'content': m['content'],
                })

        if not agent_name:
            agent_name = os.getenv('AGENT_NAME', 'Email Assistant')

        llm = get_llm_client()
        response = llm.chat(
            user_message=message,
            agent_name=agent_name,
            agent_type="Email Agent",
            memory_context=memory_context,
            conversation_history=conversation_history,
        )

        # Record conversational interaction to memory
        if agent_id and MEMORY_AVAILABLE and response:
            try:
                memory = get_agent_memory(agent_id)
                memory.add_interaction(
                    command=message,
                    action="conversation",
                    result={'status': 'success',
                            'message': 'Natural conversation'},
                    metadata={'response_preview': response[:100] if len(
                        response) > 100 else response},
                    importance="Low",
                )
                logger.debug("Recorded conversational interaction to memory")
            except Exception as mem_error:
                logger.error(
                    f"Failed to record conversation to memory: {str(mem_error)}")

        return response

    except Exception as e:
        logger.error(f"LLM conversation error: {str(e)}")
        return (
            "I'm having trouble understanding that right now. "
            "Could you try rephrasing, or ask me to help with your emails?"
        )
