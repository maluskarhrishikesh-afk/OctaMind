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

def _get_skill_context() -> str:
    """Build the calendar skill context with the real current date+timezone."""
    import datetime
    try:
        local = datetime.datetime.now().astimezone()
        today_str = local.strftime("%A, %d %B %Y")   # e.g. "Sunday, 01 March 2026"
        tz_name   = local.strftime("%Z")              # e.g. "IST"
        offset    = local.strftime("%z")              # e.g. "+0530"
        tz_display = f"{tz_name} (UTC{offset[:3]}:{offset[3:]})"
        iso_offset = f"{offset[:3]}:{offset[3:]}"
    except Exception:
        import datetime as _dt
        today_str  = _dt.date.today().strftime("%d %B %Y")
        tz_display = "UTC"
        iso_offset = "+00:00"
    return f"""You are the Google Calendar Skill Agent.
Today's date: {today_str}. ALWAYS use this exact date as the reference for EVERY relative expression ("today", "tomorrow", "this evening", "next Monday", "in 2 hours", etc.). NEVER use any other date.
User's local timezone: {tz_display}. Always apply this timezone — never ask the user to specify it.

CRITICAL RULE — choosing the right tool:
  • For ANY natural-language time expression (e.g. "today at 8 PM", "tomorrow 3pm", "next Friday") -> ALWAYS call quick_add_event(text). It resolves relative times correctly.
  • Only call create_event() when you have an exact, pre-computed ISO8601 datetime (e.g. "{local.year}-{local.month:02d}-{local.day:02d}T20:00:00{iso_offset}").
  • NEVER invent or guess a date for create_event() — derive it strictly from today ({today_str}).

When displaying event times, always show them in the user's local timezone.""".strip()

# Kept for backward compatibility (static fallback)
_SKILL_CONTEXT = _get_skill_context()


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
            skill_context=_get_skill_context(),
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
