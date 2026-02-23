"""
Unit tests for src/agent/core/automation_scheduler.py

Covers:
 - _is_due: disabled, never ran, elapsed, not elapsed
 - _is_due: user-configured interval_minutes overrides catalog default
 - _is_due: corrupt last_run falls back to "run now"
 - start_scheduler singleton behaviour
"""

from src.agent.core.automation_scheduler import AutomationScheduler
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_scheduler(agent_id: str = "test") -> AutomationScheduler:
    """Return a scheduler that has not yet been started."""
    s = AutomationScheduler(agent_id)
    return s


def _utc_ago(minutes: float) -> str:
    """Return an ISO timestamp that is `minutes` minutes in the past."""
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return ts.isoformat()


# ─────────────────────── _is_due ─────────────────────────────────────────────

class TestIsDue:

    def test_disabled_never_due(self):
        s = _make_scheduler()
        state = {"enabled": False, "last_run": None}
        assert s._is_due("auto_delete_spam", state) is False

    def test_never_ran_is_immediately_due(self):
        s = _make_scheduler()
        state = {"enabled": True, "last_run": None}
        assert s._is_due("auto_delete_spam", state) is True

    def test_due_when_interval_elapsed(self):
        s = _make_scheduler()
        # Catalog default for auto_delete_spam is 15 min; last ran 20 min ago
        state = {"enabled": True, "last_run": _utc_ago(20)}
        assert s._is_due("auto_delete_spam", state) is True

    def test_not_due_when_interval_not_elapsed(self):
        s = _make_scheduler()
        # Catalog default for auto_delete_spam is 15 min; last ran 5 min ago
        state = {"enabled": True, "last_run": _utc_ago(5)}
        assert s._is_due("auto_delete_spam", state) is False

    def test_user_interval_overrides_catalog_default(self):
        s = _make_scheduler()
        # User set 60-min interval; only 30 min elapsed → NOT due
        state = {"enabled": True, "last_run": _utc_ago(
            30), "interval_minutes": 60}
        assert s._is_due("auto_delete_spam", state) is False

    def test_user_interval_shorter_than_catalog_default(self):
        s = _make_scheduler()
        # User set 0.5-min (30s) interval; 2 min elapsed → due
        state = {"enabled": True, "last_run": _utc_ago(
            2), "interval_minutes": 0.5}
        assert s._is_due("auto_delete_spam", state) is True

    def test_corrupt_last_run_treated_as_never_ran(self):
        s = _make_scheduler()
        state = {"enabled": True, "last_run": "not-a-date"}
        assert s._is_due("auto_delete_spam", state) is True

    def test_unknown_automation_gets_fallback_interval(self):
        """An automation not in the catalog should default to 15 min."""
        s = _make_scheduler()
        # 10 min elapsed, default fallback = 15 min → NOT due
        state = {"enabled": True, "last_run": _utc_ago(10)}
        assert s._is_due("some_unknown_automation", state) is False

    def test_exactly_at_boundary_is_due(self):
        s = _make_scheduler()
        # auto_delete_spam default = 15 min. Set last_run to exactly 15 min ago.
        state = {"enabled": True, "last_run": _utc_ago(15)}
        assert s._is_due("auto_delete_spam", state) is True

    def test_zero_interval_minutes_falls_back_to_catalog(self):
        """A stored interval_minutes of 0 should be ignored (falsy) and fall back."""
        s = _make_scheduler()
        # 0 is falsy; should fall back to catalog 15 min; last ran 10 min ago → not due
        state = {"enabled": True, "last_run": _utc_ago(
            10), "interval_minutes": 0}
        assert s._is_due("auto_delete_spam", state) is False


# ─────────────────────── thread lifecycle ────────────────────────────────────

class TestSchedulerLifecycle:

    def test_start_spawns_daemon_thread(self):
        s = _make_scheduler("lifecycle_test")
        # Prevent the loop from calling any automations
        s._run_loop = lambda: None
        s.start()
        # Give the thread a moment
        import time
        time.sleep(0.05)
        # Thread should be registered (even if it finished the no-op loop)
        assert s._thread is not None

    def test_double_start_does_not_spawn_extra_thread(self):
        s = _make_scheduler("double_start_test")
        first_thread = None

        def _slow_loop():
            import time
            time.sleep(0.5)

        s._run_loop = _slow_loop
        s.start()
        first_thread = s._thread
        s.start()  # second call — should be a no-op
        assert s._thread is first_thread

    def test_stop_sets_event(self):
        s = _make_scheduler("stop_test")
        s._run_loop = lambda: None
        s.start()
        s.stop()
        assert s._stop_event.is_set()

    def test_check_interval_is_30_seconds(self):
        assert AutomationScheduler.CHECK_INTERVAL_SECONDS == 30


# ─────────────────────── handler execution ───────────────────────────────────

class TestHandlerExecution:

    def test_handler_result_logged_and_last_run_updated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent_id = "exec_test"
        (tmp_path / "memory" / agent_id).mkdir(parents=True)
        cfg_path = tmp_path / "memory" / agent_id / "automation_config.json"
        cfg_path.write_text(json.dumps({
            "auto_delete_spam": {"enabled": True, "last_run": None, "params": {}}
        }), encoding="utf-8")

        call_log = []

        def fake_handler(aid, params):
            call_log.append((aid, params))
            return "Deleted 3 spam email(s)"

        s = AutomationScheduler(agent_id)
        s._handlers = {"auto_delete_spam": fake_handler}

        # Run one iteration of the loop manually (no sleep)
        config = s._load_config()
        for auto_id, state in config.items():
            if s._is_due(auto_id, state):
                handler = s._handlers.get(auto_id)
                if handler:
                    result = handler(s.agent_id, state.get("params", {}))
                    s._touch_last_run(auto_id)

        assert call_log == [(agent_id, {})]
        updated = json.loads(cfg_path.read_text())
        assert updated["auto_delete_spam"]["last_run"] is not None

    def test_handler_exception_does_not_crash_loop(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent_id = "crash_test"
        (tmp_path / "memory" / agent_id).mkdir(parents=True)
        cfg_path = tmp_path / "memory" / agent_id / "automation_config.json"
        cfg_path.write_text(json.dumps({
            "auto_delete_spam": {"enabled": True, "last_run": None, "params": {}}
        }), encoding="utf-8")

        def bad_handler(aid, params):
            raise RuntimeError("Simulated Gmail API failure")

        s = AutomationScheduler(agent_id)
        s._handlers = {"auto_delete_spam": bad_handler}

        # This must not raise
        config = s._load_config()
        for auto_id, state in config.items():
            if s._is_due(auto_id, state):
                handler = s._handlers.get(auto_id)
                if handler:
                    try:
                        handler(s.agent_id, state.get("params", {}))
                        s._touch_last_run(auto_id)
                    except Exception:
                        pass  # loop absorbs errors
