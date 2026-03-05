"""
Google Calendar Service

All calendar operations exposed as plain Python functions that the LLM
orchestrator calls.  Follows the same design as gmail_service.py:
  - Module-level singleton client (lazy init, reset on auth error)
  - Each function returns a plain dict with at least "status" and "message"
  - Auth error → {"status": "auth_error", "message": "…"}

Quick reference of functions exported:
    list_events · get_todays_events · get_tomorrows_events
    get_upcoming_events · get_events_for_date · search_events
    create_event · update_event · delete_event · get_event
    quick_add_event · create_recurring_event
    list_calendars · get_calendar
    find_free_slots · find_conflicts
    get_daily_agenda · get_weekly_agenda
    set_reminder · accept_invite · decline_invite
    export_events_ics
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date, timezone
from typing import Any

logger = logging.getLogger("calendar_agent")


def _local_tz():
    """Return the system's local timezone as a fixed-offset timezone object.

    Works on any OS without third-party libraries.  The returned object is a
    :class:`datetime.timezone` with the correct UTC offset for *right now*,
    so daylight-saving transitions within a single session are handled
    automatically on the next call.
    """
    return datetime.now().astimezone().tzinfo

# ── Singleton client ──────────────────────────────────────────────────────────
_client = None

_AUTH_ERROR_PHRASES = (
    "authorization", "credentials", "token", "oauth", "invalid_grant",
    "unauthorized", "forbidden",
)


def _get_client():
    global _client
    if _client is None:
        from src.calendar.calendar_auth import get_calendar_service, is_calendar_authorized
        if not is_calendar_authorized():
            raise PermissionError(
                "Google Calendar is not authorised. Run `python setup_google_auth.py` to set up access."
            )
        _client = get_calendar_service()
    return _client


def _reset_client() -> None:
    global _client
    _client = None


def _auth_error(exc: Exception) -> dict:
    _reset_client()
    return {
        "status": "auth_error",
        "message": (
            "🔑 Google Calendar is not authorised yet.\n\n"
            f"Error: {exc}\n\n"
            "Run `python setup_google_auth.py` to authorise Calendar access."
        ),
    }


def _is_auth_error(exc: Exception) -> bool:
    if isinstance(exc, PermissionError):
        return True
    msg = str(exc).lower()
    return any(p in msg for p in _AUTH_ERROR_PHRASES)


def _dt(s: str | None) -> datetime | None:
    """Parse ISO-8601 date/datetime string or return None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_local_tz())
    return dt.isoformat()


def _today_start() -> datetime:
    """Return midnight **local time** today as a timezone-aware datetime."""
    d = date.today()
    return datetime(d.year, d.month, d.day, tzinfo=_local_tz())


def _event_summary(ev: dict) -> dict:
    """Extract a readable summary dict from a raw Calendar API event."""
    start_raw = ev.get("start", {})
    end_raw   = ev.get("end", {})
    start_str = start_raw.get("dateTime") or start_raw.get("date", "")
    end_str   = end_raw.get("dateTime") or end_raw.get("date", "")
    attendees = [
        a.get("email", "")
        for a in ev.get("attendees", [])
        if not a.get("self")
    ]
    return {
        "id":          ev.get("id", ""),
        "title":       ev.get("summary", "(No title)"),
        "start":       start_str,
        "end":         end_str,
        "location":    ev.get("location", ""),
        "description": ev.get("description", "")[:300] if ev.get("description") else "",
        "attendees":   attendees,
        "status":      ev.get("status", "confirmed"),
        "html_link":   ev.get("htmlLink", ""),
        "recurring":   bool(ev.get("recurringEventId")),
    }


# ── List / Fetch ──────────────────────────────────────────────────────────────

