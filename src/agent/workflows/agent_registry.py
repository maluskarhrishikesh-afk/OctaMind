"""
Agent Registry — single source of truth for which agents exist.

Adding a new agent = add one entry to AGENT_REGISTRY.
The orchestrator and planner stay unchanged regardless of agent count.

Context cost: ~10 tokens per agent (description only), not per tool.
With 10 agents: ~100 tokens for planning context   (vs ~8,000 tokens with the old flat tool list).
"""
from __future__ import annotations

import importlib
import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger("workflows")


# ---------------------------------------------------------------------------
# Registry
# Each entry: {
#   "description": one-sentence capability summary for the planning LLM,
#   "module":      dotted module path to the orchestrator,
#   "function":    name of the execute_with_llm_orchestration function,
# }
# ---------------------------------------------------------------------------
AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    "drive": {
        "description": (
            "Google Drive agent. Handles: search/list/download/upload files, "
            "create/move/copy/trash/restore folders and files, share and manage "
            "permissions, summarize content, find duplicates, auto-organize, "
            "bulk rename, version history, and storage analytics."
        ),
        "module": "src.agent.ui.drive_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "email": {
        "description": (
            "Gmail agent. Handles: read/search/count emails, send/reply/forward, "
            "create/send drafts, download attachments, schedule emails, extract "
            "action items and calendar events, set follow-up reminders, "
            "auto-categorize and label, detect urgent/newsletter emails, "
            "manage contacts, and generate email reports."
        ),
        "module": "src.agent.ui.email_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    # ── Add future agents here, e.g.: ───────────────────────────────────────
    # "calendar": {
    #     "description": "Google Calendar agent. Handles: create/read/update/delete events...",
    #     "module": "src.agent.ui.calendar_agent.orchestrator",
    #     "function": "execute_with_llm_orchestration",
    # },
}


def get_capabilities_text() -> str:
    """
    Return a compact per-agent capabilities block for use in the planning prompt.

    Example output (2 agents, ~40 tokens):
        drive: Google Drive agent. Handles: search/list/download/upload files...
        email: Gmail agent. Handles: read/search/count emails, send/reply/forward...
    """
    lines = [f"{name}: {info['description']}" for name, info in AGENT_REGISTRY.items()]
    return "\n".join(lines)


def get_executor(agent_name: str) -> Optional[Callable]:
    """
    Dynamically import and return the execute_with_llm_orchestration callable
    for the named agent.  Returns None if the agent is not registered.
    """
    info = AGENT_REGISTRY.get(agent_name)
    if info is None:
        logger.warning("Agent '%s' not found in registry", agent_name)
        return None
    try:
        mod = importlib.import_module(info["module"])
        fn = getattr(mod, info["function"])
        return fn
    except Exception as exc:
        logger.error("Failed to load executor for agent '%s': %s", agent_name, exc)
        return None


def registered_agents() -> list[str]:
    """Return the list of registered agent names."""
    return list(AGENT_REGISTRY.keys())
