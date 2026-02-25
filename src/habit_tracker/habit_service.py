"""
Habit & Health Tracker Service

Data storage:
  data/habits.json      — habit definitions (name, frequency, target_time, active, ...)
  data/habit_logs.json  — daily completion logs (habit_id, date, completed, notes)
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT       = Path(__file__).parent.parent.parent  # project root
_DATA_DIR   = _ROOT / "data"
_HABITS_FILE = _DATA_DIR / "habits.json"
_LOGS_FILE   = _DATA_DIR / "habit_logs.json"


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_habits() -> List[Dict[str, Any]]:
    try:
        if _HABITS_FILE.exists():
            data = json.loads(_HABITS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("habits", [])
    except Exception:
        pass
    return []


def _save_habits(habits: List[Dict[str, Any]]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _HABITS_FILE.write_text(json.dumps(habits, indent=2), encoding="utf-8")


def _load_logs() -> List[Dict[str, Any]]:
    try:
        if _LOGS_FILE.exists():
            data = json.loads(_LOGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("logs", [])
    except Exception:
        pass
    return []


def _save_logs(logs: List[Dict[str, Any]]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _LOGS_FILE.write_text(json.dumps(logs, indent=2, default=str), encoding="utf-8")


def _find_habit(name: str, habits: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Case-insensitive habit lookup by name or id."""
    name_lower = name.lower().strip()
    for h in habits:
        if h.get("name", "").lower() == name_lower or h.get("id") == name:
            return h
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def add_habit(
    name: str,
    frequency: str = "daily",
    target_time: str = "",
    description: str = "",
    unit: str = "times",
    target_count: int = 1,
) -> Dict[str, Any]:
    """
    Add a new habit.

    Args:
        name:          Habit name (e.g. "Morning Run")
        frequency:     "daily" | "weekly" | "weekdays" | "weekends"
        target_time:   Optional preferred time, e.g. "07:00"
        description:   Optional longer description
        unit:          What you're counting (times, minutes, km, glasses, ...)
        target_count:  Target count per occurrence
    """
    habits = _load_habits()
    existing = _find_habit(name, habits)
    if existing:
        if existing.get("active", True):
            return {"status": "error", "message": f"Habit '{name}' already exists. Use a different name."}
        # Re-activate an inactive habit instead of creating a duplicate
        existing["active"]        = True
        existing["target_time"]   = target_time or existing.get("target_time", "")
        existing["description"]   = description or existing.get("description", "")
        existing["unit"]          = unit
        existing["target_count"]  = target_count
        existing["frequency"]     = frequency
        _save_habits(habits)
        return {
            "status":  "success",
            "habit":   existing,
            "message": f"✅ Habit '{name}' re-activated! Frequency: {frequency}. Start tracking with 'log {name} done'.",
        }

    habit = {
        "id":           str(uuid.uuid4())[:8],
        "name":         name,
        "frequency":    frequency,
        "target_time":  target_time,
        "description":  description,
        "unit":         unit,
        "target_count": target_count,
        "created_at":   date.today().isoformat(),
        "active":       True,
    }
    habits.append(habit)
    _save_habits(habits)

    return {
        "status":  "success",
        "habit":   habit,
        "message": f"✅ Habit '{name}' added! Frequency: {frequency}. Start tracking with 'log {name} done'.",
    }


def log_completion(
    habit_name: str,
    completed: bool = True,
    count: int = 1,
    notes: str = "",
    log_date: str = "",
) -> Dict[str, Any]:
    """
    Log a habit completion for today (or a specific date).

    Args:
        habit_name: Name of the habit
        completed:  True = done, False = skipped/missed
        count:      How many times/units completed
        notes:      Optional notes (e.g. "Ran 5km")
        log_date:   ISO date string, defaults to today
    """
    habits = _load_habits()
    habit  = _find_habit(habit_name, habits)
    if not habit:
        return {"status": "error", "message": f"Habit '{habit_name}' not found. Add it first."}

    target_date = log_date or date.today().isoformat()
    logs        = _load_logs()

    # Check for duplicate log on same date
    for log in logs:
        if log.get("habit_id") == habit["id"] and log.get("date") == target_date:
            log["completed"]  = completed
            log["count"]      = count
            log["notes"]      = notes
            log["logged_at"]  = datetime.now().isoformat()
            _save_logs(logs)
            return {
                "status":  "success",
                "message": f"✅ Updated log for '{habit_name}' on {target_date}: {'done' if completed else 'skipped'}.",
            }

    logs.append({
        "habit_id":  habit["id"],
        "habit_name": habit["name"],
        "date":      target_date,
        "completed": completed,
        "count":     count,
        "notes":     notes,
        "logged_at": datetime.now().isoformat(),
    })
    _save_logs(logs)

    return {
        "status":  "success",
        "message": f"✅ Logged '{habit_name}' for {target_date}: {'✓ done' if completed else '✗ skipped'}."
        + (f" ({count} {habit.get('unit','times')})" if count > 1 else "")
        + (f" — {notes}" if notes else ""),
    }


