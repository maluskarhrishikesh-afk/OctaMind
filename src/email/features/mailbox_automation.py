from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.agent.core.automations.automation_config import update_automation_state
from src.email.features.mailbox_preferences import (
    default_mailbox_preferences,
    detect_mailbox_signals,
    load_mailbox_preferences,
    load_mailbox_review_history,
    record_mailbox_review_event,
)


logger = logging.getLogger("email.mailbox_automation")

_PROMOTIONS_QUERY = "category:promotions in:inbox"
_NEWSLETTERS_QUERY = 'in:inbox (unsubscribe OR newsletter OR "mailing list") -category:promotions'


def _load_client():
    from src.email.gmail_service import _get_client  # noqa: PLC0415

    return _get_client()


def _extract_unread_total(inbox_result: Dict[str, Any]) -> int:
    return int(
        inbox_result.get("unread_messages", inbox_result.get("count", inbox_result.get("unread_count", 0)))
        or 0
    )


def _extract_count(result: Dict[str, Any]) -> int:
    return int(result.get("total_count", result.get("count", 0)) or 0)


def build_mailbox_snapshot(preferences: Dict[str, Any] | None = None) -> Dict[str, Any]:
    prefs = preferences or load_mailbox_preferences()
    client = _load_client()
    inbox_result = client.get_inbox_count()
    promotions_result = client.count_matching_emails(_PROMOTIONS_QUERY)
    newsletters_result = client.count_matching_emails(_NEWSLETTERS_QUERY)
    counts = {
        "unread_total": _extract_unread_total(inbox_result) if isinstance(inbox_result, dict) else 0,
        "promotions": _extract_count(promotions_result) if isinstance(promotions_result, dict) else 0,
        "newsletters": _extract_count(newsletters_result) if isinstance(newsletters_result, dict) else 0,
    }
    history = load_mailbox_review_history()
    signals = detect_mailbox_signals(counts, prefs, history)
    return {
        "preferences": prefs,
        "counts": counts,
        "signals": signals,
        "history": history,
    }


def sync_mailbox_automation_config(agent_id: str | None, preferences: Dict[str, Any] | None = None) -> Dict[str, Any]:
    normalized_agent_id = str(agent_id or "").strip()
    if not normalized_agent_id:
        return {
            "status": "skipped",
            "message": "Mailbox automation was not synced because no agent id was available in this execution path.",
        }

    prefs = preferences or load_mailbox_preferences()
    review_schedule = str(prefs.get("review_schedule", "manual") or "manual")
    cleanup = prefs.get("continuous_cleanup", {}) if isinstance(prefs.get("continuous_cleanup"), dict) else {}
    requested_cleanup_enabled = bool(cleanup.get("enabled", False))
    cleanup_interval = max(int(cleanup.get("interval_minutes", 30) or 30), 5)
    cleanup_enabled = requested_cleanup_enabled and str(prefs.get("operation_mode", "") or "") == "safe_autopilot"

    update_automation_state(normalized_agent_id, "mailbox_daily_review", enabled=review_schedule == "daily")
    update_automation_state(normalized_agent_id, "mailbox_weekly_review", enabled=review_schedule == "weekly")
    update_automation_state(
        normalized_agent_id,
        "mailbox_continuous_cleanup",
        enabled=cleanup_enabled,
        params={},
        interval_minutes=cleanup_interval,
    )

    try:
        from src.agent.core.automation_scheduler import start_scheduler  # noqa: PLC0415

        start_scheduler(normalized_agent_id)
    except Exception as exc:
        logger.warning("Could not start scheduler for %s: %s", normalized_agent_id, exc)

    details: List[str] = []
    if review_schedule == "daily":
        details.append("Daily mailbox review is enabled.")
    elif review_schedule == "weekly":
        details.append("Weekly mailbox review is enabled.")
    else:
        details.append("Scheduled mailbox review is off.")

    if cleanup_enabled:
        details.append(f"Continuous safe cleanup is enabled every {cleanup_interval} minutes.")
    elif requested_cleanup_enabled:
        details.append("Continuous cleanup is configured, but it will only run while mailbox mode is Safe autopilot.")
    else:
        details.append("Continuous safe cleanup is off.")

    return {
        "status": "success",
        "daily_review_enabled": review_schedule == "daily",
        "weekly_review_enabled": review_schedule == "weekly",
        "continuous_cleanup_enabled": cleanup_enabled,
        "message": " ".join(details),
    }


def run_scheduled_mailbox_review(review_kind: str) -> Dict[str, Any]:
    prefs = load_mailbox_preferences()
    snapshot = build_mailbox_snapshot(prefs)
    counts = snapshot["counts"]
    signals = snapshot["signals"]
    event = record_mailbox_review_event(
        {
            "kind": review_kind,
            "counts": counts,
            "signals": signals,
        }
    )

    lines = [
        f"Recorded {review_kind.replace('_', ' ')}.",
        f"Unread inbox count: {int(counts.get('unread_total', 0) or 0)}",
        f"Promotion emails in inbox: {int(counts.get('promotions', 0) or 0)}",
        f"Newsletter-style emails in inbox: {int(counts.get('newsletters', 0) or 0)}",
    ]
    if signals:
        lines.append("Signals:")
        lines.extend(f"- {signal}" for signal in signals)
    return {
        "status": "success",
        "recorded_at": event.get("recorded_at", ""),
        "message": "\n".join(lines),
    }


def run_continuous_mailbox_cleanup() -> Dict[str, Any]:
    prefs = load_mailbox_preferences()
    cleanup = prefs.get("continuous_cleanup", {}) if isinstance(prefs.get("continuous_cleanup"), dict) else {}
    if not cleanup.get("enabled", False):
        return {"status": "success", "message": "Continuous mailbox cleanup is disabled in mailbox preferences."}
    if str(prefs.get("operation_mode", "") or "") != "safe_autopilot":
        return {"status": "success", "message": "Continuous mailbox cleanup is configured but paused until mailbox mode is Safe autopilot."}

    client = _load_client()
    promotions_archived = 0
    newsletter_archived = 0
    results: List[str] = []

    if str(prefs.get("promotions_action", "") or "") == "archive":
        promotions_result = client.archive_all_matching_emails(_PROMOTIONS_QUERY, batch_size=200)
        promotions_archived = int(promotions_result.get("archived_count", 0) or 0)
        results.append(f"Promotions archived: {promotions_archived}")

    if str(prefs.get("newsletters_action", "") or "") in {"archive", "summarize_then_archive"}:
        newsletter_result = client.archive_all_matching_emails(_NEWSLETTERS_QUERY, batch_size=200)
        newsletter_archived = int(newsletter_result.get("archived_count", 0) or 0)
        results.append(f"Newsletters archived: {newsletter_archived}")

    event = record_mailbox_review_event(
        {
            "kind": "mailbox_continuous_cleanup",
            "promotions_archived": promotions_archived,
            "newsletter_archived": newsletter_archived,
        }
    )
    return {
        "status": "success",
        "recorded_at": event.get("recorded_at", ""),
        "promotions_archived": promotions_archived,
        "newsletter_archived": newsletter_archived,
        "message": "; ".join(results) if results else "No continuous cleanup actions were enabled.",
    }