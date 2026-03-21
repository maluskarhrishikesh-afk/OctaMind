from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.agent.runtime_paths import get_your_data_dir


_CALENDAR_PREFERENCES_PATH = get_your_data_dir("calendar_preferences.md")
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

DEFAULT_CALENDAR_PREFERENCES: Dict[str, Any] = {
    "version": 2,
    "updated_at": "",
    "working_hours": {
        "start_hour": 9,
        "start_minute": 0,
        "end_hour": 18,
        "end_minute": 0,
    },
    "default_meeting_minutes": 45,
    "default_reminder_minutes": 15,
}


def _clock_to_string(hour: int, minute: int) -> str:
    return f"{int(hour) % 24:02d}:{max(0, min(int(minute), 59)):02d}"


def get_calendar_preferences_path() -> Path:
    return _CALENDAR_PREFERENCES_PATH


def default_calendar_preferences() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_CALENDAR_PREFERENCES)


def _normalize_calendar_preferences(raw_preferences: Dict[str, Any] | None) -> Dict[str, Any]:
    preferences = default_calendar_preferences()
    if isinstance(raw_preferences, dict):
        preferences.update(raw_preferences)

    working_hours = copy.deepcopy(DEFAULT_CALENDAR_PREFERENCES["working_hours"])
    raw_working_hours = preferences.get("working_hours", {})
    if isinstance(raw_working_hours, dict):
        working_hours.update(raw_working_hours)
    try:
        working_hours["start_hour"] = max(min(int(working_hours.get("start_hour", 9) or 9), 23), 0)
    except Exception:
        working_hours["start_hour"] = int(DEFAULT_CALENDAR_PREFERENCES["working_hours"]["start_hour"])
    try:
        working_hours["start_minute"] = max(min(int(working_hours.get("start_minute", 0) or 0), 59), 0)
    except Exception:
        working_hours["start_minute"] = int(DEFAULT_CALENDAR_PREFERENCES["working_hours"]["start_minute"])
    try:
        working_hours["end_hour"] = max(min(int(working_hours.get("end_hour", 18) or 18), 24), 1)
    except Exception:
        working_hours["end_hour"] = int(DEFAULT_CALENDAR_PREFERENCES["working_hours"]["end_hour"])
    try:
        working_hours["end_minute"] = max(min(int(working_hours.get("end_minute", 0) or 0), 59), 0)
    except Exception:
        working_hours["end_minute"] = int(DEFAULT_CALENDAR_PREFERENCES["working_hours"]["end_minute"])
    if (working_hours["end_hour"], working_hours["end_minute"]) <= (working_hours["start_hour"], working_hours["start_minute"]):
        working_hours = copy.deepcopy(DEFAULT_CALENDAR_PREFERENCES["working_hours"])
    preferences["working_hours"] = working_hours

    try:
        preferences["default_meeting_minutes"] = max(int(preferences.get("default_meeting_minutes", 45) or 45), 15)
    except Exception:
        preferences["default_meeting_minutes"] = int(DEFAULT_CALENDAR_PREFERENCES["default_meeting_minutes"])
    try:
        preferences["default_reminder_minutes"] = max(int(preferences.get("default_reminder_minutes", 30) or 30), 5)
    except Exception:
        preferences["default_reminder_minutes"] = int(DEFAULT_CALENDAR_PREFERENCES["default_reminder_minutes"])
    preferences["version"] = int(preferences.get("version", DEFAULT_CALENDAR_PREFERENCES["version"]) or DEFAULT_CALENDAR_PREFERENCES["version"])
    preferences["updated_at"] = str(preferences.get("updated_at", "") or "").strip()
    return preferences


def calendar_preferences_exist() -> bool:
    return get_calendar_preferences_path().exists()


def load_calendar_preferences() -> Dict[str, Any]:
    path = get_calendar_preferences_path()
    if not path.exists():
        return default_calendar_preferences()
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return default_calendar_preferences()
    match = _JSON_BLOCK_RE.search(content)
    if not match:
        return default_calendar_preferences()
    try:
        payload = json.loads(match.group(1))
    except Exception:
        return default_calendar_preferences()
    return _normalize_calendar_preferences(payload)


def render_calendar_preferences_summary(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_calendar_preferences(preferences)
    lines = [
        "Saved calendar preferences:",
        f"- Working hours: {_clock_to_string(int(prefs['working_hours']['start_hour']), int(prefs['working_hours']['start_minute']))} to {_clock_to_string(int(prefs['working_hours']['end_hour']), int(prefs['working_hours']['end_minute']))}",
        f"- Default meeting duration: {int(prefs['default_meeting_minutes'])} minutes",
        f"- Default reminder: {int(prefs['default_reminder_minutes'])} minutes before",
    ]
    return "\n".join(lines)


def render_calendar_preferences_markdown(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_calendar_preferences(preferences)
    return "\n".join([
        "# Calendar Preferences",
        "",
        "This file stores durable defaults for Calendar slot finding and event handling.",
        "",
        "## Structured Preferences",
        "```json",
        json.dumps(prefs, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Human Summary",
        render_calendar_preferences_summary(prefs),
        "",
        "## What The Assistant Will Do",
        "- Use these hours as the default window for slot-finding when you do not specify one.",
        "- Use the default duration when you ask for a meeting and do not give a duration.",
        "- Use the default reminder when you ask to add one without specifying minutes.",
        "",
        "## Editing Notes",
        "- Say 'show my calendar preferences' to review them.",
        "- Say 'edit my calendar preferences' to update them through a guided flow.",
        "- Say 'review my calendar' to get a recommendation digest.",
        "- Say 'apply my calendar preferences' to confirm that these defaults should be used going forward.",
    ])


def save_calendar_preferences(preferences: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_calendar_preferences(preferences)
    normalized["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = get_calendar_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_calendar_preferences_markdown(normalized), encoding="utf-8")
    return {
        "status": "success",
        "file_path": str(path),
        "preferences": normalized,
        "message": f"Saved calendar preferences to {path}",
    }


def get_calendar_review_recommendations(preferences: Dict[str, Any] | None = None) -> List[str]:
    prefs = _normalize_calendar_preferences(preferences)
    recommendations: List[str] = []
    if int(prefs.get("default_meeting_minutes", 45) or 45) > 60:
        recommendations.append("Your default meeting duration is long. Consider 30 or 45 minutes if you want a tighter calendar by default.")
    if int(prefs.get("default_reminder_minutes", 30) or 30) < 10:
        recommendations.append("A reminder under 10 minutes is easy to miss. Consider a slightly earlier default reminder.")
    if int(prefs["working_hours"].get("end_hour", 18) or 18) - int(prefs["working_hours"].get("start_hour", 9) or 9) > 10:
        recommendations.append("Your working-hours window is broad. Narrowing it can improve slot suggestions and protect personal time.")
    return recommendations


def render_calendar_preference_guidance(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_calendar_preferences(preferences)
    return "\n".join([
        "Calendar preferences currently active:",
        f"- Preferred working hours for slot searches: {_clock_to_string(int(prefs['working_hours']['start_hour']), int(prefs['working_hours']['start_minute']))} to {_clock_to_string(int(prefs['working_hours']['end_hour']), int(prefs['working_hours']['end_minute']))}",
        f"- Default meeting duration when omitted: {int(prefs['default_meeting_minutes'])} minutes",
        f"- Default reminder when omitted: {int(prefs['default_reminder_minutes'])} minutes before the event",
    ])