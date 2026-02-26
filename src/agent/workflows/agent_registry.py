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
#
# MEMORY POLICY: Skills are stateless executors — they do NOT have their own
# memory.  Always call skill executors with agent_id=None.  Memory lives at
# the Personal Assistant (PA) level; the PA's id is used when recording
# interactions and loading context for conversational replies.
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
    "whatsapp": {
        "description": (
            "WhatsApp agent. Handles: send/receive text and media messages, "
            "reply to messages, manage contacts and groups, search conversations, "
            "schedule messages, set auto-reply, summarize chats, extract action items, "
            "draft and translate messages, detect urgent messages, sentiment analysis, "
            "message analytics, and cross-agent forwarding to email or Drive."
        ),
        "module": "src.agent.ui.whatsapp_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "files": {
        "description": (
            "Files Agent. Handles: list/copy/move/delete/rename local files and folders, "
            "search by name/extension/date/size, find duplicates, zip/unzip archives, "
            "bulk organise by type or date, read text/CSV/JSON files, disk usage analytics, "
            "AI file summarisation and folder analysis, and cross-agent workflows "
            "(zip+email, zip+Drive upload, attach file to email)."
        ),
        "module": "src.agent.ui.files_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "calendar": {
        "description": (
            "Google Calendar agent. Handles: list/view/search events, create/update/delete events, "
            "quick natural-language event creation, recurring events, find free slots, detect conflicts, "
            "daily/weekly agenda, set reminders, accept/decline invites, and list calendars."
        ),
        "module": "src.agent.ui.calendar_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "scheduler": {
        "description": (
            "Scheduler / Smart Calendar agent. Handles: find best meeting time slots, "
            "find mutual availability for multi-attendee meetings, protect deep-work / focus blocks, "
            "analyse and optimise a day's schedule, smart conflict resolution with proposed alternatives, "
            "create named time blocks (focus/admin/break/review/learning), "
            "get scheduling insights and meeting-load analytics, "
            "set up recurring focus time. "
            "Use instead of the Calendar agent when the request involves INTELLIGENT scheduling, "
            "optimisation, or scheduling for multiple people."
        ),
        "module": "src.agent.ui.scheduler_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "file_organizer": {
        "description": (
            "File Organizer agent. Approval-driven file organization: scan a folder and propose a plan "
            "(by type/date/name prefix), preview the plan, then apply only after confirmation. "
            "Also: archive old files by age, set archival policies for folders, run archival policies, "
            "and clean up Octa Bot's own data/ directory (old exports, stale plan records). "
            "Use instead of the Files agent when the request is about ORGANIZING a whole folder or "
            "setting up ARCHIVAL RULES — it never modifies files without user approval."
        ),
        "module": "src.agent.ui.file_organizer_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "habit_tracker": {
        "description": (
            "Habit & Health Tracker agent. Handles: add/delete habits, log daily completions, "
            "daily check-in (show pending habits), streak tracking (current and longest), "
            "weekly habit completion reports, per-habit analytics over 30/60/90 days, "
            "and optional Google Calendar integration to schedule habit sessions. "
            "Completely new — no overlap with Calendar or Files agents."
        ),
        "module": "src.agent.ui.habit_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "browser": {
        "description": (
            "Browser agent. Handles: browse any URL, search the web (DuckDuckGo), "
            "extract clean page text, list hyperlinks, get page title and metadata, "
            "find a phrase on a page, extract structured tables/lists, "
            "download files from URLs, and summarise page content. "
            "Completely new — no overlap with existing agents."
        ),
        "module": "src.agent.ui.browser_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "stock_market": {
        "description": (
            "Stock Market Analysis agent (READ-ONLY — no buy/sell). Handles: "
            "real-time stock quotes, historical OHLCV data, technical analysis (RSI/MACD/Bollinger), "
            "risk scoring (volatility/Beta/VaR/Sharpe), candlestick pattern detection, "
            "portfolio diversification analysis, portfolio rebalancing suggestions, "
            "news sentiment analysis, side-by-side stock comparison, broad market overview, "
            "Warren Buffett-style fundamental analysis (moat/ROE/FCF/valuation), "
            "and FULL PDF REPORT GENERATION — one tool that runs ALL analyses and builds a "
            "comprehensive PDF report, with optional email delivery of the report to any address. "
            "Use generate_full_report when the user asks for: 'full analysis', 'stock report', "
            "'PDF report', 'send report to me', 'email me the analysis', 'complete analysis of [stock]'."
        ),
        "module": "src.agent.ui.stock_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
    "linkedin": {
        "description": (
            "LinkedIn agent. Fully manages a LinkedIn page or personal profile. Handles: "
            "publish text/image/video/article posts, AI-generate post text (tone, length, audience), "
            "AI-generate images via DALL·E 3, schedule posts for future dates, "
            "cancel scheduled posts, list published posts, delete posts, "
            "get post-level analytics (impressions/clicks/likes/comments/shares/engagement), "
            "get page-level analytics over any date range, get organisation follower count, "
            "and manage OAuth setup (get auth URL, exchange code for token)."
        ),
        "module": "src.agent.ui.linkedin_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
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
