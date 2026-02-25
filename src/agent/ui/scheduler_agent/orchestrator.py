"""
Scheduler / Smart Calendar Agent

Builds on the Google Calendar API to provide INTELLIGENT scheduling:
  - Find best meeting slots for multiple attendees
  - Protect deep-work / focus blocks
  - Optimize a day's schedule (group meetings, add buffers)
  - Smart conflict resolution with proposed alternatives
  - Pattern-aware scheduling (respects energy peaks, meeting-free mornings, etc.)

Differentiator from the base Calendar Agent:
  Calendar Agent  = CRUD on individual events (create/read/update/delete)
  Scheduler Agent = Reasoning OVER the calendar to propose optimal time usage
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("scheduler_agent")

# ── Tool descriptions for the LLM planner ─────────────────────────────────────
_SCHEDULER_TOOLS_DESCRIPTION = """
1. **suggest_meeting_time**(title: str, duration_minutes: int, within_days: int = 7,
                            preferred_hours_start: int = 9, preferred_hours_end: int = 18,
                            avoid_back_to_back: bool = True)
   - Find the best available slot in the next N days for a meeting.
   - Respects business hours, avoids back-to-back meetings when possible.
   - Use for: "find a good time for a 1hr meeting", "when can I schedule this?"

2. **find_mutual_availability**(attendees: list[str], duration_minutes: int, within_days: int = 7,
                                 preferred_hours_start: int = 9, preferred_hours_end: int = 18)
   - Finds free slots by checking YOUR calendar for availability.
   - Returns top 3 candidate slots with reasoning.
   - Use for: "find a time that works for all of us", "what slots are free next week?"

3. **protect_deep_work_block**(date_str: str, duration_hours: float = 2.0,
                                focus_topic: str = "Deep Work",
                                preferred_start_hour: int = 9)
   - Creates a focus/deep-work block on the calendar, avoiding existing meetings.
   - Use for: "block time for focused work", "protect my mornings for coding"

4. **optimize_day_schedule**(date_str: str)
   - Analyses the day's events and suggests improvements:
     - Group meetings together, add buffers, protect focus time.
   - Returns a written analysis with actionable suggestions (does NOT modify calendar).
   - Use for: "how can I improve my schedule?", "analyse my Wednesday"

5. **smart_reschedule_conflicts**(within_days: int = 7)
   - Finds conflicting events and proposes specific reschedule slots for each.
   - Returns a plan you can review before applying.
   - Use for: "fix my scheduling conflicts", "resolve double bookings"

6. **create_time_block**(title: str, date_str: str, start_time: str, duration_minutes: int,
                          block_type: str = "focus", color: str = "graphite")
   - Creates a dedicated time block (focus, admin, break, review, learning).
   - Use for: "block 2 hours for admin tasks", "add a review block Friday afternoon"

7. **get_scheduling_insights**(within_days: int = 14)
   - Analyses meeting patterns: busiest days, average meeting load,
     meeting-free time, back-to-back frequency, and suggested improvements.
   - Use for: "how is my meeting load?", "give me scheduling insights"

8. **schedule_recurring_focus_time**(title: str, days_of_week: list[str],
                                      start_time: str, duration_minutes: int)
   - Sets up recurring focus/deep-work blocks (e.g. every Mon/Wed 9-11am).
   - Use for: "block every morning for deep work", "protect Friday afternoons"
