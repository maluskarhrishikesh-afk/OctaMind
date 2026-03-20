"""
Scheduler / Smart Calendar skill orchestrator.

Uses the Google Calendar service to handle scheduling-specific tasks:
finding free slots, booking time blocks, suggesting meeting times, etc.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src.agent.runtime_paths import get_runtime_state_path
from src.calendar.scheduler_preferences import (
    default_scheduler_preferences,
    derive_no_meeting_window_preset,
    get_scheduler_preferences_path,
    get_scheduler_review_recommendations,
    load_scheduler_preferences,
    _preset_to_no_meeting_windows,
    render_scheduler_preference_guidance,
    render_scheduler_preferences_summary,
    save_scheduler_preferences,
    try_apply_scheduler_preference_edits,
)
from src.agent.workflows.skill_react_engine import run_skill_react

from src.agent.workflows.skill_dag_engine import run_skill_dag


_SESSION_STATE_MARKER = "## Session State"
_CONTEXT_MARKER = "## Context from Previous Turn"
_DIARY_MARKER = "## Conversation Diary"


_PENDING_SCHEDULER_PREFERENCES_PATH = get_runtime_state_path(
    "runtime_state",
    "scheduler_preferences_pending.json",
    create_parent=True,
)
_NUMERIC_REPLY_RE = re.compile(r"^\s*(?:option\s+)?\d{1,2}\s*[?.!]*\s*$", re.IGNORECASE)
_SCHEDULER_PREFERENCES_SHOW_RE = re.compile(
    r"\b(show|view|list|open|read)\b.*\b(scheduler|schedular|schedule)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b"
    r"|\b(scheduler|schedular|schedule)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b.*\b(show|view|list|open|read)\b",
    re.IGNORECASE,
)
_SCHEDULER_PREFERENCES_EDIT_RE = re.compile(
    r"\b(edit|change|update|modify|reconfigure|set|setup|set\s*up|configure|customi[sz]e)\b.*\b(scheduler|schedular|schedule)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b"
    r"|\b(scheduler|schedular|schedule)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b.*\b(edit|change|update|modify|reconfigure|set|setup|set\s*up|configure|customi[sz]e)\b",
    re.IGNORECASE,
)
_SCHEDULER_PREFERENCES_APPLY_RE = re.compile(
    r"\b(apply|use|follow)\b.*\b(scheduler|schedular|schedule)\b.*\b(preferences|settings)\b"
    r"|\b(scheduler|schedular|schedule)\b.*\b(preferences|settings)\b.*\b(apply|use|follow)\b",
    re.IGNORECASE,
)
_SCHEDULER_REVIEW_RE = re.compile(
    r"\b(review|digest|recap)\b.*\b(scheduler|schedular|schedule)\b"
    r"|\b(scheduler|schedular|schedule)\b.*\b(review|digest|recap)\b",
    re.IGNORECASE,
)
_SCHEDULER_PREFERENCE_FOLLOWUP_RE = re.compile(
    r"\b(edit|change|update|modify|setup|set\s*up|configure|customi[sz]e|adjust|restart)\b"
    r"|\b(add\s+new\s+ones?|want\s+to\s+add\s+new\s+ones?)\b"
    r"|\b(change\s+them|update\s+them|edit\s+them|use\s+different\s+ones?)\b",
    re.IGNORECASE,
)
_SCHEDULER_PREFERENCE_QUESTIONS = [
    {
        "key": "focus_block_minutes",
        "title": "Default focus block length",
        "prompt": "Choose the default focus-block length to use when you ask for deep work without giving a duration.",
        "options": [(60, "60 minutes"), (90, "90 minutes"), (120, "120 minutes")],
    },
    {
        "key": "meeting_buffer_minutes",
        "title": "Meeting buffer",
        "prompt": "Choose the default buffer to protect before or after meetings.",
        "options": [(0, "No buffer"), (10, "10 minutes"), (15, "15 minutes")],
    },
    {
        "key": "daily_planning_style",
        "title": "Planning style",
        "prompt": "Choose the default planning style for the Scheduler.",
        "options": [("balanced", "Balanced day"), ("deep_work_first", "Deep-work first"), ("meeting_friendly", "Meeting-friendly")],
    },
    {
        "key": "constraint_mode",
        "title": "Constraint mode",
        "prompt": "Choose how aggressively the Scheduler should protect your defaults.",
        "options": [("soft", "Soft constraints"), ("hard", "Hard constraints")],
    },
    {
        "key": "no_meeting_windows_preset",
        "title": "Protected no-meeting window",
        "prompt": "Choose an optional protected window that the Scheduler should avoid when possible.",
        "options": [("none", "No protected window"), ("lunch_weekdays", "Weekday lunch window (13:00-14:00)"), ("focus_mornings", "Weekday focus mornings (09:00-12:00)")],
    },
]


def _get_session_id(artifacts_out: Optional[Dict[str, Any]]) -> str:
    if not isinstance(artifacts_out, dict):
        return ""
    return str(artifacts_out.get("_session_id", "") or "").strip()


def _extract_preference_query(user_query: str) -> str:
    raw_query = str(user_query or "")
    for marker in (_CONTEXT_MARKER, _DIARY_MARKER, _SESSION_STATE_MARKER):
        if marker in raw_query:
            raw_query = raw_query.split(marker, 1)[0]
    return raw_query.strip()


def _scheduler_preferences_session_key(artifacts_out: Optional[Dict[str, Any]]) -> str:
    return _get_session_id(artifacts_out) or "__default__"


def _load_pending_scheduler_preferences() -> Dict[str, Dict[str, Any]]:
    try:
        if _PENDING_SCHEDULER_PREFERENCES_PATH.exists():
            payload = json.loads(_PENDING_SCHEDULER_PREFERENCES_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def _save_pending_scheduler_preferences(state: Dict[str, Dict[str, Any]]) -> None:
    _PENDING_SCHEDULER_PREFERENCES_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _sync_scheduler_preferences_context(session_key: str, state: Optional[Dict[str, Any]]) -> None:
    try:
        from src.agent.manifest.context_manifest import clear_context, write_context  # noqa: PLC0415

        if not state:
            clear_context(agent="scheduler")
            return
        resolved_entities = {
            "session_key": session_key,
            "preference_file": str(get_scheduler_preferences_path()),
            "state_kind": str(state.get("kind", "") or ""),
            "step": int(state.get("step", 0) or 0),
        }
        if isinstance(state.get("preferences"), dict):
            resolved_entities["scheduler_preferences"] = state.get("preferences", {})
        write_context(
            agent="scheduler",
            topic="scheduler_preferences",
            resolved_entities=resolved_entities,
            awaiting="scheduler_action",
            pending_selection={
                "kind": "scheduler_preferences",
                "session_key": session_key,
                "state_kind": str(state.get("kind", "") or ""),
                "step": int(state.get("step", 0) or 0),
            },
        )
    except Exception:
        pass


def _sync_scheduler_preferences_followup_context(session_key: str, preferences: Dict[str, Any], *, followup_kind: str) -> None:
    try:
        from src.agent.manifest.context_manifest import write_context  # noqa: PLC0415

        write_context(
            agent="scheduler",
            topic="scheduler_preferences",
            resolved_entities={
                "session_key": session_key,
                "followup_kind": followup_kind,
                "preference_file": str(get_scheduler_preferences_path()),
                "scheduler_preferences": preferences,
            },
            awaiting="scheduler_action",
        )
    except Exception:
        pass


def _get_pending_scheduler_preferences(session_key: str) -> Dict[str, Any]:
    return _load_pending_scheduler_preferences().get(session_key, {})


def _set_pending_scheduler_preferences(session_key: str, state: Dict[str, Any]) -> None:
    all_state = _load_pending_scheduler_preferences()
    all_state[session_key] = state
    _save_pending_scheduler_preferences(all_state)
    _sync_scheduler_preferences_context(session_key, state)


def _clear_pending_scheduler_preferences(session_key: str) -> None:
    all_state = _load_pending_scheduler_preferences()
    if session_key in all_state:
        del all_state[session_key]
        _save_pending_scheduler_preferences(all_state)
    _sync_scheduler_preferences_context(session_key, None)


def _build_scheduler_skill_context() -> str:
    return f"{_load_skill_context()}\n\n## Active Scheduler Preferences\n{render_scheduler_preference_guidance(load_scheduler_preferences())}"


def _build_scheduler_preference_question_message(state: Dict[str, Any]) -> str:
    step = int(state.get("step", 0) or 0)
    preferences = state.get("preferences", {}) if isinstance(state.get("preferences"), dict) else {}
    question = _SCHEDULER_PREFERENCE_QUESTIONS[step]
    current_value = derive_no_meeting_window_preset(preferences) if question["key"] == "no_meeting_windows_preset" else preferences.get(question["key"])
    lines = [
        f"Scheduler setup {step + 1}/{len(_SCHEDULER_PREFERENCE_QUESTIONS)}: {question['title']}",
        question["prompt"],
    ]
    for index, (value, label) in enumerate(question["options"], start=1):
        marker = " (current)" if value == current_value else ""
        lines.append(f"{index}. {label}{marker}")
    return "\n".join(lines)


def _start_scheduler_preferences_setup(session_key: str, *, base_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = {
        "kind": "guided_setup",
        "step": 0,
        "preferences": base_preferences or load_scheduler_preferences() or default_scheduler_preferences(),
    }
    _set_pending_scheduler_preferences(session_key, state)
    return {
        "status": "success",
        "action": "scheduler_preferences_question",
        "_fast_path": "scheduler_preferences_question",
        "message": _build_scheduler_preference_question_message(state),
    }


def _handle_pending_scheduler_preferences_reply(raw_query: str, session_key: str) -> Optional[Dict[str, Any]]:
    pending = _get_pending_scheduler_preferences(session_key)
    if not pending:
        return None
    if not _NUMERIC_REPLY_RE.match(str(raw_query or "")):
        return None
    selection = int(re.findall(r"\d+", raw_query)[0])
    step = int(pending.get("step", 0) or 0)
    question = _SCHEDULER_PREFERENCE_QUESTIONS[step]
    options = question["options"]
    if selection < 1 or selection > len(options):
        return {
            "status": "success",
            "action": "scheduler_preferences_question",
            "_fast_path": "scheduler_preferences_question",
            "message": f"Please reply with a number between 1 and {len(options)}.\n\n{_build_scheduler_preference_question_message(pending)}",
        }
    chosen_value = options[selection - 1][0]
    preferences = dict(pending.get("preferences", {}) if isinstance(pending.get("preferences"), dict) else {})
    if question["key"] == "no_meeting_windows_preset":
        preferences["no_meeting_windows"] = _preset_to_no_meeting_windows(str(chosen_value))
    else:
        preferences[question["key"]] = chosen_value
    next_step = step + 1
    if next_step >= len(_SCHEDULER_PREFERENCE_QUESTIONS):
        _clear_pending_scheduler_preferences(session_key)
        save_result = save_scheduler_preferences(preferences)
        return {
            "status": "success",
            "action": "scheduler_preferences_saved",
            "_fast_path": "scheduler_preferences_saved",
            "message": f"Scheduler preferences saved.\n{render_scheduler_preferences_summary(save_result.get('preferences', {}))}",
            "file_path": save_result.get("file_path", ""),
        }
    pending["preferences"] = preferences
    pending["step"] = next_step
    _set_pending_scheduler_preferences(session_key, pending)
    return {
        "status": "success",
        "action": "scheduler_preferences_question",
        "_fast_path": "scheduler_preferences_question",
        "message": _build_scheduler_preference_question_message(pending),
    }


def _build_scheduler_review_digest() -> Dict[str, Any]:
    prefs = load_scheduler_preferences()
    recommendations = get_scheduler_review_recommendations(prefs)
    lines = [
        "Scheduler review digest:",
        render_scheduler_preferences_summary(prefs),
        "",
        "Recommendations:",
    ]
    if recommendations:
        lines.extend(f"- {item}" for item in recommendations)
    else:
        lines.append("- Your current Scheduler defaults look stable.")
    return {
        "status": "success",
        "action": "scheduler_review_digest",
        "_fast_path": "scheduler_review_digest",
        "message": "\n".join(lines),
    }


def _apply_direct_scheduler_preference_edits(raw_query: str, session_key: str) -> Optional[Dict[str, Any]]:
    parsed = try_apply_scheduler_preference_edits(raw_query, load_scheduler_preferences())
    if not isinstance(parsed, dict):
        return None
    save_result = save_scheduler_preferences(parsed.get("preferences", {}))
    updated_preferences = save_result.get("preferences", {}) if isinstance(save_result.get("preferences"), dict) else {}
    _sync_scheduler_preferences_followup_context(session_key, updated_preferences, followup_kind="edit")
    changes = parsed.get("changes", []) if isinstance(parsed.get("changes"), list) else []
    change_lines = "\n".join(f"- {item}" for item in changes if str(item or "").strip())
    message = f"Scheduler preferences updated.\n{render_scheduler_preferences_summary(updated_preferences)}"
    if change_lines:
        message = f"{message}\n\nApplied changes:\n{change_lines}"
    return {
        "status": "success",
        "action": "scheduler_preferences_saved",
        "_fast_path": "scheduler_preferences_saved",
        "message": message,
        "file_path": save_result.get("file_path", ""),
    }


def _looks_like_scheduler_preference_followup_setup(raw_query: str) -> bool:
    text = str(raw_query or "")
    lowered = text.lower()
    if not _SCHEDULER_PREFERENCE_FOLLOWUP_RE.search(lowered):
        return False
    return "topic=scheduler_preferences" in lowered or '"scheduler_preferences"' in lowered or "scheduler preferences" in lowered


def _extract_session_state(user_query: str) -> Dict[str, Any]:
    marker = "## Session State"
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


def _load_skill_context() -> str:
    """Load the scheduler skill context from skill_context.md."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _build_all_tools(user_query: str = "") -> Dict[str, Any]:
    from src.calendar import calendar_service as cs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_calendar_context, make_save_context_tool, write_context,
    )
    from datetime import date as _date, timedelta as _td

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
                agent="scheduler",
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
        return auto_save_calendar_context(result, _date.today().isoformat(), "today", agent="scheduler")

    def get_tomorrows_events() -> dict:
        result = cs.get_tomorrows_events()
        tomorrow = (_date.today() + _td(days=1)).isoformat()
        return auto_save_calendar_context(result, tomorrow, "tomorrow", agent="scheduler")

    def get_upcoming_events(days: int = 7, max_results: int = 30) -> dict:
        result = cs.get_upcoming_events(days, max_results)
        return auto_save_calendar_context(result, _date.today().isoformat(), f"next {days} days", agent="scheduler")

    def get_events_for_date(date_str: str) -> dict:
        result = cs.get_events_for_date(date_str)
        return auto_save_calendar_context(result, date_str, agent="scheduler")

    return {
        "get_todays_events":    get_todays_events,
        "get_tomorrows_events": get_tomorrows_events,
        "get_upcoming_events":  get_upcoming_events,
        "get_events_for_date":  get_events_for_date,
        "search_events":  lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "create_event":   lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": _remember_event(cs.create_event(title, start, end, description, location, attendees, calendar_id)),
        "quick_add_event": lambda text: _remember_event(cs.quick_add_event(_augment_quick_add_text(text))),
        "update_event":    lambda event_id, **kwargs: _remember_event(cs.update_event(event_id, **kwargs)),
        "delete_event":    lambda event_id: cs.delete_event(event_id),
        "list_calendars":  lambda: cs.list_calendars(),
        "save_context":    make_save_context_tool("scheduler"),
    }


