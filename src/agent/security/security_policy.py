from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from src.agent.runtime_paths import get_runtime_state_path

_SECURITY_EVENTS_PATH = get_runtime_state_path(
    "runtime_state",
    "security_events.jsonl",
    create_parent=True,
)
_RATE_LIMIT_STATE_PATH = get_runtime_state_path(
    "runtime_state",
    "security_rate_limits.json",
    create_parent=True,
)

_REQUESTS_PER_MINUTE_LIMIT = 20
_REQUESTS_PER_HOUR_LIMIT = 120

_HIGH_CONFIDENCE_PROMPT_INJECTION_RULES: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above)\s+instructions\b", re.IGNORECASE),
        "instruction_override",
    ),
    (
        re.compile(r"\b(?:reveal|show|print|dump|expose)\b.{0,80}\b(?:system prompt|developer instructions?|hidden prompt|internal rules?)\b", re.IGNORECASE | re.DOTALL),
        "prompt_exfiltration",
    ),
    (
        re.compile(r"\b(?:bypass|disable|override)\b.{0,60}\b(?:security|guardrails|filters|policy|confirmation)\b", re.IGNORECASE | re.DOTALL),
        "security_bypass",
    ),
    (
        re.compile(r"^\s*##\s*(?:session state|active context|context from previous turn)\b", re.IGNORECASE | re.MULTILINE),
        "forged_internal_context",
    ),
    (
        re.compile(r"\b(?:send|upload|forward|exfiltrat\w*)\b.{0,120}\b(?:all user files|all files|system prompt|credentials|token|passwords?)\b", re.IGNORECASE | re.DOTALL),
        "mass_exfiltration",
    ),
)

_LOW_CONFIDENCE_META_RULES: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:system prompt|developer instructions?|prompt injection|jailbreak)\b", re.IGNORECASE),
        "meta_prompt_reference",
    ),
)

_REDACTION_RULES: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:sk|ghp|github_pat|AIza|ya29)[:=_\-A-Za-z0-9]{8,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
    ),
    (
        re.compile(r"\b(password|passwd|pwd|secret|token|api[_\s-]?key)\b\s*[:=]\s*\S+", re.IGNORECASE),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "[REDACTED_CARD]",
    ),
    (
        re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"),
        r"\1***@\2",
    ),
)


