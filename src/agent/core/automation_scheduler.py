"""
Automation Scheduler — lightweight background thread per agent process.

Usage (from an agent's Streamlit UI):

    from src.agent.core.automation_scheduler import start_scheduler
    import streamlit as st

    @st.cache_resource
    def _init_scheduler():
        return start_scheduler(agent_id)

    _init_scheduler()

The scheduler:
- Reads  memory/<agent_id>/automation_config.json  on every tick
- Runs each enabled automation whose interval has elapsed
- Writes back the `last_run` timestamp after a successful run
- Runs in a daemon thread — stops automatically when the process exits
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_scheduler_instance: Optional["AutomationScheduler"] = None
_scheduler_lock = threading.Lock()


class AutomationScheduler:
    """Background scheduler for a single agent process."""

    # how often the loop polls (30 sec — supports sub-minute automations)
    CHECK_INTERVAL_SECONDS = 30

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._handlers: Dict[str, Callable] = {}
        self._load_handlers()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_handlers(self) -> None:
        """Populate handler map from available automation modules."""
        try:
            from src.agent.core.automations.gmail_automations import HANDLER_MAP
            self._handlers.update(HANDLER_MAP)
        except Exception as exc:
            logger.warning("Could not load Gmail automation handlers: %s", exc)

    def _config_path(self) -> Path:
        return Path("memory") / self.agent_id / "automation_config.json"

    def _load_config(self) -> Dict[str, Any]:
        path = self._config_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _touch_last_run(self, automation_id: str) -> None:
        """Write the current UTC time as `last_run` for the given automation."""
        path = self._config_path()
        config = self._load_config()
        if automation_id in config:
            config[automation_id]["last_run"] = datetime.now(
                timezone.utc).isoformat()
            try:
                path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.warning(
                    "Could not update last_run for %s: %s", automation_id, exc)

    def _is_due(self, automation_id: str, state: Dict[str, Any]) -> bool:
        """Return True when the automation is enabled and its interval has elapsed."""
        if not state.get("enabled", False):
            return False

        # User-configured interval in the saved config takes priority over catalog default
        interval_minutes: float = state.get(
            "interval_minutes", 0)  # type: ignore[assignment]
        if not interval_minutes:
            interval_minutes = 15
            try:
                from src.agent.core.automations.automation_config import AUTOMATION_CATALOG
                for catalog in AUTOMATION_CATALOG.values():
                    if automation_id in catalog:
                        interval_minutes = catalog[automation_id].get(
                            "interval_minutes", 15)
                        break
            except Exception:
                pass

        last_run_str = state.get("last_run")
        if last_run_str is None:
            return True          # never ran — run now

        try:
            last_run = datetime.fromisoformat(last_run_str)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) -
                       last_run).total_seconds() / 60
            return elapsed >= interval_minutes
        except Exception:
            return True          # bad timestamp — run now

    # ── Loop ──────────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        logger.info("[Scheduler:%s] Started", self.agent_id)
        while not self._stop_event.is_set():
            try:
                config = self._load_config()
                for auto_id, state in config.items():
                    if self._is_due(auto_id, state):
                        handler = self._handlers.get(auto_id)
                        if handler is None:
                            continue
                        params = state.get("params", {})
                        try:
                            result = handler(self.agent_id, params)
                            self._touch_last_run(auto_id)
                            logger.info("[Scheduler:%s] %s → %s",
                                        self.agent_id, auto_id, result)
                        except Exception as exc:
                            logger.error(
                                "[Scheduler:%s] %s failed: %s", self.agent_id, auto_id, exc
                            )
            except Exception as exc:
                logger.error("[Scheduler:%s] Loop error: %s",
                             self.agent_id, exc)

            self._stop_event.wait(self.CHECK_INTERVAL_SECONDS)

        logger.info("[Scheduler:%s] Stopped", self.agent_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"octa-scheduler-{self.agent_id}",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the loop to exit (next wake-up)."""
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


# ── Module-level helpers ──────────────────────────────────────────────────────

def start_scheduler(agent_id: str) -> AutomationScheduler:
    """Return the singleton scheduler for *agent_id*, starting it if needed.

    Intended to be called once via ``@st.cache_resource`` from an agent UI:

        @st.cache_resource
        def _init_scheduler():
            return start_scheduler(os.environ["AGENT_ID"])
    """
    global _scheduler_instance
    with _scheduler_lock:
        if _scheduler_instance is None or _scheduler_instance.agent_id != agent_id:
            if _scheduler_instance:
                _scheduler_instance.stop()
            _scheduler_instance = AutomationScheduler(agent_id)
            _scheduler_instance.start()
        return _scheduler_instance


def get_scheduler() -> Optional[AutomationScheduler]:
    """Return the running scheduler, or None if not started."""
    return _scheduler_instance
