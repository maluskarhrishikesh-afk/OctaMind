"""
WorkflowContext — shared state bag for a multi-agent workflow run.

Each workflow run gets its own context. Steps read from and write to it
so that results from step N can be used as inputs to step N+1.
Temp files registered here are cleaned up automatically after the workflow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("workflows")


@dataclass
class WorkflowStep:
    """A single planned action within a workflow (legacy: tool+params style)."""
    step_num: int
    agent: str          # "drive" or "email"
    tool: str           # exact tool function name e.g. "search_files"
    params: Dict[str, Any]
    output_key: str     # key used to store the result in WorkflowContext
    description: str    # human-readable label shown in the UI


@dataclass
class WorkflowPlan:
    """Full execution plan produced by the master orchestrator (legacy)."""
    command: str
    agents_needed: List[str]
    steps: List[WorkflowStep]
    created_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# New natural-language step types (used by NL orchestrator)
# ---------------------------------------------------------------------------

@dataclass
class NLWorkflowStep:
    """
    A natural-language instruction for a single agent.

    The orchestrator knows *which* agent to call and *what* to ask it —
    but not *which tools* the agent uses internally.  The agent runs its
    own ReAct loop with its own full tool list.

    ``instruction`` may contain ``{output_key}`` or ``{output_key.field}``
    tokens that are resolved from WorkflowContext before the agent is called.
    """
    step_num: int
    agent: str          # registry key, e.g. "drive", "email"
    instruction: str    # natural language task for this agent
    output_key: str     # key to store the agent's result under in WorkflowContext
    description: str    # human-readable label for UI display


@dataclass
class NLWorkflowPlan:
    """Full execution plan produced by the NL orchestrator."""
    command: str
    agents_needed: List[str]
    steps: List[NLWorkflowStep]
    created_at: datetime = field(default_factory=datetime.now)


class WorkflowContext:
    """
    Holds all intermediate results and temp files for one workflow run.

    Usage:
        ctx = WorkflowContext(command="download budget and email it")
        ctx.set("file_id", "abc123")
        fid = ctx.get("file_id")   # → "abc123"
        ctx.cleanup()              # delete temp files
    """

    def __init__(self, command: str = "") -> None:
        self.command = command
        self.started_at = datetime.now()
        self._results: Dict[str, Any] = {}
        self._temp_files: List[Path] = []

    # ── Result store ──────────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Store a value produced by a step."""
        logger.debug("WorkflowContext.set(%s)", key)
        self._results[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value stored by a previous step."""
        return self._results.get(key, default)

    def all_results(self) -> Dict[str, Any]:
        return dict(self._results)

    # ── Temp-file tracking ────────────────────────────────────────────────────

    def register_temp_file(self, path: str | Path) -> None:
        """Mark a file for deletion when cleanup() is called."""
        self._temp_files.append(Path(path))

    def cleanup(self) -> None:
        """Delete all registered temp files. Safe to call multiple times."""
        for f in self._temp_files:
            try:
                if f.exists():
                    f.unlink()
                    logger.debug("Deleted temp file: %s", f)
                # Also remove parent dir if it's an Octa Bot temp dir and now empty
                if f.parent.name.startswith("Octa Bot_wf_") and not any(f.parent.iterdir()):
                    f.parent.rmdir()
            except Exception as exc:
                logger.warning("Could not delete temp file %s: %s", f, exc)
        self._temp_files.clear()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def elapsed_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"WorkflowContext(command={self.command!r}, "
            f"keys={list(self._results.keys())}, "
            f"temp_files={len(self._temp_files)})"
        )
