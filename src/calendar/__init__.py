"""
Calendar Module — Google Calendar integration for Octa Bot.

Provides Google Calendar read/write operations via the Calendar API v3.
All functions return plain dicts with at least ``status`` and ``message``.

Quick start:
    from src.calendar import get_todays_events, create_event, find_free_slots
"""
from .calendar_auth import is_calendar_authorized
from .calendar_service import (
    list_events,
    get_todays_events,
    get_tomorrows_events,
    get_upcoming_events,
    get_events_for_date,
    search_events,
    get_event,
    create_event,
    quick_add_event,
    update_event,
    delete_event,
    create_recurring_event,
    list_calendars,
    find_free_slots,
    find_conflicts,
    get_daily_agenda,
    get_weekly_agenda,
    set_reminder,
    accept_invite,
    decline_invite,
)

__all__ = [
    "list_events",
    "get_todays_events",
    "get_tomorrows_events",
    "get_upcoming_events",
    "get_events_for_date",
    "search_events",
    "get_event",
    "create_event",
    "quick_add_event",
    "update_event",
    "delete_event",
    "create_recurring_event",
    "list_calendars",
    "find_free_slots",
    "find_conflicts",
    "get_daily_agenda",
    "get_weekly_agenda",
    "set_reminder",
    "accept_invite",
    "decline_invite",
    "is_calendar_authorized",
]
