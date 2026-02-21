"""
Core agent infrastructure: lifecycle management and process control.
"""

from .agent_manager import AgentManager, get_agent_manager
from .process_manager import (
    start_agent,
    stop_agent,
    get_agent_status,
    cleanup_stale,
    remove_agent_from_state,
)

__all__ = [
    "AgentManager",
    "get_agent_manager",
    "start_agent",
    "stop_agent",
    "get_agent_status",
    "cleanup_stale",
    "remove_agent_from_state",
]
