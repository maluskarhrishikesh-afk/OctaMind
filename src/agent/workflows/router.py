"""
Router — decides which agents a user command needs.

Fully dynamic: agent knowledge comes entirely from AGENT_REGISTRY.
Adding a new agent requires ONLY an entry in agent_registry.py —
this file never needs to change.

Strategy:
1. Build the routing prompt at runtime from the registry descriptions.
2. Ask the LLM to return a JSON array of agent names, e.g. ["files"] or
   ["drive", "email"] or [] for pure conversation.
3. If the LLM is unavailable, fall back to a keyword scan built dynamically
   from the same registry descriptions.

Usage:
    agents = detect_agents_needed("zip Images and upload to Drive, then mail me")
    # → ["files", "drive", "email"]
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, FrozenSet, List, Optional

logger = logging.getLogger("workflows")

# ---------------------------------------------------------------------------
# Dynamic keyword fallback — built once from the registry at import time.
# Each agent gets a frozenset of significant words extracted from its description.
# No words are hardcoded here.
# ---------------------------------------------------------------------------

# Common English stop-words to skip when extracting capability keywords
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "to", "in", "for", "on",
        "with", "by", "from", "at", "is", "are", "be", "as", "it",
        "its", "this", "that", "also", "both", "all", "any", "can",
        "set", "get", "use", "per", "via", "new", "add", "own",
        "handles", "handle", "agent", "operations", "manage", "find",
    }
)


def _build_keyword_map() -> Dict[str, FrozenSet[str]]:
    """
    Extract significant words from each agent's description in the registry
    and return a dict: {agent_name → frozenset of keywords}.
    Called lazily the first time the fallback is needed.
    """
    from src.agent.workflows.agent_registry import AGENT_REGISTRY
    keyword_map: Dict[str, FrozenSet[str]] = {}
    for name, info in AGENT_REGISTRY.items():
        desc = info.get("description", "")
        # Split on non-alpha chars, lowercase, remove stop-words and short tokens
        words = frozenset(
            w for w in re.findall(r"[a-z]{3,}", desc.lower())
            if w not in _STOP_WORDS
        )
        keyword_map[name] = words
        logger.debug("Router keyword map [%s]: %s", name, sorted(words))
    return keyword_map


_KEYWORD_MAP: Optional[Dict[str, FrozenSet[str]]] = None


def _get_keyword_map() -> Dict[str, FrozenSet[str]]:
    global _KEYWORD_MAP
    if _KEYWORD_MAP is None:
        _KEYWORD_MAP = _build_keyword_map()
    return _KEYWORD_MAP


# ---------------------------------------------------------------------------
# LLM prompt builder — fully driven by the registry
# ---------------------------------------------------------------------------

def _build_routing_prompt(command: str) -> str:
    """
    Construct a routing prompt that lists every registered agent and its
    capabilities, then asks the LLM to return a JSON array of needed agents.
    """
    from src.agent.workflows.agent_registry import AGENT_REGISTRY

    agent_lines = "\n".join(
        f'  "{name}": {info["description"]}'
        for name, info in AGENT_REGISTRY.items()
    )
    valid_names = json.dumps(list(AGENT_REGISTRY.keys()))

    return f"""\
You are a command router for a multi-agent AI system.

Available agents:
{agent_lines}

Your job: read the user command and return a JSON array of agent names that are \
needed to fully complete it.

Rules:
- Only use names from this list: {valid_names}
- Return [] (empty array) if no agent is needed (pure conversation / small talk)
- Return multiple agents when the command spans more than one agent's capabilities
- Return agents in the order they should logically execute
- Output ONLY the JSON array — no explanation, no markdown, no extra text

Examples:
  "how are you?" → []
  "send an email to bob" → ["email"]
  "zip my Downloads folder" → ["files"]
  "zip the report and upload it to Drive" → ["files", "drive"]
  "zip folder, upload to Drive, then mail me" → ["files", "drive", "email"]

Command: {command}
Answer:"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def keyword_pre_filter(command: str) -> bool:
    """
    Fast keyword pre-filter — runs BEFORE any LLM call.

    Returns
    -------
    True   — at least one agent keyword found; proceed to LLM routing.
    False  — zero agent keyword matches; command is almost certainly
             conversational (casual chat, small talk).  Skip the LLM
             routing call entirely and return None from detect_agents_needed().

    This saves one LLM call per request for casual queries such as
    "How are you?", "What time is it?", "Tell me a joke", etc.
    """
    kmap = _get_keyword_map()
    lower = command.lower()
    cmd_words = set(re.findall(r"[a-z]{3,}", lower))
    matched = any(keywords & cmd_words for keywords in kmap.values())
    if not matched:
        logger.debug("Router [pre-filter]: no agent keywords found — skipping LLM call")
    return matched


def detect_agents_needed(command: str) -> Optional[List[str]]:
    """
    Analyse *command* and return the list of agents required.

    Strategy (ordered by cost):
      1. Keyword pre-filter (0 LLM calls) — if no agent keywords found,
         skip the LLM call and return None immediately.
      2. LLM-based detection (1 LLM call) — accurate routing for
         commands that contain at least one agent keyword.
      3. Keyword fallback (0 LLM calls) — if LLM call fails, use the
         keyword match result.

    Returns
    -------
    List of agent names (e.g. ["drive", "email"]) — agents needed.
    None — no agent needed; treat as conversational.
    """
    from src.agent.workflows.agent_registry import registered_agents

    valid = set(registered_agents())

    # ── Step 1: keyword pre-filter (0 LLM calls) ────────────────────────────
    if not keyword_pre_filter(command):
        logger.info("Router [pre-filter]: no agent keywords — returning None (conversational)")
        return None

    # ── Step 2: LLM-based detection (1 LLM call) ────────────────────────────
    try:
        from src.agent.llm.llm_parser import get_llm_client
        llm = get_llm_client()

        prompt = _build_routing_prompt(command)
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()

        # Parse JSON array, be tolerant of trailing punctuation
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"Expected list, got: {type(parsed)}")

        # Validate every name against the live registry
        agents = [a.lower() for a in parsed if a.lower() in valid]

        if not agents:
            logger.info("Router [LLM]: no agents needed — conversational")
            return None

        logger.info("Router [LLM]: %s", agents)
        return agents

    except Exception as exc:
        logger.warning("Router LLM classification failed (%s), falling back to keywords", exc)

    # ── Step 3: Keyword fallback (0 LLM calls) ──────────────────────────────
    # Only reached when the LLM call above raised an exception.
    # We already know keyword_pre_filter() returned True (otherwise we
    # returned None in step 1), so there is at least one keyword match here.
    kmap = _get_keyword_map()
    lower = command.lower()
    cmd_words = set(re.findall(r"[a-z]{3,}", lower))

    matched: List[str] = [
        agent for agent, keywords in kmap.items()
        if keywords & cmd_words
    ]

    if not matched:
        return None

    logger.info("Router [keywords]: %s", matched)
    return matched if len(matched) > 0 else None


def describe_routing(command: str) -> dict:
    """Return a debug-friendly dict showing the routing decision (for testing/logging)."""
    kmap = _get_keyword_map()
    lower = command.lower()
    cmd_words = set(re.findall(r"[a-z]{3,}", lower))
    keyword_hits = {
        agent: sorted(keywords & cmd_words)
        for agent, keywords in kmap.items()
        if keywords & cmd_words
    }
    agents = detect_agents_needed(command)
    return {
        "command": command,
        "keyword_hits_per_agent": keyword_hits,
        "routing_decision": agents or [],
    }
