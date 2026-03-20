from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from src.agent.runtime_paths import get_runtime_state_path


_MAILBOX_LEARNING_PATH = get_runtime_state_path(
    "runtime_state",
    "email_mailbox_learning.json",
    create_parent=True,
)

_TRACKED_FIELDS = (
    "operation_mode",
    "promotions_action",
    "newsletters_action",
    "task_extraction",
    "draft_replies",
    "review_schedule",
)


def get_mailbox_learning_path():
    return _MAILBOX_LEARNING_PATH


def load_mailbox_learning_log() -> Dict[str, Any]:
    path = get_mailbox_learning_path()
    if not path.exists():
        return {"events": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"events": []}
    if not isinstance(payload, dict):
        return {"events": []}
    events = payload.get("events", [])
    return {"events": [item for item in events if isinstance(item, dict)]}


def save_mailbox_learning_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "events": [item for item in payload.get("events", []) if isinstance(item, dict)]
        if isinstance(payload, dict)
        else []
    }
    normalized["events"] = normalized["events"][-100:]
    path = get_mailbox_learning_path()
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def record_mailbox_learning_event(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = load_mailbox_learning_log()
    entry = dict(event or {})
    entry.setdefault("recorded_at", datetime.now().isoformat(timespec="seconds"))
    payload.setdefault("events", []).append(entry)
    save_mailbox_learning_log(payload)
    return entry


def record_mailbox_preference_learning(
    previous_preferences: Dict[str, Any],
    updated_preferences: Dict[str, Any],
    *,
    source: str,
) -> List[Dict[str, Any]]:
    previous = previous_preferences if isinstance(previous_preferences, dict) else {}
    updated = updated_preferences if isinstance(updated_preferences, dict) else {}
    payload = load_mailbox_learning_log()
    history = payload.get("events", []) if isinstance(payload.get("events", []), list) else []

    recorded: List[Dict[str, Any]] = []
    for field in _TRACKED_FIELDS:
        old_value = previous.get(field)
        new_value = updated.get(field)
        if old_value == new_value:
            continue
        prior_change = next(
            (
                item
                for item in reversed(history)
                if str(item.get("kind", "") or "") == "preference_change"
                and str(item.get("field", "") or "") == field
            ),
            None,
        )
        is_reversal = bool(
            prior_change
            and prior_change.get("from") == new_value
            and prior_change.get("to") == old_value
        )
        recorded.append(
            record_mailbox_learning_event(
                {
                    "kind": "preference_change",
                    "field": field,
                    "from": old_value,
                    "to": new_value,
                    "source": source,
                    "reversal": is_reversal,
                }
            )
        )
    return recorded


def summarize_mailbox_learning() -> Dict[str, Any]:
    payload = load_mailbox_learning_log()
    events = payload.get("events", []) if isinstance(payload.get("events", []), list) else []
    summary: Dict[str, Any] = {
        "event_count": len(events),
        "reversal_counts": {},
        "latest_preferences": {},
        "events": events,
    }
    for event in events:
        field = str(event.get("field", "") or "").strip()
        if field and str(event.get("kind", "") or "") == "preference_change":
            summary["latest_preferences"][field] = event.get("to")
        if field and bool(event.get("reversal")):
            summary["reversal_counts"][field] = int(summary["reversal_counts"].get(field, 0) or 0) + 1
    return summary


def detect_mailbox_learning_signals() -> List[str]:
    summary = summarize_mailbox_learning()
    reversals = summary.get("reversal_counts", {}) if isinstance(summary.get("reversal_counts"), dict) else {}
    signals: List[str] = []
    if int(reversals.get("newsletters_action", 0) or 0) >= 2:
        signals.append(
            "You have reversed newsletter handling more than once. I should be more conservative when recommending newsletter cleanup."
        )
    if int(reversals.get("promotions_action", 0) or 0) >= 2:
        signals.append(
            "You have changed promotion handling repeatedly. I should ask before tightening promotion cleanup again."
        )
    if int(reversals.get("draft_replies", 0) or 0) >= 2:
        signals.append(
            "You have changed draft-reply preferences multiple times. I should keep reply suggestions explicit rather than assumed."
        )
    return signals