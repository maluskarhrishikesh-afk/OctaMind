"""
Scheduler / Smart Calendar skill orchestrator.

Uses the Google Calendar service to handle scheduling-specific tasks:
finding free slots, booking time blocks, suggesting meeting times, etc.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src.agent.runtime_paths import get_runtime_state_path, get_your_data_dir
from src.calendar.scheduler_preferences import (
    default_scheduler_preferences,
    get_scheduler_preferences_path,
    get_scheduler_review_recommendations,
    load_scheduler_preferences,
    parse_scheduler_preferences_template,
    render_scheduler_preference_guidance,
    render_scheduler_preferences_summary,
    render_scheduler_preferences_template,
    save_scheduler_preferences,
    try_apply_scheduler_preference_edits,
    upsert_no_meeting_window,
    upsert_recurring_reminder,
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
_SCHEDULER_SCHEDULE_DRAFT_PATH = get_your_data_dir("scheduler_schedule_draft.md")
_DRAFT_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
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
    r"\b(apply|use|follow)\b.*\b(scheduler|schedular|schedule)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b"
    r"|\b(scheduler|schedular|schedule)\b.*\b(preferences|settings|preference|prefrence|prefrences)\b.*\b(apply|use|follow)\b",
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
_SCHEDULER_SETUP_CANCEL_RE = re.compile(r"\b(cancel|stop|skip|exit|never\s*mind|nevermind)\b", re.IGNORECASE)
_SCHEDULE_REPORT_RE = re.compile(
    r"\b(report|summary|overview|analytics|insights?)\b.*\b(schedule|scheduler|calendar|meetings?|free\s+time)\b"
    r"|\b(how\s+many\s+meetings?|how\s+much\s+free\s+time)\b",
    re.IGNORECASE,
)
_SUGGESTED_SCHEDULE_RE = re.compile(
    r"\b(set|setup|set\s*up|create|build|plan|organi[sz]e)\b.*\b(my|the|a)?\s*(daily\s+)?(schedule|day|routine)\b"
    r"|\bcan\s+you\s+setup\s+my\s+schedule\b"
    r"|\bhelp\s+me\s+setup\s+my\s+schedule\b",
    re.IGNORECASE,
)
_SCHEDULE_APPROVAL_RE = re.compile(
    r"\b(looks\s+good|look\s+good|sounds\s+good|this\s+works|keep\s+it|use\s+this|go\s+with\s+this|approved?)\b",
    re.IGNORECASE,
)
_SCHEDULE_APPLY_RE = re.compile(
    r"\b(apply|save|use|activate)\b.*\b(these\s+changes|this\s+schedule|my\s+schedule|schedule)\b"
    r"|\bapply\s+these\s+changes\s+to\s+my\s+sched(?:u|e)d?ule\b",
    re.IGNORECASE,
)


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


def _build_scheduler_preference_setup_message(state: Dict[str, Any]) -> str:
    preferences = state.get("preferences", {}) if isinstance(state.get("preferences"), dict) else {}
    if str(state.get("kind", "") or "") == "daily_schedule_setup":
        return _build_suggested_schedule_message(preferences)
    return render_scheduler_preferences_template(preferences)


def _render_scheduler_schedule_draft_markdown(preferences: Dict[str, Any]) -> str:
    return "\n".join([
        "# Scheduler Draft Schedule",
        "",
        "This draft is editable through natural-language follow-ups.",
        "It is not active until you say `apply these changes to my schedule` or `looks good`.",
        "",
        _build_suggested_schedule_message(preferences),
        "",
        "```json",
        json.dumps(preferences, indent=2, ensure_ascii=False),
        "```",
    ])


def _save_scheduler_schedule_draft(preferences: Dict[str, Any]) -> str:
    normalized = _seed_suggested_schedule_preferences(preferences)
    _SCHEDULER_SCHEDULE_DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SCHEDULER_SCHEDULE_DRAFT_PATH.write_text(_render_scheduler_schedule_draft_markdown(normalized), encoding="utf-8")
    return str(_SCHEDULER_SCHEDULE_DRAFT_PATH)


def _load_scheduler_schedule_draft() -> Dict[str, Any] | None:
    try:
        if not _SCHEDULER_SCHEDULE_DRAFT_PATH.exists():
            return None
        content = _SCHEDULER_SCHEDULE_DRAFT_PATH.read_text(encoding="utf-8")
        match = _DRAFT_JSON_BLOCK_RE.search(content)
        if not match:
            return None
        payload = json.loads(match.group(1))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _schedule_suggestion_context_present(raw_query: str) -> bool:
    lowered = str(raw_query or "").lower()
    return any(token in lowered for token in (
        "daily_schedule_setup",
        '"followup_kind": "schedule_suggestion"',
        "schedule_setup_suggestion",
        "scheduler draft schedule",
    ))


def _save_schedule_suggestion_preview(session_key: str, preferences: Dict[str, Any], changes: Optional[list[str]] = None) -> Dict[str, Any]:
    normalized = _seed_suggested_schedule_preferences(preferences)
    pending = {
        "kind": "daily_schedule_setup",
        "preferences": normalized,
    }
    _set_pending_scheduler_preferences(session_key, pending)
    draft_path = _save_scheduler_schedule_draft(normalized)
    message = _build_suggested_schedule_message(normalized)
    if changes:
        change_lines = "\n".join(f"- {item}" for item in changes if str(item or "").strip())
        if change_lines:
            message = f"Updated the suggested schedule.\n\n{message}\n\nApplied changes:\n{change_lines}"
    return {
        "status": "success",
        "action": "schedule_setup_suggestion",
        "_fast_path": "schedule_setup_suggestion",
        "message": message,
        "file_path": draft_path,
    }


def _apply_schedule_draft(session_key: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
    _clear_pending_scheduler_preferences(session_key)
    save_result = save_scheduler_preferences(preferences)
    _save_scheduler_schedule_draft(save_result.get("preferences", preferences) if isinstance(save_result.get("preferences"), dict) else preferences)
    return {
        "status": "success",
        "action": "scheduler_preferences_saved",
        "_fast_path": "scheduler_preferences_saved",
        "message": f"Daily schedule applied and active.\n{render_scheduler_preferences_summary(save_result.get('preferences', {}))}",
        "file_path": save_result.get("file_path", ""),
    }


def _seed_suggested_schedule_preferences(preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    prefs = preferences or load_scheduler_preferences() or default_scheduler_preferences()
    seeded = dict(prefs)
    working_hours = dict(seeded.get("working_hours", {}) if isinstance(seeded.get("working_hours"), dict) else {})
    if (
        int(working_hours.get("start_hour", 9) or 9),
        int(working_hours.get("start_minute", 0) or 0),
        int(working_hours.get("end_hour", 18) or 18),
        int(working_hours.get("end_minute", 0) or 0),
    ) == (9, 0, 18, 0):
        working_hours = {
            "start_hour": 9,
            "start_minute": 30,
            "end_hour": 18,
            "end_minute": 30,
        }
    seeded["working_hours"] = working_hours
    seeded["default_meeting_reminder_minutes"] = int(seeded.get("default_meeting_reminder_minutes", 15) or 15)

    window_labels = {
        str(item.get("label", "") or "").strip().lower()
        for item in seeded.get("no_meeting_windows", []) if isinstance(item, dict)
    }
    if "lunch window" not in window_labels:
        seeded = upsert_no_meeting_window(
            seeded,
            label="Lunch window",
            start_hour=13,
            start_minute=0,
            end_hour=14,
            end_minute=0,
            days=["mon", "tue", "wed", "thu", "fri"],
        )
    if "focus time" not in window_labels and "focus block" not in window_labels and "focus mornings" not in window_labels:
        seeded = upsert_no_meeting_window(
            seeded,
            label="Focus time",
            start_hour=10,
            start_minute=0,
            end_hour=12,
            end_minute=0,
            days=["mon", "tue", "wed", "thu", "fri"],
        )

    reminder_labels = {
        str(item.get("label", "") or "").strip().lower()
        for item in seeded.get("recurring_reminders", []) if isinstance(item, dict)
    }
    if "gym" not in reminder_labels and "gym time" not in reminder_labels:
        seeded = upsert_recurring_reminder(seeded, label="Gym", hour=20, minute=0, days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    if "meditation" not in reminder_labels:
        seeded = upsert_recurring_reminder(seeded, label="Meditation", hour=6, minute=30, days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    return seeded


def _clock_to_label(hour: int, minute: int) -> str:
    normalized_hour = int(hour) % 24
    suffix = "AM" if normalized_hour < 12 else "PM"
    display_hour = normalized_hour % 12 or 12
    return f"{display_hour}:{max(0, min(int(minute), 59)):02d} {suffix}"


def _find_window(preferences: Dict[str, Any], *labels: str) -> Dict[str, Any]:
    windows = preferences.get("no_meeting_windows", []) if isinstance(preferences.get("no_meeting_windows"), list) else []
    normalized_labels = {label.lower() for label in labels}
    for item in windows:
        if not isinstance(item, dict):
            continue
        if str(item.get("label", "") or "").strip().lower() in normalized_labels:
            return item
    return {}


def _find_reminder(preferences: Dict[str, Any], *labels: str) -> Dict[str, Any]:
    reminders = preferences.get("recurring_reminders", []) if isinstance(preferences.get("recurring_reminders"), list) else []
    normalized_labels = {label.lower() for label in labels}
    for item in reminders:
        if not isinstance(item, dict):
            continue
        if str(item.get("label", "") or "").strip().lower() in normalized_labels:
            return item
    return {}


def _format_time_range(item: Dict[str, Any], start_key: str, end_key: str, start_minute_key: str, end_minute_key: str) -> str:
    return (
        f"{_clock_to_label(int(item.get(start_key, 9) or 9), int(item.get(start_minute_key, 0) or 0))}"
        f" -> {_clock_to_label(int(item.get(end_key, 18) or 18), int(item.get(end_minute_key, 0) or 0))}"
    )


def _build_suggested_schedule_message(preferences: Dict[str, Any]) -> str:
    prefs = _seed_suggested_schedule_preferences(preferences)
    working_hours = prefs.get("working_hours", {}) if isinstance(prefs.get("working_hours"), dict) else {}
    lunch_window = _find_window(prefs, "Lunch window")
    focus_window = _find_window(prefs, "Focus time", "Focus block", "Focus mornings")
    gym_reminder = _find_reminder(prefs, "Gym", "Gym time")
    meditation_reminder = _find_reminder(prefs, "Meditation")
    lines = [
        "Here is a suggested daily schedule (you can edit anything):",
        "",
        f"Work hours: {_format_time_range(working_hours, 'start_hour', 'end_hour', 'start_minute', 'end_minute')}",
        f"Lunch: {_format_time_range(lunch_window or {'start_hour': 13, 'start_minute': 0, 'end_hour': 14, 'end_minute': 0}, 'start_hour', 'end_hour', 'start_minute', 'end_minute')}",
        f"Focus time (no meetings): {_format_time_range(focus_window or {'start_hour': 10, 'start_minute': 0, 'end_hour': 12, 'end_minute': 0}, 'start_hour', 'end_hour', 'start_minute', 'end_minute')}",
        f"Meeting reminder: {int(prefs.get('default_meeting_reminder_minutes', 15) or 15)} minutes before",
        "",
        "Personal reminders:",
        f"- Gym: {_clock_to_label(int(gym_reminder.get('hour', 20) or 20), int(gym_reminder.get('minute', 0) or 0))}",
        f"- Meditation: {_clock_to_label(int(meditation_reminder.get('hour', 6) or 6), int(meditation_reminder.get('minute', 30) or 30))}",
        "",
        "You can:",
        "1. Edit anything directly",
        '2. Say "looks good"',
        "3. Ask me to customize",
    ]
    return "\n".join(lines)


def _looks_like_scheduler_preference_input(raw_query: str) -> bool:
    text = str(raw_query or "").strip()
    lowered = text.lower()
    if not text:
        return False
    if _NUMERIC_REPLY_RE.match(text):
        return True
    if parse_scheduler_preferences_template(text, load_scheduler_preferences()) is not None:
        return True
    return any(token in lowered for token in (
        "scheduler preference",
        "scheduler preferences",
        "prefrence",
        "prefrences",
        "work hours",
        "work start",
        "work end",
        "focus block",
        "meeting buffer",
        "meeting reminder",
        "protected window",
        "protected time",
        "lunch",
        "gym",
        "meditation",
        "recurring reminders",
    ))


def _start_scheduler_preferences_setup(session_key: str, *, base_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = {
        "kind": "template_setup",
        "preferences": base_preferences or load_scheduler_preferences() or default_scheduler_preferences(),
    }
    _set_pending_scheduler_preferences(session_key, state)
    return {
        "status": "success",
        "action": "scheduler_preferences_question",
        "_fast_path": "scheduler_preferences_question",
        "message": _build_scheduler_preference_setup_message(state),
    }


def _start_suggested_schedule_setup(session_key: str, *, base_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _save_schedule_suggestion_preview(
        session_key,
        _seed_suggested_schedule_preferences(base_preferences or _load_scheduler_schedule_draft() or load_scheduler_preferences() or default_scheduler_preferences()),
    )


def _handle_pending_scheduler_preferences_reply(raw_query: str, session_key: str) -> Optional[Dict[str, Any]]:
    pending = _get_pending_scheduler_preferences(session_key)
    if not pending:
        return None
    text = str(raw_query or "").strip()
    if not text:
        return None
    if _SCHEDULER_SETUP_CANCEL_RE.search(text):
        _clear_pending_scheduler_preferences(session_key)
        return {
            "status": "success",
            "action": "scheduler_preferences_cancelled",
            "_fast_path": "scheduler_preferences_cancelled",
            "message": "Scheduler preference setup cancelled. Your existing preferences are unchanged.",
        }
    if _SCHEDULE_APPROVAL_RE.search(text) or _SCHEDULE_APPLY_RE.search(text):
        approved_preferences = pending.get("preferences", {}) if isinstance(pending.get("preferences"), dict) else load_scheduler_preferences()
        return _apply_schedule_draft(session_key, approved_preferences)
    parsed = parse_scheduler_preferences_template(
        text,
        pending.get("preferences", {}) if isinstance(pending.get("preferences"), dict) else load_scheduler_preferences(),
    )
    if parsed is None:
        direct_edit = try_apply_scheduler_preference_edits(
            text,
            pending.get("preferences", {}) if isinstance(pending.get("preferences"), dict) else load_scheduler_preferences(),
        )
        if not isinstance(direct_edit, dict):
            return None
        updated_preferences = direct_edit.get("preferences", {}) if isinstance(direct_edit.get("preferences"), dict) else pending.get("preferences", {})
        if str(pending.get("kind", "") or "") == "daily_schedule_setup":
            changes = direct_edit.get("changes", []) if isinstance(direct_edit.get("changes"), list) else []
            return _save_schedule_suggestion_preview(session_key, updated_preferences, changes)
        _clear_pending_scheduler_preferences(session_key)
        save_result = save_scheduler_preferences(updated_preferences)
        changes = direct_edit.get("changes", []) if isinstance(direct_edit.get("changes"), list) else []
        change_lines = "\n".join(f"- {item}" for item in changes if str(item or "").strip())
        message = f"Scheduler preferences saved.\n{render_scheduler_preferences_summary(save_result.get('preferences', {}))}"
        if change_lines:
            message = f"{message}\n\nApplied changes:\n{change_lines}"
        return {
            "status": "success",
            "action": "scheduler_preferences_saved",
            "_fast_path": "scheduler_preferences_saved",
            "message": message,
            "file_path": save_result.get("file_path", ""),
        }
    _clear_pending_scheduler_preferences(session_key)
    save_result = save_scheduler_preferences(parsed)
    return {
        "status": "success",
        "action": "scheduler_preferences_saved",
        "_fast_path": "scheduler_preferences_saved",
        "message": f"Scheduler preferences saved.\n{render_scheduler_preferences_summary(save_result.get('preferences', {}))}",
        "file_path": save_result.get("file_path", ""),
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


def _parse_schedule_report_window(raw_query: str) -> tuple[str, str] | None:
    from datetime import date as _date, timedelta as _td  # noqa: PLC0415

    lowered = str(raw_query or "").lower()
    if not _SCHEDULE_REPORT_RE.search(lowered):
        return None
    today = _date.today()
    if "tomorrow" in lowered:
        value = (today + _td(days=1)).isoformat()
        return value, value
    if "today" in lowered:
        value = today.isoformat()
        return value, value
    if "this week" in lowered or "next 7 days" in lowered:
        return today.isoformat(), (today + _td(days=6)).isoformat()
    explicit = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lowered)
    if explicit:
        value = explicit.group(1)
        return value, value
    return today.isoformat(), (today + _td(days=6)).isoformat()


def _build_scheduler_report(session_key: str, raw_query: str) -> Optional[Dict[str, Any]]:
    from src.agent.runtime_paths import get_your_data_dir  # noqa: PLC0415
    import src.calendar.calendar_service as cs  # noqa: PLC0415

    date_window = _parse_schedule_report_window(raw_query)
    if date_window is None:
        return None
    prefs = load_scheduler_preferences()
    report = cs.generate_schedule_report(
        date_window[0],
        date_window[1],
        int(prefs["working_hours"]["start_hour"]),
        int(prefs["working_hours"].get("start_minute", 0)),
        int(prefs["working_hours"]["end_hour"]),
        int(prefs["working_hours"].get("end_minute", 0)),
        prefs.get("no_meeting_windows", []),
        int(prefs.get("meeting_buffer_minutes", 0) or 0),
    )
    if not isinstance(report, dict) or report.get("status") != "success":
        return report if isinstance(report, dict) else None
    report_path = get_your_data_dir(
        "reports",
        f"schedule_report_{date_window[0]}_{date_window[1]}.md",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.get("message", ""), encoding="utf-8")
    _sync_scheduler_preferences_followup_context(session_key, prefs, followup_kind="report")
    report["action"] = "scheduler_report"
    report["_fast_path"] = "scheduler_report"
    report["file_path"] = str(report_path)
    return report


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
    import src.calendar.calendar_service as cs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_calendar_context, make_save_context_tool, write_context,
    )
    from datetime import date as _date, datetime as _datetime, timedelta as _td

    session_vars = _extract_session_state(user_query)
    scheduler_preferences = load_scheduler_preferences()

    def _window_conflicts(start_iso: str, end_iso: str) -> str:
        day = _date.fromisoformat(str(start_iso)[:10])
        start_dt = _datetime.fromisoformat(str(start_iso).replace("Z", "+00:00"))
        end_dt = _datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
        working_hours = scheduler_preferences.get("working_hours", {}) if isinstance(scheduler_preferences.get("working_hours"), dict) else {}
        work_start = _datetime(day.year, day.month, day.day, int(working_hours.get("start_hour", 9) or 9), int(working_hours.get("start_minute", 0) or 0), tzinfo=start_dt.tzinfo)
        work_end = _datetime(day.year, day.month, day.day, int(working_hours.get("end_hour", 18) or 18), int(working_hours.get("end_minute", 0) or 0), tzinfo=end_dt.tzinfo)
        if start_dt < work_start or end_dt > work_end:
            return "Requested time is outside your saved work hours."
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][day.weekday()]
        for window in scheduler_preferences.get("no_meeting_windows", []) if isinstance(scheduler_preferences.get("no_meeting_windows"), list) else []:
            if not isinstance(window, dict):
                continue
            days = window.get("days", []) if isinstance(window.get("days"), list) else []
            if days and weekday not in {str(value).strip().lower() for value in days}:
                continue
            blocked_start = _datetime(day.year, day.month, day.day, int(window.get("start_hour", 0) or 0), int(window.get("start_minute", 0) or 0), tzinfo=start_dt.tzinfo)
            blocked_end = _datetime(day.year, day.month, day.day, int(window.get("end_hour", 0) or 0), int(window.get("end_minute", 0) or 0), tzinfo=end_dt.tzinfo)
            if blocked_start < end_dt and blocked_end > start_dt:
                return f"Requested time overlaps protected window: {window.get('label', 'Protected time')}."
        return ""

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

    def find_free_slots(date_str: str, duration_minutes: int | None = None, calendar_id: str = "primary") -> dict:
        working_hours = scheduler_preferences.get("working_hours", {}) if isinstance(scheduler_preferences.get("working_hours"), dict) else {}
        result = cs.find_free_slots(
            date_str,
            int(duration_minutes or scheduler_preferences.get("focus_block_minutes", 90) or 90),
            int(working_hours.get("start_hour", 9) or 9),
            int(working_hours.get("start_minute", 0) or 0),
            int(working_hours.get("end_hour", 18) or 18),
            int(working_hours.get("end_minute", 0) or 0),
            int(scheduler_preferences.get("meeting_buffer_minutes", 0) or 0),
            calendar_id,
        )
        if result.get("status") != "success":
            return result
        protected_windows = scheduler_preferences.get("no_meeting_windows", []) if isinstance(scheduler_preferences.get("no_meeting_windows"), list) else []
        if not protected_windows:
            return result
        filtered = []
        for slot in result.get("free_slots", []):
            start_iso = str(slot.get("start", "") or "")
            end_iso = str(slot.get("end", "") or "")
            if not start_iso or not end_iso:
                continue
            if _window_conflicts(start_iso, end_iso):
                continue
            filtered.append(slot)
        result["free_slots"] = filtered
        result["message"] = (
            f"Found {len(filtered)} preference-aware free slot(s) on {date_str}."
            if filtered else
            f"No free slots matched your saved work hours and protected windows on {date_str}."
        )
        return result

    def create_event_with_preferences(title: str, start: str, end: str, description: str = "", location: str = "", attendees=None, calendar_id: str = "primary") -> dict:
        conflict = _window_conflicts(start, end)
        if conflict:
            return {"status": "error", "message": conflict}
        result = cs.create_event(title, start, end, description, location, attendees, calendar_id)
        if isinstance(result, dict) and result.get("status") == "success":
            event = result.get("event") if isinstance(result.get("event"), dict) else {}
            event_id = str(event.get("id", "") or "")
            if event_id:
                cs.set_reminder(event_id, int(scheduler_preferences.get("default_meeting_reminder_minutes", 15) or 15), calendar_id)
        return _remember_event(result)

    def update_event_with_preferences(event_id: str, **kwargs) -> dict:
        start_value = str(kwargs.get("start", "") or "")
        end_value = str(kwargs.get("end", "") or "")
        if start_value and end_value:
            conflict = _window_conflicts(start_value, end_value)
            if conflict:
                return {"status": "error", "message": conflict}
        return _remember_event(cs.update_event(event_id, **kwargs))

    def get_schedule_report(start_date: str, end_date: str, calendar_id: str = "primary") -> dict:
        working_hours = scheduler_preferences.get("working_hours", {}) if isinstance(scheduler_preferences.get("working_hours"), dict) else {}
        return cs.generate_schedule_report(
            start_date,
            end_date,
            int(working_hours.get("start_hour", 9) or 9),
            int(working_hours.get("start_minute", 0) or 0),
            int(working_hours.get("end_hour", 18) or 18),
            int(working_hours.get("end_minute", 0) or 0),
            scheduler_preferences.get("no_meeting_windows", []),
            int(scheduler_preferences.get("meeting_buffer_minutes", 0) or 0),
            calendar_id,
        )

    return {
        "get_todays_events":    get_todays_events,
        "get_tomorrows_events": get_tomorrows_events,
        "get_upcoming_events":  get_upcoming_events,
        "get_events_for_date":  get_events_for_date,
        "find_free_slots": find_free_slots,
        "get_schedule_report": get_schedule_report,
        "search_events":  lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "create_event":   create_event_with_preferences,
        "quick_add_event": lambda text: _remember_event(cs.quick_add_event(_augment_quick_add_text(text))),
        "update_event":    update_event_with_preferences,
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
        always_include=["save_context", "create_event", "quick_add_event", "find_free_slots", "get_schedule_report"],
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
            always_include=["save_context", "create_event", "quick_add_event", "find_free_slots", "get_schedule_report"],
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
    draft_preferences = _load_scheduler_schedule_draft() or load_scheduler_preferences()

    pending_result = _handle_pending_scheduler_preferences_reply(fast_path_query, session_key)
    if pending_result is not None:
        return pending_result

    if _get_pending_scheduler_preferences(session_key) and not _looks_like_scheduler_preference_input(fast_path_query):
        _clear_pending_scheduler_preferences(session_key)

    if _SUGGESTED_SCHEDULE_RE.search(normalized_query):
        return _start_suggested_schedule_setup(session_key, base_preferences=draft_preferences)

    if (_SCHEDULE_APPROVAL_RE.search(normalized_query) or _SCHEDULE_APPLY_RE.search(normalized_query)) and _schedule_suggestion_context_present(user_query):
        return _apply_schedule_draft(session_key, draft_preferences)

    if _schedule_suggestion_context_present(user_query):
        draft_direct_edit = try_apply_scheduler_preference_edits(fast_path_query, draft_preferences)
        if isinstance(draft_direct_edit, dict):
            updated_preferences = draft_direct_edit.get("preferences", {}) if isinstance(draft_direct_edit.get("preferences"), dict) else draft_preferences
            changes = draft_direct_edit.get("changes", []) if isinstance(draft_direct_edit.get("changes"), list) else []
            return _save_schedule_suggestion_preview(session_key, updated_preferences, changes)
        if _SCHEDULER_PREFERENCE_FOLLOWUP_RE.search(normalized_query):
            return _start_suggested_schedule_setup(session_key, base_preferences=draft_preferences)

    if _SCHEDULER_PREFERENCE_FOLLOWUP_RE.search(normalized_query) and _looks_like_scheduler_preference_followup_setup(user_query):
        return _start_scheduler_preferences_setup(session_key, base_preferences=load_scheduler_preferences())

    direct_edit_result = _apply_direct_scheduler_preference_edits(fast_path_query, session_key)
    if direct_edit_result is not None:
        return direct_edit_result

    report_result = _build_scheduler_report(session_key, fast_path_query)
    if report_result is not None:
        return report_result

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
