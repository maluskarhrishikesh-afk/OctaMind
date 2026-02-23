"""
Global Consolidation Runner

Runs memory consolidation for ALL registered agents (including __multi_agent__)
in a daemon background thread.

Lifecycle:
  - Starts automatically when the OctaMind application boots.
  - Performs an immediate first-pass consolidation on startup.
  - Then repeats every 24 hours.
  - Stops cleanly when the process exits (daemon thread).

Usage:
    from src.agent.memory.consolidation_runner import get_consolidation_runner
    runner = get_consolidation_runner()
    runner.start()          # idempotent — safe to call multiple times
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("octamind.consolidation_runner")

# How long between full consolidation passes (seconds)
_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_AGENTS_JSON = _PROJECT_ROOT / "agents.json"
_MULTI_AGENT_ID = "__multi_agent__"


class ConsolidationRunner:
    """
    Background thread that consolidates memory for every agent once every 24 hours.

    Thread is started as a daemon so it dies automatically when the main
    Streamlit process exits — no cleanup needed.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the consolidation loop (idempotent)."""
        if self._thread and self._thread.is_alive():
            logger.debug("[ConsolidationRunner] Already running — skipping start.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="ConsolidationRunner",
            daemon=True,
        )
        self._thread.start()
        logger.info("[ConsolidationRunner] Background thread started.")

    def stop(self) -> None:
        """Signal the thread to stop after the current cycle."""
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Internal ───────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Main loop: run immediately, then sleep 24 h and repeat."""
        logger.info("[ConsolidationRunner] First consolidation pass starting…")
        self._run_cycle()

        while not self._stop_event.is_set():
            # Sleep in 1-second ticks so stop() is responsive
            for _ in range(_INTERVAL_SECONDS):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

            if not self._stop_event.is_set():
                logger.info("[ConsolidationRunner] 24-hour consolidation pass starting…")
                self._run_cycle()

        logger.info("[ConsolidationRunner] Thread exiting.")

    def _get_all_agent_ids(self) -> list[str]:
        """Return every registered agent ID, plus the multi-agent hub."""
        ids: list[str] = [_MULTI_AGENT_ID]
        try:
            if _AGENTS_JSON.exists():
                data = json.loads(_AGENTS_JSON.read_text(encoding="utf-8"))
                for agent in data.get("agents", []):
                    aid = agent.get("id", "")
                    if aid and aid != _MULTI_AGENT_ID:
                        ids.append(aid)
        except Exception as exc:
            logger.error(f"[ConsolidationRunner] Could not read agents.json: {exc}")
        return ids

    def _run_cycle(self) -> None:
        """Run one full consolidation cycle across all agents."""
        # Lazy import to avoid circular deps at module load time
        from src.agent.memory.agent_memory import get_agent_memory
        from src.agent.memory.memory_consolidator import MemoryConsolidator

        agent_ids = self._get_all_agent_ids()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            f"[ConsolidationRunner] [{ts}] Consolidating {len(agent_ids)} agent(s): "
            + ", ".join(agent_ids)
        )

        for agent_id in agent_ids:
            try:
                memory = get_agent_memory(agent_id)
                consolidator = MemoryConsolidator(memory)
                consolidator.consolidate()
                logger.info(f"[ConsolidationRunner] ✔ {agent_id}")
            except Exception as exc:
                logger.error(
                    f"[ConsolidationRunner] ✘ {agent_id} — {exc}", exc_info=True
                )

        logger.info(f"[ConsolidationRunner] Cycle complete at {ts}.")


# ── Singleton ──────────────────────────────────────────────────────────────────

_runner_instance: ConsolidationRunner | None = None
_runner_lock = threading.Lock()


def get_consolidation_runner() -> ConsolidationRunner:
    """Return the process-wide singleton ConsolidationRunner."""
    global _runner_instance
    if _runner_instance is None:
        with _runner_lock:
            if _runner_instance is None:
                _runner_instance = ConsolidationRunner()
    return _runner_instance