"""

# Colour codes for Google Calendar blocks
_BLOCK_COLORS = {
    "focus":    "9",   # Blueberry — deep work
    "admin":    "6",   # Tangerine — admin/email
    "break":    "2",   # Sage — rest
    "review":   "5",   # Banana — review/planning
    "learning": "10",  # Basil — study/learning
    "meeting":  "7",   # Peacock
    "graphite": "8",   # Graphite
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _calendar_imports():
    from src.calendar import (
        get_events_for_date, get_upcoming_events, find_free_slots,
        find_conflicts, create_event, create_recurring_event, list_events
    )
    return {
        "get_events_for_date": get_events_for_date,
        "get_upcoming_events": get_upcoming_events,
        "find_free_slots": find_free_slots,
        "find_conflicts": find_conflicts,
        "create_event": create_event,
        "create_recurring_event": create_recurring_event,
        "list_events": list_events,
    }


def _parse_time_from_event(event: Dict[str, Any]) -> Optional[tuple]:
    """Return (start_dt, end_dt) or None for all-day events."""
    start = event.get("start", "")
    end   = event.get("end", "")
    if not start or len(start) <= 10:
        return None  # all-day
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        s = datetime.strptime(start[:19], fmt)
        e = datetime.strptime(end[:19], fmt)
        return s, e
    except Exception:
        return None


# ── Tool implementations ───────────────────────────────────────────────────────

def _suggest_meeting_time(
    title: str = "Meeting",
    duration_minutes: int = 60,
    within_days: int = 7,
    preferred_hours_start: int = 9,
    preferred_hours_end: int = 18,
    avoid_back_to_back: bool = True,
) -> Dict[str, Any]:
    """Find the best available slot in the next N days."""
    cal = _calendar_imports()
    candidates = []

    for offset in range(1, within_days + 1):
        day = date.today() + timedelta(days=offset)
        day_str = day.isoformat()

        slots_result = cal["find_free_slots"](day_str, duration_minutes)
        if slots_result.get("status") != "success":
            continue

        slots = slots_result.get("free_slots", [])
        events_result = cal["get_events_for_date"](day_str)
        events = events_result.get("events", []) if events_result.get("status") == "success" else []

        for slot in slots:
            slot_start = slot.get("start", "")
            if not slot_start:
                continue
            try:
                slot_dt = datetime.strptime(slot_start[:16], "%Y-%m-%dT%H:%M")
            except Exception:
                continue

            # Filter by preferred hours
            if not (preferred_hours_start <= slot_dt.hour < preferred_hours_end):
                continue

            # Check back-to-back if requested
            slot_end_dt = slot_dt + timedelta(minutes=duration_minutes)
            back_to_back = False
            if avoid_back_to_back:
                for ev in events:
                    times = _parse_time_from_event(ev)
                    if times:
                        ev_start, ev_end = times
                        # Check if slot is immediately after or before existing event (within 5 min)
                        if abs((ev_end - slot_dt).total_seconds()) < 300:
                            back_to_back = True
                            break
                        if abs((slot_end_dt - ev_start).total_seconds()) < 300:
                            back_to_back = True
                            break

            score = 10
            if back_to_back:
                score -= 3
            # Prefer mornings
            if 9 <= slot_dt.hour <= 11:
                score += 2
            # Prefer mid-week
            if day.weekday() in (1, 2, 3):
                score += 1

            candidates.append({
                "date": day_str,
                "day_name": day.strftime("%A"),
                "start": slot_start,
                "end": (slot_dt + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%dT%H:%M:00"),
                "score": score,
                "back_to_back": back_to_back,
            })

    if not candidates:
        return {
            "status": "not_found",
            "message": f"No available {duration_minutes}-minute slot found in the next {within_days} days.",
        }

    candidates.sort(key=lambda x: (-x["score"], x["start"]))
    top3 = candidates[:3]

    return {
        "status": "success",
        "title": title,
        "duration_minutes": duration_minutes,
        "suggestions": top3,
        "message": (
            f"Found {len(candidates)} available slots. Top suggestion: "
            f"{top3[0]['day_name']} {top3[0]['date']} at "
            f"{top3[0]['start'][11:16]}"
        ),
    }


def _find_mutual_availability(
    attendees: List[str],
    duration_minutes: int = 60,
    within_days: int = 7,
    preferred_hours_start: int = 9,
    preferred_hours_end: int = 18,
) -> Dict[str, Any]:
    """Return top candidate slots based on YOUR calendar's free time."""
    # Note: True multi-attendee free/busy would require the attendees' calendars.
    # We check YOUR calendar and present slots clearly labelled.
    result = _suggest_meeting_time(
        title="Meeting",
        duration_minutes=duration_minutes,
        within_days=within_days,
        preferred_hours_start=preferred_hours_start,
        preferred_hours_end=preferred_hours_end,
        avoid_back_to_back=True,
    )
    if result.get("status") == "success":
        result["attendees"] = attendees
        result["note"] = (
            "Slots are based on your calendar availability. "
            "Share these options with your attendees to confirm their availability."
        )
    return result


