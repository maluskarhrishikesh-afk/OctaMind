"""
Collective Memory — aggregates episodic memory from all registered agents.

The Multi-Agent Hub uses this to give the LLM awareness of everything every
agent has done, creating a shared cross-agent context across the platform.

Usage:
    from src.agent.memory.collective_memory import get_collective_context
    context = get_collective_context()
    # pass as memory_context to llm.chat()
"""

from __future__ import annotations

import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_AGENTS_JSON = _PROJECT_ROOT / "agents.json"
_RUNNING_JSON = _PROJECT_ROOT / "running_agents.json"
_MEMORY_BASE = _PROJECT_ROOT / "memory"

# How much of each agent's episodic memory to include (last N chars = most recent)
_MAX_CHARS_PER_AGENT = 1500
# How much of the multi-agent's own memory to include
_MAX_CHARS_OWN = 800


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def get_collective_context(
    max_chars_per_agent: int = _MAX_CHARS_PER_AGENT,
    include_own: bool = True,
) -> str:
    """
    Read recent episodic memories from every agent registered in agents.json,
    plus the multi-agent hub's own memory, and return a combined context string.

    The context tells the LLM:
    - Which agents exist and whether they are currently running
    - What each agent has done recently (from their episodic_memory.md)

    Args:
        max_chars_per_agent: Max characters to pull from each agent's episodic
                             memory (takes from the end = most recent events).
        include_own:         Whether to also include _collective_memory_ own memory.
    Returns:
        A multi-section markdown string ready to inject into llm.chat() as
        memory_context.
    """
    sections: list[str] = []

    # ── Load registered agents ────────────────────────────────────────────────
    agents_data = _load_json(_AGENTS_JSON)
    agents: list[dict] = agents_data.get("agents", [])
    if not agents:
        return ""

    # ── Load running state ────────────────────────────────────────────────────
    running_state: dict = _load_json(_RUNNING_JSON)

    sections.append("## Collective Agent Memory\n")
    sections.append(
        f"You have access to {len(agents)} registered agent(s). "
        f"Their recent activities are shown below.\n"
    )

    # ── Per-agent episodic snapshots ──────────────────────────────────────────
    for agent in agents:
        agent_id: str = agent.get("id", "")
        agent_name: str = agent.get("name", agent_id)
        icon: str = agent.get("metadata", {}).get("icon", "🤖")
        type_name: str = agent.get("metadata", {}).get("name", agent.get("type", "Agent"))
        is_running: bool = agent_id in running_state

        status_label = "🟢 Running" if is_running else "⚫ Stopped"
        sections.append(
            f"### {icon} {agent_name} ({type_name}) — {status_label}"
        )

        episodic_path = _MEMORY_BASE / agent_id / "episodic_memory.md"
        if episodic_path.exists():
            try:
                content = episodic_path.read_text(encoding="utf-8")
                # Strip the markdown header at top (boilerplate)
                if "##" in content:
                    # Keep only the events section
                    first_event = content.find("### ")
                    if first_event > 0:
                        content = content[first_event:]

                # Take the last N characters (most recent events are at bottom)
                if len(content) > max_chars_per_agent:
                    content = "...(earlier events omitted)...\n\n" + content[-max_chars_per_agent:]

                sections.append(content.strip())
            except Exception as exc:
                sections.append(f"(Memory unreadable: {exc})")
        else:
            sections.append("(No activity recorded yet)")

        sections.append("")  # blank line between agents

    # ── Multi-agent own memory ────────────────────────────────────────────────
    if include_own:
        own_id = "_collective_memory_"
        own_path = _MEMORY_BASE / own_id / "episodic_memory.md"
        if own_path.exists():
            try:
                own_content = own_path.read_text(encoding="utf-8")
                if len(own_content) > _MAX_CHARS_OWN:
                    own_content = "...\n" + own_content[-_MAX_CHARS_OWN:]
                if own_content.strip():
                    sections.append("### ⚡ Personal Assistant — My own workflow history")
                    sections.append(own_content.strip())
                    sections.append("")
            except Exception:
                pass

    return "\n".join(sections)


def get_running_agent_names() -> list[str]:
    """Return display names of all currently-running agents (excluding multi-agent)."""
    agents_data = _load_json(_AGENTS_JSON)
    agents: list[dict] = agents_data.get("agents", [])
    running_state: dict = _load_json(_RUNNING_JSON)

    names = []
    for agent in agents:
        aid = agent.get("id", "")
        if aid in running_state:
            names.append(agent.get("name", aid))
    return names
