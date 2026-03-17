from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional

from src.agent.runtime_paths import get_runtime_state_path

_PENDING_CONFIRMATIONS_PATH = get_runtime_state_path(
    "runtime_state",
    "destructive_action_pending.json",
    create_parent=True,
)

_DESTRUCTIVE_PREFIXES = (
    "delete_",
    "trash_",
    "remove_",
)

_DESTRUCTIVE_EXACT = {
    "empty_trash",
}

_AFFIRMATIVE_PATTERNS = (
    r"^yes[.!?\s]*$",
    r"^yes,? delete(?: them| it| all(?: of them)?)?[.!?\s]*$",
    r"^delete (?:them|it|all(?: of them)?) now[.!?\s]*$",
    r"^go ahead(?: and delete(?: them| it| all(?: of them)?)?)?[.!?\s]*$",
    r"^proceed(?: to delete(?: them| it| all(?: of them)?)?)?[.!?\s]*$",
    r"^do it[.!?\s]*$",
    r"^confirm(?: delete.*)?[.!?\s]*$",
    r"^confirm action(?: [a-f0-9]{16})?[.!?\s]*$",
)

_NEGATIVE_PATTERNS = (
    r"^no[.!?\s]*$",
    r"^cancel(?: it| that| action)?(?: [a-f0-9]{16})?[.!?\s]*$",
    r"^don't delete(?: them| it| anything)?[.!?\s]*$",
    r"^do not delete(?: them| it| anything)?[.!?\s]*$",
    r"^stop[.!?\s]*$",
    r"^never mind[.!?\s]*$",
)


def normalize_confirmation_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def destructive_tool_requires_confirmation(tool_name: str) -> bool:
    normalized = str(tool_name or "").strip().lower()
    if not normalized:
        return False
    return normalized in _DESTRUCTIVE_EXACT or normalized.startswith(_DESTRUCTIVE_PREFIXES)


def build_confirmation_action_key(skill_name: str, tool_name: str, kwargs: Dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "skill": str(skill_name or "").strip().lower(),
            "tool": str(tool_name or "").strip().lower(),
            "kwargs": kwargs or {},
        },
        sort_keys=True,
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def describe_destructive_action(skill_name: str, tool_name: str, kwargs: Dict[str, Any]) -> str:
    human_tool = str(tool_name or "").replace("_", " ").strip()
    details = []
    for key, value in (kwargs or {}).items():
        if value in (None, "", [], {}):
            continue
        if len(details) >= 3:
            break
        rendered = str(value)
        if len(rendered) > 80:
            rendered = rendered[:77] + "..."
        details.append(f"{key}={rendered}")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{skill_name}::{human_tool}{suffix}"


def build_confirmation_reply_markup(action_key: str) -> Dict[str, Any]:
    return {
        "inline_keyboard": [[
            {
                "text": "Yes, confirm",
                "callback_data": f"destructive_action:confirm:{action_key}",
            },
            {
                "text": "No, cancel",
                "callback_data": f"destructive_action:cancel:{action_key}",
            },
        ]]
    }


def build_confirmation_result(skill_name: str, tool_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    action_key = build_confirmation_action_key(skill_name, tool_name, kwargs)
    action_description = describe_destructive_action(skill_name, tool_name, kwargs)
    return {
        "status": "confirmation_required",
        "action": tool_name,
        "message": (
            f"Please confirm this destructive action before I continue: {action_description}. "
            f"Reply with 'confirm action {action_key}' or 'cancel action {action_key}', or use the buttons below."
        ),
        "confirmation": {
            "action_key": action_key,
            "skill_name": skill_name,
            "tool_name": tool_name,
            "kwargs": kwargs,
            "message": action_description,
        },
        "channel_payloads": {
            "telegram": {
                "reply_markup": build_confirmation_reply_markup(action_key),
            }
        },
    }


def maybe_guard_destructive_tool_call(
    skill_name: str,
    tool_name: str,
    kwargs: Dict[str, Any],
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not destructive_tool_requires_confirmation(tool_name):
        return None

    action_key = build_confirmation_action_key(skill_name, tool_name, kwargs)
    confirmed = {
        str(item).strip()
        for item in (artifacts_out or {}).get("_confirmed_action_keys", [])
        if str(item).strip()
    }
    if action_key in confirmed:
        return None
    return build_confirmation_result(skill_name, tool_name, kwargs)


def parse_confirmation_reply(message: str) -> Optional[Dict[str, str]]:
    normalized = normalize_confirmation_text(message)
    explicit_match = re.fullmatch(r"(confirm|cancel) action(?: ([a-f0-9]{16}))?[.!?\s]*", normalized)
    if explicit_match:
        decision = "confirm" if explicit_match.group(1) == "confirm" else "cancel"
        return {
            "decision": decision,
            "action_key": explicit_match.group(2) or "",
        }

    if any(re.fullmatch(pattern, normalized) for pattern in _AFFIRMATIVE_PATTERNS):
        return {"decision": "confirm", "action_key": ""}
    if any(re.fullmatch(pattern, normalized) for pattern in _NEGATIVE_PATTERNS):
        return {"decision": "cancel", "action_key": ""}
    return None


def load_pending_confirmations() -> Dict[str, Dict[str, Any]]:
    try:
        if _PENDING_CONFIRMATIONS_PATH.exists():
            payload = json.loads(_PENDING_CONFIRMATIONS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def save_pending_confirmations(state: Dict[str, Dict[str, Any]]) -> None:
    _PENDING_CONFIRMATIONS_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_pending_confirmation(session_id: str) -> Dict[str, Any]:
    return load_pending_confirmations().get(str(session_id or "").strip(), {})


def set_pending_confirmation(session_id: str, payload: Dict[str, Any]) -> None:
    normalized = str(session_id or "").strip()
    if not normalized:
        return
    state = load_pending_confirmations()
    state[normalized] = payload
    save_pending_confirmations(state)


def clear_pending_confirmation(session_id: str) -> None:
    normalized = str(session_id or "").strip()
    if not normalized:
        return
    state = load_pending_confirmations()
    if normalized in state:
        del state[normalized]
        save_pending_confirmations(state)