"""
Conversation State Tracker
==========================

Parses recent conversation history and extracts resolved, structured entities
(dates, times, files, e-mail addresses, …) so they can be injected as a
deterministic JSON block into every skill-agent query.

Why this exists
---------------
LLMs accept natural language but tool calls / APIs need exact values.
Passing resolved entities as structured JSON eliminates ambiguity:

    Bad  → "User wants to book the day they mentioned earlier at 2 PM"
    Good → {"active_date": "2026-03-12", "active_time": "20:00", ...}

Usage
-----
    from src.agent.context.conversation_state import build_structured_query

    enriched = build_structured_query(
        task="Schedule a meeting at 8 PM for Gym Session",
        history=st.session_state["chat_messages"],
    )
    # enriched is the full string you pass to run_skill_react as user_query
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent.context.conversation_state")

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Matches concrete date expressions (ordinal + month, bare day + month, ISO)
_DATE_RE = re.compile(
    r"\b("
    # "12th March" / "3rd April" / "1st January"
    r"\d{1,2}\s*(?:st|nd|rd|th)\s+(?:of\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
    r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)"
    # "8 March" / "8 march 2026"
    r"|\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)(?:\s+\d{4})?"
    # ISO 8601 "2026-03-12"
    r"|\d{4}-\d{2}-\d{2}"
    r"|tomorrow|today|tonight|yesterday"
    r"|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)"
    r"|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend)"
    r")\b",
    re.IGNORECASE,
)

# Matches clock times: "8 PM", "8:30 PM", "14:00"
_TIME_RE = re.compile(
    r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|(?:[01]\d|2[0-3]):[0-5]\d)\b",
    re.IGNORECASE,
)

# Matches time ranges: "8 PM to 9 PM" or "14:00-15:00"
_TIME_RANGE_RE = re.compile(
    r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*(?:to|[-–])\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
    re.IGNORECASE,
)

# File names (e.g. "report.pdf", "data.xlsx", "notes.txt")
_FILE_RE = re.compile(
    r"\b([\w\-]+\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|json|png|jpg|jpeg|zip|py|md))\b",
    re.IGNORECASE,
)

# Absolute file paths reported by tool results in assistant messages.
# Windows:  C:\Users\foo\bar.jpg  (also forward-slash variant)
# Unix/Mac: /home/foo/bar.jpg
_PATH_RE = re.compile(
    r"(?:"
    r"[A-Za-z]:[/\\][^\s\n\r\"'<>|*?]+"   # Windows drive-letter paths (C:\... or C:/...)
    r"|/(?:[^\s\n\r\"'<>|*?]+/)*[^\s\n\r\"'<>|*?]+"  # Unix absolute paths
    r")"
    r"\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|json|png|jpg|jpeg|gif|zip|py|md)\b",
    re.IGNORECASE,
)

# E-mail addresses
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}")

# The previous assistant action verb, used to tag "last_action"
_ACTION_VERB_RE = re.compile(
    r"\b(scheduled|created|booked|sent|shared|uploaded|downloaded|found|"
    r"deleted|moved|updated|checked|searched|listed|retrieved)\b",
    re.IGNORECASE,
)

# Month name → month number
_MONTH_MAP: Dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_WEEKDAY_MAP: Dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# ---------------------------------------------------------------------------
# Date resolution
# ---------------------------------------------------------------------------

def _resolve_to_iso(raw: str, ref: date) -> Optional[str]:
    """
    Attempt to convert a natural-language date string to ISO-8601 (YYYY-MM-DD).
    Returns None when resolution is not possible.
    """
    s = raw.strip().lower()

    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s  # already ISO

    if s in ("today", "tonight"):
        return ref.isoformat()
    if s == "yesterday":
        return (ref - timedelta(days=1)).isoformat()
    if s == "tomorrow":
        return (ref + timedelta(days=1)).isoformat()

    # next <weekday> / this <weekday>
    m = re.match(r"(next|this)\s+(\w+)", s)
    if m:
        wd = _WEEKDAY_MAP.get(m.group(2))
        if wd is not None:
            days_ahead = (wd - ref.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7 if m.group(1) == "next" else 0
            return (ref + timedelta(days=days_ahead)).isoformat()

    # next week / this week  — return start of that week (Monday)
    if re.match(r"(next|this)\s+(week|month)", s):
        return None  # too vague to pin to a single date

    # "12th March" / "3rd April" / "8 March" / "8 March 2026"
    dm = re.match(
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
        r"(?:of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"(?:\s+(\d{4}))?",
        s,
    )
    if dm:
        day   = int(dm.group(1))
        month = _MONTH_MAP.get(dm.group(2)[:3], None)
        year  = int(dm.group(3)) if dm.group(3) else ref.year
        if month:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None

    return None


def _time_to_24h(raw: str) -> Optional[str]:
    """Convert a clock string to 'HH:MM' 24-hour format."""
    s = raw.strip().lower().replace(" ", "")
    m = re.match(r"(\d{1,2})(?::(\d{2}))?(am|pm)", s)
    if m:
        h, mi, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if period == "pm" and h != 12:
            h += 12
        if period == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}"
    # already 24h "14:00"
    m2 = re.match(r"(\d{2}):(\d{2})", s)
    if m2:
        return f"{int(m2.group(1)):02d}:{int(m2.group(2)):02d}"
    return None


# ---------------------------------------------------------------------------
# Main tracker
# ---------------------------------------------------------------------------

class ConversationStateTracker:
    """
    Builds a structured state dict from a conversation history list.

    The history is expected to be a list of dicts:
        [{"role": "user"|"assistant", "content": "..."}, ...]

    Extracted entities are resolved to canonical forms:
        - dates  → ISO-8601 strings ("2026-03-12")
        - times  → 24-hour strings  ("20:00")
        - files  → list of filenames
        - emails → list of addresses

    The tracker scans the LAST `window` messages (default 10) so stale
    context from much earlier in a long conversation doesn't pollute state.
    """

    def __init__(self, window: int = 10):
        self.window = window

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def build(
        self,
        history: List[Dict[str, Any]],
        current_command: str = "",
    ) -> Dict[str, Any]:
        """
        Return a structured state dict.  Fields are omitted when empty/unknown
        so the JSON block stays compact.
        """
        try:
            local = datetime.now().astimezone()
            ref   = local.date()
            tz    = local.strftime("%Z (UTC%z)")
            # Clean up tz string to "IST (UTC+05:30)" format
            tz_str = local.strftime("%Z")
            off    = local.strftime("%z")  # "+0530"
            tz_display = f"{tz_str} (UTC{off[:3]}:{off[3:]})"
        except Exception:
            ref        = date.today()
            tz_display = "UTC (+00:00)"

        state: Dict[str, Any] = {
            "current_date": ref.isoformat(),
            "timezone":     tz_display,
        }

        recent = history[-self.window:] if len(history) >= self.window else history
        # Add the current command to the scan corpus
        all_text = " ".join(m.get("content", "") for m in recent)
        if current_command:
            all_text = all_text + " " + current_command

        # ── resolved dates ─────────────────────────────────────────────
        raw_dates = _DATE_RE.findall(all_text)
        resolved_dates: List[str] = []
        for rd in raw_dates:
            iso = _resolve_to_iso(rd, ref)
            if iso and iso not in resolved_dates:
                resolved_dates.append(iso)

        # The *active* date is the most recent concrete date from a USER message.
        # We PREFER user messages over assistant messages — old assistant replies
        # (e.g. confirmations) can reference stale dates that are no longer the
        # user's intent.  Fall back to all messages only when no user message
        # contains a date.
        active_date: Optional[str] = None

        # Pass 1 — scan USER messages backwards (most-recent-user-date wins)
        for msg in reversed(recent):
            if msg.get("role") != "user":
                continue
            for rd in _DATE_RE.findall(msg.get("content", "")):
                iso = _resolve_to_iso(rd, ref)
                if iso:
                    active_date = iso
                    break
            if active_date:
                break

        # Pass 2 — fall back to all recent messages if no user date was found
        if not active_date:
            for msg in reversed(recent):
                for rd in _DATE_RE.findall(msg.get("content", "")):
                    iso = _resolve_to_iso(rd, ref)
                    if iso:
                        active_date = iso
                        break
                if active_date:
                    break

        # Pass 3 — current command overrides everything (highest priority)
        if current_command:
            for rd in _DATE_RE.findall(current_command):
                iso = _resolve_to_iso(rd, ref)
                if iso:
                    active_date = iso
                    break

        if active_date:
            state["active_date"] = active_date
        if resolved_dates:
            state["mentioned_dates"] = resolved_dates

        # ── resolved times ─────────────────────────────────────────────
        # Prefer time from the CURRENT command; fall back to history
        active_time_start: Optional[str] = None
        active_time_end:   Optional[str] = None

        # Check time range first
        tr = _TIME_RANGE_RE.search(current_command or all_text)
        if tr:
            active_time_start = _time_to_24h(tr.group(1))
            active_time_end   = _time_to_24h(tr.group(2))
        else:
            # Single time
            tm = _TIME_RE.search(current_command or "")
            if not tm:
                tm = _TIME_RE.search(all_text)
            if tm:
                active_time_start = _time_to_24h(tm.group(1))

        if active_time_start:
            state["active_time_start"] = active_time_start
        if active_time_end:
            state["active_time_end"] = active_time_end

        # ── files ──────────────────────────────────────────────────────
        mentioned_files = list(dict.fromkeys(
            f.lower() for f in _FILE_RE.findall(all_text)
        ))
        if mentioned_files:
            state["mentioned_files"] = mentioned_files

        # ── last found file paths (full absolute paths from assistant tool results) ──
        # Extract paths that the files/drive agent reported back, so follow-up
        # commands like "mail that to me" can attach the exact file without
        # a second search.
        logger.debug(
            "[CST] build() history=%d recent=%d command=%.80s",
            len(history), len(recent), current_command or "",
        )
        last_found_paths: List[str] = []
        for msg in reversed(recent):
            if msg.get("role") == "assistant":
                # Prefer structured file_artifacts stored directly on the entry
                # (populated by the hub after every dispatch turn).
                artifacts = msg.get("file_artifacts", [])
                if artifacts:
                    last_found_paths = list(dict.fromkeys(str(p) for p in artifacts))
                    logger.debug("[CST] last_found_paths from file_artifacts: %s", last_found_paths)
                    break
                # Fall back: regex-parse the assistant's text response
                content = msg.get("content", "")
                paths = _PATH_RE.findall(content)
                logger.debug(
                    "[CST] assistant msg (%.120s) → regex path matches: %s",
                    content.replace("\n", " "), paths,
                )
                if paths:
                    # Most recent assistant message that mentioned paths wins;
                    # deduplicate, preserve order.
                    last_found_paths = list(dict.fromkeys(paths))
                    break
        if last_found_paths:
            state["last_found_paths"] = last_found_paths
            # Convenience: expose the single best path as a scalar too
            state["last_found_file_path"] = last_found_paths[0]
            # Derive the common parent folder — used by DAG planner for "zip them"
            # If all files share the same parent, record it as last_found_folder.
            try:
                from pathlib import Path as _PPath
                parent_counts: dict = {}
                for fp in last_found_paths:
                    parent = str(_PPath(fp).parent)
                    parent_counts[parent] = parent_counts.get(parent, 0) + 1
                if parent_counts:
                    # Most common parent wins; ties pick the one with most files
                    best_folder = max(parent_counts.items(), key=lambda kv: kv[1])[0]
                    state["last_found_folder"] = best_folder
            except Exception:
                pass

        # ── e-mail recipients ──────────────────────────────────────────
        all_emails = list(dict.fromkeys(_EMAIL_RE.findall(all_text)))
        if all_emails:
            state["mentioned_emails"] = all_emails

        # ── last assistant action ──────────────────────────────────────
        last_action: Optional[str] = None
        for msg in reversed(recent):
            if msg.get("role") == "assistant":
                vm = _ACTION_VERB_RE.search(msg.get("content", ""))
                if vm:
                    # Grab up to 120 chars around the verb as a summary
                    snippet = msg["content"].replace("\n", " ")[:120]
                    last_action = snippet
                    break
        if last_action:
            state["last_assistant_action"] = last_action

        return state

    def build_structured_query(
        self,
        task: str,
        history: List[Dict[str, Any]],
    ) -> str:
        """
        Return the task string augmented with a compact JSON state block.

        The LLM sees:

            Task: <original command>

            ## Session State (structured — use these resolved values, not raw text)
            {
              "current_date": "2026-03-04",
              "timezone": "IST (UTC+05:30)",
              "active_date": "2026-03-12",
              ...
            }
        """
        state = self.build(history, task)
        state_json = json.dumps(state, indent=2)
        return (
            f"{task}\n\n"
            "## Session State (structured — prefer these resolved values over raw text)\n"
            f"{state_json}"
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

_default_tracker = ConversationStateTracker()


def build_structured_query(task: str, history: List[Dict[str, Any]]) -> str:
    """
    Module-level convenience wrapper around ConversationStateTracker.

    Use in place of _inject_conversation_context() wherever you need
    deterministic, structured context passed to a skill agent.
    """
    # Only inject state for commands that plausibly involve agent actions.
    # Pure conversational replies don't need the overhead.
    return _default_tracker.build_structured_query(task, history)
