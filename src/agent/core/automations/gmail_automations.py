"""
Gmail Automation Handlers

Each function matches an automation_id in GMAIL_AUTOMATIONS and is called by
the AutomationScheduler with signature:

    handler(agent_id: str, params: dict) -> str   # human-readable result

Functions are designed to be self-contained and safe — they catch all exceptions
so a single failing automation never crashes the scheduler loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


# ── Shared helper ─────────────────────────────────────────────────────────────

def _svc():
    """Return a raw Google Gmail API service object (lazy import)."""
    from src.email.gmail_auth import get_gmail_service
    return get_gmail_service()


# ── Handlers ─────────────────────────────────────────────────────────────────

def auto_delete_spam(agent_id: str, params: Dict[str, Any]) -> str:
    """Trash all messages currently in the Spam label."""
    try:
        service = _svc()
        result = service.users().messages().list(
            userId="me", labelIds=["SPAM"], maxResults=50
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return "No spam emails found"
        for m in messages:
            service.users().messages().trash(userId="me", id=m["id"]).execute()
        return f"Deleted {len(messages)} spam email(s)"
    except Exception as exc:
        logger.error("[%s] auto_delete_spam: %s", agent_id, exc)
        return f"Error: {exc}"


def auto_archive_newsletters(agent_id: str, params: Dict[str, Any]) -> str:
    """Move Promotions-category emails out of the inbox."""
    try:
        service = _svc()
        result = service.users().messages().list(
            userId="me", q="is:read label:promotions in:inbox", maxResults=30
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return "No newsletter emails to archive"
        for m in messages:
            service.users().messages().modify(
                userId="me", id=m["id"],
                body={"removeLabelIds": ["INBOX"]}
            ).execute()
        return f"Archived {len(messages)} newsletter email(s)"
    except Exception as exc:
        logger.error("[%s] auto_archive_newsletters: %s", agent_id, exc)
        return f"Error: {exc}"


def daily_digest(agent_id: str, params: Dict[str, Any]) -> str:
    """Generate a daily digest and write a note to agent episodic memory."""
    try:
        from src.email.gmail_service import generate_daily_digest
        digest = generate_daily_digest()
        # Write result to episodic memory so the agent can reference it
        try:
            from src.agent.memory.agent_memory import get_agent_memory
            mem = get_agent_memory(agent_id)
            digest_text = str(digest)[:600] if digest else "(empty)"
            mem.add_episodic_event(
                event=f"[Auto] Daily digest at {datetime.now().strftime('%H:%M')}: {digest_text}",
                importance="low",
            )
        except Exception as exc:
            logger.warning("[%s] daily_digest memory write: %s", agent_id, exc)
        return f"Daily digest generated: {str(digest)[:200] if digest else '(empty)'}"
    except Exception as exc:
        logger.error("[%s] daily_digest: %s", agent_id, exc)
        return f"Error: {exc}"


def auto_label_vip(agent_id: str, params: Dict[str, Any]) -> str:
    """Star emails from the agent's top frequent contacts."""
    try:
        from src.email.features.contacts import get_frequent_contacts
        contacts_info = get_frequent_contacts(limit=10)
        vip_emails = [c.get("email")
                      for c in (contacts_info or []) if c.get("email")]
        if not vip_emails:
            return "No frequent contacts found yet"
        service = _svc()
        count = 0
        for email in vip_emails[:15]:
            res = service.users().messages().list(
                userId="me", q=f"from:{email} -is:starred", maxResults=10
            ).execute()
            for m in res.get("messages", []):
                service.users().messages().modify(
                    userId="me", id=m["id"],
                    body={"addLabelIds": ["STARRED"]}
                ).execute()
                count += 1
        return f"Starred {count} VIP email(s)"
    except Exception as exc:
        logger.error("[%s] auto_label_vip: %s", agent_id, exc)
        return f"Error: {exc}"


def flag_old_unread(agent_id: str, params: Dict[str, Any]) -> str:
    """Star unread emails that are older than `age_days` days."""
    try:
        age_days = int(params.get("age_days", 7))
        service = _svc()
        res = service.users().messages().list(
            userId="me",
            q=f"is:unread older_than:{age_days}d -is:starred",
            maxResults=50,
        ).execute()
        messages = res.get("messages", [])
        for m in messages:
            service.users().messages().modify(
                userId="me", id=m["id"],
                body={"addLabelIds": ["STARRED"]}
            ).execute()
        return f"Flagged {len(messages)} old unread email(s)"
    except Exception as exc:
        logger.error("[%s] flag_old_unread: %s", agent_id, exc)
        return f"Error: {exc}"


def weekly_report(agent_id: str, params: Dict[str, Any]) -> str:
    """Generate a 7-day email analytics report and store in agent memory."""
    try:
        from src.email.features.analytics import get_email_stats
        stats = get_email_stats(days=7)
        try:
            from src.agent.memory.agent_memory import get_agent_memory
            mem = get_agent_memory(agent_id)
            summary = str(stats)[:400] if stats else "No stats"
            mem.add_episodic_event(
                event=f"[Auto] Weekly report: {summary}",
                importance="medium",
            )
        except Exception as exc:
            logger.warning(
                "[%s] weekly_report memory write: %s", agent_id, exc)
        return "Weekly report generated and saved to memory"
    except Exception as exc:
        logger.error("[%s] weekly_report: %s", agent_id, exc)
        return f"Error: {exc}"