def _protect_deep_work_block(
    date_str: str,
    duration_hours: float = 2.0,
    focus_topic: str = "Deep Work",
    preferred_start_hour: int = 9,
) -> Dict[str, Any]:
    """Find a clear slot and create a focus block event."""
    cal = _calendar_imports()
    duration_min = int(duration_hours * 60)

    slots_result = cal["find_free_slots"](date_str, duration_min)
    if slots_result.get("status") != "success":
        return slots_result

    slots = slots_result.get("free_slots", [])
    best_slot = None
    for slot in slots:
        start = slot.get("start", "")
        if not start:
            continue
        try:
            slot_dt = datetime.strptime(start[:16], "%Y-%m-%dT%H:%M")
        except Exception:
            continue
        if slot_dt.hour >= preferred_start_hour:
            best_slot = slot
            break

    if not best_slot:
        return {
            "status": "not_found",
            "message": f"No {duration_hours}h free block found on {date_str} after {preferred_start_hour}:00.",
        }

    start_str = best_slot["start"]
    try:
        start_dt = datetime.strptime(start_str[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        start_dt = datetime.strptime(start_str[:16], "%Y-%m-%dT%H:%M")
    end_dt  = start_dt + timedelta(minutes=duration_min)

    event_result = cal["create_event"](
        title=f"🎯 {focus_topic}",
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        description=(
            f"Protected focus block: {focus_topic}.\n"
            "Created by OctaMind Scheduler — please don't book meetings over this slot."
        ),
        location="",
        attendees=[],
        all_day=False,
    )

    if event_result.get("status") == "success":
        return {
            "status": "success",
            "message": (
                f"✅ Focus block '{focus_topic}' created on {date_str} "
                f"from {start_dt.strftime('%H:%M')} to {end_dt.strftime('%H:%M')}."
            ),
            "event": event_result.get("event", {}),
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
        }
    return event_result


def _optimize_day_schedule(date_str: str) -> Dict[str, Any]:
    """Analyse and suggest improvements to a day's schedule (read-only)."""
    cal = _calendar_imports()
    events_result = cal["get_events_for_date"](date_str)
    if events_result.get("status") != "success":
        return events_result

    events = events_result.get("events", [])
    if not events:
        return {
            "status": "success",
            "message": f"No events on {date_str} — a free day! Consider scheduling focused work blocks.",
            "analysis": {"event_count": 0, "observations": [], "suggestions": []},
        }

    # Collect timed events
    timed = []
    for ev in events:
        times = _parse_time_from_event(ev)
        if times:
            timed.append((ev.get("title", ev.get("summary", "Event")), times[0], times[1]))

    timed.sort(key=lambda x: x[1])

    observations = []
    suggestions  = []
    total_meeting_min = sum((e[2] - e[1]).seconds // 60 for e in timed)

    # Check back-to-back meetings
    for i in range(len(timed) - 1):
        _, _, end_i   = timed[i]
        title_next, start_next, _ = timed[i + 1]
        gap = (start_next - end_i).seconds // 60
        if gap < 10:
            observations.append(f"⚠️ Back-to-back: '{timed[i][0]}' ends at {end_i.strftime('%H:%M')}, "
                                 f"'{title_next}' starts at {start_next.strftime('%H:%M')} (only {gap}min gap)")
            suggestions.append(f"Add a 15-minute buffer between '{timed[i][0]}' and '{title_next}'.")

    # Check total meeting load
    if total_meeting_min > 300:
        observations.append(f"🔴 Heavy meeting day: {total_meeting_min//60}h {total_meeting_min%60}m in meetings.")
        suggestions.append("Consider moving 1–2 meetings to another day or making them async.")
    elif total_meeting_min > 180:
        observations.append(f"🟡 Moderate meeting load: {total_meeting_min//60}h {total_meeting_min%60}m.")
    else:
        observations.append(f"🟢 Light meeting load: {total_meeting_min//60}h {total_meeting_min%60}m.")

    # Check for focus time
    if timed:
        first_event_hour = timed[0][1].hour
        if first_event_hour < 10:
            observations.append("⚠️ First meeting before 10am — no protected morning focus time.")
            suggestions.append("Try to keep 9–10am free for deep work and async catch-up.")

        last_event_hour = timed[-1][2].hour
        if last_event_hour >= 17:
            observations.append(f"⚠️ Events run until {timed[-1][2].strftime('%H:%M')} — consider an earlier end.")

    # Check for long gaps (potential for focus blocks)
    for i in range(len(timed) - 1):
        _, _, end_i = timed[i]
        title_next, start_next, _ = timed[i + 1]
        gap = (start_next - end_i).seconds // 60
        if gap >= 90:
            suggestions.append(
                f"💡 You have a {gap}min gap between {end_i.strftime('%H:%M')} and "
                f"{start_next.strftime('%H:%M')} — perfect for a deep-work block."
            )

    return {
        "status": "success",
        "date": date_str,
        "event_count": len(events),
        "timed_event_count": len(timed),
        "total_meeting_minutes": total_meeting_min,
        "observations": observations,
        "suggestions": suggestions,
        "message": f"Analysed {len(timed)} timed events on {date_str}. "
                   f"Total meeting time: {total_meeting_min//60}h {total_meeting_min%60}m.",
    }


def _smart_reschedule_conflicts(within_days: int = 7) -> Dict[str, Any]:
    """Find conflicts and propose reschedule slots for each conflicting event."""
    cal = _calendar_imports()
    conflicts_result = cal["find_conflicts"](within_days)
    if conflicts_result.get("status") != "success":
        return conflicts_result

    conflicts = conflicts_result.get("conflicts", [])
    if not conflicts:
        return {
            "status": "success",
            "message": f"✅ No conflicts found in the next {within_days} days!",
            "conflicts": [],
        }

    plans = []
    for conflict in conflicts:
        date_str = conflict.get("date", "")
        events   = conflict.get("events", [])
        if not events or not date_str:
            continue

        # Suggest moving the LATER event to the next free slot
        later_event = events[-1] if len(events) > 1 else events[0]
        suggestion_result = _suggest_meeting_time(
            title=later_event.get("title", "Event"),
            duration_minutes=later_event.get("duration_minutes", 60),
            within_days=within_days,
        )
        suggestion = suggestion_result.get("suggestions", [{}])[0] if suggestion_result.get("status") == "success" else {}

        plans.append({
            "conflict_date": date_str,
            "conflicting_events": [e.get("title", "Event") for e in events],
            "recommendation": (
                f"Move '{later_event.get('title','Event')}' from {date_str} "
                f"to {suggestion.get('day_name','?')} {suggestion.get('date','?')} "
                f"at {suggestion.get('start','?')[11:16] if suggestion.get('start') else '?'}"
                if suggestion else "No free slot found in search window"
            ),
            "proposed_slot": suggestion,
        })

    return {
        "status": "success",
        "conflict_count": len(conflicts),
        "resolution_plan": plans,
        "message": (
            f"Found {len(conflicts)} conflict(s). "
            "Review the resolution plan below and confirm before rescheduling."
        ),
    }


def _create_time_block(
    title: str,
    date_str: str,
    start_time: str,
    duration_minutes: int = 60,
    block_type: str = "focus",
    color: str = "graphite",
) -> Dict[str, Any]:
    """Create a named time block on a specific date."""
    cal = _calendar_imports()
    try:
        start_dt = datetime.strptime(f"{date_str}T{start_time}", "%Y-%m-%dT%H:%M")
    except Exception:
        try:
            start_dt = datetime.strptime(f"{date_str}T{start_time}:00", "%Y-%m-%dT%H:%M:%S")
        except Exception as e:
            return {"status": "error", "message": f"Invalid time format: {e}"}

    end_dt = start_dt + timedelta(minutes=duration_minutes)

    type_emojis = {
        "focus": "🎯", "admin": "📋", "break": "☕",
        "review": "📝", "learning": "📚", "meeting": "👥"
    }
    emoji = type_emojis.get(block_type, "📌")

    result = cal["create_event"](
        title=f"{emoji} {title}",
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        description=f"Time block type: {block_type.title()}\nCreated by OctaMind Scheduler.",
        location="",
        attendees=[],
        all_day=False,
    )

    if result.get("status") == "success":
        result["message"] = (
            f"✅ {block_type.title()} block '{title}' created on {date_str} "
            f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}."
        )
    return result


def _get_scheduling_insights(within_days: int = 14) -> Dict[str, Any]:
    """Analyse meeting patterns over the next N days."""
    cal = _calendar_imports()
    upcoming = cal["get_upcoming_events"](within_days, max_results=200)
    if upcoming.get("status") != "success":
        return upcoming

    events = upcoming.get("events", [])
    if not events:
        return {
            "status": "success",
            "message": f"No events found in the next {within_days} days.",
            "insights": {},
        }

    day_counts: Dict[str, int] = {}
    day_minutes: Dict[str, int] = {}
    back_to_back_count = 0
    total_meetings = 0
    total_minutes  = 0

    by_date: Dict[str, list] = {}
    for ev in events:
        times = _parse_time_from_event(ev)
        if not times:
            continue
        s, e = times
        day = s.strftime("%A")
        date_key = s.date().isoformat()
        duration = (e - s).seconds // 60
        day_counts[day] = day_counts.get(day, 0) + 1
        day_minutes[day] = day_minutes.get(day, 0) + duration
        total_meetings += 1
        total_minutes  += duration
        by_date.setdefault(date_key, []).append((s, e, ev.get("title", "")))

    # Count back-to-back per day
    for date_key, day_evs in by_date.items():
        day_evs.sort(key=lambda x: x[0])
        for i in range(len(day_evs) - 1):
            gap = (day_evs[i+1][0] - day_evs[i][1]).seconds // 60
            if gap < 10:
                back_to_back_count += 1

    busiest_day   = max(day_counts, key=day_counts.get) if day_counts else "N/A"
    avg_per_day   = round(total_minutes / max(within_days, 1) / 60, 1)
    pct_back2back = round(back_to_back_count / max(total_meetings, 1) * 100)

    insights = {
        "total_meetings": total_meetings,
        "total_hours": round(total_minutes / 60, 1),
        "avg_meeting_hours_per_day": avg_per_day,
        "busiest_day_of_week": busiest_day,
        "back_to_back_count": back_to_back_count,
        "back_to_back_pct": pct_back2back,
        "meetings_by_day": day_counts,
        "hours_by_day": {k: round(v/60, 1) for k, v in day_minutes.items()},
    }

    recommendations = []
    if avg_per_day > 4:
        recommendations.append("⚠️ You're spending 4+ hours/day in meetings — consider meeting-free blocks.")
    if pct_back2back > 30:
        recommendations.append(f"⚠️ {pct_back2back}% back-to-back meetings — add buffer time between them.")
    if "Monday" == busiest_day:
        recommendations.append("💡 Mondays are your busiest day — consider moving some to mid-week.")
    if total_meetings == 0:
        recommendations.append("✅ Your calendar looks clear — great time to schedule important work.")
    else:
        recommendations.append(f"💡 Busiest day of the week: {busiest_day} — consider redistributing.")

    return {
        "status": "success",
        "period_days": within_days,
        "insights": insights,
        "recommendations": recommendations,
        "message": (
            f"Analysed {total_meetings} events over {within_days} days. "
            f"Avg: {avg_per_day} meeting hours/day. "
            f"Busiest day: {busiest_day}."
        ),
    }


def _schedule_recurring_focus_time(
    title: str,
    days_of_week: List[str],
    start_time: str,
    duration_minutes: int = 120,
) -> Dict[str, Any]:
    """Set up recurring focus blocks on chosen days of the week."""
    cal = _calendar_imports()

    day_map = {
        "monday": "MO", "tuesday": "TU", "wednesday": "WE",
        "thursday": "TH", "friday": "FR", "saturday": "SA", "sunday": "SU",
    }
    byday_parts = [day_map.get(d.lower(), d.upper()[:2]) for d in days_of_week]
    recurrence = f"RRULE:FREQ=WEEKLY;BYDAY={','.join(byday_parts)}"

    today = date.today()
    # Find the next occurrence of the first specified day
    target_day_num = list(day_map.keys()).index(days_of_week[0].lower()) if days_of_week else 0
    days_ahead = (target_day_num - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    first_date = today + timedelta(days=days_ahead)

    try:
        start_dt = datetime.strptime(f"{first_date.isoformat()}T{start_time}", "%Y-%m-%dT%H:%M")
    except Exception as e:
        return {"status": "error", "message": f"Invalid time format: {e}"}
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    result = cal["create_recurring_event"](
        title=f"🎯 {title}",
        start=start_dt.isoformat(),
        recurrence=recurrence,
        description=(
            f"Recurring focus block: {title}\n"
            f"Days: {', '.join(days_of_week)}\n"
            f"Duration: {duration_minutes} minutes\n"
            "Created by OctaMind Scheduler."
        ),
        location="",
        attendees=[],
    )

    if result.get("status") == "success":
        result["message"] = (
            f"✅ Recurring focus block '{title}' created every "
            f"{', '.join(days_of_week)} at {start_time} for {duration_minutes//60}h {duration_minutes%60}m."
        )
    return result


# ── Tool dispatcher ────────────────────────────────────────────────────────────
def _dispatch_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
    _MAP = {
        "suggest_meeting_time":          lambda p: _suggest_meeting_time(**p),
        "find_mutual_availability":      lambda p: _find_mutual_availability(**p),
        "protect_deep_work_block":       lambda p: _protect_deep_work_block(**p),
        "optimize_day_schedule":         lambda p: _optimize_day_schedule(**p),
        "smart_reschedule_conflicts":    lambda p: _smart_reschedule_conflicts(**p),
        "create_time_block":             lambda p: _create_time_block(**p),
        "get_scheduling_insights":       lambda p: _get_scheduling_insights(**p),
        "schedule_recurring_focus_time": lambda p: _schedule_recurring_focus_time(**p),
    }
    fn = _MAP.get(tool)
    if fn is None:
        return {"status": "error", "message": f"Unknown scheduler tool: {tool}"}
    return fn(params)


# ── Main entry point ───────────────────────────────────────────────────────────
def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> Dict[str, Any]:
    """
    Execute a natural-language scheduling command.

    Flow:
      1. Auth preflight — requires Google Calendar to be authorised.
      2. LLM selects the right scheduling tool + parameters.
      3. Tool executes.
      4. LLM composes a friendly, actionable response.
    """
    from src.agent.llm.llm_parser import get_llm_client

    user_command = user_query

    # ── Auth preflight ─────────────────────────────────────────────────────────
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
                    "Authorise Calendar access in the Calendar Agent settings first."
                ),
                "action": "react_response",
            }
        raise

    today_str = date.today().isoformat()
    llm = get_llm_client()

    # ── Step 1: Tool selection ─────────────────────────────────────────────────
    selection_prompt = f"""Today's date is {today_str}.

You are an intelligent scheduling assistant. Based on the user's request, select ONE tool.

Available tools:
{_SCHEDULER_TOOLS_DESCRIPTION}

User request: "{user_command}"

Respond with ONLY valid JSON:
{{
  "tool": "<tool_name>",
  "params": {{<key>: <value>, ...}},
  "reasoning": "<one sentence>"
}}

Rules:
- Dates: YYYY-MM-DD format. Times: HH:MM (24h) format.
- days_of_week must be full lowercase names: ["monday", "wednesday"]
- duration_minutes is an integer (e.g. 60 for 1 hour)
- Omit optional params you don't need
- For "find a time for a meeting with X" → use find_mutual_availability with attendees list
- For "protect my morning" → use protect_deep_work_block
- For "how am I doing with meetings?" → use get_scheduling_insights
"""

    try:
        sel_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a precise scheduling tool selector. Return ONLY valid JSON."},
                {"role": "user",   "content": selection_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=30,
        )
        sel_text = sel_response.choices[0].message.content.strip()
        clean = re.sub(r"^```[a-z]*\n?", "", sel_text)
        clean = re.sub(r"\n?```$", "", clean).strip()
        selection = json.loads(clean)
        tool   = selection.get("tool", "get_scheduling_insights")
        params = selection.get("params", {})
        logger.info("[scheduler_agent] Tool selected: %s params=%s", tool, params)
    except Exception as exc:
        logger.warning("[scheduler_agent] Tool selection failed: %s — fallback to insights", exc)
        tool   = "get_scheduling_insights"
        params = {}

    # ── Step 2: Execute ────────────────────────────────────────────────────────
    raw = _dispatch_tool(tool, params)

    # ── Step 3: Compose response ───────────────────────────────────────────────
    compose_prompt = f"""The user asked: "{user_command}"

The scheduling tool "{tool}" returned:
{json.dumps(raw, indent=2, default=str)[:3000]}

Write a clear, friendly scheduling assistant response:
- Use **bold** for dates, times, and event names
- Use bullet points for multiple options/slots
- Use calendar/scheduling emojis (📅 🗓️ ⏰ 🎯 📊) naturally
- Be actionable: tell the user what to do next if relevant
- Do NOT expose IDs, JSON keys, or internal fields
- If suggestions are returned, present them as ranked options with brief reasoning
"""

    try:
        compose_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful scheduling assistant. Be clear and actionable."},
                {"role": "user",   "content": compose_prompt},
            ],
            temperature=0.4,
            max_tokens=1500,
            timeout=30,
        )
        final_message = compose_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[scheduler_agent] Response composition failed: %s", exc)
        final_message = raw.get("message", str(raw))

    return {
        "status":    raw.get("status", "success"),
        "message":   final_message,
        "action":    "react_response",
        "raw":       raw,
        "tool_used": tool,
    }
