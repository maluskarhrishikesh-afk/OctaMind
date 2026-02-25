"""
Habit & Health Tracker Agent

Completely new agent with no overlap with existing Calendar/Files agents.
Tracks daily habits, streaks, check-ins, weekly reports, and optionally
schedules habit blocks on Google Calendar.

Data stores:
  data/habits.json     — habit definitions
  data/habit_logs.json — daily completion logs
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Dict

logger = logging.getLogger("habit_agent")

# ── Tool descriptions ──────────────────────────────────────────────────────────
_HABIT_TOOLS_DESCRIPTION = """
1. **add_habit**(name: str, frequency: str = "daily", target_time: str = "",
                  description: str = "", unit: str = "times", target_count: int = 1)
   - Add a new habit to track.
   - frequency: "daily" | "weekly" | "weekdays" | "weekends"
   - target_time: optional preferred time e.g. "07:00"
   - Use for: "add habit Morning Run", "track daily meditation", "start a reading habit"

2. **log_completion**(habit_name: str, completed: bool = True, count: int = 1,
                       notes: str = "", log_date: str = "")
   - Log today's completion of a habit. Can update a previous entry.
   - Use for: "log morning run done", "mark yoga complete", "I finished reading today",
     "log run with note 'ran 5km'"

3. **get_habits**()
   - List all active habits with today's completion status.
   - Use for: "show my habits", "what habits do I have?", "habit list"

4. **daily_checkin**()
   - Show habits not yet logged today — a quick morning/evening check-in.
   - Use for: "daily check-in", "what habits are pending today?", "check-in"

5. **get_streak**(habit_name: str)
   - Get the current and longest streak for a habit.
   - Use for: "what's my streak?", "how many days in a row?", "streak for [habit]"

6. **get_weekly_report**(weeks_back: int = 0)
   - Completion report for this week (weeks_back=0) or last week (weeks_back=1).
   - Use for: "weekly habit report", "how did I do this week?", "last week's habits"

7. **get_habit_analytics**(habit_name: str, days: int = 30)
   - Detailed stats for a single habit over the past N days.
   - Use for: "analyse my running habit", "30-day stats for meditation"

8. **delete_habit**(habit_name: str)
   - Deactivate a habit (logs are preserved).
   - Use for: "remove habit X", "stop tracking X", "delete morning run habit"

9. **schedule_habit_on_calendar**(habit_name: str, date_str: str, time: str,
                                    duration_minutes: int = 30)
   - Create a Google Calendar event for a habit session.
   - Requires Google Calendar to be authorised.
   - Use for: "schedule my run on calendar", "add gym to calendar for Thursday"
"""


# ── Tool: schedule on calendar ─────────────────────────────────────────────────

def _schedule_habit_on_calendar(
    habit_name: str,
    date_str: str,
    time: str,
    duration_minutes: int = 30,
) -> Dict[str, Any]:
    """Create a Google Calendar event for a habit session."""
    try:
        from src.calendar.calendar_service import _get_client
        _get_client()
    except Exception as exc:
        msg = str(exc).lower()
        if any(p in msg for p in ("authorization", "credentials", "token", "oauth", "auth")):
            return {
                "status": "auth_error",
                "message": "🔑 Google Calendar is not authorised. Authorise in Calendar Agent settings first.",
            }
        return {"status": "error", "message": f"Calendar error: {exc}"}

    from src.habit_tracker import get_habits as _get_habits
    from datetime import datetime, timedelta
    from src.calendar import create_event

    # Validate habit exists
    habits_result = _get_habits()
    habit = next((h for h in habits_result.get("habits", []) if h["name"].lower() == habit_name.lower()), None)
    if not habit:
        return {"status": "error", "message": f"Habit '{habit_name}' not found."}

    try:
        start_dt = datetime.strptime(f"{date_str}T{time}", "%Y-%m-%dT%H:%M")
    except Exception as e:
        return {"status": "error", "message": f"Invalid date/time: {e}"}

    end_dt = start_dt + timedelta(minutes=duration_minutes)

    result = create_event(
        title=f"🏃 {habit_name}",
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        description=f"Habit session: {habit_name}\n{habit.get('description','')}\nTracked by OctaMind Habit Tracker.",
        location="",
        attendees=[],
        all_day=False,
    )

    if result.get("status") == "success":
        result["message"] = (
            f"✅ '{habit_name}' added to Google Calendar on {date_str} "
            f"at {time} for {duration_minutes} minutes."
        )
    return result


# ── Tool dispatcher ────────────────────────────────────────────────────────────

def _dispatch_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from src.habit_tracker import (
        add_habit, log_completion, get_streak, get_habits,
        daily_checkin, get_weekly_report, get_habit_analytics, delete_habit,
    )
    _MAP = {
        "add_habit":                  lambda p: add_habit(**p),
        "log_completion":             lambda p: log_completion(**p),
        "get_habits":                 lambda p: get_habits(**p),
        "daily_checkin":              lambda p: daily_checkin(**p),
        "get_streak":                 lambda p: get_streak(**p),
        "get_weekly_report":          lambda p: get_weekly_report(**p),
        "get_habit_analytics":        lambda p: get_habit_analytics(**p),
        "delete_habit":               lambda p: delete_habit(**p),
        "schedule_habit_on_calendar": lambda p: _schedule_habit_on_calendar(**p),
    }
    fn = _MAP.get(tool)
    if fn is None:
        return {"status": "error", "message": f"Unknown habit tool: {tool}"}
    return fn(params)


# ── Main entry point ───────────────────────────────────────────────────────────

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> Dict[str, Any]:
    """
    Execute a natural-language habit tracking command.
    """
    from src.agent.llm.llm_parser import get_llm_client

    user_command = user_query
    today_str    = date.today().isoformat()
    llm          = get_llm_client()

    selection_prompt = f"""Today's date is {today_str}.

