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
        from src.agent.manifest.context_manifest import auto_save_email_context  # noqa: PLC0415
        result = svc.list_emails(query, max_results)
        return auto_save_email_context(result, query)

    def get_inbox_count() -> dict:
        return svc.get_inbox_count()

    def get_todays_emails() -> dict:
        from src.agent.manifest.context_manifest import auto_save_email_context  # noqa: PLC0415
        result = svc.get_todays_emails()
        return auto_save_email_context(result, "today")

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
        from src.agent.manifest.context_manifest import auto_save_email_context  # noqa: PLC0415
        result = svc.fetch_emails_to_markdown(query, max_results, cap)
        # fetch_emails_to_markdown returns a dict with a 'messages' key
        msgs = result.get("messages", []) if isinstance(result, dict) else []
        auto_save_email_context(msgs, query)
        return result

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

    def write_pdf_report(path: str, title: str, content: str) -> dict:
        from src.files.features.file_ops import write_pdf_report as _wpdf  # noqa: PLC0415
        return _wpdf(path, title, content)

    def write_text_file(path: str, content: str) -> dict:
        try:
            from pathlib import Path as _Path
            _p = _Path(path).expanduser()
            _p.parent.mkdir(parents=True, exist_ok=True)
            _p.write_text(content, encoding="utf-8")
            return {"status": "success", "path": str(_p), "file_path": str(_p),
                    "message": f"Written {len(content)} chars to '{_p}'."}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def deliver_file(path: str) -> dict:
        from src.files.features.file_ops import deliver_file as _df  # noqa: PLC0415
        return _df(path)

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
        # ── NEW ────────────────────────────────────────────────────────
        "recover_deleted_emails": recover_deleted_emails,
        "analyze_email_sentiment": analyze_email_sentiment,
        "extract_urls_from_email": extract_urls_from_email,
        "get_email_chains_summary": get_email_chains_summary,
        "send_completion_reminder": send_completion_reminder,
        # ── Report / deliver (for PDF summaries) ─────────────────────────
        "write_pdf_report": write_pdf_report,
        "write_text_file": write_text_file,
        "deliver_file": deliver_file,
        # ── Context Manifest ──────────────────────────────────────────────
        "save_context": __import__(
            "src.agent.manifest.context_manifest", fromlist=["make_save_context_tool"]
        ).make_save_context_tool("email"),
    }

def _load_skill_context() -> str:
    """Load the email skill context from skill_context.md (next to this file)."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()

# ---------------------------------------------------------------------------
# Required entry-point
# ---------------------------------------------------------------------------

def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner (needs all tools to plan)."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    docs = get_all_tool_docs("email")
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("email.orchestrator").error(
            "[email-agent] skills.md returned no tools — check ui/email_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs

def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine (cosine-similarity top-K)."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    docs = load_tool_docs(
        "email", user_query, top_k=15,
        always_include=["save_context", "deliver_file", "write_pdf_report"],
    )
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("email.orchestrator").error(
            "[email-agent] FAISS returned no tool docs for query=%r — "
            "check ui/email_agent/skills.md", user_query[:60]
        )
    return docs

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
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    try:
        result = run_skill_dag(
            skill_name="email",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=dag_tool_docs,
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
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        return run_skill_react(
            skill_name="email",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=react_tool_docs,
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
