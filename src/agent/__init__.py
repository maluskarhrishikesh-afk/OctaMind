"""
Agent Module

Sub-packages
------------
core/    – AgentManager, ProcessManager (agent lifecycle & process control)
memory/  – AgentMemory, MemoryConsolidator (multi-layer memory system)
llm/     – GitHubModelsLLM, Gemma runner, model downloader (LLM backends)
ui/      – Streamlit dashboards and chat interfaces
"""

from .core.agent_manager import AgentManager, get_agent_manager
from .core.process_manager import (
    start_agent,
    stop_agent,
    get_agent_status,
    cleanup_stale,
    remove_agent_from_state,
)
from .memory.agent_memory import AgentMemory, get_agent_memory
from .memory.memory_consolidator import MemoryConsolidator
from .llm.llm_parser import GitHubModelsLLM, get_llm_client
from .llm.model_downloader import download_gemma, HARD_CODED_HF_TOKEN

__all__ = [
    # core
    "AgentManager",
    "get_agent_manager",
    "start_agent",
    "stop_agent",
    "get_agent_status",
    "cleanup_stale",
    "remove_agent_from_state",
    # memory
    "AgentMemory",
    "get_agent_memory",
    "MemoryConsolidator",
    # llm
    "GitHubModelsLLM",
    "get_llm_client",
    "download_gemma",
    "HARD_CODED_HF_TOKEN",
]
