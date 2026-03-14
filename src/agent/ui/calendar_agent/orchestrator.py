"""
Google Calendar skill orchestrator.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag


_SESSION_STATE_MARKER = "## Session State"
_CONTEXT_MARKER = "## Context from Previous Turn"
_DIARY_MARKER = "## Conversation Diary"
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_OVERVIEW_NOISE_TOKENS = {
    "a", "an", "and", "appointments", "appointment", "are", "booked", "calendar",
    "count", "current", "do", "event", "events", "for", "have", "how", "i", "in",
    "is", "list", "many", "meeting", "meetings", "month", "my", "number", "of", "on",
    "scheduled", "schedule", "show", "this", "upcoming", "what", "which",
    "next", "last", "previous",
    *_MONTH_NAMES.keys(),
}


def _load_skill_context() -> str:
    """Load the calendar skill context from skill_context.md."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _extract_session_state(user_query: str) -> Dict[str, Any]:
    marker = _SESSION_STATE_MARKER
    if marker not in user_query:
        return {}
    raw = user_query.split(marker, 1)[1].strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _strip_session_state(user_query: str) -> str:
    text = str(user_query or "")
    cut_points = [
        idx for idx in (
            text.find(_CONTEXT_MARKER),
            text.find(_DIARY_MARKER),
            text.find(_SESSION_STATE_MARKER),
        )
        if idx != -1
    ]
    if cut_points:
        text = text[: min(cut_points)]
    return text.strip()


def _read_calendar_context() -> Dict[str, Any]:
    try:
        from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

        context = read_context(agent="calendar")
        return context if isinstance(context, dict) else {}
    except Exception:
        return {}


_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
}


def _extract_ordinal_positions(query_text: str) -> list[int]:
    lowered = query_text.lower()
    positions: list[int] = []

    for match in re.finditer(r"\b(\d{1,3})(?:st|nd|rd|th)\b", lowered):
        try:
            positions.append(int(match.group(1)))
        except Exception:
            continue

    for word, value in _ORDINAL_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            positions.append(value)

    seen: set[int] = set()
    ordered: list[int] = []
    for value in positions:
        if value < 1 or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _handle_ordinal_event_delete_query(user_query: str, tool_map: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from src.agent.manifest.context_manifest import write_context  # noqa: PLC0415

    raw_text = _strip_session_state(user_query)
    lowered = raw_text.lower()
    if not re.search(r"\b(cancel|delete|remove|clear)\b", lowered):
        return None
    if not re.search(r"\b(meeting|meetings|event|events|appointment|appointments|booking|bookings)\b", lowered):
        return None

    positions = _extract_ordinal_positions(raw_text)
    if not positions:
        return None

    context = _read_calendar_context()
    entities = context.get("resolved_entities", {}) if isinstance(context, dict) else {}
    events = list(entities.get("events") or [])
    if not events:
        return None

    missing = [position for position in positions if position > len(events)]
    matched_positions = [position for position in positions if 1 <= position <= len(events)]
    if not matched_positions:
        return {
            "status": "error",
            "message": (
                f"I could not match those references to the current event list. "
                f"The saved list only contains {len(events)} event(s)."
            ),
            "action": "react_response",
        }

    deleted_titles: list[tuple[int, str]] = []
    failed: list[str] = []
    delete_indices = sorted({position - 1 for position in matched_positions}, reverse=True)
    remaining_events = list(events)

    for index in delete_indices:
        event = events[index]
        event_id = str(event.get("id") or "").strip()
        title = str(event.get("title") or f"Event #{index + 1}")
        if not event_id:
            failed.append(f"{index + 1}. {title} (missing event id)")
            continue
        result = tool_map["delete_event"](event_id)
        if isinstance(result, dict) and result.get("status") == "success":
            deleted_titles.append((index + 1, title))
            if index < len(remaining_events):
                remaining_events.pop(index)
        else:
            message = result.get("message", "unknown error") if isinstance(result, dict) else "unknown error"
            failed.append(f"{index + 1}. {title} ({message})")

    if deleted_titles:
        try:
            updated_entities = dict(entities)
            updated_entities["events"] = remaining_events
            write_context(
                agent="calendar",
                topic=str(context.get("topic") or "calendar_query"),
                resolved_entities=updated_entities,
                awaiting="event_selection" if remaining_events else "time_selection",
            )
        except Exception:
            pass

    message_lines: list[str] = []
    if deleted_titles:
        label = "meeting" if len(deleted_titles) == 1 else "meetings"
        message_lines.append(f"Deleted {len(deleted_titles)} {label} from the saved list:")
        message_lines.extend(
            f"- {position}. {title}" for position, title in sorted(deleted_titles, key=lambda item: item[0])
        )
    if missing:
        if message_lines:
            message_lines.append("")
        message_lines.append(
            f"These positions were outside the saved list range: {', '.join(str(value) for value in missing)}."
        )
    if failed:
        if message_lines:
            message_lines.append("")
        message_lines.append("I could not delete these event(s):")
        message_lines.extend(f"- {item}" for item in failed)

    return {
        "status": "success" if deleted_titles and not failed else "error" if failed and not deleted_titles else "success",
        "message": "\n".join(message_lines) if message_lines else "No matching events were deleted.",
        "action": "react_response",
        "file_path": "",
        "found_paths": [],
        "results": [{"position": position, "title": title} for position, title in deleted_titles],
        "_fast_path": "ordinal_event_delete",
    }


def _get_reference_date(user_query: str):
    from datetime import date as _date, datetime as _datetime

    session_state = _extract_session_state(user_query)
    current_date = str(session_state.get("current_date") or "").strip()
    if current_date:
        try:
            return _datetime.fromisoformat(current_date[:10]).date()
        except Exception:
            pass
    return _date.today()


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + delta
    shifted_year, shifted_zero_based_month = divmod(month_index, 12)
    return shifted_year, shifted_zero_based_month + 1


def _extract_significant_tokens(query_text: str) -> list[str]:
    tokens = re.findall(r"[a-z]+", query_text.lower())
    return [token for token in tokens if token not in _OVERVIEW_NOISE_TOKENS]


def _parse_month_overview_query(user_query: str) -> Optional[Dict[str, Any]]:
    from datetime import datetime as _datetime

    raw_text = _strip_session_state(user_query)
    lowered = raw_text.lower()

    mode: Optional[str] = None
    if re.search(r"\b(how many|count|number of)\b", lowered):
        mode = "count"
    elif re.search(r"\b(show|list|what|which)\b", lowered):
        mode = "list"
    if mode is None:
        return None

    anchor_date = _get_reference_date(user_query)
    year, month = anchor_date.year, anchor_date.month

    if re.search(r"\b(this|current)\s+month\b", lowered):
        pass
    elif re.search(r"\bnext\s+month\b", lowered):
        year, month = _shift_month(year, month, 1)
    elif re.search(r"\b(last|previous)\s+month\b", lowered):
        year, month = _shift_month(year, month, -1)
    else:
        explicit_match = re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b(?:\s+(\d{4}))?",
            lowered,
        )
        if not explicit_match:
            return None
        month = _MONTH_NAMES[explicit_match.group(1)]
        year = int(explicit_match.group(2) or anchor_date.year)

    if _extract_significant_tokens(lowered):
        return None

    month_label = _datetime(year, month, 1).strftime("%B %Y")
    return {
        "year": year,
        "month": month,
        "mode": mode,
        "month_label": month_label,
    }


