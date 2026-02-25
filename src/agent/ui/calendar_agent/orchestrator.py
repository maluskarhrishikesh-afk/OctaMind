"""
LLM-orchestrated Calendar agent executor.

execute_with_llm_orchestration() lets the LLM select the right Calendar tool
and runs it, returning a structured result dict.

Auth preflight: if Google Calendar is not authorised the function returns
{"status": "auth_error", "message": "…"} immediately — no LLM call needed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.agent.llm.llm_parser import get_llm_client

logger = logging.getLogger("calendar_agent")

# Skills are stateless executors — memory belongs to Personal Assistants only.

# ── Tool descriptions for LLM planning ────────────────────────────────────────
_CALENDAR_TOOLS_DESCRIPTION = """
1. **get_todays_events**()
   - List ALL events for today
   - Use for: "today's schedule", "what do I have today", "today's meetings"

2. **get_tomorrows_events**()
   - List ALL events for tomorrow
   - Use for: "tomorrow's schedule", "what do I have tomorrow"

3. **get_upcoming_events**(days: int = 7, max_results: int = 20)
   - List events in the next N days
   - Use for: "this week", "next 7 days", "upcoming meetings"

4. **get_events_for_date**(date_str: str)
   - List events on a specific date (YYYY-MM-DD)
   - Use for: "events on March 5", "schedule for Friday"

5. **search_events**(query: str, days: int = 30)
   - Search events by keyword (title/description/location)
   - Use for: "find standup meetings", "search for dentist appointment"

6. **get_daily_agenda**(date_str: str = today)
   - Formatted agenda for a date — best for "what's today's schedule?"
   - Use for: "agenda for today", "what's on this week Thursday"

7. **get_weekly_agenda**()
   - Day-by-day view of next 7 days — best for weekly overview
   - Use for: "weekly agenda", "overview of my week", "what's happening this week"

8. **create_event**(title: str, start: str, end: str | None, description: str, location: str, attendees: list[str], all_day: bool)
   - Create a new event. start/end format: "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS"
   - Use for: "schedule a meeting", "add event", "book a slot"

9. **quick_add_event**(text: str)
   - Create event from natural language (e.g. "Team standup tomorrow 10am")
   - Use for free-form scheduling commands without exact times

10. **update_event**(event_id: str, title? end? start? description? location? add_attendees?)
    - Modify fields of an existing event — only supplied fields change
    - Use for: "reschedule", "change time", "add someone to meeting"

11. **delete_event**(event_id: str)
    - Cancel / delete an event
    - Use for: "cancel meeting", "delete event", "remove from calendar"

12. **create_recurring_event**(title: str, start: str, recurrence: str, description?, location?, attendees?)
    - Create weekly/daily/monthly recurring event
    - recurrence e.g.: "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"
    - Use for: "every Monday", "daily standup", "monthly review"

13. **find_free_slots**(date_str: str, duration_minutes: int = 60)
    - Find available time slots on a given day for a meeting
    - Use for: "when am I free", "find a 30-min slot", "availability on Friday"

14. **find_conflicts**(days: int = 7)
    - Detect overlapping/double-booked events in next N days
    - Use for: "any conflicts?", "double bookings", "check schedule conflicts"

15. **set_reminder**(event_id: str, minutes_before: int = 30)
    - Add email + popup reminder to an event
    - Use for: "remind me before meeting", "set alert for event"

16. **accept_invite**(event_id: str)
    - Accept a calendar invite
    - Use for: "accept meeting invite", "confirm attendance"

17. **decline_invite**(event_id: str)
    - Decline a calendar invite
    - Use for: "decline meeting", "reject invite"

18. **list_calendars**()
    - List all Google Calendars the user has access to
    - Use for: "what calendars do I have", "list my calendars"

19. **get_event**(event_id: str)
    - Fetch full details of a single event by ID
    - Use for looking up a specific event after listing/searching
"""

# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _dispatch_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Call the matching calendar_service function."""
    from src.calendar import (
        list_events, get_todays_events, get_tomorrows_events,
        get_upcoming_events, get_events_for_date, search_events,
        get_event, create_event, quick_add_event, update_event,
        delete_event, create_recurring_event, list_calendars,
        find_free_slots, find_conflicts, get_daily_agenda,
        get_weekly_agenda, set_reminder, accept_invite, decline_invite,
    )

    _MAP = {
        "get_todays_events":     lambda p: get_todays_events(**p),
        "get_tomorrows_events":  lambda p: get_tomorrows_events(**p),
        "get_upcoming_events":   lambda p: get_upcoming_events(**p),
        "get_events_for_date":   lambda p: get_events_for_date(**p),
        "search_events":         lambda p: search_events(**p),
        "get_event":             lambda p: get_event(**p),
        "get_daily_agenda":      lambda p: get_daily_agenda(**p),
        "get_weekly_agenda":     lambda p: get_weekly_agenda(**p),
        "create_event":          lambda p: create_event(**p),
        "quick_add_event":       lambda p: quick_add_event(**p),
        "update_event":          lambda p: update_event(**p),
        "delete_event":          lambda p: delete_event(**p),
        "create_recurring_event": lambda p: create_recurring_event(**p),
        "list_calendars":        lambda p: list_calendars(**p),
        "find_free_slots":       lambda p: find_free_slots(**p),
        "find_conflicts":        lambda p: find_conflicts(**p),
        "set_reminder":          lambda p: set_reminder(**p),
        "accept_invite":         lambda p: accept_invite(**p),
        "decline_invite":        lambda p: decline_invite(**p),
        "list_events":           lambda p: list_events(**p),
    }

    fn = _MAP.get(tool)
    if fn is None:
        return {"status": "error", "message": f"Unknown tool: {tool}"}
    return fn(params)


