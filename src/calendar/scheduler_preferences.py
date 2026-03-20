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
    "version": 1,
    "updated_at": "",
    "focus_block_minutes": 90,
    "meeting_buffer_minutes": 10,
    "daily_planning_style": "balanced",
    "constraint_mode": "soft",
    "no_meeting_windows": [],
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
_TIME_RANGE_RE = re.compile(
    r"\b(?:between|from)\s*(?P<start>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)\s*(?:and|to|-)\s*(?P<end>\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)",
    re.IGNORECASE,
)
_WEEKDAYS_RE = re.compile(r"\bweek\s*days?\b|\bweekdays\b", re.IGNORECASE)
_WEEKENDS_RE = re.compile(r"\bweek\s*ends?\b|\bweekends\b", re.IGNORECASE)
_EVERY_DAY_RE = re.compile(r"\b(every\s+day|daily|each\s+day)\b", re.IGNORECASE)


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


def _extract_requested_days(raw_query: str) -> List[str]:
    text = str(raw_query or "")
    if _WEEKDAYS_RE.search(text):
        return list(_ALL_DAYS[:5])
    if _WEEKENDS_RE.search(text):
        return list(_ALL_DAYS[5:])
    if _EVERY_DAY_RE.search(text):
        return list(_ALL_DAYS)
    return list(_ALL_DAYS)


def _derive_window_label(raw_query: str) -> str:
    lowered = str(raw_query or "").lower()
    if "gym" in lowered:
        return "Gym time"
    if "lunch" in lowered:
        return "Lunch window"
    if "focus" in lowered or "deep work" in lowered:
        return "Focus block"
    return "Protected time"


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
    lowered = str(raw_query or "").lower()
    if not any(token in lowered for token in ("preference", "preferences", "prefrence", "prefrences", "settings", "default", "defaults", "gym", "no meetings", "no meeting", "avoid meetings", "protected time")):
        return None
    range_match = _TIME_RANGE_RE.search(str(raw_query or ""))
    if not range_match:
        return None
    start_clock = _parse_clock_text(range_match.group("start"))
    end_clock = _parse_clock_text(range_match.group("end"))
    if not start_clock or not end_clock:
        return None
    start_hour, start_minute = start_clock
    end_hour, end_minute = end_clock
    if (end_hour, end_minute) <= (start_hour, start_minute):
        return None
    label = _derive_window_label(raw_query)
    days = _extract_requested_days(raw_query)
    updated_preferences = upsert_no_meeting_window(
        preferences,
        label=label,
        start_hour=start_hour,
        start_minute=start_minute,
        end_hour=end_hour,
        end_minute=end_minute,
        days=days,
    )
    return {
        "preferences": updated_preferences,
        "changes": [
            f"Avoid meetings during {label.lower()} ({_format_days(days)} {_clock_to_string(start_hour, start_minute)}-{_clock_to_string(end_hour, end_minute)})"
        ],
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

    try:
        preferences["focus_block_minutes"] = max(int(preferences.get("focus_block_minutes", 90) or 90), 15)
    except Exception:
        preferences["focus_block_minutes"] = int(DEFAULT_SCHEDULER_PREFERENCES["focus_block_minutes"])
    try:
        preferences["meeting_buffer_minutes"] = max(int(preferences.get("meeting_buffer_minutes", 10) or 10), 0)
    except Exception:
        preferences["meeting_buffer_minutes"] = int(DEFAULT_SCHEDULER_PREFERENCES["meeting_buffer_minutes"])

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
                start_hour = max(min(int(item.get("start_hour", 9) or 9), 23), 0)
                start_minute = max(min(int(item.get("start_minute", 0) or 0), 59), 0)
                end_hour = max(min(int(item.get("end_hour", 17) or 17), 24), 1)
                end_minute = max(min(int(item.get("end_minute", 0) or 0), 59), 0)
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
    if windows:
        window_summary = ", ".join(format_no_meeting_window(item) for item in windows[:2] if isinstance(item, dict))
        if len(windows) > 2:
            window_summary += f", and {len(windows) - 2} more"
    else:
        window_summary = "None"
    lines = [
        "Saved scheduler preferences:",
        f"- Focus block length: {int(prefs['focus_block_minutes'])} minutes",
        f"- Meeting buffer: {int(prefs['meeting_buffer_minutes'])} minutes",
        f"- Planning style: {_PLANNING_STYLE_LABELS[prefs['daily_planning_style']]}",
        f"- Constraint mode: {_CONSTRAINT_MODE_LABELS[prefs['constraint_mode']]}",
        f"- No-meeting windows: {window_summary}",
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
        "- Use these defaults when planning focus time and schedule suggestions.",
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
    return {
        "status": "success",
        "file_path": str(path),
        "preferences": normalized,
        "message": f"Saved scheduler preferences to {path}",
    }


def get_scheduler_review_recommendations(preferences: Dict[str, Any] | None = None) -> List[str]:
    prefs = _normalize_scheduler_preferences(preferences)
    recommendations: List[str] = []
    if int(prefs.get("focus_block_minutes", 90) or 90) < 60:
        recommendations.append("Your focus block default is short. Consider 90 minutes if you want deeper uninterrupted work.")
    if int(prefs.get("meeting_buffer_minutes", 10) or 10) < 10:
        recommendations.append("Your meeting buffer is tight. A 10-15 minute buffer is usually safer for context switching.")
    if not prefs.get("no_meeting_windows"):
        recommendations.append("You have no protected no-meeting windows yet. Adding one helps the Scheduler defend deep-work time.")
    if str(prefs.get("constraint_mode", "soft") or "soft") == "soft":
        recommendations.append("Soft constraints allow more flexibility. Switch to hard constraints only if the Scheduler should protect your rules more aggressively.")
    return recommendations


def render_scheduler_preference_guidance(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_scheduler_preferences(preferences)
    lines = [
        "Scheduler preferences currently active:",
        f"- Default focus block length: {int(prefs['focus_block_minutes'])} minutes",
        f"- Default meeting buffer: {int(prefs['meeting_buffer_minutes'])} minutes",
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
    return "\n".join(lines)