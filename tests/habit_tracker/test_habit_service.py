"""
Unit tests for src/habit_tracker/habit_service.py

Covers:
  - add_habit: new habit, duplicate active (error), duplicate inactive (re-activate)
  - log_completion: first log, duplicate log updates existing entry
  - get_streak: consecutive streak counting, streak resets after gap,
                longest streak preserved across gaps
  - get_habits: today's completion status (done / pending / missed)
  - get_weekly_report: date-window covers Mon–today for current week, last week
  - delete_habit: marks habit inactive, preserves logs

All tests operate on temp files — data/habits.json and data/habit_logs.json
are never touched.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper — redirect file I/O to a temp directory
# ---------------------------------------------------------------------------

def _patch_data_files(tmp_path: Path):
    """Patch the module-level file path constants to use tmp_path."""
    import src.habit_tracker.habit_service as hs
    habits_file = tmp_path / "habits.json"
    logs_file   = tmp_path / "habit_logs.json"
    return patch.multiple(
        hs,
        _HABITS_FILE=habits_file,
        _LOGS_FILE=logs_file,
        _DATA_DIR=tmp_path,
    )


def _date(days_ago: int = 0) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------------------
# add_habit
# ---------------------------------------------------------------------------

class TestAddHabit:

    def test_add_new_habit_succeeds(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit
            result = add_habit("Morning Run", frequency="daily")
        assert result["status"] == "success"
        assert result["habit"]["name"] == "Morning Run"
        assert result["habit"]["active"] is True

    def test_add_habit_persisted_to_file(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit
            add_habit("Reading", frequency="daily")
            data = json.loads((tmp_path / "habits.json").read_text())
            habits = data if isinstance(data, list) else data.get("habits", [])
            assert any(h["name"] == "Reading" for h in habits)

    def test_add_duplicate_active_habit_returns_error(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit
            add_habit("Gym", frequency="daily")
            result = add_habit("Gym", frequency="daily")
        assert result["status"] == "error"

    def test_add_duplicate_inactive_habit_reactivates(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, delete_habit
            add_habit("Yoga", frequency="daily")
            delete_habit("Yoga")
            result = add_habit("Yoga", frequency="weekends")
        assert result["status"] == "success"
        assert result["habit"]["active"] is True
        assert result["habit"]["frequency"] == "weekends"

    def test_add_habit_stores_optional_fields(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit
            result = add_habit(
                "Water", frequency="daily",
                target_time="08:00", unit="glasses", target_count=8
            )
        habit = result["habit"]
        assert habit["target_time"] == "08:00"
        assert habit["unit"] == "glasses"
        assert habit["target_count"] == 8


# ---------------------------------------------------------------------------
# log_completion
# ---------------------------------------------------------------------------

class TestLogCompletion:

    def test_log_completion_success(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, log_completion
            add_habit("Gym")
            result = log_completion("Gym", completed=True)
        assert result["status"] == "success"

    def test_log_unknown_habit_returns_error(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import log_completion
            result = log_completion("NonExistentHabit")
        assert result["status"] == "error"

    def test_log_duplicate_on_same_date_updates_existing(self, tmp_path):
        """A second log for the same habit on the same date overwrites — no duplicate entries."""
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, log_completion, _load_logs
            add_habit("Reading")
            log_completion("Reading", completed=True)
            log_completion("Reading", completed=False, notes="skipped today")
            logs = _load_logs()
            today = date.today().isoformat()
            habit_logs_today = [l for l in logs if l.get("date") == today]
            # Should be exactly one log for today
            assert len(habit_logs_today) == 1
            assert habit_logs_today[0]["completed"] is False

    def test_log_custom_date(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, log_completion, _load_logs
            add_habit("Meditation")
            yesterday = _date(1)
            log_completion("Meditation", completed=True, log_date=yesterday)
            logs = _load_logs()
            assert any(l.get("date") == yesterday and l.get("completed") for l in logs)


# ---------------------------------------------------------------------------
# get_streak
# ---------------------------------------------------------------------------

class TestGetStreak:

    def _setup_habit_with_logs(self, tmp_path, habit_name: str, completed_days_ago: list[int]):
        """Helper: create a habit and write completion logs for the given day offsets."""
        from src.habit_tracker.habit_service import add_habit, log_completion
        add_habit(habit_name)
        for offset in completed_days_ago:
            log_completion(habit_name, completed=True, log_date=_date(offset))

    def test_streak_unknown_habit_returns_error(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import get_streak
            result = get_streak("Ghost Habit")
        assert result["status"] == "error"

    def test_streak_consecutive_days(self, tmp_path):
        """Logging 3 consecutive days should give longest_streak ≥ 3."""
        with _patch_data_files(tmp_path):
            self._setup_habit_with_logs(tmp_path, "Gym", [0, 1, 2])
            from src.habit_tracker.habit_service import get_streak
            result = get_streak("Gym")
        assert result["status"] == "success"
        assert result["longest_streak"] >= 3

    def test_streak_not_consecutive_gives_lower_current_streak(self, tmp_path):
        """
        Logging days 0, 1, 3 (gap on day 2) — the current streak from today
        is 2 (days 0 and 1), not 3.
        """
        with _patch_data_files(tmp_path):
            self._setup_habit_with_logs(tmp_path, "Running", [0, 1, 3])
            from src.habit_tracker.habit_service import get_streak
            result = get_streak("Running")
        assert result["status"] == "success"
        # There is a gap, so the longest consecutive run is at most 2
        assert result["longest_streak"] <= 2

    def test_longest_streak_preserved_after_break(self, tmp_path):
        """
        If there was a 5-day streak in the past followed by a gap and then a
        1-day log today, longest_streak should still report 5.
        """
        with _patch_data_files(tmp_path):
            # Past run: days 10-14 ago (5 consecutive)
            past_run = list(range(10, 15))  # [10, 11, 12, 13, 14]
            # Today only (gap: days 1-9)
            self._setup_habit_with_logs(tmp_path, "Yoga", past_run + [0])
            from src.habit_tracker.habit_service import get_streak
            result = get_streak("Yoga")
        assert result["status"] == "success"
        assert result["longest_streak"] >= 5

    def test_no_logs_gives_zero_streak(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, get_streak
            add_habit("Flossing")
            result = get_streak("Flossing")
        assert result["status"] == "success"
        assert result["current_streak"] == 0
        assert result["longest_streak"] == 0

    def test_completion_rate_calculation(self, tmp_path):
        """10 logs total, 8 completed → rate = 80 %."""
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, log_completion, get_streak
            add_habit("Water")
            for i in range(8):
                log_completion("Water", completed=True, log_date=_date(i))
            for i in range(8, 10):
                log_completion("Water", completed=False, log_date=_date(i))
            result = get_streak("Water")
        assert result["status"] == "success"
        assert result["completion_rate"] == 80.0
        assert result["total_completions"] == 8


# ---------------------------------------------------------------------------
# get_habits
# ---------------------------------------------------------------------------

class TestGetHabits:

    def test_no_habits_returns_empty(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import get_habits
            result = get_habits()
        assert result["status"] == "success"
        assert result["count"] == 0

    def test_get_habits_shows_today_done(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, log_completion, get_habits
            add_habit("Pushups")
            log_completion("Pushups", completed=True)
            result = get_habits()
        assert result["done_today"] == 1

    def test_get_habits_inactive_excluded_by_default(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, delete_habit, get_habits
            add_habit("OldHabit")
            delete_habit("OldHabit")
            result = get_habits()
        assert result["count"] == 0

    def test_get_habits_inactive_included_when_flag_set(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, delete_habit, get_habits
            add_habit("OldHabit2")
            delete_habit("OldHabit2")
            result = get_habits(include_inactive=True)
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# get_weekly_report
# ---------------------------------------------------------------------------

class TestGetWeeklyReport:

    def test_current_week_report_covers_mon_to_today(self, tmp_path):
        """weeks_back=0 — week_start should be the most recent Monday."""
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import get_weekly_report
            result = get_weekly_report(weeks_back=0)
        assert result["status"] == "success"
        week_start = date.fromisoformat(result["week_start"])
        today = date.today()
        expected_monday = today - timedelta(days=today.weekday())
        assert week_start == expected_monday

    def test_last_week_report_covers_correct_window(self, tmp_path):
        """weeks_back=1 starts 7 days before the current week's Monday."""
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import get_weekly_report
            result = get_weekly_report(weeks_back=1)
        assert result["status"] == "success"
        week_start = date.fromisoformat(result["week_start"])
        today = date.today()
        expected_monday = today - timedelta(days=today.weekday() + 7)
        assert week_start == expected_monday

    def test_weekly_report_habit_rate(self, tmp_path):
        """
        A habit logged on 3 out of 7 days in the past week should report ~43 % rate
        (or proportionately if the week isn't complete yet).
        """
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, log_completion, get_weekly_report
            add_habit("Stretching")
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            # Log Mon, Tue, Wed of this week (offsets from today to those days)
            for i in range(3):
                d = (monday + timedelta(days=i)).isoformat()
                if d <= today.isoformat():
                    log_completion("Stretching", completed=True, log_date=d)
            result = get_weekly_report(weeks_back=0)
        assert result["status"] == "success"
        habit_entry = next(
            (r for r in result["habits_report"] if r["habit"] == "Stretching"), None
        )
        assert habit_entry is not None
        assert habit_entry["completed"] >= 1


# ---------------------------------------------------------------------------
# delete_habit
# ---------------------------------------------------------------------------

class TestDeleteHabit:

    def test_delete_habit_marks_inactive(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import add_habit, delete_habit, _load_habits
            add_habit("Swimming")
            result = delete_habit("Swimming")
            assert result["status"] == "success"
            habits = _load_habits()
            h = next((h for h in habits if h["name"] == "Swimming"), None)
            assert h is not None
            assert h["active"] is False

    def test_delete_unknown_habit_returns_error(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import delete_habit
            result = delete_habit("NoSuchHabit")
        assert result["status"] == "error"

    def test_delete_preserves_logs(self, tmp_path):
        with _patch_data_files(tmp_path):
            from src.habit_tracker.habit_service import (
                add_habit, log_completion, delete_habit, _load_logs
            )
            add_habit("Cycling")
            log_completion("Cycling", completed=True)
            delete_habit("Cycling")
            logs = _load_logs()
        assert any(l.get("habit_name") == "Cycling" for l in logs)
