"""
email_agent package — modular sub-components for the OctaMind Email Agent UI.
"""
from .conversation import handle_conversation
from .orchestrator import execute_with_llm_orchestration
from .app import main

__all__ = [
    "handle_conversation",
    "execute_with_llm_orchestration",
    "main",
]
