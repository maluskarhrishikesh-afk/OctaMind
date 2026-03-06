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
from dataclasses import dataclass, field
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
        # Articles / prepositions / conjunctions
        "a", "an", "the", "and", "or", "of", "to", "in", "for", "on",
        "with", "by", "from", "at", "as", "its", "this", "that", "also",
        "both", "all", "any", "per", "via",
        # Very common verbs / adjectives that leak into descriptions
        "is", "are", "be", "can", "will", "not", "never",
        "use", "get", "set", "run", "add", "own",
        "new", "old",
        # Words that appear in MANY agent descriptions and would cause
        # false-positive routing matches on generic user queries
        "about",   # "about ORGANIZING" — matches "Do you know about cricket?"
        "when",    # "when the user asks"
        "your",    # various descriptions
        "user",    # nearly every description
        "users",
        "agent",
        "handles", "handle",
        "operations", "operation",
        "manage",  "find",
    }
)


def _build_keyword_map() -> Dict[str, FrozenSet[str]]:
    """
    Extract significant words from each agent's description in the registry
    and return a dict: {agent_name → frozenset of keywords}.
    Also merges in the curated ``trigger_keywords`` list so hand-picked terms
    (e.g. "payslip", "whatsapp", "rsi") are always present regardless of
    how many agents mention similar words.
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
        # Curated trigger_keywords are unioned in directly (multi-word phrases are
        # split into tokens, e.g. "google drive" → {"google", "drive"})
        trigger_kw = frozenset(
            w
            for kw in info.get("trigger_keywords", [])
            for w in re.findall(r"[a-z]{3,}", kw.lower())
        )
        keyword_map[name] = words | trigger_kw
        logger.debug("Router keyword map [%s]: %s", name, sorted(keyword_map[name]))
    return keyword_map


_KEYWORD_MAP: Optional[Dict[str, FrozenSet[str]]] = None


def _get_keyword_map() -> Dict[str, FrozenSet[str]]:
    global _KEYWORD_MAP
    if _KEYWORD_MAP is None:
        _KEYWORD_MAP = _build_keyword_map()
    return _KEYWORD_MAP


# ── IDF-filtered "distinctive" keyword map — used by classify_and_route ─────
# Only keeps words that appear in ≤ 30 % of agent descriptions.  Generic words
# like "files" (found in 6+ descriptions) are excluded so they can't cause a
# false-positive multi-agent result when the LLM is unavailable.

_DISTINCTIVE_KEYWORD_MAP: Optional[Dict[str, FrozenSet[str]]] = None


def _build_distinctive_keyword_map() -> Dict[str, FrozenSet[str]]:
    from collections import Counter
    from src.agent.workflows.agent_registry import AGENT_REGISTRY

    # Build raw keyword sets first (same logic as _build_keyword_map)
    raw_map: Dict[str, FrozenSet[str]] = {}
    for name, info in AGENT_REGISTRY.items():
        desc = info.get("description", "")
        words = frozenset(
            w for w in re.findall(r"[a-z]{3,}", desc.lower())
            if w not in _STOP_WORDS
        )
        raw_map[name] = words

    # Count how many agents each word appears in (document frequency)
    n_agents = len(raw_map)
    word_freq: Counter = Counter(w for kws in raw_map.values() for w in kws)

    # Drop words that appear in more than 30 % of agents — too generic to route
    max_freq = max(1, round(n_agents * 0.30))
    common_words = {w for w, cnt in word_freq.items() if cnt > max_freq}
    logger.debug("Router [distinctive map]: filtering %d generic words: %s",
                 len(common_words), sorted(common_words))

    result: Dict[str, FrozenSet[str]] = {}
    for name, kws in raw_map.items():
        # Always keep the agent's own name-derived tokens as distinctive keywords
        # regardless of IDF score.  This means a user saying "email ...", "files ...",
        # "calendar ..." etc. will always uniquely route to the right agent.
        name_tokens = frozenset(re.findall(r"[a-z]{3,}", name.lower()))
        # Curated trigger_keywords are ALWAYS distinctive — they bypass the IDF filter
        # entirely.  This prevents high-frequency words like "file" or "email" from
        # being silently dropped when they appear in many agent descriptions.
        info = AGENT_REGISTRY.get(name, {})
        trigger_kw = frozenset(
            w
            for kw in info.get("trigger_keywords", [])
            for w in re.findall(r"[a-z]{3,}", kw.lower())
        )
        result[name] = (kws - common_words) | name_tokens | trigger_kw
        logger.debug("Router [distinctive map] [%s]: %s", name, sorted(result[name]))
    return result


def _get_distinctive_keyword_map() -> Dict[str, FrozenSet[str]]:
    global _DISTINCTIVE_KEYWORD_MAP
    if _DISTINCTIVE_KEYWORD_MAP is None:
        _DISTINCTIVE_KEYWORD_MAP = _build_distinctive_keyword_map()
    return _DISTINCTIVE_KEYWORD_MAP


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
  "copy them to a folder" → ["files"]
  "put those files in OctaMind" → ["files"]
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


# ---------------------------------------------------------------------------
# Unified intent classification  (classify_and_route)
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    """
    Unified result from intent classification and routing.

    category:
        "chat"              — pure conversation, no agents or tools needed.
        "context_followup"  — the user is acting on results from the previous
                              turn (pronouns like "them/that/those", short
                              action commands referencing earlier output).
        "fresh_task"        — a new actionable request for specific agent(s).

    agents:
        The list of agent names to invoke.  Empty for "chat".

    reason:
        A short explanation string for log/debug purposes only.
    """
    category: str             # "chat" | "context_followup" | "fresh_task"
    agents: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def is_chat(self) -> bool:
        return self.category == "chat"

    @property
    def is_context_followup(self) -> bool:
        return self.category == "context_followup"

    @property
    def is_fresh_task(self) -> bool:
        return self.category == "fresh_task"


def _build_intent_prompt(
    command: str,
    active_context: Optional[dict],
    session_state: Optional[dict],
    agent_registry: dict,
) -> str:
    """Build the unified intent-routing prompt for the LLM."""
    agent_lines = "\n".join(
        f'  "{name}": {info["description"]}'
        for name, info in agent_registry.items()
    )
    valid_names = json.dumps(list(agent_registry.keys()))

    # --- Active context block ------------------------------------------------
    if active_context:
        ctx_agent    = active_context.get("agent", "?")
        ctx_topic    = active_context.get("topic", "?")
        ctx_awaiting = active_context.get("awaiting", "?")
        ctx_entities = active_context.get("resolved_entities", {})
        entities_str = json.dumps(ctx_entities, ensure_ascii=False)[:500]
        context_block = (
            f"ACTIVE — source_agent={ctx_agent} | topic={ctx_topic} | "
            f"awaiting={ctx_awaiting}\n"
            f"data: {entities_str}"
        )
    else:
        context_block = "(none — no active context from previous turn)"

    # --- Session state block -------------------------------------------------
    state_block = "(none)"
    if session_state:
        relevant = {
            k: v for k, v in session_state.items()
            if k in ("last_found_paths", "last_found_folder", "last_assistant_action") and v
        }
        if relevant:
            state_block = json.dumps(relevant, ensure_ascii=False)[:400]

    return f"""\
