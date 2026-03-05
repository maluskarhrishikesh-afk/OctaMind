"""
Scheduler / Smart Calendar skill orchestrator.

Uses the Google Calendar service to handle scheduling-specific tasks:
finding free slots, booking time blocks, suggesting meeting times, etc.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
get_todays_events() – Return today's events to understand current schedule.
get_tomorrows_events() – Return tomorrow's events.
get_upcoming_events(days=7, max_results=30) – Return events for the next N days to find free slots.
get_events_for_date(date_str) – Check events on a specific date (YYYY-MM-DD).
search_events(query, days=30, max_results=10) – Search for specific events.
create_event(title, start, end, description="", location="", attendees=None, calendar_id="primary") – Book a time slot / create a meeting (ISO 8601 datetimes).
quick_add_event(text) – Create an event from natural language (e.g. "Focus block Friday 2-4pm").
update_event(event_id, **kwargs) – Reschedule or modify an existing booking.
delete_event(event_id) – Cancel / remove a scheduled block.
list_calendars() – List all calendars to select the right one.
save_context(topic, resolved_entities, awaiting="") – Persist resolved context (date, events, free slots) for the next turn. Call IMMEDIATELY after fetching events so the user can reply "2 PM" without re-specifying the date. topic="calendar_query", resolved_entities={"resolved_date":"<ISO>", "date_label":"<tomorrow/today/etc>", "events":[...]}, awaiting="time_selection".
""".strip()

_SKILL_CONTEXT_TEMPLATE = """
You are the Scheduler / Smart Calendar Skill Agent.
Your speciality is time management: finding open slots, planning focus blocks, booking meetings and
suggesting optimal scheduling strategies based on the user's existing calendar.

TODAY'S DATE: {today}  (use this EXACT year {year} when the user mentions a date like "5th March" or "March 5")
IMPORTANT: NEVER use a year earlier than {year} when calling get_events_for_date or create_event.

Workflow:
1. First fetch the relevant events to understand what's already booked.
2. Analyse gaps to suggest or pick free time.
3. Create / update / delete events as needed.

Use human-friendly language when explaining free slots (e.g. "Wednesday 10-11 am looks free").
Always confirm the final booking summary with the user in your final_answer.

CONTEXT MANIFEST (cross-turn awareness):
After EVERY call to get_todays_events, get_tomorrows_events, get_upcoming_events, or get_events_for_date,
context is AUTOMATICALLY saved to the manifest — no extra step needed.
This ensures that when the user replies with just "2 PM" on the next turn, the system knows exactly which date to book.
If you need to save context for edge cases not covered by the auto-wrap, use the save_context tool via call_tool.
""".strip()


def _build_skill_context() -> str:
    today = date.today()
    return _SKILL_CONTEXT_TEMPLATE.format(today=today.isoformat(), year=today.year)


def _get_tools() -> Dict[str, Any]:
    from src.calendar import calendar_service as cs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_calendar_context, make_save_context_tool,
    )
    from datetime import date as _date, timedelta as _td

    def get_todays_events() -> dict:
        result = cs.get_todays_events()
        return auto_save_calendar_context(result, _date.today().isoformat(), "today")

    def get_tomorrows_events() -> dict:
        result = cs.get_tomorrows_events()
        tomorrow = (_date.today() + _td(days=1)).isoformat()
        return auto_save_calendar_context(result, tomorrow, "tomorrow")

    def get_upcoming_events(days: int = 7, max_results: int = 30) -> dict:
        result = cs.get_upcoming_events(days, max_results)
        return auto_save_calendar_context(result, _date.today().isoformat(), f"next {days} days")

    def get_events_for_date(date_str: str) -> dict:
        result = cs.get_events_for_date(date_str)
        return auto_save_calendar_context(result, date_str)

    return {
        "get_todays_events":    get_todays_events,
        "get_tomorrows_events": get_tomorrows_events,
        "get_upcoming_events":  get_upcoming_events,
        "get_events_for_date":  get_events_for_date,
        "search_events":  lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "create_event":   lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": cs.create_event(title, start, end, description, location, attendees, calendar_id),
        "quick_add_event": lambda text: cs.quick_add_event(text),
        "update_event":    lambda event_id, **kwargs: cs.update_event(event_id, **kwargs),
        "delete_event":    lambda event_id: cs.delete_event(event_id),
        "list_calendars":  lambda: cs.list_calendars(),
        "save_context":    make_save_context_tool("scheduler"),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="scheduler",
            skill_context=_build_skill_context(),
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Scheduler skill error: {exc}",
            "action": "react_response",
        }
