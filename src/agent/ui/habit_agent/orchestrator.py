"""
Habit Tracker skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
get_habits(include_inactive=False) – List all habits being tracked. Also auto-saves the habit list as context.
add_habit(name, description="", frequency="daily", target=1, unit="times") – Create a new habit to track.
log_completion(habit_name, date=None, notes="") – Record completing a habit today (or a specific date YYYY-MM-DD).
get_streak(habit_name) – Get the current and longest streak for a habit.
daily_checkin() – Show today\'s habit checklist with completion status. Also auto-saves the habit list as context.
get_weekly_report(weeks_back=0) – Get a weekly completion report (weeks_back=0 is current week).
get_habit_analytics(habit_name, days=30) – Deep analytics for a specific habit over N days.
get_all_habits_summary() – Summary stats for all habits.
delete_habit(habit_name) – Remove a habit from tracking.
save_context(topic, resolved_entities, awaiting="") – Persist the current habit listing or resolved habit reference as cross-turn context. Call AFTER listing habits / checkin so the user can say 'log the second one' without repeating the habit name.
""".strip()

_SKILL_CONTEXT = """
You are the Habit Tracker Skill Agent.
Help the user build and maintain positive habits by tracking daily completions, streaks and trends.

Typical flows:
- "Log my workout" → log_completion with the corresponding habit name.
- "How am I doing this week?" → get_weekly_report.
- "Show my streak for reading" → get_streak.
- "Add a new habit: drink 8 glasses of water" → add_habit.

Always be encouraging and motivational in your final_answer messages.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.habit_tracker import habit_service as hs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_habit_context, make_save_context_tool,
    )

    def get_habits(include_inactive: bool = False):
        result = hs.get_habits(include_inactive)
        return auto_save_habit_context(result)

    def daily_checkin():
        result = hs.daily_checkin()
        return auto_save_habit_context(result)

    return {
        "get_habits":           get_habits,
        "add_habit":            lambda name, description="", frequency="daily", target=1, unit="times": hs.add_habit(name, description, frequency, target, unit),
        "log_completion":       lambda habit_name, date=None, notes="": hs.log_completion(habit_name, date, notes),
        "get_streak":           lambda habit_name: hs.get_streak(habit_name),
        "daily_checkin":        daily_checkin,
        "get_weekly_report":    lambda weeks_back=0: hs.get_weekly_report(weeks_back),
        "get_habit_analytics":  lambda habit_name, days=30: hs.get_habit_analytics(habit_name, days),
        "get_all_habits_summary": lambda: hs.get_all_habits_summary(),
        "delete_habit":         lambda habit_name: hs.delete_habit(habit_name),
        # ── Context manifest ──────────────────────────────────────────────
        "save_context":         make_save_context_tool("habit"),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="habit",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Habit Tracker skill error: {exc}",
            "action": "react_response",
        }
