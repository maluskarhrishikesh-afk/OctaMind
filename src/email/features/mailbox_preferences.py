from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from src.agent.runtime_paths import get_runtime_state_path, get_your_data_dir


_MAILBOX_PREFERENCES_PATH = get_your_data_dir("mailbox_preferences.md")
_MAILBOX_REVIEW_HISTORY_PATH = get_runtime_state_path(
    "runtime_state",
    "email_mailbox_review_history.json",
    create_parent=True,
)
_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

DEFAULT_MAILBOX_PREFERENCES: Dict[str, Any] = {
    "version": 1,
    "operation_mode": "confirm_before_action",
    "promotions_action": "archive",
    "newsletters_action": "summarize_then_archive",
    "task_extraction": True,
    "draft_replies": "suggest",
    "review_schedule": "manual",
    "continuous_cleanup": {
        "enabled": False,
        "interval_minutes": 30,
    },
    "label_rules": [],
    "proactive_offers": {
        "enabled": True,
        "inbox_overload_threshold": 75,
        "newsletter_cleanup_repeat_threshold": 2,
        "manual_triage_repeat_threshold": 3,
    },
}

_OPERATION_MODE_LABELS = {
    "suggest_only": "Suggest only",
    "confirm_before_action": "Confirm before action",
    "safe_autopilot": "Safe autopilot",
}
_PROMOTIONS_ACTION_LABELS = {
    "keep": "Keep in inbox",
    "archive": "Archive promotions",
}
_NEWSLETTERS_ACTION_LABELS = {
    "keep": "Keep in inbox",
    "archive": "Archive newsletters",
    "summarize_then_archive": "Summarize then archive",
}
_DRAFT_REPLY_LABELS = {
    "off": "Off",
    "on_request": "Only when asked",
    "suggest": "Suggest drafts",
}
_REVIEW_SCHEDULE_LABELS = {
    "manual": "Only when asked",
    "daily": "Daily review",
    "weekly": "Weekly review",
}


def get_mailbox_preferences_path() -> Path:
    return _MAILBOX_PREFERENCES_PATH


def default_mailbox_preferences() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULT_MAILBOX_PREFERENCES)


def _normalize_mailbox_preferences(raw_preferences: Dict[str, Any] | None) -> Dict[str, Any]:
    preferences = default_mailbox_preferences()
    if not isinstance(raw_preferences, dict):
        return preferences

    preferences.update(raw_preferences)

    if preferences.get("operation_mode") not in _OPERATION_MODE_LABELS:
        preferences["operation_mode"] = DEFAULT_MAILBOX_PREFERENCES["operation_mode"]
    if preferences.get("promotions_action") not in _PROMOTIONS_ACTION_LABELS:
        preferences["promotions_action"] = DEFAULT_MAILBOX_PREFERENCES["promotions_action"]
    if preferences.get("newsletters_action") not in _NEWSLETTERS_ACTION_LABELS:
        preferences["newsletters_action"] = DEFAULT_MAILBOX_PREFERENCES["newsletters_action"]
    if preferences.get("draft_replies") not in _DRAFT_REPLY_LABELS:
        preferences["draft_replies"] = DEFAULT_MAILBOX_PREFERENCES["draft_replies"]
    if preferences.get("review_schedule") not in _REVIEW_SCHEDULE_LABELS:
        preferences["review_schedule"] = DEFAULT_MAILBOX_PREFERENCES["review_schedule"]

    preferences["task_extraction"] = bool(preferences.get("task_extraction", DEFAULT_MAILBOX_PREFERENCES["task_extraction"]))
    raw_cleanup = preferences.get("continuous_cleanup", {})
    cleanup_defaults = copy.deepcopy(DEFAULT_MAILBOX_PREFERENCES["continuous_cleanup"])
    if isinstance(raw_cleanup, dict):
        cleanup_defaults.update(raw_cleanup)
    cleanup_defaults["enabled"] = bool(cleanup_defaults.get("enabled", False))
    try:
        cleanup_defaults["interval_minutes"] = max(int(cleanup_defaults.get("interval_minutes", 30) or 30), 5)
    except Exception:
        cleanup_defaults["interval_minutes"] = int(DEFAULT_MAILBOX_PREFERENCES["continuous_cleanup"]["interval_minutes"])
    preferences["continuous_cleanup"] = cleanup_defaults

    raw_rules = preferences.get("label_rules", [])
    rules: List[Dict[str, Any]] = []
    if isinstance(raw_rules, list):
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                continue
            match_value = str(raw_rule.get("match_value", "") or "").strip()
            label_name = str(raw_rule.get("label_name", "") or "").strip()
            if not match_value or not label_name:
                continue
            rules.append(
                {
                    "match_type": str(raw_rule.get("match_type", "sender") or "sender").strip().lower(),
                    "match_value": match_value,
                    "label_name": label_name,
                    "also_archive": bool(raw_rule.get("also_archive", False)),
                }
            )
    preferences["label_rules"] = rules

    proactive_defaults = copy.deepcopy(DEFAULT_MAILBOX_PREFERENCES["proactive_offers"])
    raw_proactive = preferences.get("proactive_offers", {})
    if isinstance(raw_proactive, dict):
        proactive_defaults.update(raw_proactive)
    proactive_defaults["enabled"] = bool(proactive_defaults.get("enabled", True))
    for key in (
        "inbox_overload_threshold",
        "newsletter_cleanup_repeat_threshold",
        "manual_triage_repeat_threshold",
    ):
        try:
            proactive_defaults[key] = max(int(proactive_defaults.get(key, 1) or 1), 1)
        except Exception:
            proactive_defaults[key] = int(DEFAULT_MAILBOX_PREFERENCES["proactive_offers"][key])
    preferences["proactive_offers"] = proactive_defaults
    preferences["version"] = int(preferences.get("version", DEFAULT_MAILBOX_PREFERENCES["version"]) or DEFAULT_MAILBOX_PREFERENCES["version"])
    return preferences


