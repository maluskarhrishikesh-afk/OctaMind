"""
Google Calendar skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
get_todays_events() – List all events scheduled for today.
get_tomorrows_events() – List all events scheduled for tomorrow.
get_upcoming_events(days=7, max_results=20) – List upcoming events for the next N days.
get_events_for_date(date_str) – List events on a specific date (e.g. "2024-12-25").
search_events(query, days=30, max_results=10) – Search calendar events by keyword.
list_events(start=None, end=None, max_results=20, calendar_id="primary") – List events within a date range (ISO8601 strings).
get_event(event_id) – Get details of a specific event.
create_event(title, start, end, description="", location="", attendees=None, calendar_id="primary") – Create a new event (start/end in ISO8601).
quick_add_event(text) – Create an event from natural language (e.g. "Lunch tomorrow at 1pm").
update_event(event_id, **kwargs) – Update fields of an existing event.
delete_event(event_id) – Delete an event.
create_recurring_event(title, start, end, recurrence, description="", location="", attendees=None) – Create a recurring event.
list_calendars() – List all available calendars.
""".strip()

_SKILL_CONTEXT = """
You are the Google Calendar Skill Agent.
Help the user view, create, update and delete calendar events.
When creating events, confirm the date/time and timezone with the user if ambiguous.
Prefer quick_add_event for natural language inputs like "Meeting tomorrow at 3pm".
Use ISO 8601 format (e.g. "2024-12-25T14:00:00") when calling create_event or update_event directly.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.calendar import calendar_service as cs  # noqa: PLC0415

    return {
        "get_todays_events": lambda: cs.get_todays_events(),
        "get_tomorrows_events": lambda: cs.get_tomorrows_events(),
        "get_upcoming_events": lambda days=7, max_results=20: cs.get_upcoming_events(days, max_results),
        "get_events_for_date": lambda date_str: cs.get_events_for_date(date_str),
        "search_events": lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "list_events": lambda start=None, end=None, max_results=20, calendar_id="primary": cs.list_events(start, end, max_results, calendar_id),
        "get_event": lambda event_id: cs.get_event(event_id),
        "create_event": lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": cs.create_event(title, start, end, description, location, attendees, calendar_id),
        "quick_add_event": lambda text: cs.quick_add_event(text),
        "update_event": lambda event_id, **kwargs: cs.update_event(event_id, **kwargs),
        "delete_event": lambda event_id: cs.delete_event(event_id),
        "create_recurring_event": lambda title, start, end, recurrence, description="", location="", attendees=None: cs.create_recurring_event(title, start, end, recurrence, description, location, attendees),
        "list_calendars": lambda: cs.list_calendars(),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="calendar",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Calendar skill error: {exc}",
            "action": "react_response",
        }
