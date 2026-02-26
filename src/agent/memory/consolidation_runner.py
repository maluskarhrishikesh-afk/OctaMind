"""
Global Consolidation Runner

Runs memory consolidation for all Personal Assistants (including __multi_agent__)
in a smart background thread.

Skills (gmail, google_drive, files, whatsapp, telegram, calendar) are stateless
executors and never accumulate memory, so they are intentionally excluded.

Lifecycle:
  - Starts automatically when the Octa Bot application boots.
  - Performs an immediate first-pass consolidation on startup.
  - Then checks every 30 minutes — only consolidates if new interactions have
    arrived since the last run (avoids pointless LLM calls on idle systems).
  - Also picks up new messages from Live Channels (hub_conversations.json).
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

logger = logging.getLogger("Octa Bot.consolidation_runner")

# ── Tuning ────────────────────────────────────────────────────────────────────
_CHECK_INTERVAL_SECONDS = 30 * 60   # poll every 30 minutes
_TICK_SECONDS = 5                   # granularity for stop responsiveness

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_ASSISTANTS_JSON = _PROJECT_ROOT / "data" / "assistants.json"   # Personal Assistants only
_HUB_CONV_JSON   = _PROJECT_ROOT / "data" / "hub_conversations.json"  # Live Channels
_MEMORY_ROOT     = _PROJECT_ROOT / "memory"
_MULTI_AGENT_ID  = "__multi_agent__"


class ConsolidationRunner:
    """
    Background thread that consolidates memory for every Personal Assistant.

    Runs on startup + every 30 minutes, skipping agents whose working_memory.md
    has NOT been modified since the previous consolidation cycle.
    Also records Live Channel conversations into each PA's episodic memory so
    interactions via Telegram, WhatsApp, API etc. are captured alongside
    direct chat sessions.
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
        """Main loop: run immediately, then repeat every 30 minutes."""
        logger.info("[ConsolidationRunner] Initial consolidation pass starting…")
        self._ingest_live_channels()
        self._run_cycle()

        elapsed = 0
        while not self._stop_event.is_set():
            time.sleep(_TICK_SECONDS)
            elapsed += _TICK_SECONDS
            if elapsed >= _CHECK_INTERVAL_SECONDS:
                elapsed = 0
                logger.info("[ConsolidationRunner] 30-minute check triggered.")
                self._ingest_live_channels()
                self._run_cycle()

        logger.info("[ConsolidationRunner] Thread exiting.")

    # ── Live Channels ingestion ────────────────────────────────────────────────

    def _ingest_live_channels(self) -> None:
        """
        Pull new messages from hub_conversations.json into each PA's episodic
        memory so Live Channel conversations are consolidated alongside PA chat.

        We track which sessions we've already ingested via a small state file
        in each PA's memory folder.
        """
        if not _HUB_CONV_JSON.exists():
            return
        try:
            data = json.loads(_HUB_CONV_JSON.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[ConsolidationRunner] Could not read hub_conversations.json: %s", exc)
            return

        sessions = data.get("sessions", {})
        if not sessions:
            return

        agent_ids = self._get_all_agent_ids()
        for agent_id in agent_ids:
            state_file = _MEMORY_ROOT / agent_id / "_channel_ingest_state.json"
            ingested: dict[str, str] = {}
            if state_file.exists():
                try:
                    ingested = json.loads(state_file.read_text(encoding="utf-8"))
                except Exception:
                    ingested = {}

            new_entries = 0
            try:
                from src.agent.memory.agent_memory import get_agent_memory
                mem = get_agent_memory(agent_id)
                for session_id, sess in sessions.items():
                    last_known = ingested.get(session_id, "")
                    last_updated = sess.get("last_updated", "")
                    if last_updated <= last_known:
                        continue   # nothing new in this session

                    # Add a compact episodic entry summarising this channel session
                    source  = sess.get("source", "unknown")
                    msgs    = sess.get("messages", [])
                    if not msgs:
                        continue
                    # Build a short human-readable transcript (last 6 messages)
                    snippet = "\n".join(
                        f"  [{m.get('role','?')}] {str(m.get('content',''))[:120]}"
                        for m in msgs[-6:]
                    )
                    mem.add_interaction(
                        command=f"[Live Channel:{source}] session={session_id}",
                        action="channel_conversation",
                        result={"status": "recorded", "source": source, "transcript": snippet},
                        importance="Low",
                    )
                    ingested[session_id] = last_updated
                    new_entries += 1

                if new_entries:
                    state_file.parent.mkdir(parents=True, exist_ok=True)
                    state_file.write_text(json.dumps(ingested, indent=2), encoding="utf-8")
                    logger.info(
                        "[ConsolidationRunner] Ingested %d new channel session(s) for %s.",
                        new_entries, agent_id,
                    )
            except Exception as exc:
                logger.debug("[ConsolidationRunner] Channel ingest skipped for %s: %s", agent_id, exc)

    # ── Dirty-check helpers ────────────────────────────────────────────────────

    def _has_new_interactions(self, agent_id: str) -> bool:
        """
        Return True only when *working_memory.md* has been modified after the
        last consolidation timestamp stored in *consolidation_state.json*.

        This prevents the consolidator from doing LLM work on perfectly quiet
        agents and keeps resource usage proportional to actual activity.
        """
        memory_dir = _MEMORY_ROOT / agent_id
        working_md = memory_dir / "working_memory.md"
        state_file = memory_dir / "consolidation_state.json"

        if not working_md.exists():
            return False   # agent has no memory yet

        # If we've never consolidated this agent, always run once.
        if not state_file.exists():
            return True

        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            last_str = state.get("last_consolidation")
            if not last_str:
                return True

            last_consolidation_ts = datetime.fromisoformat(last_str).timestamp()
            wm_mtime = working_md.stat().st_mtime
            return wm_mtime > last_consolidation_ts
        except Exception:
            return True   # conservative: consolidate if state is unreadable

    # ── Agent list ────────────────────────────────────────────────────────────

    def _get_all_agent_ids(self) -> list[str]:
        """Return all Personal Assistant IDs.

        Skills (gmail, google_drive, files, whatsapp, telegram, calendar) are
        stateless executors and are intentionally excluded from consolidation.
        """
        ids: list[str] = [_MULTI_AGENT_ID]
        try:
            if _ASSISTANTS_JSON.exists():
                data = json.loads(_ASSISTANTS_JSON.read_text(encoding="utf-8"))
                # Support both bare-list format (current) and {"assistants": [...]} (wrapped)
                pa_list: list = data if isinstance(data, list) else data.get("assistants", [])
                for pa in pa_list:
                    if isinstance(pa, dict):
                        aid = pa.get("id", "")
                        if aid and aid != _MULTI_AGENT_ID:
                            ids.append(aid)
        except Exception as exc:
            logger.error("[ConsolidationRunner] Could not read assistants.json: %s", exc)
        return ids

    def _run_cycle(self) -> None:
        """Run one full consolidation cycle across all agents (dirty-check gated)."""
        from src.agent.memory.agent_memory import get_agent_memory
        from src.agent.memory.memory_consolidator import MemoryConsolidator

        agent_ids = self._get_all_agent_ids()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        candidates = [aid for aid in agent_ids if self._has_new_interactions(aid)]

        if not candidates:
            logger.debug("[ConsolidationRunner] [%s] No new interactions — skipping cycle.", ts)
            return

        logger.info(
            "[ConsolidationRunner] [%s] Consolidating %d agent(s): %s",
            ts, len(candidates), ", ".join(candidates),
        )
        for agent_id in candidates:
            try:
                memory = get_agent_memory(agent_id)
                consolidator = MemoryConsolidator(memory)
                consolidator.consolidate()
                logger.info("[ConsolidationRunner] ✔ %s", agent_id)
            except Exception as exc:
                logger.error(
                    "[ConsolidationRunner] ✘ %s — %s", agent_id, exc, exc_info=True
                )

        logger.info("[ConsolidationRunner] Cycle complete at %s.", ts)


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
