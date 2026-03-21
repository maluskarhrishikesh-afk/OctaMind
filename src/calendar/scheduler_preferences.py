from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.agent.runtime_paths import get_your_data_dir


_SCHEDULER_PREFERENCES_PATH = get_your_data_dir("scheduler_preferences.md")
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

DEFAULT_SCHEDULER_PREFERENCES: Dict[str, Any] = {
    "version": 2,
    "updated_at": "",
    "working_hours": {
        "start_hour": 9,
        "start_minute": 0,
        "end_hour": 18,
        "end_minute": 0,
    },
    "focus_block_minutes": 90,
    "meeting_buffer_minutes": 10,
    "default_meeting_reminder_minutes": 15,
    "daily_planning_style": "balanced",
    "constraint_mode": "soft",
    "no_meeting_windows": [],
    "recurring_reminders": [],
}

_PLANNING_STYLE_LABELS = {
    "balanced": "Balanced day",
    "deep_work_first": "Deep-work first",
    "meeting_friendly": "Meeting-friendly",
}
_CONSTRAINT_MODE_LABELS = {
    "soft": "Soft constraints",
    "hard": "Hard constraints",
}
_ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY_ALIASES = {
    "monday": "mon", "mondays": "mon", "mon": "mon",
    "tuesday": "tue", "tuesdays": "tue", "tue": "tue", "tues": "tue",
    "wednesday": "wed", "wednesdays": "wed", "wed": "wed",
    "thursday": "thu", "thursdays": "thu", "thu": "thu", "thurs": "thu",
    "friday": "fri", "fridays": "fri", "fri": "fri",
    "saturday": "sat", "saturdays": "sat", "sat": "sat",
    "sunday": "sun", "sundays": "sun", "sun": "sun",
}
_DAY_TOKEN_PATTERN = "|".join(sorted((re.escape(token) for token in _DAY_ALIASES), key=len, reverse=True))
_DAY_RANGE_RE = re.compile(
    rf"\b(?P<start>{_DAY_TOKEN_PATTERN})\b\s*(?:to|through|thru|until|till|\-|–)\s*\b(?P<end>{_DAY_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)
_TIME_RANGE_RE = re.compile(
    r"(?:(?:\bbetween|\bfrom)\s*)?(?P<start>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)\s*(?:and|to|-|–)\s*(?P<end>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_WEEKDAYS_RE = re.compile(r"\bweek\s*days?\b|\bweekdays\b", re.IGNORECASE)
_WEEKENDS_RE = re.compile(r"\bweek\s*ends?\b|\bweekends\b", re.IGNORECASE)
_EVERY_DAY_RE = re.compile(r"\b(every\s+day|daily|each\s+day)\b", re.IGNORECASE)
_WORK_HOURS_RE = re.compile(
    r"\bwork(?:ing)?\s+hours?\b\s*[:\-]?\s*(?P<start>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)\s*(?:to|\-|–)\s*(?P<end>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_WORK_START_RE = re.compile(
    r"\bwork(?:ing)?\s+start(?:\s+time)?\b\s*[:\-]?\s*(?P<value>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_WORK_END_RE = re.compile(
    r"\bwork(?:ing)?\s+end(?:\s+time)?\b\s*[:\-]?\s*(?P<value>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_FOCUS_BLOCK_RE = re.compile(r"\bfocus(?:\s+block)?(?:\s+length)?\b.*?(\d{2,3})\s*(?:minutes?|mins?)", re.IGNORECASE)
_MEETING_BUFFER_RE = re.compile(r"\bmeeting\s+buffer\b.*?(\d{1,3})\s*(?:minutes?|mins?)", re.IGNORECASE)
_MEETING_REMINDER_RE = re.compile(
    r"\b(?:meeting\s+reminders?|reminder\s+before\s+meetings?|default\s+meeting\s+reminder)\b.*?(\d{1,3})\s*(?:minutes?|mins?)",
    re.IGNORECASE,
)
_PLANNING_STYLE_RE = re.compile(r"\bplanning\s+style\b\s*[:\-]?\s*(balanced|deep[- ]work first|meeting[- ]friendly)", re.IGNORECASE)
_CONSTRAINT_MODE_RE = re.compile(r"\bconstraint\s+mode\b\s*[:\-]?\s*(soft|hard)", re.IGNORECASE)
_FOCUS_TIME_RANGE_RE = re.compile(
    r"\bfocus\s+time\b\s*[:\-]?\s*(?P<start>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)\s*(?:and|to|-|–)\s*(?P<end>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_LUNCH_TIME_RANGE_RE = re.compile(
    r"\blunch\b\s*[:\-]?\s*(?P<start>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)\s*(?:and|to|-|–)\s*(?P<end>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_NO_MEETINGS_ALLOWED_RE = re.compile(r"\b(no\s+meetings?|no\s+meeting\s+allowed|avoid\s+meetings?)\b", re.IGNORECASE)
_NO_MEETINGS_WITH_TIME_RE = re.compile(
    r"\b(no\s+meetings?|no\s+meeting\s+allowed|avoid\s+meetings?)\b.{0,40}\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?",
    re.IGNORECASE,
)
_NO_MEETINGS_DAY_ONLY_RE = re.compile(
    r"\b(?:no\s+meetings?|no\s+meeting\s+allowed|avoid\s+meetings?)\b(?:\s+allowed)?\s+on\s+(?P<days>.+?)(?=\s+(?:and|also|between|from)\b|[,.!?;\n]|$)",
    re.IGNORECASE,
)
_TEMPLATE_FIELD_RE = re.compile(r"^\s*(?P<label>[A-Za-z /-]+):\s*(?P<value>.+?)\s*$")
_TEMPLATE_WINDOW_ITEM_RE = re.compile(r"^\s*[-*]\s*(?P<label>[^|]+?)\s*\|\s*(?P<days>[^|]+?)\s*\|\s*(?P<start>[^-]+?)\s*(?:-|to)\s*(?P<end>.+?)\s*$")
_TEMPLATE_REMINDER_ITEM_RE = re.compile(r"^\s*[-*]\s*(?P<label>[^|]+?)\s*\|\s*(?P<days>[^|]+?)\s*\|\s*(?P<time>.+?)\s*$")


def get_scheduler_preferences_path() -> Path:
    return _SCHEDULER_PREFERENCES_PATH


def default_scheduler_preferences() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_SCHEDULER_PREFERENCES)


def _default_no_meeting_window_preset() -> str:
    return "none"


def _clock_to_string(hour: int, minute: int) -> str:
    normalized_hour = int(hour) % 24
    normalized_minute = max(0, min(int(minute), 59))
    suffix = "AM" if normalized_hour < 12 else "PM"
    display_hour = normalized_hour % 12 or 12
    return f"{display_hour}:{normalized_minute:02d} {suffix}"


def _clock_24_to_string(hour: int, minute: int) -> str:
    return f"{int(hour) % 24:02d}:{max(0, min(int(minute), 59)):02d}"


def _format_days(days: List[str]) -> str:
    normalized = [str(day or "").strip().lower() for day in days if str(day or "").strip()]
    if not normalized or normalized == _ALL_DAYS:
        return "Daily"
    if normalized == _ALL_DAYS[:5]:
        return "Weekdays"
    if normalized == _ALL_DAYS[5:]:
        return "Weekends"
    labels = {
        "mon": "Mon",
        "tue": "Tue",
        "wed": "Wed",
        "thu": "Thu",
        "fri": "Fri",
        "sat": "Sat",
        "sun": "Sun",
    }
    return ", ".join(labels.get(day, day.title()) for day in normalized)


def format_no_meeting_window(window: Dict[str, Any]) -> str:
    days = window.get("days", []) if isinstance(window.get("days"), list) else []
    return (
        f"{str(window.get('label', 'Protected time') or 'Protected time').strip()} "
        f"({_format_days(days)} {_clock_to_string(int(window.get('start_hour', 9) or 9), int(window.get('start_minute', 0) or 0))}"
        f"-{_clock_to_string(int(window.get('end_hour', 17) or 17), int(window.get('end_minute', 0) or 0))})"
    )


def _parse_clock_text(value: str) -> tuple[int, int] | None:
    text = str(value or "").strip().lower().replace(".", "")
    match = re.fullmatch(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<suffix>am|pm)?", text)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    suffix = str(match.group("suffix") or "").strip()
    if minute < 0 or minute > 59:
        return None
    if suffix:
        if hour < 1 or hour > 12:
            return None
        if suffix == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif hour > 23:
        return None
    return hour, minute


def _normalize_days_for_window(days: List[str] | None) -> List[str]:
    if not days:
        return list(_ALL_DAYS)
    normalized = []
    for item in days:
        lowered = str(item or "").strip().lower()
        if lowered in _ALL_DAYS and lowered not in normalized:
            normalized.append(lowered)
    return normalized or list(_ALL_DAYS)


def _expand_day_range(start_day: str, end_day: str) -> List[str]:
    start = str(start_day or "").strip().lower()
    end = str(end_day or "").strip().lower()
    if start not in _ALL_DAYS or end not in _ALL_DAYS:
        return []
    start_index = _ALL_DAYS.index(start)
    end_index = _ALL_DAYS.index(end)
    if start_index <= end_index:
        return list(_ALL_DAYS[start_index:end_index + 1])
    return list(_ALL_DAYS[start_index:] + _ALL_DAYS[:end_index + 1])


def _extract_explicit_days(raw_query: str) -> List[str]:
    text = str(raw_query or "")
    matched_days: List[str] = []
    for match in _DAY_RANGE_RE.finditer(text):
        start = _DAY_ALIASES.get(str(match.group("start") or "").strip().lower())
        end = _DAY_ALIASES.get(str(match.group("end") or "").strip().lower())
        for normalized in _expand_day_range(start or "", end or ""):
            if normalized not in matched_days:
                matched_days.append(normalized)
    for token, normalized in _DAY_ALIASES.items():
        if re.search(rf"\b{token}\b", text, re.IGNORECASE) and normalized not in matched_days:
            matched_days.append(normalized)
    if matched_days:
        return [day for day in _ALL_DAYS if day in matched_days]
    if _WEEKDAYS_RE.search(text):
        return list(_ALL_DAYS[:5])
    if _WEEKENDS_RE.search(text):
        return list(_ALL_DAYS[5:])
    if _EVERY_DAY_RE.search(text):
        return list(_ALL_DAYS)
    return []


def _extract_requested_days(raw_query: str) -> List[str]:
    explicit_days = _extract_explicit_days(raw_query)
    return explicit_days or list(_ALL_DAYS)


def _derive_window_label(raw_query: str) -> str:
    lowered = str(raw_query or "").lower()
    if "gym" in lowered:
        return "Gym time"
    if "lunch" in lowered:
        return "Lunch window"
    if "focus time" in lowered:
        return "Focus time"
    if "focus" in lowered or "deep work" in lowered:
        return "Focus block"
    return "Protected time"


def _normalize_reminder_days(raw_days: str) -> List[str]:
    text = str(raw_days or "").strip().lower()
    if not text or text in {"daily", "every day", "all days"}:
        return list(_ALL_DAYS)
    if text in {"weekdays", "weekday"}:
        return list(_ALL_DAYS[:5])
    if text in {"weekends", "weekend"}:
        return list(_ALL_DAYS[5:])
    parts = re.split(r"\s*,\s*|\s+/\s*|\s+", text)
    mapped: List[str] = []
    for part in parts:
        key = _DAY_ALIASES.get(part)
        if key and key not in mapped:
            mapped.append(key)
    return mapped or list(_ALL_DAYS)


def _format_working_hours(working_hours: Dict[str, Any]) -> str:
    return (
        f"{_clock_to_string(int(working_hours.get('start_hour', 9) or 9), int(working_hours.get('start_minute', 0) or 0))}"
        f"-{_clock_to_string(int(working_hours.get('end_hour', 18) or 18), int(working_hours.get('end_minute', 0) or 0))}"
    )


def _int_or_default(value: Any, default: int) -> int:
    if value is None or value == "":
        return int(default)
    return int(value)


def format_recurring_reminder(reminder: Dict[str, Any]) -> str:
    return (
        f"{str(reminder.get('label', 'Reminder') or 'Reminder').strip()} "
        f"({_format_days(reminder.get('days', []))} {_clock_to_string(int(reminder.get('hour', 8) or 8), int(reminder.get('minute', 0) or 0))})"
    )


def upsert_recurring_reminder(
    preferences: Dict[str, Any] | None,
    *,
    label: str,
    hour: int,
    minute: int,
    days: List[str] | None = None,
) -> Dict[str, Any]:
    prefs = _normalize_scheduler_preferences(preferences)
    normalized_label = str(label or "Reminder").strip() or "Reminder"
    normalized_days = _normalize_days_for_window(days)
    reminders: List[Dict[str, Any]] = []
    replaced = False
    for item in prefs.get("recurring_reminders", []) if isinstance(prefs.get("recurring_reminders"), list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("label", "") or "").strip().lower() == normalized_label.lower():
            reminders.append(
                {
                    "label": normalized_label,
                    "days": normalized_days,
                    "hour": int(hour),
                    "minute": int(minute),
                }
            )
            replaced = True
        else:
            reminders.append(item)
    if not replaced:
        reminders.append(
            {
                "label": normalized_label,
                "days": normalized_days,
                "hour": int(hour),
                "minute": int(minute),
            }
        )
    prefs["recurring_reminders"] = reminders
    return _normalize_scheduler_preferences(prefs)


def render_scheduler_preferences_template(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_scheduler_preferences(preferences)
    windows = prefs.get("no_meeting_windows", []) if isinstance(prefs.get("no_meeting_windows"), list) else []
    reminders = prefs.get("recurring_reminders", []) if isinstance(prefs.get("recurring_reminders"), list) else []
    window_lines = [
        f"- {str(item.get('label', 'Protected time')).strip()} | {_format_days(item.get('days', []))} | {_clock_24_to_string(int(item.get('start_hour', 9) or 9), int(item.get('start_minute', 0) or 0))}-{_clock_24_to_string(int(item.get('end_hour', 17) or 17), int(item.get('end_minute', 0) or 0))}"
        for item in windows if isinstance(item, dict)
    ]
    if not window_lines:
        window_lines = ["- None | Daily | 00:00-00:00"]
    reminder_lines = [
        f"- {str(item.get('label', 'Reminder')).strip()} | {_format_days(item.get('days', []))} | {_clock_24_to_string(int(item.get('hour', 8) or 8), int(item.get('minute', 0) or 0))}"
        for item in reminders if isinstance(item, dict)
    ]
    if not reminder_lines:
        reminder_lines = ["- Gym | Daily | 20:00", "- Meditation | Daily | 06:00"]
    return "\n".join([
        "Scheduler setup template:",
        "Edit the lines below and send the full template back in one message.",
        "",
        f"Work hours: {_clock_24_to_string(int(prefs['working_hours']['start_hour']), int(prefs['working_hours']['start_minute']))}-{_clock_24_to_string(int(prefs['working_hours']['end_hour']), int(prefs['working_hours']['end_minute']))}",
        f"Default focus block: {int(prefs['focus_block_minutes'])} minutes",
        f"Meeting buffer: {int(prefs['meeting_buffer_minutes'])} minutes",
        f"Meeting reminder: {int(prefs['default_meeting_reminder_minutes'])} minutes",
        f"Planning style: {prefs['daily_planning_style']}",
        f"Constraint mode: {prefs['constraint_mode']}",
        "Protected windows:",
        *window_lines,
        "Recurring reminders:",
        *reminder_lines,
        "",
        "Examples:",
        "- Lunch window | Weekdays | 13:00-14:00",
        "- Focus mornings | Weekdays | 09:00-11:00",
    ])


def parse_scheduler_preferences_template(
    raw_query: str,
    preferences: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    text = str(raw_query or "")
    if "Scheduler setup template:" not in text and "Work hours:" not in text:
        return None
    prefs = _normalize_scheduler_preferences(preferences)
    matched_fields = 0
    section = ""
    windows: List[Dict[str, Any]] = []
    reminders: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("protected windows"):
            section = "windows"
            continue
        if lowered.startswith("recurring reminders"):
            section = "reminders"
            continue
        field_match = _TEMPLATE_FIELD_RE.match(raw_line)
        if field_match:
            section = ""
            label = field_match.group("label").strip().lower()
            value = field_match.group("value").strip()
            if label == "work hours":
                hours_match = re.search(r"(?P<start>\d{1,2}:\d{2})\s*(?:to|\-|–)\s*(?P<end>\d{1,2}:\d{2})", value, re.IGNORECASE)
                if hours_match:
                    start_hour, start_minute = [int(part) for part in hours_match.group("start").split(":", 1)]
                    end_hour, end_minute = [int(part) for part in hours_match.group("end").split(":", 1)]
                    prefs["working_hours"] = {
                        "start_hour": start_hour,
                        "start_minute": start_minute,
                        "end_hour": end_hour,
                        "end_minute": end_minute,
                    }
                    matched_fields += 1
                    continue
            if label == "default focus block":
                number_match = re.search(r"(\d{2,3})", value)
                if number_match:
                    prefs["focus_block_minutes"] = int(number_match.group(1))
                    matched_fields += 1
                    continue
            if label == "meeting buffer":
                number_match = re.search(r"(\d{1,3})", value)
                if number_match:
                    prefs["meeting_buffer_minutes"] = int(number_match.group(1))
                    matched_fields += 1
                    continue
            if label == "meeting reminder":
                number_match = re.search(r"(\d{1,3})", value)
                if number_match:
                    prefs["default_meeting_reminder_minutes"] = int(number_match.group(1))
                    matched_fields += 1
                    continue
            if label == "planning style":
                normalized_style = value.lower().replace(" ", "_").replace("-", "_")
                if normalized_style in {"balanced", "deep_work_first", "meeting_friendly"}:
                    prefs["daily_planning_style"] = normalized_style
                    matched_fields += 1
                    continue
            if label == "constraint mode":
                normalized_mode = value.lower().strip()
                if normalized_mode in {"soft", "hard"}:
                    prefs["constraint_mode"] = normalized_mode
                    matched_fields += 1
                    continue
        if section == "windows":
            item_match = _TEMPLATE_WINDOW_ITEM_RE.match(raw_line)
            if item_match:
                label = item_match.group("label").strip()
                if label.lower() == "none":
                    matched_fields += 1
                    continue
                start_clock = _parse_clock_text(item_match.group("start"))
                end_clock = _parse_clock_text(item_match.group("end"))
                if start_clock and end_clock and end_clock > start_clock:
                    windows.append(
                        {
                            "label": label,
                            "days": _normalize_reminder_days(item_match.group("days")),
                            "start_hour": start_clock[0],
                            "start_minute": start_clock[1],
                            "end_hour": end_clock[0],
                            "end_minute": end_clock[1],
                        }
                    )
                    matched_fields += 1
                continue
        if section == "reminders":
            item_match = _TEMPLATE_REMINDER_ITEM_RE.match(raw_line)
            if item_match:
                label = item_match.group("label").strip()
                reminder_clock = _parse_clock_text(item_match.group("time"))
                if reminder_clock:
                    reminders.append(
                        {
                            "label": label,
                            "days": _normalize_reminder_days(item_match.group("days")),
                            "hour": reminder_clock[0],
                            "minute": reminder_clock[1],
                        }
                    )
                    matched_fields += 1
                continue
    if matched_fields <= 0:
        return None
    prefs["no_meeting_windows"] = windows
    prefs["recurring_reminders"] = reminders
    return _normalize_scheduler_preferences(prefs)


def upsert_no_meeting_window(
    preferences: Dict[str, Any] | None,
    *,
    label: str,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
    days: List[str] | None = None,
) -> Dict[str, Any]:
    prefs = _normalize_scheduler_preferences(preferences)
    normalized_label = str(label or "Protected time").strip() or "Protected time"
    normalized_days = _normalize_days_for_window(days)
    updated_windows: List[Dict[str, Any]] = []
    replaced = False
    for item in prefs.get("no_meeting_windows", []) if isinstance(prefs.get("no_meeting_windows"), list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("label", "") or "").strip().lower() == normalized_label.lower():
            updated_windows.append(
                {
                    "label": normalized_label,
                    "days": normalized_days,
                    "start_hour": int(start_hour),
                    "start_minute": int(start_minute),
                    "end_hour": int(end_hour),
                    "end_minute": int(end_minute),
                }
            )
            replaced = True
        else:
            updated_windows.append(item)
    if not replaced:
        updated_windows.append(
            {
                "label": normalized_label,
                "days": normalized_days,
                "start_hour": int(start_hour),
                "start_minute": int(start_minute),
                "end_hour": int(end_hour),
                "end_minute": int(end_minute),
            }
        )
    prefs["no_meeting_windows"] = updated_windows
    return _normalize_scheduler_preferences(prefs)


def try_apply_scheduler_preference_edits(
    raw_query: str,
    preferences: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    template_result = parse_scheduler_preferences_template(raw_query, preferences)
    if template_result is not None:
        return {
            "preferences": template_result,
            "changes": ["Applied the scheduler template updates."],
        }

    lowered = str(raw_query or "").lower()
    if not any(token in lowered for token in ("preference", "preferences", "prefrence", "prefrences", "settings", "default", "defaults", "gym", "no meetings", "no meeting", "avoid meetings", "protected time", "work hours", "work start", "work end", "lunch", "focus", "reminder")):
        return None
    prefs = _normalize_scheduler_preferences(preferences)
    changes: List[str] = []

    work_hours_match = _WORK_HOURS_RE.search(raw_query)
    if work_hours_match:
        start_clock = _parse_clock_text(work_hours_match.group("start"))
        end_clock = _parse_clock_text(work_hours_match.group("end"))
        if start_clock and end_clock and end_clock > start_clock:
            prefs["working_hours"] = {
                "start_hour": start_clock[0],
                "start_minute": start_clock[1],
                "end_hour": end_clock[0],
                "end_minute": end_clock[1],
            }
            changes.append(f"Set working hours to {_format_working_hours(prefs['working_hours'])}")
    else:
        start_match = _WORK_START_RE.search(raw_query)
        end_match = _WORK_END_RE.search(raw_query)
        if start_match:
            start_clock = _parse_clock_text(start_match.group("value"))
            if start_clock:
                prefs["working_hours"]["start_hour"] = start_clock[0]
                prefs["working_hours"]["start_minute"] = start_clock[1]
                changes.append(f"Set work start time to {_clock_to_string(*start_clock)}")
        if end_match:
            end_clock = _parse_clock_text(end_match.group("value"))
            if end_clock:
                prefs["working_hours"]["end_hour"] = end_clock[0]
                prefs["working_hours"]["end_minute"] = end_clock[1]
                changes.append(f"Set work end time to {_clock_to_string(*end_clock)}")

    focus_match = _FOCUS_BLOCK_RE.search(raw_query)
    if focus_match:
        prefs["focus_block_minutes"] = max(int(focus_match.group(1)), 15)
        changes.append(f"Set the default focus block length to {prefs['focus_block_minutes']} minutes")

    buffer_match = _MEETING_BUFFER_RE.search(raw_query)
    if buffer_match:
        prefs["meeting_buffer_minutes"] = max(int(buffer_match.group(1)), 0)
        changes.append(f"Set the meeting buffer to {prefs['meeting_buffer_minutes']} minutes")

    reminder_match = _MEETING_REMINDER_RE.search(raw_query)
    if reminder_match:
        prefs["default_meeting_reminder_minutes"] = max(int(reminder_match.group(1)), 5)
        changes.append(f"Set the default meeting reminder to {prefs['default_meeting_reminder_minutes']} minutes")

    planning_match = _PLANNING_STYLE_RE.search(raw_query)
    if planning_match:
        style = planning_match.group(1).lower().replace(" ", "_").replace("-", "_")
        prefs["daily_planning_style"] = style
        changes.append(f"Set the planning style to {_PLANNING_STYLE_LABELS[style]}")

    constraint_match = _CONSTRAINT_MODE_RE.search(raw_query)
    if constraint_match:
        mode = constraint_match.group(1).lower()
        prefs["constraint_mode"] = mode
        changes.append(f"Set constraint mode to {_CONSTRAINT_MODE_LABELS[mode]}")

    focus_time_match = _FOCUS_TIME_RANGE_RE.search(str(raw_query or ""))
    if focus_time_match:
        start_clock = _parse_clock_text(focus_time_match.group("start"))
        end_clock = _parse_clock_text(focus_time_match.group("end"))
        if start_clock and end_clock and end_clock > start_clock:
            prefs = upsert_no_meeting_window(
                prefs,
                label="Focus time",
                start_hour=start_clock[0],
                start_minute=start_clock[1],
                end_hour=end_clock[0],
                end_minute=end_clock[1],
                days=["mon", "tue", "wed", "thu", "fri"],
            )
            changes.append(
                f"Set focus time to {_format_days(['mon', 'tue', 'wed', 'thu', 'fri'])} {_clock_to_string(start_clock[0], start_clock[1])}-{_clock_to_string(end_clock[0], end_clock[1])}"
            )

    lunch_time_match = _LUNCH_TIME_RANGE_RE.search(str(raw_query or ""))
    if lunch_time_match:
        start_clock = _parse_clock_text(lunch_time_match.group("start"))
        end_clock = _parse_clock_text(lunch_time_match.group("end"))
        if start_clock and end_clock and end_clock > start_clock:
            prefs = upsert_no_meeting_window(
                prefs,
                label="Lunch window",
                start_hour=start_clock[0],
                start_minute=start_clock[1],
                end_hour=end_clock[0],
                end_minute=end_clock[1],
                days=["mon", "tue", "wed", "thu", "fri"],
            )
            changes.append(
                f"Set lunch window to {_format_days(['mon', 'tue', 'wed', 'thu', 'fri'])} {_clock_to_string(start_clock[0], start_clock[1])}-{_clock_to_string(end_clock[0], end_clock[1])}"
            )

    range_match = _TIME_RANGE_RE.search(str(raw_query or ""))
    if range_match and not (focus_time_match or lunch_time_match):
        start_clock = _parse_clock_text(range_match.group("start"))
        end_clock = _parse_clock_text(range_match.group("end"))
        if start_clock and end_clock and end_clock > start_clock:
            start_hour, start_minute = start_clock
            end_hour, end_minute = end_clock
            trailing_days = _extract_explicit_days(str(raw_query or "")[range_match.end():])
            requested_days = trailing_days or _extract_requested_days(raw_query)
            if any(token in lowered for token in ("gym", "meditation", "reminder", "remind me", "personal reminder")) and not any(token in lowered for token in ("no meetings", "no meeting", "avoid meetings", "protected")):
                prefs = upsert_recurring_reminder(
                    prefs,
                    label=_derive_window_label(raw_query),
                    hour=start_hour,
                    minute=start_minute,
                    days=requested_days,
                )
                changes.append(
                    f"Added recurring reminder {_derive_window_label(raw_query)} ({_format_days(requested_days)} {_clock_to_string(start_hour, start_minute)})"
                )
            else:
                label = _derive_window_label(raw_query)
                days = requested_days
                prefs = upsert_no_meeting_window(
                    prefs,
                    label=label,
                    start_hour=start_hour,
                    start_minute=start_minute,
                    end_hour=end_hour,
                    end_minute=end_minute,
                    days=days,
                )
                changes.append(
                    f"Avoid meetings during {label.lower()} ({_format_days(days)} {_clock_to_string(start_hour, start_minute)}-{_clock_to_string(end_hour, end_minute)})"
                )

    day_only_match = _NO_MEETINGS_DAY_ONLY_RE.search(raw_query)
    if day_only_match:
        requested_days = _extract_requested_days(day_only_match.group("days"))
        if requested_days:
            prefs = upsert_no_meeting_window(
                prefs,
                label="No meetings",
                start_hour=0,
                start_minute=0,
                end_hour=23,
                end_minute=59,
                days=requested_days,
            )
            changes.append(f"Avoid meetings all day on {_format_days(requested_days)}")
    elif _NO_MEETINGS_ALLOWED_RE.search(raw_query) and not _NO_MEETINGS_WITH_TIME_RE.search(raw_query):
        requested_days = _extract_requested_days(raw_query)
        if requested_days:
            prefs = upsert_no_meeting_window(
                prefs,
                label="No meetings",
                start_hour=0,
                start_minute=0,
                end_hour=23,
                end_minute=59,
                days=requested_days,
            )
            changes.append(f"Avoid meetings all day on {_format_days(requested_days)}")

    if not changes:
        return None
    return {
        "preferences": _normalize_scheduler_preferences(prefs),
        "changes": changes,
    }


def _preset_to_no_meeting_windows(preset: str) -> List[Dict[str, Any]]:
    normalized = str(preset or "none").strip().lower()
    if normalized == "lunch_weekdays":
        return [{"label": "Lunch window", "days": ["mon", "tue", "wed", "thu", "fri"], "start_hour": 13, "start_minute": 0, "end_hour": 14, "end_minute": 0}]
    if normalized == "focus_mornings":
        return [{"label": "Focus mornings", "days": ["mon", "tue", "wed", "thu", "fri"], "start_hour": 9, "start_minute": 0, "end_hour": 12, "end_minute": 0}]
    return []


def derive_no_meeting_window_preset(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_scheduler_preferences(preferences)
    windows = prefs.get("no_meeting_windows", []) if isinstance(prefs.get("no_meeting_windows"), list) else []
    if not windows:
        return "none"
    first = windows[0] if isinstance(windows[0], dict) else {}
    label = str(first.get("label", "") or "").strip().lower()
    if label == "lunch window" and first.get("start_hour") == 13 and first.get("start_minute", 0) == 0 and first.get("end_hour") == 14 and first.get("end_minute", 0) == 0:
        return "lunch_weekdays"
    if label == "focus mornings" and first.get("start_hour") == 9 and first.get("start_minute", 0) == 0 and first.get("end_hour") == 12 and first.get("end_minute", 0) == 0:
        return "focus_mornings"
    return "custom"


def _normalize_scheduler_preferences(raw_preferences: Dict[str, Any] | None) -> Dict[str, Any]:
    preferences = default_scheduler_preferences()
    if isinstance(raw_preferences, dict):
        preferences.update(raw_preferences)

    working_hours = copy.deepcopy(DEFAULT_SCHEDULER_PREFERENCES["working_hours"])
    raw_working_hours = preferences.get("working_hours", {})
    if isinstance(raw_working_hours, dict):
        working_hours.update(raw_working_hours)
    try:
        working_hours["start_hour"] = max(min(_int_or_default(working_hours.get("start_hour", 9), 9), 23), 0)
    except Exception:
        working_hours["start_hour"] = int(DEFAULT_SCHEDULER_PREFERENCES["working_hours"]["start_hour"])
    try:
        working_hours["start_minute"] = max(min(int(working_hours.get("start_minute", 0) or 0), 59), 0)
    except Exception:
        working_hours["start_minute"] = int(DEFAULT_SCHEDULER_PREFERENCES["working_hours"]["start_minute"])
    try:
        working_hours["end_hour"] = max(min(_int_or_default(working_hours.get("end_hour", 18), 18), 23), 0)
    except Exception:
        working_hours["end_hour"] = int(DEFAULT_SCHEDULER_PREFERENCES["working_hours"]["end_hour"])
    try:
        working_hours["end_minute"] = max(min(int(working_hours.get("end_minute", 0) or 0), 59), 0)
    except Exception:
        working_hours["end_minute"] = int(DEFAULT_SCHEDULER_PREFERENCES["working_hours"]["end_minute"])
    if (working_hours["end_hour"], working_hours["end_minute"]) <= (working_hours["start_hour"], working_hours["start_minute"]):
        working_hours = copy.deepcopy(DEFAULT_SCHEDULER_PREFERENCES["working_hours"])
    preferences["working_hours"] = working_hours

    try:
        preferences["focus_block_minutes"] = max(int(preferences.get("focus_block_minutes", 90) or 90), 15)
    except Exception:
        preferences["focus_block_minutes"] = int(DEFAULT_SCHEDULER_PREFERENCES["focus_block_minutes"])
    try:
        preferences["meeting_buffer_minutes"] = max(int(preferences.get("meeting_buffer_minutes", 10) or 10), 0)
    except Exception:
        preferences["meeting_buffer_minutes"] = int(DEFAULT_SCHEDULER_PREFERENCES["meeting_buffer_minutes"])
    try:
        preferences["default_meeting_reminder_minutes"] = max(int(preferences.get("default_meeting_reminder_minutes", 15) or 15), 5)
    except Exception:
        preferences["default_meeting_reminder_minutes"] = int(DEFAULT_SCHEDULER_PREFERENCES["default_meeting_reminder_minutes"])

    if preferences.get("daily_planning_style") not in _PLANNING_STYLE_LABELS:
        preferences["daily_planning_style"] = DEFAULT_SCHEDULER_PREFERENCES["daily_planning_style"]
    if preferences.get("constraint_mode") not in _CONSTRAINT_MODE_LABELS:
        preferences["constraint_mode"] = DEFAULT_SCHEDULER_PREFERENCES["constraint_mode"]

    normalized_windows: List[Dict[str, Any]] = []
    raw_windows = preferences.get("no_meeting_windows", [])
    if isinstance(raw_windows, list):
        for item in raw_windows:
            if not isinstance(item, dict):
                continue
            try:
                start_hour = max(min(_int_or_default(item.get("start_hour", 9), 9), 23), 0)
                start_minute = max(min(_int_or_default(item.get("start_minute", 0), 0), 59), 0)
                end_hour = max(min(_int_or_default(item.get("end_hour", 17), 17), 24), 1)
                end_minute = max(min(_int_or_default(item.get("end_minute", 0), 0), 59), 0)
            except Exception:
                continue
            if (end_hour, end_minute) <= (start_hour, start_minute):
                continue
            days = _normalize_days_for_window(item.get("days", []) if isinstance(item.get("days"), list) else [])
            normalized_windows.append(
                {
                    "label": str(item.get("label", "Protected time") or "Protected time").strip(),
                    "days": days,
                    "start_hour": start_hour,
                    "start_minute": start_minute,
                    "end_hour": end_hour,
                    "end_minute": end_minute,
                }
            )
    preferences["no_meeting_windows"] = normalized_windows
    normalized_reminders: List[Dict[str, Any]] = []
    raw_reminders = preferences.get("recurring_reminders", [])
    if isinstance(raw_reminders, list):
        for item in raw_reminders:
            if not isinstance(item, dict):
                continue
            try:
                hour = max(min(_int_or_default(item.get("hour", 8), 8), 23), 0)
                minute = max(min(_int_or_default(item.get("minute", 0), 0), 59), 0)
            except Exception:
                continue
            normalized_reminders.append(
                {
                    "label": str(item.get("label", "Reminder") or "Reminder").strip(),
                    "days": _normalize_days_for_window(item.get("days", []) if isinstance(item.get("days"), list) else []),
                    "hour": hour,
                    "minute": minute,
                }
            )
    preferences["recurring_reminders"] = normalized_reminders
    preferences["version"] = int(preferences.get("version", DEFAULT_SCHEDULER_PREFERENCES["version"]) or DEFAULT_SCHEDULER_PREFERENCES["version"])
    updated_at = str(preferences.get("updated_at", "") or "").strip()
    preferences["updated_at"] = updated_at
    return preferences


def scheduler_preferences_exist() -> bool:
    return get_scheduler_preferences_path().exists()


def load_scheduler_preferences() -> Dict[str, Any]:
    path = get_scheduler_preferences_path()
    if not path.exists():
        return default_scheduler_preferences()
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return default_scheduler_preferences()
    match = _JSON_BLOCK_RE.search(content)
    if not match:
        return default_scheduler_preferences()
    try:
        payload = json.loads(match.group(1))
    except Exception:
        return default_scheduler_preferences()
    return _normalize_scheduler_preferences(payload)


def render_scheduler_preferences_summary(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_scheduler_preferences(preferences)
    windows = prefs.get("no_meeting_windows", []) if isinstance(prefs.get("no_meeting_windows"), list) else []
    reminders = prefs.get("recurring_reminders", []) if isinstance(prefs.get("recurring_reminders"), list) else []
    if windows:
        window_summary = ", ".join(format_no_meeting_window(item) for item in windows[:2] if isinstance(item, dict))
        if len(windows) > 2:
            window_summary += f", and {len(windows) - 2} more"
    else:
        window_summary = "None"
    if reminders:
        reminder_summary = ", ".join(format_recurring_reminder(item) for item in reminders[:2] if isinstance(item, dict))
        if len(reminders) > 2:
            reminder_summary += f", and {len(reminders) - 2} more"
    else:
        reminder_summary = "None"
    lines = [
        "Saved scheduler preferences:",
        f"- Working hours: {_format_working_hours(prefs['working_hours'])}",
        f"- Focus block length: {int(prefs['focus_block_minutes'])} minutes",
        f"- Meeting buffer: {int(prefs['meeting_buffer_minutes'])} minutes",
        f"- Meeting reminder: {int(prefs['default_meeting_reminder_minutes'])} minutes before",
        f"- Planning style: {_PLANNING_STYLE_LABELS[prefs['daily_planning_style']]}",
        f"- Constraint mode: {_CONSTRAINT_MODE_LABELS[prefs['constraint_mode']]}",
        f"- No-meeting windows: {window_summary}",
        f"- Recurring reminders: {reminder_summary}",
    ]
    return "\n".join(lines)


def render_scheduler_preferences_markdown(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_scheduler_preferences(preferences)
    return "\n".join([
        "# Scheduler Preferences",
        "",
        "This file stores durable planning defaults for the Scheduler skill.",
        "",
        "## Structured Preferences",
        "```json",
        json.dumps(prefs, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Human Summary",
        render_scheduler_preferences_summary(prefs),
        "",
        "## What The Assistant Will Do",
        "- Use your saved working hours as the default frame for schedule analysis and slot recommendations.",
        "- Use these defaults when planning focus time and schedule suggestions.",
        "- Use the meeting reminder default when creating calendar events without an explicit reminder override.",
        "- Prefer these settings only when you do not give more specific instructions in the current request.",
        "- Treat these preferences as planning defaults, not destructive automation rules.",
        "",
        "## Editing Notes",
        "- Say 'show my scheduler preferences' to review them.",
        "- Say 'edit my scheduler preferences' to update them through a guided flow.",
        "- Say 'review my scheduler' to get a short recommendation digest.",
        "- Say 'apply my scheduler preferences' to confirm that these defaults should guide future scheduling requests.",
    ])


def save_scheduler_preferences(preferences: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_scheduler_preferences(preferences)
    normalized["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = get_scheduler_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_scheduler_preferences_markdown(normalized), encoding="utf-8")
    try:
        from src.calendar.calendar_preferences import load_calendar_preferences, save_calendar_preferences  # noqa: PLC0415

        calendar_preferences = load_calendar_preferences()
        calendar_preferences["working_hours"] = copy.deepcopy(normalized["working_hours"])
        calendar_preferences["default_reminder_minutes"] = int(normalized["default_meeting_reminder_minutes"])
        save_calendar_preferences(calendar_preferences)
    except Exception:
        pass
    return {
        "status": "success",
        "file_path": str(path),
        "preferences": normalized,
        "message": f"Saved scheduler preferences to {path}",
    }


def get_scheduler_review_recommendations(preferences: Dict[str, Any] | None = None) -> List[str]:
    prefs = _normalize_scheduler_preferences(preferences)
    recommendations: List[str] = []
    if int(prefs["working_hours"].get("end_hour", 18) or 18) - int(prefs["working_hours"].get("start_hour", 9) or 9) > 10:
        recommendations.append("Your workday window is broad. Narrowing it can make scheduling suggestions more useful.")
    if int(prefs.get("focus_block_minutes", 90) or 90) < 60:
        recommendations.append("Your focus block default is short. Consider 90 minutes if you want deeper uninterrupted work.")
    if int(prefs.get("meeting_buffer_minutes", 10) or 10) < 10:
        recommendations.append("Your meeting buffer is tight. A 10-15 minute buffer is usually safer for context switching.")
    if int(prefs.get("default_meeting_reminder_minutes", 15) or 15) < 10:
        recommendations.append("A reminder under 10 minutes is easy to miss. Consider a slightly earlier meeting reminder default.")
    if not prefs.get("no_meeting_windows"):
        recommendations.append("You have no protected no-meeting windows yet. Adding one helps the Scheduler defend deep-work time.")
    if str(prefs.get("constraint_mode", "soft") or "soft") == "soft":
        recommendations.append("Soft constraints allow more flexibility. Switch to hard constraints only if the Scheduler should protect your rules more aggressively.")
    return recommendations


def render_scheduler_preference_guidance(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_scheduler_preferences(preferences)
    lines = [
        "Scheduler preferences currently active:",
        f"- Preferred work hours: {_format_working_hours(prefs['working_hours'])}",
        f"- Default focus block length: {int(prefs['focus_block_minutes'])} minutes",
        f"- Default meeting buffer: {int(prefs['meeting_buffer_minutes'])} minutes",
        f"- Default meeting reminder: {int(prefs['default_meeting_reminder_minutes'])} minutes before",
        f"- Planning style: {_PLANNING_STYLE_LABELS[prefs['daily_planning_style']]}",
        f"- Constraint mode: {_CONSTRAINT_MODE_LABELS[prefs['constraint_mode']]}",
        "- Protected no-meeting windows should be avoided by default unless the user explicitly overrides them in the current request",
    ]
    windows = prefs.get("no_meeting_windows", []) if isinstance(prefs.get("no_meeting_windows"), list) else []
    if windows:
        for item in windows[:2]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- Avoid meetings during {format_no_meeting_window(item)} when possible")
    reminders = prefs.get("recurring_reminders", []) if isinstance(prefs.get("recurring_reminders"), list) else []
    for item in reminders[:2]:
        if not isinstance(item, dict):
            continue
        lines.append(f"- Remember recurring personal commitment: {format_recurring_reminder(item)}")
    return "\n".join(lines)