"""
Job Manifest — Phase 3 of the OctaMind Manifest Architecture.

Stores long-running background tasks (full-disk file scans, large searches,
heavy report generation) so the user can be notified when they complete
without blocking the chat.

File: <workspace>/data/octa_jobs.json
Schema version: 1

Public API:
    create_job(agent, description, session_id, pa_id, params) → job_id
    update_job(job_id, *, status, progress_pct, progress_detail, result_summary, result_manifest) → bool
    complete_job(job_id, result_summary, result_manifest) → bool
    fail_job(job_id, error) → bool
    get_job(job_id) → dict | None
    get_recent_jobs(limit) → list[dict]
    get_jobs_for_session(session_id, limit) → list[dict]
"""
from __future__ import annotations

import json
import logging
import random
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("job_manifest")

_MANIFEST_DIR = Path(__file__).resolve().parents[3] / "data"
_JOBS_FILE = _MANIFEST_DIR / "octa_jobs.json"
_MAX_JOBS = 200  # keep only last N jobs to prevent unbounded growth


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _new_job_id() -> str:
    """Generate a short unique job ID like job_a3f2b1."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"job_{suffix}"


def _load() -> Dict[str, Any]:
    """Load the jobs file; return empty structure if missing or corrupt."""
    if not _JOBS_FILE.exists():
        return {"schema_version": 1, "jobs": []}
    try:
        data = json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data.get("jobs"), list):
            data["jobs"] = []
        return data
    except Exception:
        return {"schema_version": 1, "jobs": []}


def _save(data: Dict[str, Any]) -> None:
    """Persist jobs to disk (write to temp file then rename for atomicity)."""
    _MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    # Prune oldest jobs beyond the limit (newest at index 0)
    jobs = data.get("jobs", [])
    if len(jobs) > _MAX_JOBS:
        data["jobs"] = jobs[:_MAX_JOBS]
    tmp = _JOBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_JOBS_FILE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_job(
    agent: str,
    description: str,
    session_id: str = "",
    pa_id: str = "",
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a new background job record and return its job_id.

    Args:
        agent:       Name of the agent that owns this job (e.g. "files").
        description: Human-readable description of the task.
        session_id:  Hub session ID used to route the completion notification
                     back to the correct user (e.g. "telegram_12345").
        pa_id:       Personal Assistant ID (e.g. "pa_7ea1659c").
        params:      Optional dict of additional parameters for the job.

    Returns:
        job_id string (e.g. "job_a3f2b1").
    """
    data = _load()
    job_id = _new_job_id()
    now = _now_iso()
    job: Dict[str, Any] = {
        "job_id":          job_id,
        "created_at":      now,
        "updated_at":      now,
        "agent":           agent,
        "description":     description,
        "status":          "pending",      # pending | running | completed | failed | cancelled
        "progress_pct":    0,
        "progress_detail": "Queued",
        "result_summary":  None,
        "result_manifest": None,           # path to octa_manifest.txt if applicable
        "session_id":      session_id,
        "pa_id":           pa_id,
        "params":          params or {},
    }
    # Insert newest-first
    data["jobs"].insert(0, job)
    _save(data)
    logger.info("[JobManifest] Created job %s: %s (session=%s)", job_id, description[:80], session_id)
    return job_id


def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress_pct: Optional[int] = None,
    progress_detail: Optional[str] = None,
    result_summary: Optional[str] = None,
    result_manifest: Optional[str] = None,
) -> bool:
    """
    Update one or more fields on an existing job.

    Returns True if the job was found and updated, False otherwise.
    """
    data = _load()
    for job in data["jobs"]:
        if job["job_id"] == job_id:
            job["updated_at"] = _now_iso()
            if status is not None:
                job["status"] = status
            if progress_pct is not None:
                job["progress_pct"] = int(max(0, min(100, progress_pct)))
            if progress_detail is not None:
                job["progress_detail"] = progress_detail
            if result_summary is not None:
                job["result_summary"] = result_summary
            if result_manifest is not None:
                job["result_manifest"] = result_manifest
            _save(data)
            return True
    logger.warning("[JobManifest] update_job: job '%s' not found", job_id)
    return False


def complete_job(
    job_id: str,
    result_summary: str,
    result_manifest: Optional[str] = None,
) -> bool:
    """
    Mark a job as completed with a human-readable result summary.

    Args:
        job_id:          The job to complete.
        result_summary:  Human-readable description of what was found/done.
        result_manifest: Optional path to octa_manifest.txt with found paths.
    """
    return update_job(
        job_id,
        status="completed",
        progress_pct=100,
        progress_detail="Done",
        result_summary=result_summary,
        result_manifest=result_manifest,
    )


def fail_job(job_id: str, error: str) -> bool:
    """Mark a job as failed with an error message."""
    return update_job(
        job_id,
        status="failed",
        progress_detail=f"Error: {error[:200]}",
        result_summary=f"Failed: {error[:200]}",
    )


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return a job record by ID, or None if not found."""
    for job in _load()["jobs"]:
        if job["job_id"] == job_id:
            return job
    return None


def get_recent_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    """Return the most recent N jobs, newest first."""
    return _load()["jobs"][:limit]


def get_jobs_for_session(session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Return recent jobs for a specific session ID, newest first."""
    return [
        j for j in _load()["jobs"]
        if j.get("session_id") == session_id
    ][:limit]