You are a habit tracking assistant. Select ONE tool to handle the user's request.

Available tools:
{_HABIT_TOOLS_DESCRIPTION}

User request: "{user_command}"

Respond with ONLY valid JSON:
{{
  "tool": "<tool_name>",
  "params": {{<key>: <value>, ...}},
  "reasoning": "<one sentence>"
}}

Rules:
- Dates: YYYY-MM-DD. Times: HH:MM (24h).
- For "log [habit] done" → log_completion with completed=true
- For "log [habit] skipped/missed" → log_completion with completed=false
- frequency must be: "daily", "weekly", "weekdays", or "weekends"
- weeks_back: 0=this week, 1=last week
- Omit optional params you don't need
"""

    try:
        sel_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a precise habit tracker tool selector. Return ONLY valid JSON."},
                {"role": "user",   "content": selection_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=30,
        )
        sel_text  = sel_response.choices[0].message.content.strip()
        clean     = re.sub(r"^```[a-z]*\n?", "", sel_text)
        clean     = re.sub(r"\n?```$", "", clean).strip()
        selection = json.loads(clean)
        tool      = selection.get("tool", "daily_checkin")
        params    = selection.get("params", {})
        logger.info("[habit_agent] Tool selected: %s params=%s", tool, params)
    except Exception as exc:
        logger.warning("[habit_agent] Tool selection failed: %s — fallback to daily_checkin", exc)
        tool   = "daily_checkin"
        params = {}

    raw = _dispatch_tool(tool, params)

    compose_prompt = f"""The user asked: "{user_command}"

The habit tracker tool "{tool}" returned:
{json.dumps(raw, indent=2, default=str)[:3000]}

Write a friendly, motivating habit tracker response:
- Use **bold** for habit names, streaks, and percentages
- Use emojis naturally: 🏃 💪 ✅ ❌ 🔥 📊 📋 🎉 ⬜
- For streaks: be encouraging — celebrate milestones (7, 14, 30, 100 days)
- For weekly reports: highlight best and worst performing habits
- For check-ins: be motivating and clear about what's pending
- Do NOT expose IDs or raw JSON
"""

    try:
        compose_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are an encouraging habit coach. Be friendly and motivating."},
                {"role": "user",   "content": compose_prompt},
            ],
            temperature=0.5,
            max_tokens=1500,
            timeout=30,
        )
        final_message = compose_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[habit_agent] Response composition failed: %s", exc)
        final_message = raw.get("message", str(raw))

    return {
        "status":    raw.get("status", "success"),
        "message":   final_message,
        "action":    "react_response",
        "raw":       raw,
        "tool_used": tool,
    }
