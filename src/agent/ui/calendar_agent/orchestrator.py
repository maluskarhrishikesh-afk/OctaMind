"""
Google Calendar skill orchestrator.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src.agent.runtime_paths import get_runtime_state_path
from src.agent.telemetry import log_fallback_to_react, log_fast_path_hit
from src.agent.workflows.execution_plan import attach_execution_plan, build_execution_plan, build_execution_step
from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag
from src.calendar.calendar_preferences import (
    default_calendar_preferences,
    get_calendar_preferences_path,
    get_calendar_review_recommendations,
    load_calendar_preferences,
    render_calendar_preference_guidance,
    render_calendar_preferences_summary,
    save_calendar_preferences,
)


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
_PENDING_CALENDAR_PREFERENCES_PATH = get_runtime_state_path(
    "runtime_state",
    "calendar_preferences_pending.json",
    create_parent=True,
)
_NUMERIC_REPLY_RE = re.compile(r"^\s*(?:option\s+)?\d{1,2}\s*[?.!]*\s*$", re.IGNORECASE)
_CALENDAR_PREFERENCES_SHOW_RE = re.compile(
    r"\b(show|view|list|open|read)\b.*\b(calendar)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b"
    r"|\b(calendar)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b.*\b(show|view|list|open|read)\b",
    re.IGNORECASE,
)
_CALENDAR_PREFERENCES_EDIT_RE = re.compile(
    r"\b(edit|change|update|modify|reconfigure|set|setup|set\s*up|configure|customi[sz]e)\b.*\b(calendar)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b"
    r"|\b(calendar)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b.*\b(edit|change|update|modify|reconfigure|set|setup|set\s*up|configure|customi[sz]e)\b",
    re.IGNORECASE,
)
_CALENDAR_PREFERENCES_APPLY_RE = re.compile(
    r"\b(apply|use|follow)\b.*\b(calendar)\b.*\b(preferences|settings)\b"
    r"|\b(calendar)\b.*\b(preferences|settings)\b.*\b(apply|use|follow)\b",
    re.IGNORECASE,
)
_CALENDAR_REVIEW_RE = re.compile(
    r"\b(review|digest|recap)\b.*\b(calendar)\b"
    r"|\b(calendar)\b.*\b(review|digest|recap)\b",
    re.IGNORECASE,
)
_CALENDAR_PREFERENCE_FOLLOWUP_RE = re.compile(
    r"\b(edit|change|update|modify|setup|set\s*up|configure|customi[sz]e|adjust|restart)\b"
    r"|\b(add\s+new\s+ones?|want\s+to\s+add\s+new\s+ones?)\b"
    r"|\b(change\s+them|update\s+them|edit\s+them|use\s+different\s+ones?)\b",
    re.IGNORECASE,
)
_CALENDAR_PREFERENCE_QUESTIONS = [
    {
        "key": "working_hours_start",
        "title": "Working-hours start",
        "prompt": "Choose the default start hour to use when looking for calendar slots.",
        "options": [(8, "08:00"), (9, "09:00"), (10, "10:00")],
    },
    {
        "key": "working_hours_end",
        "title": "Working-hours end",
        "prompt": "Choose the default end hour to use when looking for calendar slots.",
        "options": [(17, "17:00"), (18, "18:00"), (19, "19:00")],
    },
    {
        "key": "default_meeting_minutes",
        "title": "Default meeting duration",
        "prompt": "Choose the default meeting duration when you create a meeting without specifying one.",
        "options": [(30, "30 minutes"), (45, "45 minutes"), (60, "60 minutes")],
    },
    {
        "key": "default_reminder_minutes",
        "title": "Default reminder",
        "prompt": "Choose the default reminder lead time when you add a reminder without specifying minutes.",
        "options": [(10, "10 minutes before"), (15, "15 minutes before"), (30, "30 minutes before")],
    },
]


def _return_fast_path_result(result: Dict[str, Any]) -> Dict[str, Any]:
    fast_path = str(result.get("_fast_path", "") or result.get("action", "unknown"))
    log_fast_path_hit("calendar", fast_path)
    return result


def _extract_preference_query(user_query: str) -> str:
    raw_query = str(user_query or "")
    for marker in (_CONTEXT_MARKER, _DIARY_MARKER, _SESSION_STATE_MARKER):
        if marker in raw_query:
            raw_query = raw_query.split(marker, 1)[0]
    return raw_query.strip()


def _get_session_id(artifacts_out: Optional[Dict[str, Any]]) -> str:
    if not isinstance(artifacts_out, dict):
        return ""
    return str(artifacts_out.get("_session_id", "") or "").strip()


def _calendar_preferences_session_key(artifacts_out: Optional[Dict[str, Any]]) -> str:
    return _get_session_id(artifacts_out) or "__default__"


def _load_pending_calendar_preferences() -> Dict[str, Dict[str, Any]]:
    try:
        if _PENDING_CALENDAR_PREFERENCES_PATH.exists():
            payload = json.loads(_PENDING_CALENDAR_PREFERENCES_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def _save_pending_calendar_preferences(state: Dict[str, Dict[str, Any]]) -> None:
    _PENDING_CALENDAR_PREFERENCES_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _sync_calendar_preferences_context(session_key: str, state: Optional[Dict[str, Any]]) -> None:
    try:
        from src.agent.manifest.context_manifest import clear_context, write_context  # noqa: PLC0415

        if not state:
            clear_context(agent="calendar")
            return
        resolved_entities = {
            "session_key": session_key,
            "preference_file": str(get_calendar_preferences_path()),
            "state_kind": str(state.get("kind", "") or ""),
            "step": int(state.get("step", 0) or 0),
        }
        if isinstance(state.get("preferences"), dict):
            resolved_entities["calendar_preferences"] = state.get("preferences", {})
        write_context(
            agent="calendar",
            topic="calendar_preferences",
            resolved_entities=resolved_entities,
            awaiting="calendar_action",
            pending_selection={
                "kind": "calendar_preferences",
                "session_key": session_key,
                "state_kind": str(state.get("kind", "") or ""),
                "step": int(state.get("step", 0) or 0),
            },
        )
    except Exception:
        pass


def _sync_calendar_preferences_followup_context(session_key: str, preferences: Dict[str, Any], *, followup_kind: str) -> None:
    try:
        from src.agent.manifest.context_manifest import write_context  # noqa: PLC0415

        write_context(
            agent="calendar",
            topic="calendar_preferences",
            resolved_entities={
                "session_key": session_key,
                "followup_kind": followup_kind,
                "preference_file": str(get_calendar_preferences_path()),
                "calendar_preferences": preferences,
            },
            awaiting="calendar_action",
        )
    except Exception:
        pass


def _get_pending_calendar_preferences(session_key: str) -> Dict[str, Any]:
    return _load_pending_calendar_preferences().get(session_key, {})


def _set_pending_calendar_preferences(session_key: str, state: Dict[str, Any]) -> None:
    all_state = _load_pending_calendar_preferences()
    all_state[session_key] = state
    _save_pending_calendar_preferences(all_state)
    _sync_calendar_preferences_context(session_key, state)


def _clear_pending_calendar_preferences(session_key: str) -> None:
    all_state = _load_pending_calendar_preferences()
    if session_key in all_state:
        del all_state[session_key]
        _save_pending_calendar_preferences(all_state)
    _sync_calendar_preferences_context(session_key, None)


def _build_calendar_skill_context() -> str:
    return f"{_load_skill_context()}\n\n## Active Calendar Preferences\n{render_calendar_preference_guidance(load_calendar_preferences())}"


def _build_calendar_preference_question_message(state: Dict[str, Any]) -> str:
    step = int(state.get("step", 0) or 0)
    preferences = state.get("preferences", {}) if isinstance(state.get("preferences"), dict) else {}
    question = _CALENDAR_PREFERENCE_QUESTIONS[step]
    if question["key"] == "working_hours_start":
        current_value = preferences.get("working_hours", {}).get("start_hour") if isinstance(preferences.get("working_hours"), dict) else None
    elif question["key"] == "working_hours_end":
        current_value = preferences.get("working_hours", {}).get("end_hour") if isinstance(preferences.get("working_hours"), dict) else None
    else:
        current_value = preferences.get(question["key"])
    lines = [
        f"Calendar setup {step + 1}/{len(_CALENDAR_PREFERENCE_QUESTIONS)}: {question['title']}",
        question["prompt"],
    ]
    for index, (value, label) in enumerate(question["options"], start=1):
        marker = " (current)" if value == current_value else ""
        lines.append(f"{index}. {label}{marker}")
    return "\n".join(lines)


def _start_calendar_preferences_setup(session_key: str, *, base_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = {
        "kind": "guided_setup",
        "step": 0,
        "preferences": base_preferences or load_calendar_preferences() or default_calendar_preferences(),
    }
    _set_pending_calendar_preferences(session_key, state)
    return {
        "status": "success",
        "action": "calendar_preferences_question",
        "_fast_path": "calendar_preferences_question",
        "message": _build_calendar_preference_question_message(state),
    }


def _handle_pending_calendar_preferences_reply(raw_query: str, session_key: str) -> Optional[Dict[str, Any]]:
    pending = _get_pending_calendar_preferences(session_key)
    if not pending:
        return None
    if not _NUMERIC_REPLY_RE.match(str(raw_query or "")):
        return None
    selection = int(re.findall(r"\d+", raw_query)[0])
    step = int(pending.get("step", 0) or 0)
    question = _CALENDAR_PREFERENCE_QUESTIONS[step]
    options = question["options"]
    if selection < 1 or selection > len(options):
        return {
            "status": "success",
            "action": "calendar_preferences_question",
            "_fast_path": "calendar_preferences_question",
            "message": f"Please reply with a number between 1 and {len(options)}.\n\n{_build_calendar_preference_question_message(pending)}",
        }
    chosen_value = options[selection - 1][0]
    preferences = dict(pending.get("preferences", {}) if isinstance(pending.get("preferences"), dict) else {})
    working_hours = dict(preferences.get("working_hours", {}) if isinstance(preferences.get("working_hours"), dict) else {})
    if question["key"] == "working_hours_start":
        working_hours["start_hour"] = chosen_value
        preferences["working_hours"] = working_hours
    elif question["key"] == "working_hours_end":
        working_hours["end_hour"] = chosen_value
        preferences["working_hours"] = working_hours
    else:
        preferences[question["key"]] = chosen_value
    next_step = step + 1
    if next_step >= len(_CALENDAR_PREFERENCE_QUESTIONS):
        _clear_pending_calendar_preferences(session_key)
        save_result = save_calendar_preferences(preferences)
        return {
            "status": "success",
            "action": "calendar_preferences_saved",
            "_fast_path": "calendar_preferences_saved",
            "message": f"Calendar preferences saved.\n{render_calendar_preferences_summary(save_result.get('preferences', {}))}",
            "file_path": save_result.get("file_path", ""),
        }
    pending["preferences"] = preferences
    pending["step"] = next_step
    _set_pending_calendar_preferences(session_key, pending)
    return {
        "status": "success",
        "action": "calendar_preferences_question",
        "_fast_path": "calendar_preferences_question",
        "message": _build_calendar_preference_question_message(pending),
    }


def _build_calendar_review_digest() -> Dict[str, Any]:
    prefs = load_calendar_preferences()
    recommendations = get_calendar_review_recommendations(prefs)
    lines = [
        "Calendar review digest:",
        render_calendar_preferences_summary(prefs),
        "",
        "Recommendations:",
    ]
    if recommendations:
        lines.extend(f"- {item}" for item in recommendations)
    else:
        lines.append("- Your current Calendar defaults look stable.")
    return {
        "status": "success",
        "action": "calendar_review_digest",
        "_fast_path": "calendar_review_digest",
        "message": "\n".join(lines),
    }


def _looks_like_calendar_preference_followup_setup(raw_query: str) -> bool:
    text = str(raw_query or "")
    lowered = text.lower()
    if not _CALENDAR_PREFERENCE_FOLLOWUP_RE.search(lowered):
        return False
    return "topic=calendar_preferences" in lowered or '"calendar_preferences"' in lowered or "calendar preferences" in lowered


def _looks_like_calendar_preference_input(raw_query: str) -> bool:
    text = str(raw_query or "").strip().lower()
    if not text:
        return False
    if _NUMERIC_REPLY_RE.match(text):
        return True
    return any(token in text for token in (
        "calendar preference",
        "calendar preferences",
        "calendar setting",
        "working hours",
        "meeting duration",
        "default reminder",
        "reminder",
        "work start",
        "work end",
    ))


def _query_has_explicit_duration(text: str) -> bool:
    lowered = str(text or "").lower()
    return bool(
        re.search(r"\bfor\s+\d+\s*(minutes?|mins?|hours?|hrs?)\b", lowered)
        or re.search(r"\bfrom\b.*\bto\b", lowered)
        or re.search(r"\b\d{1,2}:\d{2}\b.*\b\d{1,2}:\d{2}\b", lowered)
    )


def _calendar_apply_creation_defaults(text: str, preferences: Dict[str, Any] | None, active_date: str = "") -> str:
    prefs = load_calendar_preferences() if preferences is None else preferences
    normalized = str(text or "").strip()
    if active_date and not re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized) and not re.search(r"\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", normalized, re.IGNORECASE):
        normalized = f"{normalized} on {active_date}"
    if _query_has_explicit_duration(normalized):
        return normalized
    if not re.search(r"\b(meeting|call|appointment|sync|review|session|lunch|focus block|block)\b", normalized, re.IGNORECASE):
        return normalized
    return f"{normalized} for {int(prefs.get('default_meeting_minutes', 45) or 45)} minutes"


def _build_calendar_execution_plan(
    *,
    goal: str,
    description: str,
    confidence: float,
    why: list[str],
    safe_to_apply: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    step = build_execution_step(
        step_id="calendar_fast_path",
        description=description,
        confidence=confidence,
        why=why,
        safe_to_apply=safe_to_apply,
        metadata=metadata,
    )
    return build_execution_plan(goal=goal, steps=[step], requires_confirmation=not safe_to_apply)


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

    return attach_execution_plan({
        "status": "success" if deleted_titles and not failed else "error" if failed and not deleted_titles else "success",
        "message": "\n".join(message_lines) if message_lines else "No matching events were deleted.",
        "action": "react_response",
        "file_path": "",
        "found_paths": [],
        "results": [{"position": position, "title": title} for position, title in deleted_titles],
        "_fast_path": "ordinal_event_delete",
    }, _build_calendar_execution_plan(
        goal="Delete the selected calendar events from the saved event list.",
        description=f"Delete {len(deleted_titles)} event(s) by ordinal position from the saved calendar context.",
        confidence=0.93 if deleted_titles else 0.62,
        why=[
            "The request referred to ordinal positions and the current calendar context already held a saved event list.",
            "Each deletion used the explicit event id stored in that saved context.",
        ],
        safe_to_apply=False,
        metadata={"deleted_count": len(deleted_titles), "failed_count": len(failed)},
    ), include_summary=True, heading="Execution plan", include_step_reasons=True)


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

    return attach_execution_plan({
        "status": "success",
        "message": "\n".join(message_lines),
        "action": "react_response",
        "_fast_path": "month_overview",
        "file_path": "",
        "found_paths": [],
    }, _build_calendar_execution_plan(
        goal="Summarize the calendar load for the requested month.",
        description=f"Review the saved month overview for {month_label} and summarize {count} event(s).",
        confidence=0.97,
        why=[
            "The request matched the deterministic month-overview fast path.",
            "The month boundaries were resolved explicitly before reading calendar events.",
        ],
        metadata={"month_label": month_label, "event_count": count},
    ), include_summary=True, heading="Execution plan", include_step_reasons=True)


def _build_all_tools(user_query: str = "") -> Dict[str, Any]:
    import src.calendar.calendar_service as cs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_calendar_context, make_save_context_tool, write_context,
    )
    from datetime import date as _date, datetime as _datetime, timedelta as _td

    session_vars = _extract_session_state(user_query)
    calendar_preferences = load_calendar_preferences()

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
        return _calendar_apply_creation_defaults(text, calendar_preferences, active_date)

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
        "find_free_slots": lambda date_str, duration_minutes=None, working_start_hour=None, working_start_minute=None, working_end_hour=None, working_end_minute=None, calendar_id="primary": cs.find_free_slots(
            date_str,
            int(duration_minutes or calendar_preferences["default_meeting_minutes"]),
            int(working_start_hour or calendar_preferences["working_hours"]["start_hour"]),
            int(working_start_minute if working_start_minute is not None else calendar_preferences["working_hours"].get("start_minute", 0)),
            int(working_end_hour or calendar_preferences["working_hours"]["end_hour"]),
            int(working_end_minute if working_end_minute is not None else calendar_preferences["working_hours"].get("end_minute", 0)),
            0,
            calendar_id,
        ),
        "create_event": lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": _remember_event(cs.create_event(title, start, end, description, location, attendees, calendar_id)),
        "quick_add_event": lambda text: _remember_event(cs.quick_add_event(_augment_quick_add_text(text))),
        "update_event": lambda event_id, **kwargs: _remember_event(cs.update_event(event_id, **kwargs)),
        "delete_event": lambda event_id: cs.delete_event(event_id),
        "create_recurring_event": lambda title, start, end, recurrence, description="", location="", attendees=None: cs.create_recurring_event(title, start, end, recurrence, description, location, attendees),
        "set_reminder": lambda event_id, minutes_before=None, calendar_id="primary": cs.set_reminder(
            event_id,
            int(minutes_before or calendar_preferences["default_reminder_minutes"]),
            calendar_id,
        ),
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
    _ = agent_id
    fast_path_query = _extract_preference_query(user_query)
    normalized_query = fast_path_query.lower()
    session_key = _calendar_preferences_session_key(artifacts_out)

    pending_result = _handle_pending_calendar_preferences_reply(fast_path_query, session_key)
    if pending_result is not None:
        return _return_fast_path_result(pending_result)

    if _get_pending_calendar_preferences(session_key) and not _looks_like_calendar_preference_input(fast_path_query):
        _clear_pending_calendar_preferences(session_key)

    if _looks_like_calendar_preference_followup_setup(fast_path_query):
        return _return_fast_path_result(_start_calendar_preferences_setup(session_key, base_preferences=load_calendar_preferences()))

    if _CALENDAR_PREFERENCES_SHOW_RE.search(normalized_query):
        prefs = load_calendar_preferences()
        _sync_calendar_preferences_followup_context(session_key, prefs, followup_kind="show")
        return _return_fast_path_result(
            {
                "status": "success",
                "action": "show_calendar_preferences",
                "_fast_path": "calendar_preferences_show",
                "file_path": str(get_calendar_preferences_path()),
                "message": f"{render_calendar_preferences_summary(prefs)}\n\nPreference file: {get_calendar_preferences_path()}",
            }
        )

    if _CALENDAR_PREFERENCES_EDIT_RE.search(normalized_query):
        return _return_fast_path_result(_start_calendar_preferences_setup(session_key, base_preferences=load_calendar_preferences()))

    if _CALENDAR_PREFERENCES_APPLY_RE.search(normalized_query):
        prefs = load_calendar_preferences()
        _sync_calendar_preferences_followup_context(session_key, prefs, followup_kind="apply")
        return _return_fast_path_result(
            {
                "status": "success",
                "action": "apply_calendar_preferences",
                "_fast_path": "calendar_preferences_apply",
                "message": (
                    "Calendar preferences are active and will be used as defaults for slot finding, meeting duration, and reminders when you do not override them in the current request.\n\n"
                    f"{render_calendar_preferences_summary(prefs)}"
                ),
            }
        )

    if _CALENDAR_REVIEW_RE.search(normalized_query):
        prefs = load_calendar_preferences()
        _sync_calendar_preferences_followup_context(session_key, prefs, followup_kind="review")
        return _return_fast_path_result(_build_calendar_review_digest())

    all_tools = _build_all_tools(user_query)
    ordinal_delete_result = _handle_ordinal_event_delete_query(user_query, all_tools)
    if ordinal_delete_result is not None:
        return _return_fast_path_result(ordinal_delete_result)
    fast_path_result = _handle_month_overview_query(user_query, all_tools)
    if fast_path_result is not None:
        return _return_fast_path_result(fast_path_result)
    skill_context = _build_calendar_skill_context()
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
        log_fallback_to_react("calendar", "calendar_orchestrator_exception")
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
