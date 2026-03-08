from __future__ import annotations

from contextlib import suppress
import json
import logging
import re
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, Optional

_ROOT = Path(__file__).resolve().parents[3]
_ERRORS_DIR = _ROOT / "errors"
_REGISTRY_PATH = _ERRORS_DIR / "log_error_registry.json"
_LOCK = RLock()

_LOG_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+"
    r"(?P<level>[A-Z]+)\s+\|\s+"
    r"corr=(?P<corr>\S+)\s+req=(?P<req>\S+)\s+\|\s+"
    r"(?P<logger>[^|]+?)\s*\|\s+"
    r"(?P<message>.*)$"
)

_WARNING_PATTERNS = (
    "ratelimitreached",
    "rate limit",
    "returned error",
    "falling back",
)

_CATEGORY_GUIDANCE: Dict[str, Dict[str, Any]] = {
    "provider_rate_limit": {
        "root_cause": "Provider quota or per-day model limit exhausted during routing, planning, synthesis, or memory enrichment.",
        "tool_description_guidance": [
            "Bias skill descriptions toward deterministic local tools and batch tools so fewer LLM calls are needed for common tasks.",
            "Keep high-confidence tool wording explicit for report generation, latest-email retrieval, and file counting so the planner reaches the right local tool in one step.",
        ],
    },
    "email_followup_selection_failure": {
        "root_cause": "Planner or follow-up resolution passed a serialized email object/list where a single message id was required.",
        "tool_description_guidance": [
            "Email list and summary tool descriptions should explicitly mention positional follow-ups like 'summarize the 2nd one' and require using saved listed email ids.",
            "Result-shape docs should consistently call out stable keys such as results, emails, id, and report_content.",
        ],
    },
    "dag_planner_fallback": {
        "root_cause": "The DAG planner failed and dropped to fallback execution, usually because of upstream provider failure or malformed planner output.",
        "tool_description_guidance": [
            "Keep tool signatures and return-key wording short and unambiguous so the planner can reference results, file_path, and report_content reliably.",
        ],
    },
    "tool_execution_error": {
        "root_cause": "A skill tool was called successfully but returned an application-level error for the given arguments.",
        "tool_description_guidance": [
            "Tool descriptions should be specific about required identifiers, supported follow-up patterns, and when to use batch tools instead of single-item tools.",
        ],
    },
    "general_error": {
        "root_cause": "Unhandled or uncategorized runtime error captured from the application log.",
        "tool_description_guidance": [
            "Review related skill descriptions if this error maps to ambiguous tool selection or missing argument expectations.",
        ],
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_registry() -> Dict[str, Any]:
    if not _REGISTRY_PATH.exists():
        return {"schema_version": 1, "updated_at": _utc_now(), "entries": []}
    with suppress(OSError, ValueError, TypeError, json.JSONDecodeError):
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    return {"schema_version": 1, "updated_at": _utc_now(), "entries": []}


def _save_registry(data: Dict[str, Any]) -> None:
    _ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    _REGISTRY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _should_capture(level: str, message: str) -> bool:
    lower = (message or "").lower()
    if level in {"ERROR", "CRITICAL"}:
        return True
    if level == "WARNING":
        return any(pattern in lower for pattern in _WARNING_PATTERNS)
    return False


def _normalize_message(message: str) -> str:
    text = re.sub(r"[A-Za-z]:\\[^\s'\"]+", "<path>", message)
    text = re.sub(r"\b[0-9a-f]{12,}\b", "<hex>", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?\b", "<date>", text)
    text = re.sub(r"wait \d+ seconds", "wait <seconds> seconds", text, flags=re.IGNORECASE)
    text = re.sub(r"corr=\S+", "corr=<corr>", text)
    text = re.sub(r"req=\S+", "req=<req>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]


def _categorize(message: str, logger_name: str) -> str:
    lower = f"{logger_name} {message}".lower()
    if "ratelimitreached" in lower or "rate limit" in lower or "error code: 429" in lower:
        return "provider_rate_limit"
    if "summarize_email" in lower and "returned error" in lower:
        return "email_followup_selection_failure"
    if "dag planner" in lower and "falling back" in lower:
        return "dag_planner_fallback"
    if "returned error" in lower or "tool=" in lower:
        return "tool_execution_error"
    return "general_error"


def _make_fingerprint(category: str, logger_name: str, normalized_message: str) -> str:
    digest = sha1(f"{category}|{logger_name}|{normalized_message}".encode("utf-8")).hexdigest()
    return digest[:16]


def _build_sample(
    *,
    timestamp: str,
    level: str,
    logger_name: str,
    message: str,
    correlation_id: str,
    request_id: str,
    source: str,
) -> Dict[str, str]:
    return {
        "timestamp": timestamp,
        "level": level,
        "logger": logger_name,
        "message": message[:1200],
        "correlation_id": correlation_id,
        "request_id": request_id,
        "source": source,
    }


def record_error_event(
    *,
    timestamp: Optional[str],
    level: str,
    logger_name: str,
    message: str,
    correlation_id: str = "-",
    request_id: str = "-",
    source: str = "runtime",
) -> Optional[str]:
    if not _should_capture(level, message):
        return None

    normalized_message = _normalize_message(message)
    category = _categorize(normalized_message, logger_name)
    fingerprint = _make_fingerprint(category, logger_name, normalized_message)
    guidance = _CATEGORY_GUIDANCE.get(category, _CATEGORY_GUIDANCE["general_error"])
    sample = _build_sample(
        timestamp=timestamp or _utc_now(),
        level=level,
        logger_name=logger_name,
        message=message,
        correlation_id=correlation_id,
        request_id=request_id,
        source=source,
    )

    with _LOCK:
        registry = _load_registry()
        entries = registry.setdefault("entries", [])
        existing = next((entry for entry in entries if entry.get("fingerprint") == fingerprint), None)
        if existing is None:
            entries.append(
                {
                    "fingerprint": fingerprint,
                    "category": category,
                    "logger": logger_name,
                    "normalized_message": normalized_message,
                    "severity": level,
                    "count": 1,
                    "first_seen": sample["timestamp"],
                    "last_seen": sample["timestamp"],
                    "root_cause": guidance["root_cause"],
                    "tool_description_guidance": guidance["tool_description_guidance"],
                    "samples": [sample],
                }
            )
        else:
            existing["count"] = int(existing.get("count", 0)) + 1
            existing["last_seen"] = sample["timestamp"]
            existing["severity"] = level if level == "CRITICAL" else existing.get("severity", level)
            samples = existing.setdefault("samples", [])
            samples.append(sample)
            del samples[:-5]
        entries.sort(key=lambda entry: (entry.get("last_seen", ""), entry.get("count", 0)), reverse=True)
        _save_registry(registry)
    return fingerprint


class JsonErrorRegistryHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        with suppress(OSError, ValueError, TypeError, json.JSONDecodeError):
            record_error_event(
                timestamp=datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                correlation_id=getattr(record, "correlation_id", "-"),
                request_id=getattr(record, "request_id", "-"),
                source="runtime",
            )


def sync_errors_from_log(log_path: str | Path, source: Optional[str] = None) -> int:
    path = Path(log_path)
    if not path.exists():
        return 0

    imported = 0
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = _LOG_LINE_RE.match(raw_line)
        if not match:
            continue
        payload = match.groupdict()
        if record_error_event(
            timestamp=payload["ts"].strip(),
            level=payload["level"].strip(),
            logger_name=payload["logger"].strip(),
            message=payload["message"].strip(),
            correlation_id=payload["corr"].strip(),
            request_id=payload["req"].strip(),
            source=source or str(path),
        ):
            imported += 1
    return imported


def sync_errors_from_logs(log_paths: Iterable[str | Path]) -> int:
    total = 0
    for log_path in log_paths:
        total += sync_errors_from_log(log_path)
    return total


__all__ = [
    "JsonErrorRegistryHandler",
    "record_error_event",
    "sync_errors_from_log",
    "sync_errors_from_logs",
]