def auto_categorize(agent_id: str, params: Dict[str, Any]) -> str:
    """Apply OctaMind Gmail category labels to recent unread emails."""
    try:
        from src.email.features.categorizer import auto_categorize_email
        service = _svc()
        res = service.users().messages().list(
            userId="me", q="is:unread", maxResults=20
        ).execute()
        messages = res.get("messages", [])
        count = 0
        for m in messages:
            try:
                auto_categorize_email(m["id"])
                count += 1
            except Exception as exc:
                logger.warning(
                    "[%s] auto_categorize email %s: %s", agent_id, m["id"], exc)
        return f"Categorized {count} email(s)"
    except Exception as exc:
        logger.error("[%s] auto_categorize: %s", agent_id, exc)
        return f"Error: {exc}"


def auto_unsubscribe(agent_id: str, params: Dict[str, Any]) -> str:
    """Scan for newsletter senders and log a report (no automatic unsubscribe)."""
    try:
        from src.email.features.unsubscribe import detect_newsletters
        newsletters = detect_newsletters() or []
        count = len(newsletters)
        try:
            from src.agent.memory.agent_memory import get_agent_memory
            mem = get_agent_memory(agent_id)
            sender_list = ", ".join(n.get("sender", "")
                                    for n in newsletters[:5])
            mem.add_episodic_event(
                event=f"[Auto] Found {count} newsletter senders: {sender_list}",
                importance="low",
            )
        except Exception as exc:
            logger.warning(
                "[%s] auto_unsubscribe memory write: %s", agent_id, exc)
        return f"Detected {count} newsletter sender(s). Check agent memory for details."
    except Exception as exc:
        logger.error("[%s] auto_unsubscribe: %s", agent_id, exc)
        return f"Error: {exc}"


def out_of_office(agent_id: str, params: Dict[str, Any]) -> str:
    """Send out-of-office auto-replies to new unread emails, then mark them read."""
    try:
        reply_message = params.get(
            "reply_message",
            "I'm currently out of the office and will respond shortly.",
        )
        active_until = params.get("active_until", "").strip()
        if active_until:
            try:
                if datetime.now() > datetime.fromisoformat(active_until):
                    return "Out-of-office period has ended — automation can be disabled"
            except ValueError:
                pass

        service = _svc()
        res = service.users().messages().list(
            userId="me", q="is:unread -from:me in:inbox", maxResults=10
        ).execute()
        messages = res.get("messages", [])
        count = 0
        errors = []
        for m in messages[:5]:
            try:
                meta = service.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Message-ID"],
                ).execute()
                headers = {
                    h["name"]: h["value"]
                    for h in meta.get("payload", {}).get("headers", [])
                }
                from_addr = headers.get("From", "")
                subject = headers.get("Subject", "(no subject)")

                # Skip no-reply senders and our own address
                skip_patterns = ["noreply", "no-reply", "donotreply",
                                 "notifications@", "mailer-daemon"]
                if not from_addr or any(p in from_addr.lower() for p in skip_patterns):
                    continue

                from src.email.gmail_service import send_email
                result = send_email(
                    to=from_addr,
                    subject=f"Re: {subject}",
                    message=reply_message,   # ← fixed: was "body="
                )
                if result.get("status") == "success":
                    # Mark as read so we don't reply again next run
                    service.users().messages().modify(
                        userId="me", id=m["id"],
                        body={"removeLabelIds": ["UNREAD"]},
                    ).execute()
                    count += 1
                else:
                    errors.append(result.get("message", "unknown error"))
            except Exception as exc:
                logger.error("[%s] out_of_office inner: %s", agent_id, exc)
                errors.append(str(exc))

        summary = f"Sent {count} auto-reply message(s)"
        if errors:
            summary += f" | {len(errors)} error(s): {errors[0]}"
        return summary
    except Exception as exc:
        logger.error("[%s] out_of_office: %s", agent_id, exc)
        return f"Error: {exc}"


def archive_old_read(agent_id: str, params: Dict[str, Any]) -> str:
    """Remove INBOX label from read emails older than `age_days` days."""
    try:
        age_days = int(params.get("age_days", 30))
        service = _svc()
        res = service.users().messages().list(
            userId="me",
            q=f"is:read older_than:{age_days}d in:inbox",
            maxResults=50,
        ).execute()
        messages = res.get("messages", [])
        for m in messages:
            service.users().messages().modify(
                userId="me", id=m["id"],
                body={"removeLabelIds": ["INBOX"]}
            ).execute()
        return f"Archived {len(messages)} old read email(s)"
    except Exception as exc:
        logger.error("[%s] archive_old_read: %s", agent_id, exc)
        return f"Error: {exc}"


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLER_MAP: Dict[str, Any] = {
    "auto_delete_spam": auto_delete_spam,
    "auto_archive_newsletters": auto_archive_newsletters,
    "daily_digest": daily_digest,
    "auto_label_vip": auto_label_vip,
    "flag_old_unread": flag_old_unread,
    "weekly_report": weekly_report,
    "auto_categorize": auto_categorize,
    "auto_unsubscribe": auto_unsubscribe,
    "out_of_office": out_of_office,
    "archive_old_read": archive_old_read,
}
