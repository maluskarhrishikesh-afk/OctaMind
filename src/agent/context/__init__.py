"""
Agent conversation state tracking.

Provides structured JSON context that is injected into every skill-agent query
so that resolved entities (dates, files, recipients …) are never lost between
turns in a multi-message conversation.
"""
from .conversation_state import ConversationStateTracker, build_structured_query

__all__ = ["ConversationStateTracker", "build_structured_query"]
