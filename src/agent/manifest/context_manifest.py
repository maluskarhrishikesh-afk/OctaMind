"""
Context Manifest — Persistent Conversational State Engine
==========================================================

Separates the *reasoning layer* (LLM) from the *state layer* (disk).
The LLM thinks. The Manifest remembers.

Problem solved
--------------
Without this, follow-up messages like "2 PM", "the first one", "reply to it"
arrive completely stripped of context — the LLM is forced to ask "which date?",
"which email?" even when the previous turn already resolved those values.

Solution
--------
Every agent that produces a "selection surface" (a list of events, emails, files,
or a resolved date the user will act on) calls write_context() immediately after
the tool result. On the NEXT user turn, inject_context_into_query() reads this
manifest and prepends a structured context block to the query, so the LLM
receives both the user's bare follow-up AND the fully-resolved context it needs
to execute without asking again.

File location: <workspace>/data/octa_context.json  (resolved at runtime relative to this file)
Format:        JSON, human-readable, UTF-8, overwritten on each new write.
TTL:           60 minutes by default (configurable; stale context auto-discarded).

Supported Agents
----------------
  scheduler  — calendar events, free slots, resolved dates
  email      — listed emails (id, subject, sender, snippet)
  drive      — listed Drive files (id, name, mimeType)
  files      — file search results (query, count, manifest reference)

Usage
-----
    # In agent orchestrators: write after a listing/search tool call
    from src.agent.manifest.context_manifest import write_context
    write_context(
        agent="scheduler",
        topic="calendar_query",
        resolved_entities={"resolved_date": "2026-03-06", "events": [...]},
        awaiting="time_selection",
    )

    # In processor.py: inject before passing query to executor
    from src.agent.manifest.context_manifest import inject_context_into_query
    effective_query = inject_context_into_query(effective_query)

    # In _get_tools(): give the LLM an explicit save_context tool
    from src.agent.manifest.context_manifest import make_save_context_tool
    tools["save_context"] = make_save_context_tool("scheduler")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agent.manifest.context")

# ---------------------------------------------------------------------------
# Storage — workspace-relative so the path is identical on Windows/Linux/macOS.
# __file__ = src/agent/manifest/context_manifest.py
#   parents[0] = src/agent/manifest/
#   parents[1] = src/agent/
#   parents[2] = src/
#   parents[3] = <workspace root>
# ---------------------------------------------------------------------------

_WORKSPACE_ROOT       = Path(__file__).resolve().parents[3]
_MANIFEST_DIR         = _WORKSPACE_ROOT / "data"
_CONTEXT_FILE         = _MANIFEST_DIR / "octa_context.json"
_CONTEXT_HISTORY_FILE = _MANIFEST_DIR / "octa_context_history.jsonl"   # append-only audit log
_PRUNE_STAMP_FILE     = _MANIFEST_DIR / ".last_context_prune"
_DEFAULT_TTL          = 60   # minutes — live context window
_AUDIT_TTL_DAYS       = 30   # days  — how long audit entries are kept

# ---------------------------------------------------------------------------
# Per-awaiting-type instructions injected into the LLM query.
# These tell the LLM exactly what to do with the persisted context so it
# never needs to ask the user to repeat themselves.
# ---------------------------------------------------------------------------

_AWAITING_INSTRUCTIONS: Dict[str, str] = {
    "time_selection": (
        "The user is selecting a time slot from the context above. "
        "Use `resolved_date` directly — do NOT ask for the date again. "
        "Parse their time (e.g. '2 PM' → '14:00', '3:30' → '15:30', "
        "'2' → '14:00' when all free slots are in the afternoon) "
        "and call create_event or the appropriate booking tool immediately."
    ),
    "event_selection": (
        "The user is referring to a specific calendar event from `events` in the context. "
        "Resolve their reference ('first meeting', 'the 3 PM one', 'the gym session') "
        "by matching to the listed events. Use the matched event's `id` for the operation."
    ),
    "email_action": (
        "The user is acting on one or more emails from `listed_emails` in the context. "
        "Match their reference ('first one', 'Alice\\'s email', 'the invoice', 'last') "
        "by zero-based index ('first' = 0, 'second' = 1, 'last' = -1) "
        "or by keyword match against `subject` / `sender` fields. "
        "Use the matched email's `id` directly — do NOT call list_emails again."
    ),
    "file_action": (
        "The user is acting on files from the previous search. "
        "File paths are stored in the file manifest (octa_manifest.txt). "
        "Call collect_files_from_manifest() to copy, or use files from `listed_files` "
        "in this context. Do NOT run a new search — the files are already resolved.\n"
        "FOLDER SHORTCUT: If `listed_files` contains a single entry with type=folder "
        "(e.g. {\"path\": \"C:\\\\Users\\\\...\\\\Text\", \"type\": \"folder\"}), "
        "call zip_folder(folder_path=<that path>) DIRECTLY — do NOT call "
        "collect_files_from_manifest for a folder path.\n"
        "DESTINATION RULES — resolve in this order and NEVER ask the user:\n"
        "  1. Absolute path given (e.g. 'C:\\\\Users\\\\...') → use as-is.\n"
        "  2. 'a folder named X' / 'a folder called X' / 'called X' → "
        "     destination=str(Downloads / 'X').\n"
        "  3. 'to downloads/X', 'to Desktop\\\\X' → expand Downloads/Desktop path.\n"
        "  4. Keyword only ('to downloads', 'to desktop', 'to documents') → "
        "     destination=str(<Keyword_path>).\n"
        "  5. Single word after 'to' (e.g. 'to qwerty') → "
        "     destination=str(Downloads / 'qwerty').\n"
        "  6. No destination at all → use default workspace data folder.\n"
        "Pass destination= to collect_files_from_manifest(). NEVER leave it empty when "
        "the user named a folder."
    ),
    "drive_file_action": (
        "The user is acting on one of the Drive files listed in `listed_files` in the context. "
        "Resolve their reference ('first one', 'the PDF', 'the report', 'second') "
        "by zero-based index or name/type match. "
        "Use the matched file's `id` for the requested operation."
    ),
    "confirmation": (
        "The user is confirming or cancelling the previously proposed action. "
        "Affirmative (yes / ok / sure / go ahead / do it / yep / correct) → execute immediately. "
        "Negative (no / cancel / stop / don't / never mind / abort) → abort and confirm cancellation."
    ),
    "whatsapp_action": (
        "The user is acting on a WhatsApp contact or conversation from the context above. "
        "Resolve their contact reference ('Bob', 'him', 'her', 'them', 'the contact') "
        "to the `resolved_contact` phone number stored in the context. "
        "Use that number directly in the send tool — do NOT ask for the phone number."
    ),
    "habit_action": (
        "The user is acting on a habit from `listed_habits` in the context. "
        "Resolve their reference ('first one', 'the gym habit', 'reading', 'second') "
        "by zero-based index or by name/description match against the habit list. "
        "Use the matched habit's `name` directly in the tool call — "
        "do NOT call get_habits or daily_checkin again."
    ),
    "stock_action": (
        "The user is acting on a previously analysed stock ticker from the context. "
        "Use `resolved_ticker` directly (e.g. 'TSLA', 'AAPL') in tool calls — "
        "do NOT call resolve_ticker again. "
        "Reference `current_price` from context for price-relative actions "
        "(alerts, percentage calculations, target comparisons)."
    ),
}

# ---------------------------------------------------------------------------
# Core write / read / clear
# ---------------------------------------------------------------------------

def write_context(
    agent: str,
    topic: str,
    resolved_entities: Dict[str, Any],
    awaiting: Optional[str] = None,
    pending_selection: Optional[Dict[str, Any]] = None,
    ttl_minutes: int = _DEFAULT_TTL,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist resolved context to <workspace>/data/octa_context.json.

    Call this immediately after any agent action that produces data the user
    will need to reference in their next turn ("2 PM", "the first one", etc.).

    The file is a **keyed store** — each agent owns its own slot so multiple
    agents' contexts can coexist without overwriting each other:
        {
          "files": {"agent": "files", "topic": "file_search", ...},
          "email": {"agent": "email", "topic": "email_list", ...}
        }

    Args:
        agent:              Agent that produced this context. One of:
                            "scheduler", "email", "drive", "files".
        topic:              Short identifier, e.g. "calendar_query", "email_list".
        resolved_entities:  Dict of resolved values to persist.
                            e.g. {"resolved_date": "2026-03-06", "events": [...]}
        awaiting:           What the system expects next from the user.
                            One of: "time_selection", "event_selection",
                            "email_action", "file_action", "drive_file_action",
                            "confirmation". Omit if no follow-up is expected.
        pending_selection:  Optional structured selection surface (options list, etc.)
        ttl_minutes:        Context validity window. Default 60 minutes.
        scope:              Optional spatial scope hint for file searches.
                            One of: "single_file", "single_folder", "multi_folder".
                            The DAG planner uses this to pick the right zip strategy.

    Returns:
        {"status": "success"|"error", "context_file": str, "message": str}
    """
    try:
        _MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

        # ── Load existing keyed store (or start fresh) ─────────────────────
        store: Dict[str, Any] = {}
        if _CONTEXT_FILE.exists():
            try:
                raw = json.loads(_CONTEXT_FILE.read_text(encoding="utf-8"))
                # Migrate legacy flat format (schema_version=1, "agent" at top level)
                if isinstance(raw, dict) and "written_at" in raw and "agent" in raw:
                    old_agent_key = raw.get("agent", "unknown")
                    store = {old_agent_key: raw}
                    logger.info(
                        "[context-manifest] migrated legacy flat context → keyed store (agent=%s)",
                        old_agent_key,
                    )
                elif isinstance(raw, dict):
                    store = raw
            except Exception as _re:
                logger.warning("[context-manifest] could not read existing store, starting fresh: %s", _re)
                store = {}

        now = datetime.now()
        payload: Dict[str, Any] = {
            "schema_version": 2,
            "written_at":     now.isoformat(timespec="seconds"),
            "expires_at":     (now + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds"),
            "agent":          agent,
            "topic":          topic,
            "resolved_entities": resolved_entities,
        }
        if scope:
            payload["scope"] = scope
        if awaiting:
            payload["awaiting"] = awaiting
        if pending_selection:
            payload["pending_selection"] = pending_selection

        # Write into the agent's dedicated slot in the store
        store[agent] = payload

        _CONTEXT_FILE.write_text(
            json.dumps(store, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            "[context-manifest] wrote  agent=%s  topic=%s  awaiting=%s  keys=%s",
            agent, topic, awaiting, list(resolved_entities.keys()),
        )

        # ── Audit history: append a compact single-line record ─────────────
        try:
            _CONTEXT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            audit_line = json.dumps(
                {k: payload[k] for k in ("written_at", "agent", "topic", "awaiting")
                 if k in payload},
                ensure_ascii=False,
            )
            with _CONTEXT_HISTORY_FILE.open("a", encoding="utf-8") as _fh:
                _fh.write(audit_line + "\n")
        except Exception as _he:
            logger.debug("[context-manifest] history append skipped: %s", _he)

        # ── Daily prune of old audit entries ──────────────────────────────
        if _should_run_prune():
            try:
                prune_context_history()
            except Exception as _pe:
                logger.debug("[context-manifest] daily prune skipped: %s", _pe)

        return {
            "status":       "success",
            "context_file": str(_CONTEXT_FILE),
            "message":      f"Context saved: agent={agent}, topic={topic}",
        }
    except Exception as exc:
        logger.error("[context-manifest] write failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def read_context(
    max_age_minutes: int = _DEFAULT_TTL,
    agent: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Return the context manifest entry if it exists and has not expired.

    The file is a keyed store ``{agent_name: {context_dict}}``.

    Args:
        max_age_minutes: Maximum age (minutes) before context is discarded.
        agent:           If given, return only that agent's context entry.
                         If None, return the most recently written entry
                         across all agents.

    Returns None if the file is missing, unreadable, malformed, or stale.
    """
    try:
        if not _CONTEXT_FILE.exists():
            return None

        raw = json.loads(_CONTEXT_FILE.read_text(encoding="utf-8"))

        # ── Determine candidate entries ────────────────────────────────────
        # Handle legacy flat format (schema_version=1, "written_at" at root level)
        if isinstance(raw, dict) and "written_at" in raw and "agent" in raw:
            entries = [raw]
        else:
            # Keyed store format — values are context dicts
            entries = [v for v in raw.values() if isinstance(v, dict) and "written_at" in v]

        # Filter by requested agent
        if agent:
            entries = [e for e in entries if e.get("agent") == agent]

        if not entries:
            return None

        # Pick the most recently written entry (if multiple)
        entries.sort(key=lambda e: e.get("written_at", ""), reverse=True)
        ctx = entries[0]

        # Check explicit expires_at field first
        expires_str = ctx.get("expires_at", "")
        if expires_str:
            try:
                if datetime.now() > datetime.fromisoformat(expires_str):
                    logger.info("[context-manifest] expired at %s — discarding", expires_str)
                    return None
            except Exception:
                pass

        # Also enforce max_age_minutes against written_at
        written_str = ctx.get("written_at", "")
        if written_str:
            try:
                age_min = (datetime.now() - datetime.fromisoformat(written_str)).total_seconds() / 60
                if age_min > max_age_minutes:
                    logger.info("[context-manifest] too old (%.1f min) — discarding", age_min)
                    return None
            except Exception:
                pass

        return ctx
    except Exception as exc:
        logger.warning("[context-manifest] read failed: %s", exc)
        return None


def clear_context(agent: Optional[str] = None) -> None:
    """Delete the live context manifest or one agent's slot within it.

    Args:
        agent: If given, remove only that agent's entry from the keyed store.
               If the store becomes empty after removal, the file is deleted.
               If None (default), delete the entire context file.

    The audit history file is NOT touched here — it is pruned separately
    by :func:`prune_context_history` on a daily schedule.
    """
    try:
        if not _CONTEXT_FILE.exists():
            return

        if agent is None:
            # Clear everything
            _CONTEXT_FILE.unlink()
            logger.info("[context-manifest] cleared (all agents)")
            return

        # Remove only the specified agent's slot
        try:
            raw = json.loads(_CONTEXT_FILE.read_text(encoding="utf-8"))
        except Exception:
            _CONTEXT_FILE.unlink()
            return

        # Handle legacy flat format
        if isinstance(raw, dict) and "written_at" in raw and "agent" in raw:
            if raw.get("agent") == agent:
                _CONTEXT_FILE.unlink()
                logger.info("[context-manifest] cleared agent=%s (legacy flat format)", agent)
            return

        if agent in raw:
            del raw[agent]
            if raw:
                _CONTEXT_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info("[context-manifest] cleared agent=%s (%d agents remain)", agent, len(raw))
            else:
                _CONTEXT_FILE.unlink()
                logger.info("[context-manifest] cleared agent=%s (store empty, file deleted)", agent)

    except Exception as exc:
        logger.warning("[context-manifest] clear failed: %s", exc)


# ---------------------------------------------------------------------------
# Audit history helpers
# ---------------------------------------------------------------------------

def _should_run_prune() -> bool:
    """Return True if a full day has elapsed since the last prune run."""
    try:
        if not _PRUNE_STAMP_FILE.exists():
            return True
        last = datetime.fromisoformat(_PRUNE_STAMP_FILE.read_text(encoding="utf-8").strip())
        return (datetime.now() - last).total_seconds() > 86_400
    except Exception:
        return True


def prune_context_history(days: int = _AUDIT_TTL_DAYS) -> int:
    """
    Remove entries older than *days* from ``octa_context_history.jsonl``.

    Runs automatically (at most once per 24 h) inside :func:`write_context`.
    Can also be invoked explicitly.  Zero LLM-memory impact — the history
    file is never injected into the prompt.

    Returns:
        Number of entries pruned.
    """
    if not _CONTEXT_HISTORY_FILE.exists():
        return 0
    try:
        cutoff = datetime.now() - timedelta(days=days)
        kept: list = []
        pruned = 0
        for raw_line in _CONTEXT_HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry.get("written_at", "1970-01-01"))
                if ts >= cutoff:
                    kept.append(line)
                else:
                    pruned += 1
            except Exception:
                kept.append(line)   # preserve malformed lines
        body = "\n".join(kept)
        if kept:
            body += "\n"
        _CONTEXT_HISTORY_FILE.write_text(body, encoding="utf-8")
        _PRUNE_STAMP_FILE.write_text(datetime.now().isoformat(), encoding="utf-8")
        if pruned:
            logger.info(
                "[context-manifest] pruned %d history entries older than %d days",
                pruned, days,
            )
        return pruned
    except Exception as exc:
        logger.warning("[context-manifest] prune_context_history failed: %s", exc)
        return 0


def get_context_history(days: int = _AUDIT_TTL_DAYS) -> list:
    """
    Return audit history entries from the last *days* days, newest-first.

    Each entry is a dict with keys: written_at, agent, topic, awaiting.
    This is a lightweight audit view — resolved_entities are NOT stored
    in the history to keep the file small.
    """
    if not _CONTEXT_HISTORY_FILE.exists():
        return []
    try:
        cutoff = datetime.now() - timedelta(days=days)
        entries: list = []
        for raw_line in _CONTEXT_HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry.get("written_at", "1970-01-01"))
                if ts >= cutoff:
                    entries.append(entry)
            except Exception:
                pass
        return list(reversed(entries))   # newest first
    except Exception as exc:
        logger.warning("[context-manifest] get_context_history failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Query injection
# ---------------------------------------------------------------------------

def inject_context_into_query(user_query: str, current_agent: str = "") -> str:
    """
    Read the active context manifest and inject it as a structured block
    into *user_query*, placed immediately before the '## Session State' section.

    If no valid context exists the original query is returned unchanged.

    The enriched query has this structure:

        <user_query>

        ## Context from Previous Turn  [agent=<X> | topic=<Y> | written N minutes ago]
        {
          "resolved_date": "2026-03-06",
          ...
        }

        CONTEXT INSTRUCTION (awaiting=time_selection):
        The user is selecting a time slot...
        Do NOT ask the user to re-specify any information already in the context.

        ## Session State (structured — prefer these resolved values over raw text)
        { "current_date": "2026-03-05", ... }

    Args:
        user_query:     The raw query to enrich.
        current_agent:  The agent that will handle *this* request (e.g. "drive",
                        "files", "email").  When supplied and it differs from the
                        agent that *wrote* the context, the tool-specific CONTEXT
                        INSTRUCTION block is suppressed — the agent receives only
                        the data JSON so it stays aware of prior context without
                        being instructed to call tools that don't belong to it.
    """
    # When current_agent is specified, prefer that agent's own context entry so
    # the injected instructions match the active agent's tool set.  Fall back to
    # the most-recently-written entry if no agent-specific context exists.
    if current_agent:
        ctx = read_context(agent=current_agent)
        if ctx is None:
            ctx = read_context()  # cross-agent awareness fallback
    else:
        ctx = read_context()

    if ctx is None:
        return user_query

    ctx_agent = ctx.get("agent", "unknown")
    topic    = ctx.get("topic", "")
    entities = ctx.get("resolved_entities", {})
    awaiting = ctx.get("awaiting", "")
    w_str    = ctx.get("written_at", "")
    # For legacy callers that read the local `agent` variable below:
    agent = ctx_agent

    # Human-friendly age stamp
    age_label = ""
    if w_str:
        try:
            age_sec = (datetime.now() - datetime.fromisoformat(w_str)).total_seconds()
            if age_sec < 120:
                age_label = "just now"
            elif age_sec < 3600:
                age_label = f"{int(age_sec / 60)} min ago"
            else:
                age_label = f"{int(age_sec / 3600)}h ago"
        except Exception:
            pass

    header = f"agent={agent}"
    if topic:
        header += f" | topic={topic}"
    if age_label:
        header += f" | written {age_label}"

    lines: List[str] = [
        f"## Context from Previous Turn  [{header}]",
        json.dumps(entities, indent=2, ensure_ascii=False),
    ]

    # Only inject tool-specific CONTEXT INSTRUCTION when the current agent
    # matches the agent that wrote the context (or the caller didn't specify).
    # Cross-agent injection of file/email/drive instructions causes the wrong
    # agent to hallucinate tools it doesn't own (BUG A fix).
    same_agent = (not current_agent) or (current_agent == ctx_agent)
    if awaiting and same_agent:
        instruction = _AWAITING_INSTRUCTIONS.get(
            awaiting,
            f"The user is following up on the above context (awaiting={awaiting}).",
        )
        lines.append(f"\nCONTEXT INSTRUCTION (awaiting={awaiting}):")
        lines.append(instruction)
        lines.append(
            "Do NOT ask the user to re-specify any information already present "
            "in the context block above."
        )
    elif awaiting and not same_agent:
        # Different agent: give awareness note only — no tool instructions
        lines.append(
            f"\n[NOTE: The previous turn was handled by the '{ctx_agent}' agent "
            f"(awaiting={awaiting}). This context is for your awareness only — "
            f"do NOT attempt to call tools that belong to the '{ctx_agent}' agent.]"
        )

    context_block = "\n".join(lines)

    logger.info(
        "[CTX-INJECT] current_agent=%s ctx_agent=%s topic=%s awaiting=%s same_agent=%s "
        "entities_keys=%s",
        current_agent or "(unset)", ctx_agent, topic, awaiting or "(none)", same_agent,
        list(entities.keys()),
    )

    # Insert BEFORE '## Session State' if present; otherwise append.
    marker = "## Session State"
    if marker in user_query:
        idx = user_query.index(marker)
        return user_query[:idx] + context_block + "\n\n" + user_query[idx:]
    return user_query + "\n\n" + context_block


# ---------------------------------------------------------------------------
# Tool factory  —  gives each agent an explicit LLM-callable save_context()
# ---------------------------------------------------------------------------

def make_save_context_tool(agent: str) -> Callable:
    """
    Return a save_context() callable pre-bound to *agent*.

    Signature exposed to the LLM:
        save_context(topic, resolved_entities, awaiting="") -> dict

    Purpose:
        The LLM calls this after producing a list or resolving a date so
        the next user turn has full context without re-asking.

    Example (in scheduler after finding free slots):
        save_context(
            topic="calendar_query",
            resolved_entities={
                "resolved_date": "2026-03-06",
                "date_label": "tomorrow",
                "events": [...],
            },
            awaiting="time_selection",
        )
    """
    def save_context(
        topic: str,
        resolved_entities: Dict[str, Any],
        awaiting: str = "",
    ) -> Dict[str, Any]:
        """
        Persist resolved context so the next turn can act on it without
        asking the user to repeat themselves.

        Args:
            topic:             Label for what was resolved.
                               e.g. "calendar_query", "email_list", "drive_listing"
            resolved_entities: Dict of resolved values.
                               e.g. {"resolved_date": "2026-03-06", "events": [...]}
            awaiting:          What the user is expected to provide next.
                               One of: "time_selection", "event_selection",
                               "email_action", "file_action", "drive_file_action",
                               "confirmation"  (leave empty if no follow-up expected)
        """
        return write_context(
            agent=agent,
            topic=topic,
            resolved_entities=resolved_entities,
            awaiting=awaiting if awaiting else None,
        )

    save_context.__name__   = "save_context"
    save_context.__module__ = __name__
    return save_context


# ---------------------------------------------------------------------------
# Agent-specific auto-context helpers
# Used by orchestrators to wrap listing tools so context is saved automatically
# without needing to rely solely on the LLM calling save_context explicitly.
# ---------------------------------------------------------------------------

def auto_save_calendar_context(
    result: Any,
    resolved_date: str,
    date_label: str = "",
) -> Any:
    """
    After a calendar fetch, save resolved_date + events as context.
    Returns `result` unchanged so it can be used inline as a passthrough.
    """
    try:
        if not isinstance(result, dict) or result.get("status") == "error":
            return result
        events = result.get("events", [])
        entities: Dict[str, Any] = {"resolved_date": resolved_date}
        if date_label:
            entities["date_label"] = date_label
        # Compact event list — strip bulky description / html_link to save space
        entities["events"] = [
            {k: v for k, v in ev.items() if k in ("id", "title", "start", "end", "location")}
            for ev in events[:20]
        ]
        write_context(
            agent="scheduler",
            topic="calendar_query",
            resolved_entities=entities,
            awaiting="time_selection" if not events else "event_selection",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_calendar_context skipped: %s", exc)
    return result


def auto_save_email_context(result: Any, query: str = "") -> Any:
    """
    After listing emails, save the compact email list as context.
    Returns `result` unchanged.
    """
    try:
        msgs = result if isinstance(result, list) else []
        if not msgs:
            return result
        listed = [
            {
                "id":      m.get("id", ""),
                "subject": m.get("subject", "")[:120],
                "sender":  m.get("sender", m.get("from", ""))[:80],
                "date":    m.get("date", ""),
                "snippet": m.get("snippet", "")[:150],
            }
            for m in msgs[:20]
        ]
        entities: Dict[str, Any] = {"listed_emails": listed}
        if query:
            entities["query"] = query
        write_context(
            agent="email",
            topic="email_list",
            resolved_entities=entities,
            awaiting="email_action",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_email_context skipped: %s", exc)
    return result


def auto_save_drive_context(result: Any, query: str = "") -> Any:
    """
    After listing Drive files, save the compact file list as context.
    Returns `result` unchanged.
    """
    try:
        files = result if isinstance(result, list) else []
        if not files:
            return result
        listed = [
            {
                "id":       f.get("id", ""),
                "name":     f.get("name", ""),
                "mimeType": f.get("mimeType", ""),
                "size":     f.get("size_human", f.get("size", "")),
                "modified": f.get("modifiedTime", "")[:10],
            }
            for f in files[:30]
        ]
        entities: Dict[str, Any] = {"listed_files": listed}
        if query:
            entities["query"] = query
        write_context(
            agent="drive",
            topic="drive_listing",
            resolved_entities=entities,
            awaiting="drive_file_action",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_drive_context skipped: %s", exc)
    return result


def auto_save_files_context(result: Any, query: str = "") -> Any:
    """
    After a local file search, save the search metadata as context.
    The actual file paths are in octa_manifest.txt (file manifest);
    for small result sets (≤ 50 files) we also embed the path list directly
    so the LLM can resolve specific-file references ('the second one', 'report.pdf').
    Returns `result` unchanged.
    """
    try:
        if not isinstance(result, dict):
            return result
        results_list = result.get("results", [])
        count = result.get("count", len(results_list))
        if count <= 0:
            return result
        entities: Dict[str, Any] = {
            "query":         query,
            "found_count":   count,
            "file_manifest": str(_MANIFEST_DIR / "octa_manifest.txt"),
        }
        # Embed compact file list for manageable result sets so the LLM can
        # resolve references like 'the second PDF' or 'report.pdf' in follow-up turns.
        if results_list and count <= 50:
            entities["listed_files"] = [
                {
                    "index": idx,
                    "path":  r.get("path", str(r)) if isinstance(r, dict) else str(r),
                    "name":  r.get("name", "") if isinstance(r, dict) else "",
                    "size":  r.get("size_human", r.get("size", "")) if isinstance(r, dict) else "",
                }
                for idx, r in enumerate(results_list[:50])
            ]
        write_context(
            agent="files",
            topic="file_search",
            resolved_entities=entities,
            awaiting="file_action",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_files_context skipped: %s", exc)
    return result


def auto_save_whatsapp_context(resolved_contact: str, contact_name: str = "", query: str = "") -> None:
    """
    After resolving a WhatsApp contact, persist the resolved phone number so
    follow-up turns ('send another message to him') don't need re-resolution.

    Args:
        resolved_contact:  E.164 phone number resolved for this turn.
        contact_name:      Display name of the contact (for readability).
        query:             Original user query (stored for audit purposes).
    """
    try:
        if not resolved_contact:
            return
        entities: Dict[str, Any] = {
            "resolved_contact": resolved_contact,
        }
        if contact_name:
            entities["contact_name"] = contact_name
        if query:
            entities["query"] = query
        write_context(
            agent="whatsapp",
            topic="contact_resolved",
            resolved_entities=entities,
            awaiting="whatsapp_action",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_whatsapp_context skipped: %s", exc)


def auto_save_habit_context(result: Any) -> Any:
    """
    After listing habits or completing a daily_checkin, save the compact habit
    list so the next turn can reference habits by index or name without
    calling get_habits again.
    Returns `result` unchanged.
    """
    try:
        habits: List[Any] = []
        if isinstance(result, list):
            habits = result
        elif isinstance(result, dict):
            habits = result.get("habits", result.get("items", []))
        if not habits:
            return result
        listed = [
            {
                "index":       idx,
                "name":        h.get("name", "") if isinstance(h, dict) else str(h),
                "frequency":   h.get("frequency", "") if isinstance(h, dict) else "",
                "completed_today": h.get("completed_today", h.get("done", False)) if isinstance(h, dict) else False,
                "streak":      h.get("current_streak", h.get("streak", 0)) if isinstance(h, dict) else 0,
            }
            for idx, h in enumerate(habits[:30])
        ]
        write_context(
            agent="habit",
            topic="habit_list",
            resolved_entities={"listed_habits": listed},
            awaiting="habit_action",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_habit_context skipped: %s", exc)
    return result


def auto_save_stock_context(result: Any, symbol: str = "") -> Any:
    """
    After fetching a stock quote or analysis, save the resolved ticker and
    key price data so follow-up turns ('set an alert at 250', 'show technical
    analysis') don't need to re-resolve the ticker.
    Returns `result` unchanged.
    """
    try:
        if not isinstance(result, dict):
            return result
        if result.get("status") == "error":
            return result
        resolved_ticker = (
            result.get("symbol") or result.get("ticker") or symbol or ""
        ).upper()
        if not resolved_ticker:
            return result
        entities: Dict[str, Any] = {
            "resolved_ticker": resolved_ticker,
        }
        # Embed compact price data for immediate follow-up use
        for key in ("price", "current_price", "close", "last"):
            if result.get(key):
                entities["current_price"] = result[key]
                break
        for key in ("change_pct", "change_percent", "percent_change"):
            if result.get(key) is not None:
                entities["change_pct"] = result[key]
                break
        company = result.get("company") or result.get("name") or result.get("longName", "")
        if company:
            entities["company"] = company
        write_context(
            agent="stock",
            topic="stock_query",
            resolved_entities=entities,
            awaiting="stock_action",
        )
    except Exception as exc:
        logger.debug("[context-manifest] auto_save_stock_context skipped: %s", exc)
    return result