You are the intent router for a multi-agent AI personal assistant.
Classify the user's message into exactly one category, then list which agents are needed.

## Active Context (from previous assistant turn)
{context_block}

## Session State (extracted facts)
{state_block}

## Available Agents
{agent_lines}

## Three Categories

─── CHAT ────────────────────────────────────────────────────────────────────
Pure conversation — no file, email, calendar, or tool actions needed.
→ "Do you know about cricket?"
→ "Tell me a joke"
→ "Explain quantum physics"
→ Any question not requiring access to the user's data or systems
agents must be [] for CHAT.

─── CONTEXT_FOLLOWUP ────────────────────────────────────────────────────────
The user is acting on results from the PREVIOUS turn.
REQUIRES: active context above is ACTIVE (not "(none)").
Signals: pronouns ("that", "them", "those", "it", "these"), short action commands
that refer to something already found/listed/searched.
→ "Can you zip that and send it to me?" (after finding files)        → ["files","email"]
→ "Copy them to my Downloads folder" (after finding files)           → ["files"]
→ "Reply to the first one" (after listing emails)                    → ["email"]
→ "Book the 2 PM slot" (after listing calendar free slots)           → ["scheduler"]
→ "Can you update me on my search?" (after file search)              → ["files"]
→ "Send those to alice@example.com" (after finding files)            → ["files","email"]
For CONTEXT_FOLLOWUP: include the source agent from context PLUS any new agent the
action requires (e.g. context files + "send it to me" → ["files","email"]).

─── FRESH_TASK ──────────────────────────────────────────────────────────────
A new actionable request for specific agents. No pronouns referring to prior results.
→ "Are there any payslip files on my computer?"                      → ["files"]
→ "Find my resume and email it to hr@company.com"                    → ["files","email"]
→ "What are my unread emails?"                                       → ["email"]
→ "What meetings do I have tomorrow?"                                → ["scheduler"]
→ "Download the Q3 report from Google Drive"                         → ["drive"]
→ "Search for all .txt files and zip them"                           → ["files"]

## Rules
1. NEVER return "context_followup" when active context is "(none)".
2. Return "chat" for pure conversation — no agents needed.
3. Only include agent names from: {valid_names}
4. If unsure between fresh_task and context_followup and context IS active,
   prefer context_followup for short commands with pronouns.

Return ONLY a single-line JSON object (no markdown, no explanation):
{{"category": "chat|context_followup|fresh_task", "agents": [...], "reason": "one sentence"}}

