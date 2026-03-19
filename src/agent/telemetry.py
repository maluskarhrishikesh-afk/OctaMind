from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger("agent.telemetry")


def _stringify(value: Any) -> str:
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(str(item) for item in value)
    return str(value)


def log_counter(event: str, **fields: Any) -> None:
    payload = " ".join(
        f"{key}={_stringify(value)}"
        for key, value in sorted(fields.items())
        if value not in (None, "", [], (), set(), frozenset())
    )
    suffix = f" {payload}" if payload else ""
    logger.info("[counter] event=%s count=1%s", event, suffix)


def log_fast_path_hit(agent: str, fast_path: str) -> None:
    log_counter("fast_path_hit", agent=agent, fast_path=fast_path)


def log_context_saved(agent: str, topic: str, awaiting: str = "") -> None:
    log_counter("context_saved", agent=agent, topic=topic, awaiting=awaiting)


def log_context_followup_resolved(source: str, agents: Iterable[str]) -> None:
    log_counter("context_followup_resolved", source=source, agents=list(agents))


def log_fallback_to_react(skill: str, phase: str) -> None:
    log_counter("fell_back_to_react", skill=skill, phase=phase)