def mailbox_preferences_exist() -> bool:
    return get_mailbox_preferences_path().exists()


def load_mailbox_preferences() -> Dict[str, Any]:
    path = get_mailbox_preferences_path()
    if not path.exists():
        return default_mailbox_preferences()

    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return default_mailbox_preferences()

    match = _JSON_BLOCK_RE.search(content)
    if not match:
        return default_mailbox_preferences()

    try:
        payload = json.loads(match.group(1))
    except Exception:
        return default_mailbox_preferences()
    return _normalize_mailbox_preferences(payload)


def render_mailbox_preferences_summary(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_mailbox_preferences(preferences)
    rule_count = len(prefs.get("label_rules", []))
    lines = [
        "Saved mailbox preferences:",
        f"- Operating mode: {_OPERATION_MODE_LABELS[prefs['operation_mode']]}",
        f"- Promotions: {_PROMOTIONS_ACTION_LABELS[prefs['promotions_action']]}",
        f"- Newsletters: {_NEWSLETTERS_ACTION_LABELS[prefs['newsletters_action']]}",
        f"- Task extraction: {'On' if prefs['task_extraction'] else 'Off'}",
        f"- Draft replies: {_DRAFT_REPLY_LABELS[prefs['draft_replies']]}",
        f"- Scheduled review: {_REVIEW_SCHEDULE_LABELS[prefs['review_schedule']]}",
        (
            f"- Continuous cleanup: Every {int(prefs['continuous_cleanup']['interval_minutes'])} minutes"
            if prefs["continuous_cleanup"].get("enabled")
            else "- Continuous cleanup: Off"
        ),
        f"- Saved label rules: {rule_count}",
    ]
    return "\n".join(lines)


def render_mailbox_capabilities() -> str:
    lines = [
        "Mailbox organization options I can truly help with right now:",
        "1. Save durable mailbox preferences in a markdown file you can inspect and edit.",
        "2. Build a mailbox organization plan before touching the inbox.",
        "3. Archive promotions out of the inbox safely.",
        "4. Archive newsletter-style emails, or keep them for summaries first.",
        "5. Surface pending action items from emails.",
        "6. Suggest reply drafts when you want help responding.",
        "7. Create Gmail label rules for future senders, domains, or repeated categories when the rule is explicit.",
        "8. Show mailbox review digests and recommend preference changes based on cleanup history.",
        "9. Run a scheduled daily or weekly mailbox review in the background.",
        "10. Run continuous safe cleanup for promotions and newsletters when you explicitly enable safe autopilot.",
    ]
    return "\n".join(lines)


def detect_mailbox_signals(counts: Dict[str, Any], preferences: Dict[str, Any], history: List[Dict[str, Any]]) -> List[str]:
    prefs = _normalize_mailbox_preferences(preferences)
    signals: List[str] = []
    proactive = prefs.get("proactive_offers", {}) if isinstance(prefs.get("proactive_offers"), dict) else {}
    if not proactive.get("enabled", True):
        return signals

    unread_total = int(counts.get("unread_total", 0) or 0)
    overload_threshold = int(proactive.get("inbox_overload_threshold", 75) or 75)
    if unread_total >= overload_threshold:
        signals.append("Your inbox looks overloaded. I recommend applying the safe cleanup actions or tightening your label rules.")

    newsletter_events = sum(
        1
        for item in history
        if str(item.get("kind", "") or "") in {"mailbox_apply", "mailbox_continuous_cleanup"}
        and int(item.get("newsletter_archived", 0) or 0) > 0
    )
    if newsletter_events >= int(proactive.get("newsletter_cleanup_repeat_threshold", 2) or 2):
        signals.append("You repeatedly clean up newsletter-style email. Consider leaving newsletters on summarize-then-archive or adding sender rules.")

    triage_events = sum(1 for item in history if str(item.get("kind", "") or "") == "manual_triage")
    if triage_events >= int(proactive.get("manual_triage_repeat_threshold", 3) or 3):
        signals.append("You have been triaging email manually several times. I can reduce that by tightening mailbox preferences or saving more label rules.")

    return signals


def render_mailbox_preferences_markdown(preferences: Dict[str, Any] | None = None) -> str:
    prefs = _normalize_mailbox_preferences(preferences)
    return "\n".join([
        "# Mailbox Preferences",
        "",
        "This file is the durable mailbox-organization contract for the assistant.",
        "Update it through the assistant when possible so the changes stay validated.",
        "",
        "## Structured Preferences",
        "```json",
        json.dumps(prefs, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Human Summary",
        render_mailbox_preferences_summary(prefs),
        "",
        "## What The Assistant Will Do",
        "- Use these preferences to build a plan before mailbox-wide actions.",
        "- Keep destructive actions behind confirmation unless you explicitly choose safe autopilot.",
        "- Prefer archive and labeling actions over deletion for organization flows.",
        "- Remember explicit mailbox label rules you approve.",
        "",
        "## Editing Notes",
        "- Say 'show my mailbox preferences' to review them.",
        "- Say 'edit my mailbox preferences' to update them through a guided flow.",
        "- Say 'apply my mailbox preferences' to run the safe organization actions allowed by this file.",
        "- Say 'review my mailbox' to get a digest of recent cleanup activity and recommendations.",
        "- Say 'set mailbox review to daily' or 'weekly' to enable scheduled review.",
        "- Say 'turn on continuous mailbox cleanup' after switching mailbox mode to Safe autopilot to keep promotions/newsletters under control automatically.",
    ])


def save_mailbox_preferences(preferences: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_mailbox_preferences(preferences)
    path = get_mailbox_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_mailbox_preferences_markdown(normalized), encoding="utf-8")
    return {
        "status": "success",
        "file_path": str(path),
        "preferences": normalized,
        "message": f"Saved mailbox preferences to {path}",
    }


def upsert_mailbox_label_rule(preferences: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_mailbox_preferences(preferences)
    candidate = {
        "match_type": str(rule.get("match_type", "sender") or "sender").strip().lower(),
        "match_value": str(rule.get("match_value", "") or "").strip(),
        "label_name": str(rule.get("label_name", "") or "").strip(),
        "also_archive": bool(rule.get("also_archive", False)),
    }
    if not candidate["match_value"] or not candidate["label_name"]:
        return normalized

    updated_rules: List[Dict[str, Any]] = []
    replaced = False
    for existing in normalized.get("label_rules", []):
        if (
            str(existing.get("match_type", "") or "") == candidate["match_type"]
            and str(existing.get("match_value", "") or "").casefold() == candidate["match_value"].casefold()
        ):
            updated_rules.append(candidate)
            replaced = True
        else:
            updated_rules.append(existing)
    if not replaced:
        updated_rules.append(candidate)
    normalized["label_rules"] = updated_rules
    return normalized


def get_mailbox_review_history_path() -> Path:
    return _MAILBOX_REVIEW_HISTORY_PATH


def load_mailbox_review_history() -> List[Dict[str, Any]]:
    path = get_mailbox_review_history_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def record_mailbox_review_event(event: Dict[str, Any]) -> Dict[str, Any]:
    path = get_mailbox_review_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    history = load_mailbox_review_history()
    entry = dict(event or {})
    entry.setdefault("recorded_at", datetime.now().isoformat(timespec="seconds"))
    history.append(entry)
    history = history[-50:]
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry