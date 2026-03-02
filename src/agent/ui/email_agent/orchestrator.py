"""
Email skill orchestrator.

Exported function: execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag

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

    def create_label(label_name: str) -> dict:
        return svc.create_label(label_name)

    def move_emails_to_label(query: str, label_name: str, max_results: int = 50) -> dict:
        return svc.move_emails_to_label(query, label_name, max_results)

    def set_vacation_responder(
        enabled: bool,
        subject: str = "",
        body: str = "",
        start_date: str = "",
        end_date: str = "",
        restrict_to_contacts: bool = False,
    ) -> dict:
        return svc.set_vacation_responder(enabled, subject, body, start_date, end_date, restrict_to_contacts)

    def get_vacation_responder() -> dict:
        return svc.get_vacation_responder()

    def sync_contacts() -> dict:
        from src.email.features.contacts_sync import sync_contacts as _sync
        return _sync()

    def search_contacts(query: str) -> dict:
        from src.email.features.contacts_sync import search_contacts as _search
        return _search(query)

    def list_contacts(limit: int = 50) -> dict:
        from src.email.features.contacts_sync import list_contacts as _list
        return _list(limit)

    def fetch_emails_to_markdown(
        query: str = "in:inbox",
        max_results: int = 5,
        cap: int = 20,
    ) -> dict:
        return svc.fetch_emails_to_markdown(query, max_results, cap)

    def unsubscribe_email(message_id: str) -> dict:
        return svc.unsubscribe_email(message_id)

    def archive_emails(query: str, max_results: int = 50) -> dict:
        return svc.archive_emails(query, max_results)

    def thread_mute(thread_id: str) -> dict:
        return svc.thread_mute(thread_id)

    def thread_archive(thread_id: str) -> dict:
        return svc.thread_archive(thread_id)

    def thread_delete(thread_id: str) -> dict:
        return svc.thread_delete(thread_id)

    def create_smart_label_rule(
        label_name: str,
        from_email: str = "",
        subject_contains: str = "",
        to_email: str = "",
        also_archive: bool = False,
    ) -> dict:
        return svc.create_smart_label_rule(
            label_name, from_email, subject_contains, to_email, also_archive
        )

    def find_unanswered_emails(days: int = 3, max_results: int = 20) -> dict:
        return svc.find_unanswered_emails(days, max_results)

    def empty_trash() -> dict:
        return svc.empty_trash()

    def batch_mark_spam(query: str, max_results: int = 50) -> dict:
        return svc.batch_mark_spam(query, max_results)

    def add_forwarding_address(forward_to: str) -> dict:
        return svc.add_forwarding_address(forward_to)

    def enable_email_forwarding(forward_to: str) -> dict:
        return svc.enable_email_forwarding(forward_to)

    def get_signature(send_as_email: str = "me") -> dict:
        return svc.get_signature(send_as_email)

    def set_signature(signature_html: str, send_as_email: str = "me") -> dict:
        return svc.set_signature(signature_html, send_as_email)

    def save_email_template(name: str, subject: str, body: str) -> dict:
        return svc.save_email_template(name, subject, body)

    def list_email_templates() -> dict:
        return svc.list_email_templates()

    def send_from_template(template_name: str, to: str, variables: dict = None) -> dict:
        return svc.send_from_template(template_name, to, variables)

    def recover_deleted_emails(query: str = "", max_results: int = 20) -> dict:
        return svc.recover_deleted_emails(query, max_results)

    def analyze_email_sentiment(message_id: str) -> dict:
        return svc.analyze_email_sentiment(message_id)

    def extract_urls_from_email(message_id: str) -> dict:
        return svc.extract_urls_from_email(message_id)

    def get_email_chains_summary(max_results: int = 10) -> dict:
        return svc.get_email_chains_summary(max_results)

    def send_completion_reminder(message_id: str, days: int = 3) -> dict:
        return svc.send_completion_reminder(message_id, days)

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
        "create_label": create_label,
        "move_emails_to_label": move_emails_to_label,
        "set_vacation_responder": set_vacation_responder,
        "get_vacation_responder": get_vacation_responder,
        "sync_contacts": sync_contacts,
        "search_contacts": search_contacts,
        "list_contacts": list_contacts,
        "fetch_emails_to_markdown": fetch_emails_to_markdown,
        "unsubscribe_email": unsubscribe_email,
        "archive_emails": archive_emails,
        "thread_mute": thread_mute,
        "thread_archive": thread_archive,
        "thread_delete": thread_delete,
        "create_smart_label_rule": create_smart_label_rule,
        "find_unanswered_emails": find_unanswered_emails,
        "empty_trash": empty_trash,
        "batch_mark_spam": batch_mark_spam,
        "add_forwarding_address": add_forwarding_address,
        "enable_email_forwarding": enable_email_forwarding,
        "get_signature": get_signature,
        "set_signature": set_signature,
        "save_email_template": save_email_template,
        "list_email_templates": list_email_templates,
        "send_from_template": send_from_template,
        # ── NEW ─────────────────────────────────────────────────
        "recover_deleted_emails": recover_deleted_emails,
        "analyze_email_sentiment": analyze_email_sentiment,
        "extract_urls_from_email": extract_urls_from_email,
        "get_email_chains_summary": get_email_chains_summary,
        "send_completion_reminder": send_completion_reminder,
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
create_label(label_name) – Create a Gmail label / folder (creates it if it doesn’t already exist).
move_emails_to_label(query, label_name, max_results=50) – Move emails matching a Gmail query into a label/folder (creates the label automatically if needed and removes them from INBOX).
get_frequent_contacts() – Return a list of frequently emailed contacts.
search_emails_with_attachments(file_type="") – Find emails that have file attachments.
generate_weekly_report() – Generate a weekly email activity report.
schedule_email(to, subject, body, send_time) – Schedule an email to be sent at a future time (send_time: ISO 8601, e.g. "2026-03-01T14:00:00").
extract_calendar_events(message_id) – Extract any calendar event details mentioned in a specific email.
set_vacation_responder(enabled, subject="", body="", start_date="", end_date="", restrict_to_contacts=False) – Enable or disable Gmail's Out-of-Office / Vacation auto-reply. enabled=True to turn on, False to turn off. start_date/end_date are ISO date strings 'YYYY-MM-DD'. Use this when the user asks to set OOO, out-of-office, vacation reply, or auto-reply.
get_vacation_responder() – Check the current state of the Gmail vacation / OOO responder (enabled/disabled, message, dates).
sync_contacts() – Sync Gmail contacts to the local cache (data/contacts.json) using Google People API + email interaction mining. Run this periodically or when the user asks to refresh/download contacts.
search_contacts(query) – Search the local contacts cache by name or email address. Fast — uses the local file, no API call.
list_contacts(limit=50) – List the top contacts from the local cache sorted by interaction frequency.
fetch_emails_to_markdown(query="in:inbox", max_results=5, cap=20) – PREFERRED for multi-email summarization. Fetches all N emails matching a Gmail query in ONE call, saves them as a Markdown file, and returns file_path + structured list + full content. Use this whenever the user asks to 'summarize the latest N emails from X' or 'get N emails and summarize'. Returns error if max_results > cap (default 20) — tell the user to reduce the number. Do NOT call summarize_email in a loop.
unsubscribe_email(message_id) – Extract the List-Unsubscribe header from an email and attempt one-click unsubscribe (RFC 8058). Returns unsubscribe URLs/mailto. Use when user says 'unsubscribe me from X' or 'stop receiving emails from X'.
archive_emails(query, max_results=50) – Remove emails matching a Gmail query from Inbox without deleting them (they remain in All Mail). Use for bulk clearing the inbox.
thread_mute(thread_id) – Mute a thread — future replies skip the Inbox.
thread_archive(thread_id) – Archive an entire thread (remove from Inbox).
thread_delete(thread_id) – Move an entire thread to Trash.
create_smart_label_rule(label_name, from_email="", subject_contains="", to_email="", also_archive=False) – Apply a label to all matching emails and instruct the user how to create a Gmail filter for future emails.
find_unanswered_emails(days=3, max_results=20) – Surface sent emails that have received no reply in the last N days.
empty_trash() – Permanently delete all emails in Trash.
batch_mark_spam(query, max_results=50) – Move emails matching a query to Spam.
add_forwarding_address(forward_to) – Register a forwarding address (sends verification email to recipient).
enable_email_forwarding(forward_to) – Enable auto-forwarding of all incoming email to an address (address must be pre-verified).
get_signature(send_as_email="me") – Get the current Gmail signature.
set_signature(signature_html, send_as_email="me") – Set the Gmail signature (HTML tags accepted).
save_email_template(name, subject, body) – Save a reusable email template to data/email_templates.json. Use {{variable}} placeholders.
list_email_templates() – List all saved email templates.
send_from_template(template_name, to, variables={}) – Send an email using a saved template, substituting {{key}} placeholders with variables dict.
recover_deleted_emails(query="", max_results=20) – Search Trash for emails matching query and restore them to Inbox. Use when user asks to 'recover', 'restore', or 'undo delete'.
analyze_email_sentiment(message_id) – Detect tone of an email: urgent / positive / negative / neutral. No LLM required — fast keyword-based heuristic. Use before prioritizing a response.
extract_urls_from_email(message_id) – Extract all hyperlinks from an email body, classified as: links, tracking_pixels, unsubscribe_urls.
get_email_chains_summary(max_results=10) – List the most active email threads sorted by reply count. Useful for 'show me long conversations' or 'which threads need attention'.
send_completion_reminder(message_id, days=3) – Set a follow-up reminder on a sent email. Triggers a self-reminder if no reply arrives within N days.
""".strip()