def _get_tool_docs_for_dag() -> str:
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    return get_all_tool_docs("scheduler")


def _get_tool_docs_for_react(user_query: str) -> str:
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    return load_tool_docs(
        "scheduler",
        user_query,
        always_include=["save_context", "create_event", "quick_add_event"],
    )


def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415
        selected = select_tool_names(
            "scheduler",
            user_query,
            always_include=["save_context", "create_event", "quick_add_event"],
        )
        filtered = {name: all_tools[name] for name in selected if name in all_tools}
        if filtered:
            return filtered
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("scheduler.orchestrator").warning(
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
    session_key = _scheduler_preferences_session_key(artifacts_out)

    pending_result = _handle_pending_scheduler_preferences_reply(fast_path_query, session_key)
    if pending_result is not None:
        return pending_result

    if _looks_like_scheduler_preference_followup_setup(user_query):
        return _start_scheduler_preferences_setup(session_key, base_preferences=load_scheduler_preferences())

    direct_edit_result = _apply_direct_scheduler_preference_edits(fast_path_query, session_key)
    if direct_edit_result is not None:
        return direct_edit_result

    if _SCHEDULER_PREFERENCES_SHOW_RE.search(normalized_query):
        prefs = load_scheduler_preferences()
        _sync_scheduler_preferences_followup_context(session_key, prefs, followup_kind="show")
        return {
            "status": "success",
            "action": "show_scheduler_preferences",
            "_fast_path": "scheduler_preferences_show",
            "file_path": str(get_scheduler_preferences_path()),
            "message": f"{render_scheduler_preferences_summary(prefs)}\n\nPreference file: {get_scheduler_preferences_path()}",
        }

    if _SCHEDULER_PREFERENCES_EDIT_RE.search(normalized_query):
        return _start_scheduler_preferences_setup(session_key, base_preferences=load_scheduler_preferences())

    if _SCHEDULER_PREFERENCES_APPLY_RE.search(normalized_query):
        prefs = load_scheduler_preferences()
        _sync_scheduler_preferences_followup_context(session_key, prefs, followup_kind="apply")
        return {
            "status": "success",
            "action": "apply_scheduler_preferences",
            "_fast_path": "scheduler_preferences_apply",
            "message": (
                "Scheduler preferences are active and will guide future planning defaults when you do not override them in the current request.\n\n"
                f"{render_scheduler_preferences_summary(prefs)}"
            ),
        }

    if _SCHEDULER_REVIEW_RE.search(normalized_query):
        prefs = load_scheduler_preferences()
        _sync_scheduler_preferences_followup_context(session_key, prefs, followup_kind="review")
        return _build_scheduler_review_digest()

    all_tools = _build_all_tools(user_query)
    skill_context = _build_scheduler_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        return run_skill_dag(
            skill_name="scheduler",
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
        _logging.getLogger("scheduler.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        return run_skill_react(
            skill_name="scheduler",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Scheduler skill error: {exc}",
            "action": "react_response",
        }