def get_streak(habit_name: str) -> Dict[str, Any]:
    """
    Calculate the current consecutive completion streak for a habit.
    """
    habits = _load_habits()
    habit  = _find_habit(habit_name, habits)
    if not habit:
        return {"status": "error", "message": f"Habit '{habit_name}' not found."}

    logs = _load_logs()
    habit_logs = {
        log["date"]: log["completed"]
        for log in logs
        if log.get("habit_id") == habit["id"]
    }

    streak       = 0
    longest      = 0
    current_date = date.today()
    temp_streak  = 0

    # Count backwards from today
    for i in range(365):
        d = (current_date - timedelta(days=i)).isoformat()
        if habit_logs.get(d):
            temp_streak += 1
            if i == streak:
                streak = temp_streak
        else:
            if i == 0:
                pass  # today not yet logged — streak counts from yesterday
            else:
                break

    # Longest streak
    sorted_dates = sorted(habit_logs.keys())
    run = 0
    prev = None
    for d in sorted_dates:
        if habit_logs.get(d):
            if prev:
                prev_dt   = date.fromisoformat(prev)
                curr_dt   = date.fromisoformat(d)
                diff_days = (curr_dt - prev_dt).days
                if diff_days == 1:
                    run += 1
                else:
                    run = 1
            else:
                run = 1
            longest = max(longest, run)
        prev = d

    total_logged    = sum(1 for v in habit_logs.values() if v)
    total_possible  = len(habit_logs)

    return {
        "status":           "success",
        "habit":            habit_name,
        "current_streak":   streak,
        "longest_streak":   longest,
        "total_completions": total_logged,
        "total_logged":     total_possible,
        "completion_rate":  round(total_logged / max(total_possible, 1) * 100, 1),
        "message": (
            f"🔥 '{habit_name}' streak: **{streak}** day(s) current, "
            f"**{longest}** day(s) longest. "
            f"Total: {total_logged}/{total_possible} logged ({round(total_logged/max(total_possible,1)*100)}%)."
        ),
    }


def get_habits(include_inactive: bool = False) -> Dict[str, Any]:
    """List all habits with today's completion status."""
    habits = _load_habits()
    if not include_inactive:
        habits = [h for h in habits if h.get("active", True)]

    if not habits:
        return {
            "status":  "success",
            "count":   0,
            "habits":  [],
            "message": "No habits tracked yet. Add one with 'add habit Morning Run daily at 7am'.",
        }

    logs       = _load_logs()
    today_str  = date.today().isoformat()
    today_logs = {
        log["habit_id"]: log
        for log in logs
        if log.get("date") == today_str
    }

    result = []
    for h in habits:
        log = today_logs.get(h["id"])
        result.append({
            **h,
            "today_completed": log["completed"] if log else None,
            "today_notes":     log.get("notes", "") if log else "",
        })

    done    = sum(1 for r in result if r["today_completed"])
    pending = sum(1 for r in result if r["today_completed"] is None)

    lines = []
    for r in result:
        status = "✅" if r["today_completed"] else ("⬜" if r["today_completed"] is None else "❌")
        line   = f"  {status} {r['name']} ({r['frequency']})"
        if r.get("target_time"):
            line += f" @ {r['target_time']}"
        lines.append(line)

    return {
        "status":  "success",
        "count":   len(result),
        "done_today":    done,
        "pending_today": pending,
        "habits":  result,
        "message": (
            f"📋 Today's habits ({done}/{len(result)} done):\n"
            + "\n".join(lines)
        ),
    }


def daily_checkin() -> Dict[str, Any]:
    """
    Quick daily check-in: show incomplete habits for today.
    Returns habits that haven't been logged yet.
    """
    habits    = _load_habits()
    active    = [h for h in habits if h.get("active", True)]
    logs      = _load_logs()
    today_str = date.today().isoformat()
    logged_ids = {l["habit_id"] for l in logs if l.get("date") == today_str}

    pending = [h for h in active if h["id"] not in logged_ids]
    done    = [h for h in active if h["id"] in logged_ids]

    if not pending:
        return {
            "status":      "success",
            "pending_count": 0,
            "done_count":  len(done),
            "pending":     [],
            "message": f"🎉 All {len(done)} habit(s) logged for today! Great work!",
        }

    lines = [f"  ⬜ {h['name']}" + (f" @ {h['target_time']}" if h.get("target_time") else "") for h in pending]
    return {
        "status":       "success",
        "pending_count": len(pending),
        "done_count":   len(done),
        "pending":      pending,
        "message": (
            f"📋 Daily check-in — {len(done)}/{len(active)} habits done today.\n\n"
            f"Still to log:\n" + "\n".join(lines)
            + "\n\nLog them with: 'log [habit name] done'"
        ),
    }