_SKILL_CONTEXT = """
You are the Email Skill Agent backed by the Gmail API.
Your job is to help the user manage their Gmail inbox: read, send, draft, delete, summarise and analyse emails.
When all required fields (to, subject, body/message) are present in your instruction, call send_email or send_email_with_attachment IMMEDIATELY — do NOT ask for confirmation or clarification.
If the body/message is not explicitly specified, compose a brief, helpful message summarising the context and actions described in the instruction (e.g. "The file XYZ was zipped and uploaded to Google Drive: <link>").
If no recipient (to) is specified in your task instruction, use the Gmail address you are authenticated as — call get_inbox_count() first to resolve it if needed, but prefer to infer it from any address already mentioned in the instruction context.
When you list emails include the snippet/preview so the user can identify messages.
Prefer using message IDs returned by list_emails or get_todays_emails when calling summarize_email or extract_action_items.
If list_emails(query="in:inbox") returns zero results, retry with list_emails(query="", max_results=10) to search across all mail before concluding the inbox is empty.
For Out-of-Office / OOO / vacation responder requests: use set_vacation_responder(). Parse the user's intended date from context (e.g. "5th March" → "2026-03-05"). The body should be the message the user described. Always call get_vacation_responder() first if the user asks to check or update existing OOO.
For contact lookup: use search_contacts(query) to find a name → email mapping before sending. If the cache is empty, call sync_contacts() first.
For multi-email summarization ('summarize latest N emails from X', 'get N emails and summarize'): ALWAYS call fetch_emails_to_markdown(query="from:X", max_results=N) ONCE — this returns all email bodies in a single call. Then summarise the returned content yourself in your final answer, flagging any urgent action items (deadlines, responses required, payments, security alerts). Do NOT loop over message IDs calling summarize_email. If N > 20, tell the user the cap is 20 and ask them to reduce the number.
For unsubscribe requests: call unsubscribe_email(message_id) — first list_emails to get the message ID.
For archiving inbox: call archive_emails(query) to bulk-clear without deleting.
For thread operations: use thread_mute / thread_archive / thread_delete with the thread_id from list_emails.
For label automation: use create_smart_label_rule(label_name, from_email='...') to label + optionally archive.
For signatures: use get_signature() to read, set_signature(html) to update.
For templates: save_email_template first, then send_from_template.
For email recovery ('restore deleted email', 'I accidentally deleted'): use recover_deleted_emails(query) to find and restore from Trash.
For sentiment / priority triage: call analyze_email_sentiment(message_id) to quickly classify tone before deciding how to respond.
For extracting links from an email: use extract_urls_from_email(message_id) — returns regular links and unsubscribe URLs separately.
For showing busy threads / long conversations: use get_email_chains_summary() to rank threads by reply count.
For follow-up reminders ('remind me if they don't reply in 3 days'): use send_completion_reminder(message_id, days=N).
""".strip()


# ---------------------------------------------------------------------------
# Required entry-point
# ---------------------------------------------------------------------------

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat.

    Primary path: DAG planner (2 LLM calls regardless of task length).
    Fallback:      ReAct loop (1 LLM call per step, up to 10 iterations).
    """
    tool_map = _get_tools()
    try:
        result = run_skill_dag(
            skill_name="email",
            skill_context=_SKILL_CONTEXT,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
        # If DAG itself fell back internally that's already handled; just return.
        return result
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("email.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        return run_skill_react(
            skill_name="email",
            skill_context=_SKILL_CONTEXT,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
            max_iterations=10,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Email skill error: {exc}",
            "action": "react_response",
        }
