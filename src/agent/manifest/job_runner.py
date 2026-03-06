"""
Job Runner — Background thread pool for OctaMind async tasks.

Executes long-running jobs (heavy file scans, full-disk searches) in
background daemon threads so the chat is never blocked.  On completion,
notifies the user via their original channel (Telegram / Dashboard).

Usage:
    from src.agent.manifest.job_runner import submit_job

    def do_scan() -> str:
        # ... heavy work ...
        return "Found 247 PDF files across all drives."

    submit_job(job_id, do_scan, session_id="telegram_12345", pa_id="pa_7ea1659c")

The callable must return a human-readable result summary string.
The result is written to the job manifest AND sent back to the user.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger("job_runner")

# Limit concurrent background jobs to avoid overwhelming the disk
_MAX_CONCURRENT = 4
_semaphore = threading.Semaphore(_MAX_CONCURRENT)


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------

def _notify_user(session_id: str, pa_id: str, message: str) -> None:
    """
    Send a completion notification back to the user.

    Routing logic:
    - session_id == "telegram_{chat_id}" → send via telegram_service.send_text()
    - session_id == "dashboard_{pa_id}"  → write to pending notifications file
                                            for PA dashboard to pick up on next poll
    - Other / empty                       → result is in job manifest; no push needed
    """
    if not session_id:
        logger.info("[JobRunner] No session_id — result written to job manifest only")
        return

    if session_id.startswith("telegram_"):
        chat_id_str = session_id[len("telegram_"):]
        try:
            chat_id: int | str = int(chat_id_str)
        except ValueError:
            chat_id = chat_id_str
        try:
            from src.telegram.telegram_service import send_text  # noqa: PLC0415
            send_text(chat_id, message)
            logger.info("[JobRunner] Notified telegram chat %s", chat_id)
        except Exception as exc:
            logger.warning("[JobRunner] Telegram notification failed for chat %s: %s", chat_id, exc)
        return

    if session_id.startswith("dashboard_"):
        _write_dashboard_notification(session_id, message)
        return

    # API / unknown — job manifest has the result; polling will get it
    logger.info("[JobRunner] Session '%s' — result written to job manifest", session_id)


def _write_dashboard_notification(session_id: str, message: str) -> None:
    """
    Append a completion notification to data/octa_job_notifications.json
    so the PA dashboard can show it on next auto-refresh.
    """
    import json as _json
    from pathlib import Path as _Path
    from datetime import datetime as _dt, timezone as _tz

    notify_file = _Path(__file__).resolve().parents[3] / "data" / "octa_job_notifications.json"
    try:
        existing: list = []
        if notify_file.exists():
            try:
                existing = _json.loads(notify_file.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append({
            "session_id": session_id,
            "message": message,
            "ts": _dt.now(_tz.utc).isoformat(),
            "read": False,
        })
        # Keep only last 50 notifications
        existing = existing[-50:]
        notify_file.parent.mkdir(parents=True, exist_ok=True)
        notify_file.write_text(
            _json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("[JobRunner] Dashboard notification written for session %s", session_id)
    except Exception as exc:
        logger.warning("[JobRunner] Dashboard notification write failed: %s", exc)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

def _run_job(
    job_id: str,
    fn: Callable[[], str],
    session_id: str,
    pa_id: str,
) -> None:
    """Execute a job in a background thread, update manifest, notify user."""
    from src.agent.manifest.job_manifest import (  # noqa: PLC0415
        update_job, complete_job, fail_job,
    )

    with _semaphore:
        try:
            update_job(job_id, status="running", progress_pct=5, progress_detail="Starting…")
            logger.info("[JobRunner] Job %s started in thread %s", job_id, threading.current_thread().name)

            result_summary = fn()

            complete_job(job_id, result_summary=result_summary)
            logger.info("[JobRunner] Job %s completed: %.120s", job_id, result_summary)

            notify_msg = f"✅ *Background task complete!*\n\n{result_summary}"
            _notify_user(session_id, pa_id, notify_msg)

        except Exception as exc:
            fail_job(job_id, error=str(exc))
            logger.exception("[JobRunner] Job %s failed: %s", job_id, exc)
            try:
                _notify_user(session_id, pa_id, f"❌ *Background task failed:* {exc}")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_job(
    job_id: str,
    fn: Callable[[], str],
    session_id: str = "",
    pa_id: str = "",
) -> None:
    """
    Submit a callable to run in a background daemon thread.

    The callable ``fn()`` should perform the heavy work and return a
    human-readable result summary string (e.g. "Found 247 PDF files.").

    When ``fn()`` returns:
    1. The result is written to the job manifest (octa_jobs.json).
    2. The user is notified via their original channel.

    Args:
        job_id:     Job ID from job_manifest.create_job().
        fn:         Callable() → str  — work to execute + result summary.
        session_id: Session ID for notification routing ("telegram_12345").
        pa_id:      Personal Assistant ID ("pa_7ea1659c").
    """
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, fn, session_id, pa_id),
        daemon=True,
        name=f"job-{job_id}",
    )
    thread.start()
    logger.info("[JobRunner] Submitted job %s → thread %s (session=%s)", job_id, thread.name, session_id)
