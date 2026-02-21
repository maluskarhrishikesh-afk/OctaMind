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
    """
    msg = message.strip().lower()

    # If message contains email-specific actions, let the LLM orchestrator handle it
    has_action_word = any(keyword in msg for keyword in [
        'count', 'list', 'show', 'send', 'delete', 'summarize', 'digest',
        'fetch', 'get', 'retrieve', 'find', 'read', 'check', 'view', 'display',
        'draft', 'attachment', 'schedule', 'followup', 'follow-up', 'follow up',
        'categorize', 'category', 'label', 'calendar', 'meeting', 'event',
        'priority', 'urgent', 'reply', 'analytics', 'stats', 'statistics',
        'contact', 'unsubscribe', 'newsletter', 'action item', 'task',
        'remind', 'unanswered', 'pending', 'insight', 'download', 'attach',
        'vip', 'export', 'complete', 'mark done', 'filter', 'rule', 'ics',
        'report', 'weekly', 'patterns', 'chart', 'visualize', 'response time',
        'reschedule', 'dismiss', 'reminder',
        'frequent', 'most often', 'top sender', 'top contact',
    ])
    has_email_word = any(keyword in msg for keyword in [
        'email', 'inbox', 'message', 'unread', 'gmail',
        'mail', 'sent', 'received', 'draft', 'folder',
        'contact', 'contacts', 'csv', 'json', 'sender', 'senders',
    ])

    if has_action_word and has_email_word:
        return None  # Let command parser handle it

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
