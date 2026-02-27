"""
Email skill orchestrator.

Exported function: execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

# ---------------------------------------------------------------------------
# Tool builders (lazy so Gmail auth errors surface at call time not import time)
# ---------------------------------------------------------------------------

def _get_tools() -> Dict[str, Any]:
    from src.email.gmail_service import _get_client  # noqa: PLC0415

    svc = _get_client()

    def send_email(to: str, subject: str, message: str) -> dict:
        return svc.send_email(to, subject, message)

    def send_email_with_attachment(to: str, subject: str, message: str, attachment_path: str) -> dict:
        return svc.send_email_with_attachment(to, subject, message, attachment_path)

    def list_emails(query: str = "in:inbox", max_results: int = 10) -> dict:
        return svc.list_emails(query, max_results)

    def get_inbox_count() -> dict:
        return svc.get_inbox_count()

    def get_todays_emails() -> dict:
        return svc.get_todays_emails()

    def delete_emails(query: str, max_results: int = 10) -> dict:
        return svc.delete_emails(query, max_results)

    def summarize_email(message_id: str) -> dict:
        return svc.summarize_email(message_id)

    def generate_daily_digest() -> dict:
        return svc.generate_daily_digest()

    def create_draft(to: str, subject: str, body: str) -> dict:
        return svc.create_draft(to, subject, body)

    def list_drafts() -> dict:
        return svc.list_drafts()

    def send_draft(draft_id: str) -> dict:
        return svc.send_draft(draft_id)

    def extract_action_items(message_id: str) -> dict:
        return svc.extract_action_items(message_id)

    def get_all_pending_actions() -> dict:
        return svc.get_all_pending_actions()

    def detect_urgent_emails() -> dict:
        return svc.detect_urgent_emails()

    def get_email_stats(days: int = 7) -> dict:
        return svc.get_email_stats(days)

    def get_frequent_contacts() -> dict:
        return svc.get_frequent_contacts()

    def search_emails_with_attachments(file_type: str = "") -> dict:
        return svc.search_emails_with_attachments(file_type)

    def generate_weekly_report() -> dict:
        return svc.generate_weekly_report()

    def schedule_email(to: str, subject: str, body: str, send_time: str) -> dict:
        return svc.schedule_email(to, subject, body, send_time)

    def extract_calendar_events(message_id: str) -> dict:
        return svc.extract_calendar_events(message_id)

    return {
        "send_email": send_email,
        "send_email_with_attachment": send_email_with_attachment,
        "list_emails": list_emails,
        "get_inbox_count": get_inbox_count,
        "get_todays_emails": get_todays_emails,
        "delete_emails": delete_emails,
        "summarize_email": summarize_email,
        "generate_daily_digest": generate_daily_digest,
        "create_draft": create_draft,
        "list_drafts": list_drafts,
        "send_draft": send_draft,
        "extract_action_items": extract_action_items,
        "get_all_pending_actions": get_all_pending_actions,
        "detect_urgent_emails": detect_urgent_emails,
        "get_email_stats": get_email_stats,
        "get_frequent_contacts": get_frequent_contacts,
        "search_emails_with_attachments": search_emails_with_attachments,
        "generate_weekly_report": generate_weekly_report,
        "schedule_email": schedule_email,
        "extract_calendar_events": extract_calendar_events,
    }


_TOOL_DOCS = """
send_email(to, subject, message) – Send an email.
send_email_with_attachment(to, subject, message, attachment_path) – Send email with a local file attachment.
list_emails(query="in:inbox", max_results=10) – List emails matching a Gmail query string.
get_inbox_count() – Return unread inbox count.
get_todays_emails() – Fetch emails received today.
delete_emails(query, max_results=10) – Delete emails matching a Gmail query.
summarize_email(message_id) – Summarise a specific email by its ID.
generate_daily_digest() – Generate a digest of today's emails.
create_draft(to, subject, body) – Save an email as a draft.
list_drafts() – List all saved drafts.
send_draft(draft_id) – Send a previously saved draft.
extract_action_items(message_id) – Extract to-do items from a specific email.
get_all_pending_actions() – List all pending action items from emails.
detect_urgent_emails() – Surface emails marked or detected as urgent.
get_email_stats(days=7) – Return email volume statistics for the past N days.
get_frequent_contacts() – Return a list of frequently emailed contacts.
search_emails_with_attachments(file_type="") – Find emails that have file attachments.
generate_weekly_report() – Generate a weekly email activity report.
schedule_email(to, subject, body, send_time) – Schedule an email to be sent at a future time (send_time: ISO 8601, e.g. "2026-03-01T14:00:00").
extract_calendar_events(message_id) – Extract any calendar event details mentioned in a specific email.
""".strip()

_SKILL_CONTEXT = """
You are the Email Skill Agent backed by the Gmail API.
Your job is to help the user manage their Gmail inbox: read, send, draft, delete, summarise and analyse emails.
When all required fields (to, subject, body/message) are present in your instruction, call send_email or send_email_with_attachment IMMEDIATELY — do NOT ask for confirmation or clarification.
If the body/message is not explicitly specified, compose a brief, helpful message summarising the context and actions described in the instruction (e.g. "The file XYZ was zipped and uploaded to Google Drive: <link>").
If no recipient (to) is specified in your task instruction, use the Gmail address you are authenticated as — call get_inbox_count() first to resolve it if needed, but prefer to infer it from any address already mentioned in the instruction context.
When you list emails include the snippet/preview so the user can identify messages.
Prefer using message IDs returned by list_emails or get_todays_emails when calling summarize_email or extract_action_items.
""".strip()


# ---------------------------------------------------------------------------
# Required entry-point
# ---------------------------------------------------------------------------

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat."""
    try:
        return run_skill_react(
            skill_name="email",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Email skill error: {exc}",
            "action": "react_response",
        }