def _format_month_event_line(index: int, event: Dict[str, Any]) -> str:
    from datetime import datetime as _datetime

    title = str(event.get("title") or "(No title)")
    start_raw = str(event.get("start") or "")
    end_raw = str(event.get("end") or "")

    if start_raw and "T" in start_raw:
        try:
            start_dt = _datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            date_label = start_dt.strftime("%b %d, %Y")
            start_time = start_dt.strftime("%I:%M %p").lstrip("0")
            if end_raw and "T" in end_raw:
                end_dt = _datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                end_time = end_dt.strftime("%I:%M %p").lstrip("0")
                when = f"{date_label}, {start_time} - {end_time}"
            else:
                when = f"{date_label}, {start_time}"
        except Exception:
            when = start_raw
    else:
        when = f"{start_raw or 'Unknown date'} (all day)"

    return f"{index}. **{title}** — {when}"


def _handle_month_overview_query(user_query: str, tool_map: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    parsed = _parse_month_overview_query(user_query)
    if parsed is None:
        return None

    result = tool_map["get_events_for_month"](parsed["year"], parsed["month"])
    if not isinstance(result, dict) or result.get("status") != "success":
        return result if isinstance(result, dict) else None

    events = list(result.get("events") or result.get("results") or [])
    count = int(result.get("count") or len(events))
    month_label = parsed["month_label"]
    message_lines = [f"You have **{count} calendar event{'s' if count != 1 else ''}** scheduled in **{month_label}**."]

    if count == 0:
        message_lines.append("Your calendar is clear for that month.")
    else:
        display_limit = 10
        shown_events = events[:display_limit]
        message_lines.append("")
        if count > display_limit:
            message_lines.append(f"Here are the first {display_limit}:")
        else:
            message_lines.append("Here are the details:")
        message_lines.append("")
        message_lines.extend(_format_month_event_line(index, event) for index, event in enumerate(shown_events, start=1))
        if count > display_limit:
            message_lines.append("")
            message_lines.append(f"{count - display_limit} more event(s) are scheduled later in the month.")

    return {
        "status": "success",
        "message": "\n".join(message_lines),
        "action": "react_response",
        "_fast_path": "month_overview",
        "file_path": "",
        "found_paths": [],
    }


def _build_all_tools(user_query: str = "") -> Dict[str, Any]:
    from src.calendar import calendar_service as cs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_calendar_context, make_save_context_tool, write_context,
    )
    from datetime import date as _date, datetime as _datetime, timedelta as _td

    session_vars = _extract_session_state(user_query)

    def _remember_event(result: dict) -> dict:
        if not isinstance(result, dict) or result.get("status") != "success":
            return result
        event = result.get("event")
        if not isinstance(event, dict):
            return result
        resolved_date = str(event.get("start", ""))[:10] if event.get("start") else session_vars.get("active_date", "")
        compact = {k: event.get(k) for k in ("id", "title", "start", "end", "location") if event.get(k)}
        try:
            write_context(
                agent="calendar",
                topic="calendar_event",
                resolved_entities={
                    "resolved_date": resolved_date,
                    "selected_event": compact,
                    "events": [compact],
                },
                awaiting="event_selection",
            )
        except Exception:
            pass
        return result

    def _augment_quick_add_text(text: str) -> str:
        active_date = session_vars.get("active_date", "")
        if not active_date:
            return text
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
            return text
        if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", text, re.IGNORECASE):
            return text
        if re.search(r"\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.IGNORECASE):
            return text
        return f"{text} on {active_date}"

    def get_todays_events() -> dict:
        result = cs.get_todays_events()
        return auto_save_calendar_context(result, _date.today().isoformat(), "today", agent="calendar")

    def get_tomorrows_events() -> dict:
        result = cs.get_tomorrows_events()
        tomorrow = (_date.today() + _td(days=1)).isoformat()
        return auto_save_calendar_context(result, tomorrow, "tomorrow", agent="calendar")

    def get_upcoming_events(days: int = 7, max_results: int = 20) -> dict:
        result = cs.get_upcoming_events(days, max_results)
        return auto_save_calendar_context(result, _date.today().isoformat(), f"next {days} days", agent="calendar")

    def get_events_for_date(date_str: str) -> dict:
        result = cs.get_events_for_date(date_str)
        return auto_save_calendar_context(result, date_str, agent="calendar")

    def get_events_for_month(year: int, month: int, max_results: int = 200) -> dict:
        result = cs.get_events_for_month(year, month, max_results=max_results)
        month_label = _datetime(year, month, 1).strftime("%B %Y")
        return auto_save_calendar_context(result, f"{year:04d}-{month:02d}-01", month_label, agent="calendar")

    return {
        "get_todays_events": get_todays_events,
        "get_tomorrows_events": get_tomorrows_events,
        "get_upcoming_events": get_upcoming_events,
        "get_events_for_date": get_events_for_date,
        "get_events_for_month": get_events_for_month,
        "search_events": lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "list_events": lambda start=None, end=None, max_results=20, calendar_id="primary": cs.list_events(start, end, max_results, calendar_id),
        "get_event": lambda event_id: cs.get_event(event_id),
        "create_event": lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": _remember_event(cs.create_event(title, start, end, description, location, attendees, calendar_id)),
        "quick_add_event": lambda text: _remember_event(cs.quick_add_event(_augment_quick_add_text(text))),
        "update_event": lambda event_id, **kwargs: _remember_event(cs.update_event(event_id, **kwargs)),
        "delete_event": lambda event_id: cs.delete_event(event_id),
        "create_recurring_event": lambda title, start, end, recurrence, description="", location="", attendees=None: cs.create_recurring_event(title, start, end, recurrence, description, location, attendees),
        "list_calendars": lambda: cs.list_calendars(),
        "save_context": make_save_context_tool("calendar"),
    }


def _get_tool_docs_for_dag() -> str:
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    return get_all_tool_docs("calendar")


def _get_tool_docs_for_react(user_query: str) -> str:
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    return load_tool_docs(
        "calendar",
        user_query,
        always_include=["save_context", "quick_add_event", "create_event"],
    )


def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if all_tools is None:
        all_tools = _build_all_tools(user_query)
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415
        selected = select_tool_names(
            "calendar",
            user_query,
            always_include=["save_context", "quick_add_event", "create_event"],
        )
        filtered = {name: all_tools[name] for name in selected if name in all_tools}
        if filtered:
            return filtered
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("calendar.orchestrator").warning(
            "[tool-map] FAISS filtering failed (%s) — using full tool map", exc
        )
    return all_tools


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    all_tools = _build_all_tools(user_query)
    ordinal_delete_result = _handle_ordinal_event_delete_query(user_query, all_tools)
    if ordinal_delete_result is not None:
        return ordinal_delete_result
    fast_path_result = _handle_month_overview_query(user_query, all_tools)
    if fast_path_result is not None:
        return fast_path_result
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        return run_skill_dag(
            skill_name="calendar",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("calendar.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        return run_skill_react(
            skill_name="calendar",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Calendar skill error: {exc}",
            "action": "react_response",
        }