# ── Main entry point ──────────────────────────────────────────────────────────

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> Dict[str, Any]:
    """
    Execute a natural-language calendar command.

    Flow:
      1. Auth preflight — return auth_error immediately if not authorised.
      2. Ask LLM to select the right calendar tool + parameters.
      3. Call that tool.
      4. Ask LLM to compose a friendly response from the raw result.
      5. Return {"status": ..., "message": ..., "action": "react_response"}.
    """
    user_command = user_query  # alias — registry calls this as user_query
    # ── Auth preflight ────────────────────────────────────────────────────────
    try:
        from src.calendar.calendar_service import _get_client
        _get_client()
    except Exception as _auth_exc:
        msg = str(_auth_exc).lower()
        if any(p in msg for p in ("authorization", "credentials", "token", "oauth", "auth", "not found")):
            return {
                "status": "auth_error",
                "message": (
                    "🔑 Google Calendar is not authorised yet.\n\n"
                    "Click **Re-authorize Google** below to grant Calendar access."
                ),
                "action": "react_response",
            }
        raise

    from datetime import date as _date
    today_str = _date.today().isoformat()

    llm = get_llm_client()

    # ── Step 1: Tool selection ────────────────────────────────────────────────
    selection_prompt = f"""Today's date is {today_str}.

You are a calendar management assistant. Based on the user's request, select ONE tool and provide the parameters.

Available tools:
{_CALENDAR_TOOLS_DESCRIPTION}

User request: "{user_command}"

Respond with ONLY valid JSON in this format:
{{
  "tool": "<tool_name>",
  "params": {{<key>: <value>, ...}},
  "reasoning": "<one sentence>"
}}

Rules:
- For date/time parameters use ISO-8601 strings (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
- For quick natural-language scheduling like "lunch tomorrow at noon", prefer quick_add_event
- Omit optional params you don't need (don't pass null values)
- If the user asks for today's schedule, use get_daily_agenda (better format than get_todays_events)
"""

    import json as _json
    import re as _re

    try:
        sel_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a precise calendar tool selector. Return ONLY valid JSON."},
                {"role": "user",   "content": selection_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=30,
        )
        sel_text = sel_response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        clean = _re.sub(r"^```[a-z]*\n?", "", sel_text)
        clean = _re.sub(r"\n?```$", "", clean).strip()
        selection = _json.loads(clean)
        tool   = selection.get("tool", "get_todays_events")
        params = selection.get("params", {})
        logger.info("[calendar_agent] Tool selected: %s params=%s", tool, params)
    except Exception as exc:
        logger.warning("[calendar_agent] Tool selection failed: %s — falling back to get_daily_agenda", exc)
        tool   = "get_daily_agenda"
        params = {}

    # ── Step 2: Execute tool ──────────────────────────────────────────────────
    raw = _dispatch_tool(tool, params)

    if raw.get("status") == "auth_error":
        return {**raw, "action": "react_response"}

    # ── Step 3: Compose friendly response ─────────────────────────────────────
    compose_prompt = f"""The user asked: "{user_command}"

The calendar tool "{tool}" returned this raw result:
{_json.dumps(raw, indent=2, default=str)[:3000]}

Write a friendly, conversational response following these rules:
- Use **bold** for event names, times, and dates
- Use bullet points when listing multiple events
- Use calendar emoji (📅 🗓️ ⏰ 📍 👥) tastefully
- Be concise — if there are many events, show the most important and state the total count
- If the result already has a nicely formatted "message" field, build on it but improve readability
- Do NOT expose raw IDs, JSON keys, or internal field names
- If an error occurred, explain clearly and suggest the next step
"""

    try:
        compose_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful calendar assistant. Write clear, friendly responses."},
                {"role": "user",   "content": compose_prompt},
            ],
            temperature=0.4,
            max_tokens=1500,
            timeout=30,
        )
        final_message = compose_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[calendar_agent] Response composition failed: %s", exc)
        final_message = raw.get("message", str(raw))

    return {
        "status":  raw.get("status", "success"),
        "message": final_message,
        "action":  "react_response",
        "raw":     raw,
        "tool_used": tool,
    }
