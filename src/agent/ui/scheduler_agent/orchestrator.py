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
""".strip()


def _build_skill_context() -> str:
    today = date.today()
    return _SKILL_CONTEXT_TEMPLATE.format(today=today.isoformat(), year=today.year)


def _get_tools() -> Dict[str, Any]:
    from src.calendar import calendar_service as cs  # noqa: PLC0415

    return {
        "get_todays_events": lambda: cs.get_todays_events(),
        "get_tomorrows_events": lambda: cs.get_tomorrows_events(),
        "get_upcoming_events": lambda days=7, max_results=30: cs.get_upcoming_events(days, max_results),
        "get_events_for_date": lambda date_str: cs.get_events_for_date(date_str),
        "search_events": lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "create_event": lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": cs.create_event(title, start, end, description, location, attendees, calendar_id),
        "quick_add_event": lambda text: cs.quick_add_event(text),
        "update_event": lambda event_id, **kwargs: cs.update_event(event_id, **kwargs),
        "delete_event": lambda event_id: cs.delete_event(event_id),
        "list_calendars": lambda: cs.list_calendars(),
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