def get_weekly_report(weeks_back: int = 0) -> Dict[str, Any]:
    """
    Generate a habit completion report for a week.

    weeks_back=0 → current week (Mon–today)
    weeks_back=1 → last full week
    """
    today      = date.today()
    week_start = today - timedelta(days=today.weekday() + (7 * weeks_back))
    week_end   = week_start + timedelta(days=6)

    habits  = [h for h in _load_habits() if h.get("active", True)]
    logs    = _load_logs()
    log_map = {}
    for log in logs:
        key = (log.get("habit_id"), log.get("date"))
        log_map[key] = log.get("completed", False)

    dates_in_week = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
    today_str     = today.isoformat()
    dates_to_check = [d for d in dates_in_week if d <= today_str]

    report = []
    for h in habits:
        completions = sum(1 for d in dates_to_check if log_map.get((h["id"], d)))
        rate = round(completions / max(len(dates_to_check), 1) * 100)
        report.append({
            "habit":       h["name"],
            "completed":   completions,
            "possible":    len(dates_to_check),
            "rate":        rate,
            "emoji":       "🔥" if rate == 100 else ("✅" if rate >= 70 else ("⚠️" if rate >= 40 else "❌")),
        })

    report.sort(key=lambda x: -x["rate"])
    overall = round(sum(r["rate"] for r in report) / max(len(report), 1))

    lines = [f"  {r['emoji']} {r['habit']}: {r['completed']}/{r['possible']} ({r['rate']}%)" for r in report]
    label = "This week" if weeks_back == 0 else f"Week of {week_start}"

    return {
        "status":        "success",
        "week_start":    week_start.isoformat(),
        "week_end":      week_end.isoformat(),
        "overall_rate":  overall,
        "habits_report": report,
        "message": (
            f"📊 {label} — Overall: {overall}%\n\n"
            + "\n".join(lines)
        ),
    }


def get_habit_analytics(habit_name: str, days: int = 30) -> Dict[str, Any]:
    """Detailed analytics for a single habit over the past N days."""
    habits = _load_habits()
    habit  = _find_habit(habit_name, habits)
    if not habit:
        return {"status": "error", "message": f"Habit '{habit_name}' not found."}

    logs = _load_logs()
    cutoff  = date.today() - timedelta(days=days)
    period_logs = [
        l for l in logs
        if l.get("habit_id") == habit["id"]
        and l.get("date", "") >= cutoff.isoformat()
    ]

    completed_dates = {l["date"] for l in period_logs if l.get("completed")}
    missed_dates    = {l["date"] for l in period_logs if not l.get("completed")}
    not_logged      = days - len(completed_dates) - len(missed_dates)

    streak_result = get_streak(habit_name)

    return {
        "status":           "success",
        "habit":            habit_name,
        "period_days":      days,
        "completed":        len(completed_dates),
        "missed":           len(missed_dates),
        "not_logged":       not_logged,
        "completion_rate":  round(len(completed_dates) / days * 100, 1),
        "current_streak":   streak_result.get("current_streak", 0),
        "longest_streak":   streak_result.get("longest_streak", 0),
        "best_day":         habit.get("target_time", "N/A"),
        "message": (
            f"📈 Analytics for '{habit_name}' (last {days} days):\n"
            f"  ✅ Completed: {len(completed_dates)}/{days} days ({round(len(completed_dates)/days*100)}%)\n"
            f"  ❌ Missed: {len(missed_dates)} · ⬜ Not logged: {not_logged}\n"
            f"  🔥 Current streak: {streak_result.get('current_streak',0)} · "
            f"Longest: {streak_result.get('longest_streak',0)}"
        ),
    }


def delete_habit(habit_name: str) -> Dict[str, Any]:
    """Mark a habit as inactive (preserves logs)."""
    habits = _load_habits()
    habit  = _find_habit(habit_name, habits)
    if not habit:
        return {"status": "error", "message": f"Habit '{habit_name}' not found."}

    habit["active"]     = False
    habit["deleted_at"] = date.today().isoformat()
    _save_habits(habits)

    return {
        "status":  "success",
        "message": f"✅ Habit '{habit_name}' deactivated. Logs are preserved.",
    }


def get_all_habits_summary() -> Dict[str, Any]:
    """Quick overview: all habits with today's status (for dashboard/check-in)."""
    return get_habits()
