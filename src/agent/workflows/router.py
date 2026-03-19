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
# Dynamic keyword fallback — built from curated trigger keywords and
# agent-name tokens. Free-text descriptions stay useful for the LLM prompt,
# but they are too noisy for deterministic fallback routing.
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
    Build a dict: {agent_name → frozenset of deterministic routing keywords}.

    The fallback router intentionally uses ONLY curated trigger keywords plus
    agent-name tokens. Description text is excluded here because cross-agent
    descriptions contain noisy words like "list", "show", "image", "email",
    and delivery examples that cause false multi-agent matches.

    Called lazily the first time the fallback is needed.
    """
    from src.agent.workflows.agent_registry import AGENT_REGISTRY
    keyword_map: Dict[str, FrozenSet[str]] = {}
    for name, info in AGENT_REGISTRY.items():
        trigger_kw = frozenset(
            w
            for kw in info.get("trigger_keywords", [])
            for w in re.findall(r"[a-z]{3,}", kw.lower())
        )
        name_tokens = frozenset(re.findall(r"[a-z]{3,}", name.lower()))
        keyword_map[name] = trigger_kw | name_tokens
        logger.debug("Router keyword map [%s]: %s", name, sorted(keyword_map[name]))
    return keyword_map


_KEYWORD_MAP: Optional[Dict[str, FrozenSet[str]]] = None

_FRESHNESS_CUES: FrozenSet[str] = frozenset(
    {
        "latest",
        "current",
        "recent",
        "today",
        "now",
        "news",
        "headline",
        "headlines",
        "update",
        "updates",
        "won",
        "winner",
        "results",
        "score",
    }
)

_FIRST_PARTY_DATA_HINTS: FrozenSet[str] = frozenset(
    {
        "email",
        "emails",
        "mail",
        "gmail",
        "inbox",
        "outbox",
        "attachment",
        "attachments",
        "calendar",
        "meeting",
        "meetings",
        "event",
        "events",
        "drive",
        "gdrive",
        "file",
        "files",
        "folder",
        "folders",
        "whatsapp",
        "telegram",
        "linkedin",
        "habit",
        "habits",
    }
)


def _get_keyword_map() -> Dict[str, FrozenSet[str]]:
    global _KEYWORD_MAP
    if _KEYWORD_MAP is None:
        _KEYWORD_MAP = _build_keyword_map()
    return _KEYWORD_MAP


# ── IDF-filtered "distinctive" keyword map — used by classify_and_route ─────
# Only keeps words that appear in ≤ 30 % of agent trigger sets. Generic words
# are filtered further for tie-breaking when the LLM is unavailable.

_DISTINCTIVE_KEYWORD_MAP: Optional[Dict[str, FrozenSet[str]]] = None


def _build_distinctive_keyword_map() -> Dict[str, FrozenSet[str]]:
    from collections import Counter
    from src.agent.workflows.agent_registry import AGENT_REGISTRY

    # Build raw keyword sets from deterministic trigger keywords, not from
    # descriptive prose, so tie-breaking stays stable and domain-driven.
    raw_map: Dict[str, FrozenSet[str]] = {}
    for name, info in AGENT_REGISTRY.items():
        trigger_kw = frozenset(
            w
            for kw in info.get("trigger_keywords", [])
            for w in re.findall(r"[a-z]{3,}", kw.lower())
        )
        name_tokens = frozenset(re.findall(r"[a-z]{3,}", name.lower()))
        raw_map[name] = trigger_kw | name_tokens

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
- Prefer the MINIMUM number of agents needed to complete the request
- Do NOT include an agent just because its description mentions downstream delivery, reports, images, email, or cross-agent workflows
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

def _stem(word: str) -> str:
    """Minimal English suffix stripping for the keyword pre-filter.

    Handles common plurals and verb inflections so 'payslips' matches
    'payslip', 'letters' matches 'letter', 'invoices' matches 'invoice', etc.
    NOT a full stemmer — only targets the most common mismatches.
    """
    if len(word) <= 4:
        return word
    if word.endswith("ies") and len(word) > 5:        # e.g. "copies" → "copy"
        return word[:-3] + "y"
    if word.endswith("ves") and len(word) > 5:         # e.g. "archives" → "archive"
        return word[:-3] + "fe"
    if word.endswith("ses") or word.endswith("xes") or word.endswith("zes"):
        return word[:-2]                                # e.g. "boxes" → "box"
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]                                # e.g. "searching" → "search"
    if word.endswith("ed") and len(word) > 5:
        return word[:-2]                                # e.g. "scanned" → "scann"
    if word.endswith("es") and len(word) > 4:
        return word[:-2]                                # e.g. "invoices" → "invoic"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]                                # e.g. "payslips" → "payslip"
    return word


def _looks_like_fresh_web_query(command: str) -> bool:
    """Heuristic for freshness-sensitive public-web questions.

    This catches prompts like "who won the latest T20 world cup" even when the
    user does not explicitly say "search online" or "browse".
    """
    lower = str(command or "").lower().strip()
    if not lower:
        return False

    words = set(re.findall(r"[a-z]{3,}", lower))
    stemmed_words = words | {_stem(word) for word in words}
    if not (_FRESHNESS_CUES & stemmed_words):
        return False

    # Freshness-sensitive phrasing like "today" or "latest" should not hijack
    # requests that are clearly about the user's own mailbox, files, calendar,
    # or other first-party connected systems.
    if _FIRST_PARTY_DATA_HINTS & stemmed_words:
        return False

    if re.search(r"\b(my|our)\b", lower):
        return False

    if re.search(r"\bhow are you(?: doing)?\b|\bhow'?s it going\b|\bwhat'?s up\b", lower):
        return False

    public_info_signals = (
        r"\b(who|what|when|where|which|how)\b",
        r"\b(tell me|show me|find|look up|search)\b",
        r"\b(world cup|cup|match|tournament|election|news|headline|winner|won|result|score)\b",
    )
    return any(re.search(pattern, lower) for pattern in public_info_signals)


def _looks_like_pronoun_followup(command: str) -> bool:
    lower = str(command or "").lower().strip()
    if not lower:
        return False
    return bool(
        re.search(
            r"\b(them|those|it|that|these|the files|the folder|the document|the documents|the email|the result|the results)\b",
            lower,
        )
    )


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

    Uses basic suffix-stripping so plurals like 'payslips' match 'payslip'.
    """
    kmap = _get_keyword_map()
    lower = command.lower()
    cmd_words = set(re.findall(r"[a-z]{3,}", lower))
    # Expand both sides with stemmed forms for plural/inflection tolerance
    cmd_stems = cmd_words | {_stem(w) for w in cmd_words}
    matched = any(
        (keywords | {_stem(w) for w in keywords}) & cmd_stems
        for keywords in kmap.values()
    )
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

    fast_multi_route = _route_high_confidence_multi_agent(command, valid)
    if fast_multi_route:
        logger.info("Router [high-confidence multi]: %s", fast_multi_route.agents)
        return fast_multi_route.agents

    if _looks_like_fresh_web_query(command) and "browser" in valid:
        logger.info("Router [freshness fast-path]: routing to browser")
        return ["browser"]

    # ── Step 1: keyword pre-filter (0 LLM calls) ────────────────────────────
    if not keyword_pre_filter(command):
        logger.info("Router [pre-filter]: no agent keywords — returning None (conversational)")
        return None

    # ── Step 2: LLM-based detection (1 LLM call) ────────────────────────────
    try:
        from src.agent.llm.llm_parser import get_llm_client, request_completion
        llm = get_llm_client()

        prompt = _build_routing_prompt(command)
        response = request_completion(
            llm=llm,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30,
            temperature=0,
            timeout=40,
            purpose="routing",
            allow_local_fallback=True,
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
    cmd_stems = cmd_words | {_stem(word) for word in cmd_words}

    matched: List[str] = [
        agent for agent, keywords in kmap.items()
        if (keywords | {_stem(word) for word in keywords}) & cmd_stems
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


@dataclass
class ClassificationStageResult:
    category: str
    reason: str = ""
    preset_agents: List[str] = field(default_factory=list)
    source: str = "heuristic"


@dataclass
class ContextResolutionStageResult:
    category: str
    reason: str = ""
    context_agent: str = ""
    default_agents: List[str] = field(default_factory=list)
    active_context: Optional[dict] = None
    session_state: Optional[dict] = None


@dataclass
class PlanningStageResult:
    category: str
    agents: List[str] = field(default_factory=list)
    reason: str = ""
    source: str = "heuristic"


@dataclass
class RoutingPipelineResult:
    classification: ClassificationStageResult
    context_resolution: ContextResolutionStageResult
    planning: PlanningStageResult
    intent: IntentResult


_EMAIL_ADDRESS_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_EXPLICIT_EMAIL_DELIVERY_RE = re.compile(r"\b(email|mail|inbox|gmail|outlook)\b", re.IGNORECASE)
_CURRENT_CHANNEL_DELIVERY_RE = re.compile(
    r"\bsend\s+(it|them|those|that)\s+to\s+me\b"
    r"|\bshare\s+(it|them|those|that)\s+here\b"
    r"|\bgive\s+me\s+the\s+(file|zip|folder)\b"
    r"|\bdownload\s+(it|them|those|that)\b",
    re.IGNORECASE,
)
_MAILBOX_DOMAIN_RE = re.compile(r"\b(email|emails|mail|mails|gmail|inbox|spam|junk)\b", re.IGNORECASE)
_MAILBOX_TIME_RE = re.compile(
    r"\b(today|today's|yesterday|yesterday's|last\s+week|this\s+week|last\s+month|between|from|since|before|after|on)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    re.IGNORECASE,
)
_MAILBOX_ORGANIZATION_RE = re.compile(
    r"\b(organi[sz]e|clean\s*up|declutter|de-clutter|tidy)\b.*\b(mailbox|inbox|gmail|email)\b"
    r"|\b(mailbox|inbox|gmail|email)\b.*\b(organi[sz]e|clean\s*up|declutter|de-clutter|tidy)\b",
    re.IGNORECASE,
)
_NUMERIC_SELECTION_ONLY_RE = re.compile(r"^\s*(?:option\s+)?\d{1,2}\s*[?.!]*\s*$", re.IGNORECASE)
_MAILBOX_PREFERENCE_EDIT_RE = re.compile(
    r"\b(change|set|turn\s+off|turn\s+on|disable|enable|edit|update)\b.*\b(newsletters?|promotions?|draft\s+suggestions?|draft\s+repl(?:y|ies)|mailbox\s+mode|mailbox\s+preferences|inbox\s+preferences)\b"
    r"|\balways\s+(label|move)\b.*\b(mail|emails?)\b"
    r"|\b(review|digest|recap)\b.*\b(mailbox|inbox|email)\b",
    re.IGNORECASE,
)
_FILENAME_SEARCH_RE = re.compile(
    r"\b(filename|file\s*name)\b.*\bcontain(?:s|ing)?\b"
    r"|\bcontain(?:s|ing)?\b.*\b(filename|file\s*name)\b",
    re.IGNORECASE,
)
_FOLLOWUP_NOISY_TOKENS: FrozenSet[str] = frozenset(
    {"can", "could", "would", "please", "show", "check", "tell", "give", "work", "best", "free", "time"}
)


def _looks_like_mailbox_query(command: str) -> bool:
    lower = str(command or "").lower().strip()
    if not lower or not _MAILBOX_DOMAIN_RE.search(lower):
        return bool(_MAILBOX_PREFERENCE_EDIT_RE.search(lower))
    if re.search(r"\b(calendar|meeting|meetings|event|events|schedule|scheduler|drive|file|files|folder|folders|linkedin|whatsapp|telegram)\b", lower):
        return False
    if _MAILBOX_ORGANIZATION_RE.search(lower):
        return True
    if _MAILBOX_TIME_RE.search(lower):
        return True
    if re.search(r"\b(list|show|find|search|count|what|which|latest|recent|unread|received)\b", lower):
        return True
    return False


def _looks_like_filename_search(command: str) -> bool:
    lower = str(command or "").lower().strip()
    if not lower or not _FILENAME_SEARCH_RE.search(lower):
        return False
    return bool(
        re.search(
            r"\b(file|files|image|images|photo|photos|picture|pictures|video|videos|document|documents|pdf)\b",
            lower,
        )
    )


def _looks_like_local_file_search(command: str) -> bool:
    lower = str(command or "").lower().strip()
    if not lower:
        return False
    if re.search(r"\b(gdrive|google drive|drive link|shared drive)\b", lower):
        return False
    if not re.search(
        r"\b(folder|folders|pdf|image|images|photo|photos|video|videos|payslip|invoice|receipt|computer|laptop|desktop|downloads|documents|resume|letter|letters)\b",
        lower,
    ):
        return False
    return bool(re.search(r"\b(find|search|look for|locate|zip|copy|move|rename|delete|show|list|count|download)\b", lower))


def _looks_like_explicit_email_delivery(command: str) -> bool:
    lower = str(command or "").lower().strip()
    if not lower:
        return False
    if _EMAIL_ADDRESS_RE.search(lower):
        return True
    return bool(re.search(r"\b(email|mail|send (?:it|them|that).*(?:email|mail))\b", lower))


def _route_high_confidence_multi_agent(command: str, valid: set[str]) -> Optional[IntentResult]:
    lower = str(command or "").lower().strip()
    drive_explicit = bool(
        re.search(r"\b(gdrive|google drive|shared drive)\b", lower)
        or re.search(r"\bupload\b.*\bdrive\b", lower)
        or re.search(r"\bdrive\b.*\bupload\b", lower)
    )
    if "files" in valid and "email" in valid and not drive_explicit and _looks_like_local_file_search(command) and _looks_like_explicit_email_delivery(command):
        return IntentResult(
            category="fresh_task",
            agents=["files", "email"],
            reason="high-confidence: local file search plus email delivery",
        )
    return None


def _route_high_confidence_single_agent(command: str, valid: set[str]) -> Optional[IntentResult]:
    if "files" in valid and _looks_like_filename_search(command):
        return IntentResult(
            category="fresh_task",
            agents=["files"],
            reason="high-confidence: filename-based local file search",
        )

    if "email" in valid and _looks_like_mailbox_query(command):
        return IntentResult(
            category="fresh_task",
            agents=["email"],
            reason="high-confidence: mailbox query",
        )

    return None


def _normalize_followup_agents(command: str, active_context: Optional[dict], agents: List[str]) -> List[str]:
    if not active_context or not agents:
        return agents

    ctx_agent = str(active_context.get("agent", "") or "").strip().lower()
    lowered = str(command or "")
    if ctx_agent != "files":
        return agents
    if not _CURRENT_CHANNEL_DELIVERY_RE.search(lowered):
        return agents
    if _EMAIL_ADDRESS_RE.search(lowered) or _EXPLICIT_EMAIL_DELIVERY_RE.search(lowered):
        return agents

    normalized = [agent for agent in agents if agent != "email"]
    if "files" not in normalized:
        normalized.insert(0, "files")
    return normalized


def _build_classification_prompt(
    command: str,
    active_context: Optional[dict],
    session_state: Optional[dict],
) -> str:
    """Build the stage-1 classification prompt for the LLM."""
    if active_context:
        ctx_agent = active_context.get("agent", "?")
        ctx_topic = active_context.get("topic", "?")
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

    state_block = "(none)"
    if session_state:
        relevant = {
            k: v for k, v in session_state.items()
            if k in ("last_found_file_path", "last_found_folder", "last_found_bundle_dir", "file_manifest", "found_count", "last_assistant_action") and v
        }
        if relevant:
            state_block = json.dumps(relevant, ensure_ascii=False)[:400]

    return f"""\
You are stage 1 of the intent router for a multi-agent AI personal assistant.
Your only job is to classify the user's message into exactly one category.

## Active Context (from previous assistant turn)
{context_block}

## Session State (extracted facts)
{state_block}

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
→ "Can you zip that and send it to me?" (after finding files)        → ["files"]
→ "Copy them to my Downloads folder" (after finding files)           → ["files"]
→ "Reply to the first one" (after listing emails)                    → ["email"]
→ "Book the 2 PM slot" (after listing calendar free slots)           → ["scheduler"]
→ "Can you update me on my search?" (after file search)              → ["files"]
→ "Send those to alice@example.com" (after finding files)            → ["files","email"]

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
2. Return "chat" for pure conversation.
3. If unsure between fresh_task and context_followup and context IS active,
   prefer context_followup for short commands with pronouns.

Return ONLY a single-line JSON object (no markdown, no explanation):
{{"category": "chat|context_followup|fresh_task", "reason": "one sentence"}}

User message: {command}"""


def _build_planning_prompt(
    command: str,
    category: str,
    active_context: Optional[dict],
    session_state: Optional[dict],
    agent_registry: dict,
    default_agents: Optional[List[str]] = None,
) -> str:
    """Build the stage-3 agent planning prompt for the LLM."""
    agent_lines = "\n".join(
        f'  "{name}": {info["description"]}'
        for name, info in agent_registry.items()
    )
    valid_names = json.dumps(list(agent_registry.keys()))
    default_agents = default_agents or []

    if active_context:
        ctx_agent = active_context.get("agent", "?")
        ctx_topic = active_context.get("topic", "?")
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

    state_block = "(none)"
    if session_state:
        relevant = {
            k: v for k, v in session_state.items()
            if k in ("last_found_file_path", "last_found_folder", "last_found_bundle_dir", "file_manifest", "found_count", "last_assistant_action") and v
        }
        if relevant:
            state_block = json.dumps(relevant, ensure_ascii=False)[:400]

    if category == "context_followup":
        category_rules = (
            "The message is already classified as CONTEXT_FOLLOWUP. "
            "Include the source agent from active context plus any additional agent needed to complete the action. "
            "Current-channel delivery phrases like 'send it to me' or 'share it here' stay on the files agent unless the user explicitly says email/mail or provides an email address."
        )
    else:
        category_rules = (
            "The message is already classified as FRESH_TASK. "
            "Return the minimum agent set needed to complete the new request."
        )

    default_block = json.dumps(default_agents)
    return f"""\
You are stage 3 of the intent router for a multi-agent AI personal assistant.
The message category has already been classified as {category!r}.

## Active Context
{context_block}

## Session State
{state_block}

## Available Agents
{agent_lines}

## Planning Rules
{category_rules}
- Prefer the MINIMUM number of agents needed to complete the request.
- Only include names from this list: {valid_names}
- Default context agents, if useful: {default_block}
- Return [] only if no agent is required for the already-classified category.

Return ONLY a single-line JSON object (no markdown, no explanation):
{{"agents": [...], "reason": "one sentence"}}

User message: {command}"""


def _classify_message(
    command: str,
    active_context: Optional[dict],
    session_state: Optional[dict],
    valid: set[str],
) -> ClassificationStageResult:
    if active_context and _NUMERIC_SELECTION_ONLY_RE.match(str(command or "")):
        pending_selection = active_context.get("pending_selection") if isinstance(active_context, dict) else None
        if isinstance(pending_selection, dict):
            return ClassificationStageResult(
                category="context_followup",
                reason="heuristic: numeric reply for active pending selection",
                source="pending_selection",
            )

    fast_multi_route = _route_high_confidence_multi_agent(command, valid)
    if fast_multi_route:
        return ClassificationStageResult(
            category=fast_multi_route.category,
            reason=fast_multi_route.reason,
            preset_agents=list(fast_multi_route.agents),
            source="high_confidence",
        )

    fast_route = _route_high_confidence_single_agent(command, valid)
    if fast_route:
        return ClassificationStageResult(
            category=fast_route.category,
            reason=fast_route.reason,
            preset_agents=list(fast_route.agents),
            source="high_confidence",
        )

    if (
        _looks_like_fresh_web_query(command)
        and "browser" in valid
        and not (active_context and _looks_like_pronoun_followup(command))
    ):
        return ClassificationStageResult(
            category="fresh_task",
            reason="freshness-priority: public-web query",
            preset_agents=["browser"],
            source="freshness_priority",
        )

    if active_context and _looks_like_pronoun_followup(command):
        return ClassificationStageResult(
            category="context_followup",
            reason="heuristic: pronoun follow-up with active context",
            source="pronoun_followup",
        )

    has_keywords = keyword_pre_filter(command)
    if active_context is None and not has_keywords:
        return ClassificationStageResult(
            category="chat",
            reason="fast-path: no agent keywords and no active context",
            source="fast_path",
        )

    try:
        from src.agent.llm.llm_parser import get_llm_client, request_completion

        prompt = _build_classification_prompt(command, active_context, session_state)
        llm = get_llm_client()
        response = request_completion(
            llm=llm,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0,
            timeout=40,
            purpose="intent_classification",
            allow_local_fallback=True,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        parsed = json.loads(raw)
        category = str(parsed.get("category", "")).lower().replace("-", "_")
        if category not in ("chat", "context_followup", "fresh_task"):
            raise ValueError(f"Unexpected category: {category!r}")
        return ClassificationStageResult(
            category=category,
            reason=str(parsed.get("reason", "") or "llm classification"),
            source="llm",
        )
    except Exception as exc:
        logger.warning("Router classification failed (%s) — using heuristic fallback", exc)

    if active_context and _looks_like_pronoun_followup(command):
        category = "context_followup"
        reason = "classification fallback: pronoun + active context"
    elif has_keywords:
        category = "fresh_task"
        reason = "classification fallback: agent keywords present"
    else:
        category = "chat"
        reason = "classification fallback: no agent keywords"

    return ClassificationStageResult(category=category, reason=reason, source="fallback")


def _resolve_context_stage(
    command: str,
    classification: ClassificationStageResult,
    active_context: Optional[dict],
    session_state: Optional[dict],
    valid: set[str],
) -> ContextResolutionStageResult:
    del command

    category = classification.category
    reason_parts = [classification.reason] if classification.reason else []
    context_agent = ""
    default_agents: List[str] = []

    if category == "context_followup":
        if not active_context:
            category = "fresh_task"
            reason_parts.append("demoted: no active context available")
        else:
            context_agent = str(active_context.get("agent", "") or "").strip().lower()
            if context_agent in valid:
                default_agents = [context_agent]
                reason_parts.append(f"bound to active context agent '{context_agent}'")
            else:
                reason_parts.append("active context agent unavailable in registry")

    return ContextResolutionStageResult(
        category=category,
        reason="; ".join(part for part in reason_parts if part),
        context_agent=context_agent,
        default_agents=default_agents,
        active_context=active_context,
        session_state=session_state,
    )


def _keyword_plan_agents(
    command: str,
    active_context: Optional[dict],
    category: str,
    valid: set[str],
    default_agents: Optional[List[str]] = None,
) -> List[str]:
    default_agents = [agent for agent in (default_agents or []) if agent in valid]

    kmap = _get_keyword_map()
    dmap = _get_distinctive_keyword_map()
    lower = command.lower()
    cmd_words = set(re.findall(r"[a-z]{3,}", lower))
    cmd_stems = cmd_words | {_stem(word) for word in cmd_words}
    broad_agents = [
        ag for ag, kws in kmap.items()
        if (kws | {_stem(word) for word in kws}) & cmd_stems
    ]

    if category == "context_followup" and broad_agents:
        filtered_agents: List[str] = []
        for agent in broad_agents:
            agent_keywords = kmap.get(agent, frozenset())
            matched_tokens = {
                token for token in (agent_keywords | {_stem(word) for word in agent_keywords})
                if token in cmd_stems
            }
            if any(token not in _FOLLOWUP_NOISY_TOKENS for token in matched_tokens):
                filtered_agents.append(agent)
        broad_agents = filtered_agents

    if len(broad_agents) > 1:
        distinctive_agents = [
            ag for ag in broad_agents
            if (dmap.get(ag, frozenset()) | {_stem(word) for word in dmap.get(ag, frozenset())}) & cmd_stems
        ]
        if distinctive_agents:
            agents = distinctive_agents
            logger.info(
                "Router [keyword fallback:plan]: narrowed %s → %s via distinctive map",
                broad_agents, distinctive_agents,
            )
        else:
            _preference = ["files", "email", "calendar", "drive", "whatsapp",
                           "file_organizer", "habit_tracker", "browser",
                           "stock_market", "linkedin", "scheduler"]
            agents = sorted(broad_agents, key=lambda a: _preference.index(a)
                            if a in _preference else 999)[:1]
            logger.info(
                "Router [keyword fallback:plan]: all generic matches %s → picking %s",
                broad_agents, agents,
            )
    else:
        agents = broad_agents

    if category == "context_followup" and default_agents:
        combined: List[str] = []
        for agent in [*default_agents, *agents]:
            if agent in valid and agent not in combined:
                combined.append(agent)
        agents = combined or list(default_agents)

    if category == "context_followup" and _EMAIL_ADDRESS_RE.search(command) and "email" in valid:
        if "email" not in agents:
            agents.append("email")

    if not agents and category == "fresh_task" and _looks_like_fresh_web_query(command) and "browser" in valid:
        return ["browser"]

    return _normalize_followup_agents(command, active_context, agents)


def _plan_agents_stage(
    command: str,
    classification: ClassificationStageResult,
    context_resolution: ContextResolutionStageResult,
    agent_registry: dict,
    valid: set[str],
) -> PlanningStageResult:
    if classification.preset_agents:
        return PlanningStageResult(
            category=context_resolution.category,
            agents=_normalize_followup_agents(command, context_resolution.active_context, list(classification.preset_agents)),
            reason=classification.reason,
            source=classification.source,
        )

    if context_resolution.category == "chat":
        return PlanningStageResult(
            category="chat",
            agents=[],
            reason=context_resolution.reason or "chat routing",
            source="no_plan",
        )

    try:
        from src.agent.llm.llm_parser import get_llm_client, request_completion

        prompt = _build_planning_prompt(
            command,
            context_resolution.category,
            context_resolution.active_context,
            context_resolution.session_state,
            agent_registry,
            default_agents=context_resolution.default_agents,
        )
        llm = get_llm_client()
        response = request_completion(
            llm=llm,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0,
            timeout=40,
            purpose="agent_planning",
            allow_local_fallback=True,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        parsed = json.loads(raw)
        planned_agents = [a.lower() for a in parsed.get("agents", []) if a.lower() in valid]
        if context_resolution.category == "context_followup" and context_resolution.default_agents:
            combined: List[str] = []
            for agent in [*context_resolution.default_agents, *planned_agents]:
                if agent in valid and agent not in combined:
                    combined.append(agent)
            planned_agents = combined or list(context_resolution.default_agents)
        planned_agents = _normalize_followup_agents(command, context_resolution.active_context, planned_agents)
        return PlanningStageResult(
            category=context_resolution.category,
            agents=planned_agents,
            reason=str(parsed.get("reason", "") or context_resolution.reason or "llm planning"),
            source="llm",
        )
    except Exception as exc:
        logger.warning("Agent planning failed (%s) — using keyword fallback", exc)

    planned_agents = _keyword_plan_agents(
        command,
        context_resolution.active_context,
        context_resolution.category,
        valid,
        default_agents=context_resolution.default_agents,
    )
    return PlanningStageResult(
        category=context_resolution.category,
        agents=planned_agents,
        reason=context_resolution.reason or "keyword fallback",
        source="keyword_fallback",
    )


def run_routing_pipeline(
    command: str,
    active_context: Optional[dict] = None,
    session_state: Optional[dict] = None,
) -> RoutingPipelineResult:
    from src.agent.workflows.agent_registry import AGENT_REGISTRY, registered_agents

    valid = set(registered_agents())
    classification = _classify_message(command, active_context, session_state, valid)
    logger.info(
        "Router [classify]: category=%s source=%s reason=%s preset_agents=%s",
        classification.category,
        classification.source,
        classification.reason,
        classification.preset_agents or [],
    )

    context_resolution = _resolve_context_stage(command, classification, active_context, session_state, valid)
    logger.info(
        "Router [resolve]: category=%s context_agent=%s default_agents=%s reason=%s",
        context_resolution.category,
        context_resolution.context_agent or "-",
        context_resolution.default_agents or [],
        context_resolution.reason,
    )

    planning = _plan_agents_stage(command, classification, context_resolution, AGENT_REGISTRY, valid)
    logger.info(
        "Router [plan]: category=%s source=%s agents=%s reason=%s",
        planning.category,
        planning.source,
        planning.agents or [],
        planning.reason,
    )

    intent = IntentResult(
        category=planning.category,
        agents=planning.agents,
        reason=planning.reason,
    )
    return RoutingPipelineResult(
        classification=classification,
        context_resolution=context_resolution,
        planning=planning,
        intent=intent,
    )


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
    return run_routing_pipeline(command, active_context, session_state).intent