@dataclass
class SecurityDecision:
    decision: str
    user_message: str = ""
    reason: str = ""
    severity: str = "info"
    matched_rules: List[str] = field(default_factory=list)
    rate_limit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def redact_sensitive_text(text: str) -> str:
    redacted = str(text or "")
    for pattern, replacement in _REDACTION_RULES:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _load_rate_limit_state() -> Dict[str, Dict[str, List[float]]]:
    try:
        if _RATE_LIMIT_STATE_PATH.exists():
            payload = json.loads(_RATE_LIMIT_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def _save_rate_limit_state(state: Dict[str, Dict[str, List[float]]]) -> None:
    _RATE_LIMIT_STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _prune_timestamps(timestamps: List[float], window_seconds: int, now_ts: float) -> List[float]:
    cutoff = now_ts - float(window_seconds)
    return [float(item) for item in timestamps if float(item) >= cutoff]


def consume_rate_limit(session_id: str, source: str, now_ts: float | None = None) -> Tuple[bool, Dict[str, Any]]:
    current = float(now_ts if now_ts is not None else time.time())
    state = _load_rate_limit_state()
    scope_key = f"{str(source or '').strip()}::{str(session_id or '').strip()}"
    session_state = state.setdefault(scope_key, {"minute": [], "hour": []})

    minute_hits = _prune_timestamps(list(session_state.get("minute", [])), 60, current)
    hour_hits = _prune_timestamps(list(session_state.get("hour", [])), 3600, current)

    if len(minute_hits) >= _REQUESTS_PER_MINUTE_LIMIT or len(hour_hits) >= _REQUESTS_PER_HOUR_LIMIT:
        session_state["minute"] = minute_hits
        session_state["hour"] = hour_hits
        state[scope_key] = session_state
        _save_rate_limit_state(state)
        return False, {
            "scope_key": scope_key,
            "per_minute_limit": _REQUESTS_PER_MINUTE_LIMIT,
            "per_hour_limit": _REQUESTS_PER_HOUR_LIMIT,
            "minute_count": len(minute_hits),
            "hour_count": len(hour_hits),
        }

    minute_hits.append(current)
    hour_hits.append(current)
    session_state["minute"] = minute_hits
    session_state["hour"] = hour_hits
    state[scope_key] = session_state
    _save_rate_limit_state(state)
    return True, {
        "scope_key": scope_key,
        "per_minute_limit": _REQUESTS_PER_MINUTE_LIMIT,
        "per_hour_limit": _REQUESTS_PER_HOUR_LIMIT,
        "minute_count": len(minute_hits),
        "hour_count": len(hour_hits),
    }


def _match_rules(message: str) -> Tuple[List[str], List[str]]:
    blocked = [
        rule_name
        for pattern, rule_name in _HIGH_CONFIDENCE_PROMPT_INJECTION_RULES
        if pattern.search(message)
    ]
    review = [
        rule_name
        for pattern, rule_name in _LOW_CONFIDENCE_META_RULES
        if pattern.search(message)
    ]
    return blocked, review


def append_security_audit_event(
    *,
    event_type: str,
    decision: str,
    session_id: str,
    source: str,
    agent_id: str,
    message: str,
    metadata: Dict[str, Any] | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "decision": decision,
        "session_id": str(session_id or ""),
        "source": str(source or ""),
        "agent_id": str(agent_id or ""),
        "message_excerpt": redact_sensitive_text(str(message or "")[:400]),
        "metadata": metadata or {},
    }
    with _SECURITY_EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def evaluate_inbound_request(
    *,
    message: str,
    session_id: str,
    source: str,
    agent_id: str,
    is_confirmation_reply: bool = False,
) -> SecurityDecision:
    normalized_message = str(message or "")

    allowed, rate_limit = consume_rate_limit(session_id=session_id, source=source)
    if not allowed:
        decision = SecurityDecision(
            decision="rate_limited",
            user_message=(
                "Too many requests arrived in a short time. Please wait a moment and try again. "
                "This protection is in place to prevent abuse and accidental automation loops."
            ),
            reason="session_rate_limit_exceeded",
            severity="high",
            rate_limit=rate_limit,
        )
        append_security_audit_event(
            event_type="rate_limit_exceeded",
            decision=decision.decision,
            session_id=session_id,
            source=source,
            agent_id=agent_id,
            message=normalized_message,
            metadata=decision.to_dict(),
        )
        return decision

    if is_confirmation_reply:
        return SecurityDecision(decision="allow", rate_limit=rate_limit)

    blocked_rules, review_rules = _match_rules(normalized_message)
    if blocked_rules:
        decision = SecurityDecision(
            decision="blocked",
            user_message=(
                "I can't follow instructions that try to override system rules, expose hidden prompts, "
                "or inject forged internal context. Rephrase the request as the business task you want completed."
            ),
            reason="prompt_injection_detected",
            severity="high",
            matched_rules=blocked_rules,
            rate_limit=rate_limit,
        )
        append_security_audit_event(
            event_type="prompt_injection_blocked",
            decision=decision.decision,
            session_id=session_id,
            source=source,
            agent_id=agent_id,
            message=normalized_message,
            metadata=decision.to_dict(),
        )
        return decision

    if review_rules:
        append_security_audit_event(
            event_type="prompt_injection_suspected",
            decision="allow",
            session_id=session_id,
            source=source,
            agent_id=agent_id,
            message=normalized_message,
            metadata={
                "matched_rules": review_rules,
                "rate_limit": rate_limit,
            },
        )

    return SecurityDecision(
        decision="allow",
        matched_rules=review_rules,
        rate_limit=rate_limit,
    )