def list_events(
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 20,
    calendar_id: str = "primary",
    query: str | None = None,
) -> dict:
    """List calendar events between time_min and time_max (ISO-8601 strings)."""
    try:
        svc = _get_client()
        params: dict[str, Any] = {
            "calendarId":  calendar_id,
            "maxResults":  min(max_results, 100),
            "singleEvents": True,
            "orderBy":     "startTime",
        }
        if time_min:
            params["timeMin"] = time_min if "T" in time_min else _rfc3339(datetime.fromisoformat(time_min + "T00:00:00").replace(tzinfo=_local_tz()))
        else:
            params["timeMin"] = _rfc3339(_today_start())
        if time_max:
            params["timeMax"] = time_max if "T" in time_max else _rfc3339(datetime.fromisoformat(time_max + "T23:59:59").replace(tzinfo=_local_tz()))
        if query:
            params["q"] = query

        result = svc.events().list(**params).execute()
        events = [_event_summary(e) for e in result.get("items", [])]
        return {
            "status": "success",
            "events": events,
            "count": len(events),
            "message": f"Found {len(events)} event(s).",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not list events: {exc}"}


def get_todays_events(calendar_id: str = "primary") -> dict:
    """Return all events scheduled for today."""
    start = _today_start()
    end   = start + timedelta(days=1)
    result = list_events(
        time_min=_rfc3339(start),
        time_max=_rfc3339(end),
        max_results=50,
        calendar_id=calendar_id,
    )
    if result["status"] == "success":
        result["message"] = (
            f"You have {result['count']} event(s) today."
            if result["count"] else "Your calendar is clear today. 🎉"
        )
    return result


def get_tomorrows_events(calendar_id: str = "primary") -> dict:
    """Return all events scheduled for tomorrow."""
    start = _today_start() + timedelta(days=1)
    end   = start + timedelta(days=1)
    result = list_events(
        time_min=_rfc3339(start),
        time_max=_rfc3339(end),
        max_results=50,
        calendar_id=calendar_id,
    )
    if result["status"] == "success":
        result["message"] = (
            f"You have {result['count']} event(s) tomorrow."
            if result["count"] else "Nothing on the calendar for tomorrow."
        )
    return result


def get_upcoming_events(days: int = 7, max_results: int = 20, calendar_id: str = "primary") -> dict:
    """Return events in the next N days (default 7)."""
    start = _today_start()
    end   = start + timedelta(days=max(1, days))
    result = list_events(
        time_min=_rfc3339(start),
        time_max=_rfc3339(end),
        max_results=max_results,
        calendar_id=calendar_id,
    )
    if result["status"] == "success":
        result["message"] = f"Found {result['count']} event(s) in the next {days} day(s)."
    return result


def get_events_for_date(date_str: str, calendar_id: str = "primary") -> dict:
    """Fetch events on a specific date (YYYY-MM-DD), using the local timezone."""
    tz = _local_tz()
    day_start = datetime.fromisoformat(f"{date_str}T00:00:00").replace(tzinfo=tz)
    day_end   = datetime.fromisoformat(f"{date_str}T23:59:59").replace(tzinfo=tz)
    result = list_events(
        time_min=_rfc3339(day_start),
        time_max=_rfc3339(day_end),
        max_results=50,
        calendar_id=calendar_id,
    )
    if result["status"] == "success":
        result["message"] = f"Found {result['count']} event(s) on {date_str}."
    return result


def search_events(query: str, days: int = 30, max_results: int = 20) -> dict:
    """Search events by keyword in the next N days."""
    start = _today_start()
    end   = start + timedelta(days=max(1, days))
    result = list_events(
        time_min=_rfc3339(start),
        time_max=_rfc3339(end),
        max_results=max_results,
        query=query,
    )
    if result["status"] == "success":
        result["message"] = f"Found {result['count']} event(s) matching '{query}'."
    return result


def get_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Fetch a single event by ID."""
    try:
        svc = _get_client()
        ev  = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return {"status": "success", "event": _event_summary(ev), "message": "Event retrieved."}
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not get event: {exc}"}


# ── Create / Update / Delete ──────────────────────────────────────────────────

def create_event(
    title: str,
    start: str,
    end: str | None = None,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
    all_day: bool = False,
) -> dict:
    """
    Create a new calendar event.

    start/end: ISO-8601 datetime strings (e.g. "2026-03-01T10:00:00")
               or date strings (e.g. "2026-03-01") when all_day=True.
    attendees: list of email addresses.
    """
    try:
        svc = _get_client()

        if all_day:
            # All-day events use date (not dateTime)
            start_d = start[:10]
            end_d   = (end or start)[:10]
            # end is exclusive in Google Calendar for all-day events
            end_exclusive = (
                (datetime.fromisoformat(end_d) + timedelta(days=1)).strftime("%Y-%m-%d")
            )
            body: dict[str, Any] = {
                "summary":     title,
                "description": description,
                "location":    location,
                "start":       {"date": start_d},
                "end":         {"date": end_exclusive},
            }
        else:
            # Timed event — attach local timezone to any naive datetime strings
            tz = _local_tz()
            def _local_dt(s: str) -> str:
                s = s if "T" in s else s + "T09:00:00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                return dt.isoformat()

            start_dt = _local_dt(start)
            if end:
                end_dt = _local_dt(end)
            else:
                end_dt = _rfc3339(datetime.fromisoformat(start_dt) + timedelta(hours=1))
            body = {
                "summary":     title,
                "description": description,
                "location":    location,
                "start":       {"dateTime": start_dt},
                "end":         {"dateTime": end_dt},
            }

        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]

        ev = svc.events().insert(calendarId=calendar_id, body=body,
                                 sendUpdates="all" if attendees else "none").execute()
        return {
            "status":  "success",
            "event":   _event_summary(ev),
            "message": f"✅ Event **{title}** created on {start[:10]}.",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not create event: {exc}"}


def quick_add_event(text: str, calendar_id: str = "primary") -> dict:
    """
    Create an event from a natural-language string using Google's quickAdd API.
    E.g. "Team standup tomorrow at 10am" or "Lunch with Alice Friday 1pm".
    """
    try:
        svc = _get_client()
        ev  = svc.events().quickAdd(calendarId=calendar_id, text=text).execute()
        return {
            "status":  "success",
            "event":   _event_summary(ev),
            "message": f"✅ Event created: **{ev.get('summary', text)}**.",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not quick-add event: {exc}"}


def update_event(
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    add_attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict:
    """Patch an existing event.  Only supplied fields are changed."""
    try:
        svc = _get_client()
        ev  = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()

        if title:
            ev["summary"] = title
        if description is not None:
            ev["description"] = description
        if location is not None:
            ev["location"] = location
        if start:
            s_str = start if "T" in start else start + "T09:00:00"
            s_dt = datetime.fromisoformat(s_str)
            if s_dt.tzinfo is None:
                s_dt = s_dt.replace(tzinfo=_local_tz())
            ev["start"] = {"dateTime": _rfc3339(s_dt)}
        if end:
            e_str = end if "T" in end else end + "T10:00:00"
            e_dt = datetime.fromisoformat(e_str)
            if e_dt.tzinfo is None:
                e_dt = e_dt.replace(tzinfo=_local_tz())
            ev["end"] = {"dateTime": _rfc3339(e_dt)}
        if add_attendees:
            existing = [a["email"] for a in ev.get("attendees", [])]
            ev.setdefault("attendees", [])
            for email in add_attendees:
                if email not in existing:
                    ev["attendees"].append({"email": email})

        updated = svc.events().update(calendarId=calendar_id, eventId=event_id,
                                       body=ev, sendUpdates="all").execute()
        return {
            "status":  "success",
            "event":   _event_summary(updated),
            "message": f"✅ Event **{updated.get('summary', event_id)}** updated.",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not update event: {exc}"}


def delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete (cancel) a calendar event."""
    try:
        svc = _get_client()
        # Fetch title first so the success message is informative
        try:
            ev = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
            title = ev.get("summary", event_id)
        except Exception:
            title = event_id
        svc.events().delete(calendarId=calendar_id, eventId=event_id,
                             sendUpdates="all").execute()
        return {"status": "success", "message": f"🗑️ Event **{title}** deleted."}
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not delete event: {exc}"}


def create_recurring_event(
    title: str,
    start: str,
    recurrence: str = "RRULE:FREQ=WEEKLY",
    end_time_offset_hours: int = 1,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict:
    """
    Create a recurring event.

    recurrence examples:
      "RRULE:FREQ=DAILY"
      "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"
      "RRULE:FREQ=MONTHLY;BYDAY=1MO"
      "RRULE:FREQ=WEEKLY;COUNT=10"
    """
    try:
        svc = _get_client()
        tz = _local_tz()
        s_str   = start if "T" in start else start + "T09:00:00"
        s_dt    = datetime.fromisoformat(s_str)
        if s_dt.tzinfo is None:
            s_dt = s_dt.replace(tzinfo=tz)
        start_dt = _rfc3339(s_dt)
        end_dt   = _rfc3339(s_dt + timedelta(hours=end_time_offset_hours))
        body: dict[str, Any] = {
            "summary":     title,
            "description": description,
            "location":    location,
            "start":       {"dateTime": start_dt},
            "end":         {"dateTime": end_dt},
            "recurrence":  [recurrence],
        }
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]
        ev = svc.events().insert(calendarId=calendar_id, body=body,
                                  sendUpdates="all" if attendees else "none").execute()
        return {
            "status":  "success",
            "event":   _event_summary(ev),
            "message": f"✅ Recurring event **{title}** created.",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not create recurring event: {exc}"}


# ── Calendars ─────────────────────────────────────────────────────────────────

def list_calendars() -> dict:
    """List all calendars the user has access to."""
    try:
        svc    = _get_client()
        result = svc.calendarList().list().execute()
        cals   = [
            {
                "id":          c["id"],
                "name":        c.get("summary", ""),
                "description": c.get("description", ""),
                "primary":     c.get("primary", False),
                "access_role": c.get("accessRole", ""),
            }
            for c in result.get("items", [])
        ]
        return {"status": "success", "calendars": cals, "count": len(cals),
                "message": f"You have {len(cals)} calendar(s)."}
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not list calendars: {exc}"}


# ── Scheduling helpers ────────────────────────────────────────────────────────

def find_free_slots(
    date_str: str,
    duration_minutes: int = 60,
    working_start_hour: int = 9,
    working_end_hour: int = 18,
    calendar_id: str = "primary",
) -> dict:
    """
    Find free time slots on a given date for a meeting of duration_minutes.
    Only considers working hours (working_start_hour – working_end_hour UTC).
    """
    try:
        result = get_events_for_date(date_str, calendar_id)
        if result["status"] != "success":
            return result

        busy: list[tuple[datetime, datetime]] = []
        for ev in result.get("events", []):
            if not ev.get("start") or not ev.get("end"):
                continue
            s = _dt(ev["start"])
            e = _dt(ev["end"])
            if s and e:
                if s.tzinfo is None:
                    s = s.replace(tzinfo=_local_tz())
                if e.tzinfo is None:
                    e = e.replace(tzinfo=_local_tz())
                busy.append((s, e))
        busy.sort(key=lambda x: x[0])

        # Generate candidate slots across working hours
        day = date.fromisoformat(date_str)
        cursor   = datetime(day.year, day.month, day.day, working_start_hour, 0, tzinfo=_local_tz())
        work_end = datetime(day.year, day.month, day.day, working_end_hour,   0, tzinfo=_local_tz())
        delta = timedelta(minutes=duration_minutes)
        free_slots: list[dict] = []

        while cursor + delta <= work_end:
            slot_end = cursor + delta
            # Check for overlap with any busy period
            conflict = any(b_start < slot_end and b_end > cursor for b_start, b_end in busy)
            if not conflict:
                free_slots.append({
                    "start": cursor.isoformat(),
                    "end":   slot_end.isoformat(),
                    "label": f"{cursor.strftime('%H:%M')} – {slot_end.strftime('%H:%M')}",
                })
            cursor += timedelta(minutes=30)  # 30-min granularity

        return {
            "status":      "success",
            "date":        date_str,
            "duration_min": duration_minutes,
            "free_slots":  free_slots[:10],   # top 10
            "message": (
                f"Found {len(free_slots)} free slot(s) on {date_str} for a "
                f"{duration_minutes}-min meeting."
                if free_slots else
                f"No free slots found on {date_str} within working hours."
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": f"Could not find free slots: {exc}"}


def find_conflicts(days: int = 7, calendar_id: str = "primary") -> dict:
    """Find overlapping events in the next N days."""
    try:
        result = get_upcoming_events(days=days, max_results=100, calendar_id=calendar_id)
        if result["status"] != "success":
            return result

        events = result.get("events", [])
        conflicts: list[dict] = []
        for i, ev1 in enumerate(events):
            s1, e1 = _dt(ev1.get("start")), _dt(ev1.get("end"))
            if not s1 or not e1:
                continue
            for ev2 in events[i + 1:]:
                s2, e2 = _dt(ev2.get("start")), _dt(ev2.get("end"))
                if not s2 or not e2:
                    continue
                if s1 < e2 and s2 < e1:
                    conflicts.append({"event_1": ev1["title"], "start_1": ev1["start"],
                                       "event_2": ev2["title"], "start_2": ev2["start"]})

        return {
            "status":    "success",
            "conflicts": conflicts,
            "count":     len(conflicts),
            "message":   (
                f"⚠️ Found {len(conflicts)} scheduling conflict(s) in the next {days} days."
                if conflicts else
                f"✅ No conflicts found in the next {days} days."
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": f"Could not check conflicts: {exc}"}


# ── Agendas ───────────────────────────────────────────────────────────────────

def get_daily_agenda(date_str: str | None = None, calendar_id: str = "primary") -> dict:
    """Return a formatted agenda for a specific date (default: today)."""
    if not date_str:
        date_str = date.today().isoformat()
    result = get_events_for_date(date_str, calendar_id)
    if result["status"] != "success":
        return result

    events = result.get("events", [])
    if not events:
        return {"status": "success", "date": date_str, "events": [],
                "message": f"📅 No events on {date_str}. Your day is clear!"}

    lines = [f"📅 **Agenda for {date_str}**\n"]
    for ev in events:
        start = ev.get("start", "")
        time_str = start[11:16] if "T" in start else "All day"
        attendee_str = (f" · with {', '.join(ev['attendees'][:2])}"
                        if ev.get("attendees") else "")
        loc_str = f" 📍 {ev['location']}" if ev.get("location") else ""
        lines.append(f"• **{ev['title']}** at {time_str}{attendee_str}{loc_str}")

    return {"status": "success", "date": date_str, "events": events,
            "message": "\n".join(lines)}


def get_weekly_agenda(calendar_id: str = "primary") -> dict:
    """Return a day-by-day agenda for the next 7 days."""
    today = date.today()
    sections: list[str] = [f"📅 **Weekly Agenda** ({today.isoformat()} → {(today + timedelta(days=6)).isoformat()})\n"]
    all_events: list[dict] = []

    for offset in range(7):
        day = today + timedelta(days=offset)
        day_str = day.isoformat()
        result = get_events_for_date(day_str, calendar_id)
        events = result.get("events", []) if result["status"] == "success" else []
        all_events.extend(events)
        label = day.strftime("%A %-d %b") if hasattr(day, "strftime") else day_str
        if events:
            sections.append(f"\n**{label}**")
            for ev in events:
                start = ev.get("start", "")
                time_str = start[11:16] if "T" in start else "All day"
                sections.append(f"  • {time_str} — {ev['title']}")
        else:
            sections.append(f"\n**{label}** — clear")

    return {
        "status":  "success",
        "events":  all_events,
        "message": "\n".join(sections),
    }


# ── RSVP / Reminders ─────────────────────────────────────────────────────────

def set_reminder(event_id: str, minutes_before: int = 30, calendar_id: str = "primary") -> dict:
    """Add an email + popup reminder to an event."""
    try:
        svc = _get_client()
        ev  = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        ev["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": minutes_before},
                {"method": "popup",  "minutes": max(10, minutes_before // 2)},
            ],
        }
        updated = svc.events().update(calendarId=calendar_id, eventId=event_id, body=ev).execute()
        return {
            "status":  "success",
            "event":   _event_summary(updated),
            "message": f"🔔 Reminder set {minutes_before} min before **{updated.get('summary', event_id)}**.",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not set reminder: {exc}"}


def accept_invite(event_id: str, calendar_id: str = "primary") -> dict:
    """Accept a calendar invite (set own RSVP to accepted)."""
    return _set_rsvp(event_id, "accepted", calendar_id)


def decline_invite(event_id: str, calendar_id: str = "primary") -> dict:
    """Decline a calendar invite."""
    return _set_rsvp(event_id, "declined", calendar_id)


def _set_rsvp(event_id: str, response: str, calendar_id: str) -> dict:
    try:
        svc = _get_client()
        ev  = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        for attendee in ev.get("attendees", []):
            if attendee.get("self"):
                attendee["responseStatus"] = response
        updated = svc.events().update(calendarId=calendar_id, eventId=event_id,
                                       body=ev, sendUpdates="all").execute()
        verb = "accepted" if response == "accepted" else "declined"
        return {
            "status":  "success",
            "event":   _event_summary(updated),
            "message": f"✅ Invite **{verb}** for **{updated.get('summary', event_id)}**.",
        }
    except Exception as exc:
        if _is_auth_error(exc):
            return _auth_error(exc)
        return {"status": "error", "message": f"Could not update RSVP: {exc}"}