User message: {command}"""


def classify_and_route(
    command: str,
    active_context: Optional[dict] = None,
    session_state: Optional[dict] = None,
) -> IntentResult:
    """
    Unified intent classification + agent routing.

    Single entry point that replaces ``detect_agents_needed()`` plus all
    bolt-on override logic.  Handles three message patterns:

    CHAT              "Do you know about cricket?"
                      → pure conversation, no agents
    CONTEXT_FOLLOWUP  "Can you zip that and mail it to me?" (after search)
                      → acts on previous turn's result, routes to found-file agents
    FRESH_TASK        "Are there any payslip files on my computer?"
                      → new request, routes to appropriate agent(s)

    Parameters
    ----------
    command:        The user's message (after scheduling enrichment).
    active_context: Live context manifest from ``read_context()``, or None.
    session_state:  Extracted state from ``ConversationStateTracker.build()``, or None.

    Returns
    -------
    IntentResult
    """
    from src.agent.workflows.agent_registry import AGENT_REGISTRY, registered_agents

    valid = set(registered_agents())

    # ── Fast-path: no context + no agent keywords → definite chat ────────────
    # Saves one LLM call for the very common "casual question" case.
    if active_context is None and not keyword_pre_filter(command):
        logger.info("Router [fast-path]: no context, no agent keywords → chat")
        return IntentResult(
            category="chat",
            agents=[],
            reason="fast-path: no agent keywords and no active context",
        )

    # ── LLM three-way classification ─────────────────────────────────────────
    try:
        from src.agent.llm.llm_parser import get_llm_client

        prompt = _build_intent_prompt(command, active_context, session_state, AGENT_REGISTRY)
        llm = get_llm_client()
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        # Tolerate models that wrap the JSON in code fences
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        parsed = json.loads(raw)

        category = parsed.get("category", "").lower().replace("-", "_")
        if category not in ("chat", "context_followup", "fresh_task"):
            raise ValueError(f"Unexpected category: {category!r}")

        agents = [a.lower() for a in parsed.get("agents", []) if a.lower() in valid]
        reason = parsed.get("reason", "")

        # Safety guards ---------------------------------------------------
        # 1. LLM returned context_followup but no active context exists
        if category == "context_followup" and active_context is None:
            logger.warning(
                "Router: LLM returned context_followup but no active context — "
                "demoting to fresh_task"
            )
            category = "fresh_task"

        # 2. context_followup with empty agents → default to context source agent
        if category == "context_followup" and not agents and active_context:
            ctx_agent = active_context.get("agent", "")
            if ctx_agent and ctx_agent in valid:
                agents = [ctx_agent]

        logger.info(
            "Router [intent]: category=%s  agents=%s  reason=%s",
            category, agents, reason,
        )
        return IntentResult(category=category, agents=agents, reason=reason)

    except Exception as exc:
        logger.warning("Intent classification failed (%s) — using keyword fallback", exc)

    # ── Keyword fallback (LLM call failed) ───────────────────────────────────
    # Use the broad map for matching (preserves "files", "email" etc.) but
    # deduplicate with the IDF-filtered distinctive map: if an agent appears in
    # both maps it gets a bonus score, preferring it over agents that only
    # matched a generic word from the broad map.
    kmap = _get_keyword_map()
    dmap = _get_distinctive_keyword_map()
    lower = command.lower()
    cmd_words = set(re.findall(r"[a-z]{3,}", lower))
    broad_agents = [ag for ag, kws in kmap.items() if kws & cmd_words]

    # Prefer agents that also match on DISTINCTIVE keywords (IDF-filtered).
    # This handles "payslip files" matching 6 agents through "files" — we keep
    # only the ones with a stronger (non-generic) signal from the distinctive map.
    if len(broad_agents) > 1:
        distinctive_agents = [ag for ag in broad_agents if dmap.get(ag, frozenset()) & cmd_words]
        if distinctive_agents:
            agents = distinctive_agents
            logger.info(
                "Router [keyword fallback]: narrowed %s → %s via distinctive map",
                broad_agents, distinctive_agents,
            )
        else:
            # All matched only via generic words — keep the most likely one
            # (files > drive > email > whatsapp by default preference order)
            _preference = ["files", "email", "calendar", "drive", "whatsapp",
                           "file_organizer", "habit_tracker", "browser",
                           "stock_market", "linkedin", "scheduler"]
            agents = sorted(broad_agents, key=lambda a: _preference.index(a)
                            if a in _preference else 999)[:1]
            logger.info(
                "Router [keyword fallback]: all generic matches %s → picking %s",
                broad_agents, agents,
            )
    else:
        agents = broad_agents

    # If context is active and the command has a pronoun, treat as follow-up
    if active_context and not agents:
        _pronoun_pat = re.compile(
            r"\b(them|those|it|that|these|the files|the folder|the ones)\b",
            re.IGNORECASE,
        )
        if _pronoun_pat.search(command):
            ctx_agent = active_context.get("agent", "")
            if ctx_agent and ctx_agent in valid:
                logger.info("Router [keyword fallback]: pronoun + active context → context_followup")
                return IntentResult(
                    category="context_followup",
                    agents=[ctx_agent],
                    reason="keyword fallback: pronoun + active context",
                )

    category = "fresh_task" if agents else "chat"
    logger.info("Router [keyword fallback]: category=%s  agents=%s", category, agents)
    return IntentResult(category=category, agents=agents, reason="keyword fallback")
