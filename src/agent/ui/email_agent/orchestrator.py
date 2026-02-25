"""
LLM-orchestrated email command executor.

execute_with_llm_orchestration() lets the LLM pick the right Gmail tool and
runs it, applying the max_operations safety cap on all bulk-fetch parameters.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

from src.agent.llm.llm_parser import get_llm_client
from src.email import (
    send_email, list_emails, get_inbox_count, get_todays_emails, delete_emails,
    extract_action_items, get_all_pending_actions,
    generate_reply_suggestions, quick_reply,
    create_draft, list_drafts, send_draft, delete_draft,
    list_attachments, download_attachment, search_emails_with_attachments,
    auto_categorize_email, apply_smart_labels,
    extract_calendar_events, suggest_calendar_entry,
    mark_for_followup, get_pending_followups, check_unanswered_emails,
    schedule_email, list_scheduled_emails, cancel_scheduled_email,
    get_frequent_contacts, get_contact_summary,
    detect_urgent_emails, auto_prioritize,
    detect_newsletters, extract_unsubscribe_link,
    get_email_stats, get_productivity_insights,
    # Phase 4
    calculate_response_time, visualize_patterns, generate_weekly_report,
    mark_action_complete, get_saved_tasks,
    create_category_rules,
    export_to_calendar,
    send_followup_reminder, mark_followup_done, dismiss_followup,
    update_scheduled_email,
    suggest_vip_contacts, export_contacts,
)

logger = logging.getLogger("email_agent")

# Skills are stateless executors — memory belongs to Personal Assistants only.

# ── Gmail tool descriptions for LLM orchestration ─────────────────────────────
# Passed to orchestrate_mcp_tool() so the LLM only sees Gmail/email tools.
_GMAIL_TOOLS_DESCRIPTION = """
1. **get_todays_messages**(max_results: int = 10)
   - Get emails received TODAY (after midnight)
   - Use for: "today", "today's emails", "emails received today"

2. **list_message**(query: str = '', max_results: int = 10)
   - List emails with Gmail search query
   - query examples: "is:unread", "from:sender@example.com", "subject:important", "after:2026/02/15", "has:attachment"
   - max_results: number of emails (1000 for "all")

3. **send_message**(to: str, subject: str, message_text: str)
   - Send an email

4. **reply_to_message**(message_id: str, reply_text: str)
   - Reply to an existing email

5. **count_messages** — use list_message with max_results=1000 and count results

6. **extract_action_items**(message_id: str)
   - Extract tasks, deadlines, and to-dos from an email using AI
   - Use for: "what do I need to do", "tasks in this email", "action items", "to-do from email"

7. **get_all_pending_actions**(max_emails: int = 20)
   - Scan recent emails for all pending action items
   - Use for: "what tasks do I have", "pending actions across emails"

8. **generate_reply_suggestions**(message_id: str)
   - Generate 3 AI reply suggestions (brief, professional, detailed)
   - Use for: "suggest reply", "how should I reply", "draft a response"

9. **quick_reply**(message_id: str, reply_type: str)
   - Send a quick pre-built reply. reply_type: yes/no/thanks/acknowledged/more_info_needed/on_it/meeting_confirm/meeting_decline
   - Use for: "reply yes", "send thanks", "acknowledge email"

10. **create_draft**(to: str, subject: str, body: str)
    - Save an email as a draft
    - Use for: "save as draft", "create draft", "draft email to X"

11. **list_drafts**(max_results: int = 10)
    - List all saved drafts
    - Use for: "show drafts", "list my drafts", "what drafts do I have"

12. **send_draft**(draft_id: str)
    - Send a saved draft
    - Use for: "send draft", "send my draft"

13. **delete_draft**(draft_id: str)
    - Delete a saved draft

14. **list_attachments**(message_id: str)
    - List all attachments in an email
    - Use for: "what attachments", "files in email", "show attachments"

15. **download_attachment**(message_id: str, attachment_id: str, filename: str)
    - Download an attachment to disk
    - Use for: "download attachment", "save file from email"

16. **search_emails_with_attachments**(file_type: str = 'all')
    - Find emails with attachments. file_type: pdf/doc/spreadsheet/image/zip/all
    - Use for: "emails with PDFs", "find attachments", "emails with files"

17. **auto_categorize_email**(message_id: str)
    - Categorize an email (work/personal/bills/newsletters/social/notifications/spam)
    - Use for: "categorize email", "what category is this email"

18. **apply_smart_labels**(batch_size: int = 20)
    - Auto-categorize and apply Gmail labels to recent emails
    - Use for: "organize emails", "label emails", "auto-label inbox"

19. **extract_calendar_events**(message_id: str)
    - Extract meeting and calendar event info from an email
    - Use for: "find meeting details", "extract event", "calendar from email", "when is the meeting"

20. **suggest_calendar_entry**(message_id: str)
    - Suggest a calendar entry based on email content

21. **mark_for_followup**(message_id: str, days: int = 3, note: str = '')
    - Mark an email for follow-up reminder after N days
    - Use for: "remind me to follow up", "follow up in 3 days", "set reminder"

22. **get_pending_followups**()
    - List all pending follow-up reminders
    - Use for: "what follow-ups do I have", "pending follow-ups", "show reminders"

23. **check_unanswered_emails**(older_than_days: int = 3)
    - Find sent emails that haven't received a reply yet
    - Use for: "unanswered emails", "no reply", "waiting for response"

24. **schedule_email**(to: str, subject: str, body: str, send_time: str)
    - Schedule email to be sent later. send_time as ISO string or natural language ("tomorrow 9am")
    - Use for: "schedule email", "send later", "send tomorrow at 9am"

25. **list_scheduled_emails**()
    - Show all scheduled (pending) emails
    - Use for: "show scheduled emails", "what emails are queued"

26. **cancel_scheduled_email**(scheduled_id: str)
    - Cancel a scheduled email
    - Use for: "cancel scheduled email", "don't send that email"

27. **get_frequent_contacts**(limit: int = 10)
    - Get top email contacts by interaction frequency
    - Use for: "who do I email most", "frequent contacts", "top contacts"

28. **get_contact_summary**(email_address: str)
    - Get interaction stats for a specific contact
    - Use for: "how many emails from X", "contact summary for X"

29. **detect_urgent_emails**(max_results: int = 20)
    - Find high-priority and urgent emails using AI
    - Use for: "urgent emails", "important emails", "priority inbox", "what needs attention"

30. **auto_prioritize**(message_id: str)
    - Score the urgency/priority of a specific email (1-10)
    - Use for: "how urgent is this email", "priority score", "is this important"

31. **detect_newsletters**(max_results: int = 30)
    - Detect newsletters and promotional emails in inbox
    - Use for: "find newsletters", "promo emails", "subscription emails"

32. **extract_unsubscribe_link**(message_id: str)
    - Extract the unsubscribe link/URL from an email
    - Use for: "how to unsubscribe", "unsubscribe link", "opt out"

33. **get_email_stats**(days: int = 30)
    - Get email volume statistics (received, sent, top senders, busiest day)
    - Use for: "email stats", "how many emails", "email analytics", "statistics"

34. **get_productivity_insights**()
    - Generate productivity insights and suggestions based on email patterns
    - Use for: "email insights", "productivity", "email habits", "email patterns"

35. **mark_action_complete**(task_id: str)
    - Mark a saved action item/task as completed
    - Use for: "mark task done", "complete task", "task completed", "done with task [id]"

36. **get_saved_tasks**(status_filter: str = 'pending')
    - List saved action items. status_filter: 'pending', 'done', 'all'
    - Use for: "show my tasks", "saved tasks", "pending action items", "completed tasks"

37. **create_category_rules**()
    - Create Gmail filters based on patterns from already-categorized emails
    - Use for: "create email rules", "auto-filter emails", "create Gmail filters", "learn email rules"

38. **export_to_calendar**(event_data: dict, save_ics: bool = True)
    - Export a detected event to Google Calendar and/or save as .ics file
    - Use for: "add to calendar", "export to calendar", "save event", "create calendar event", "download ics"

39. **send_followup_reminder**(message_id: str)
    - Send an email reminder to yourself about a tracked follow-up
    - Use for: "send reminder", "remind me now", "send follow-up reminder", "email me about this"

40. **mark_followup_done**(message_id: str)
    - Mark a follow-up as completed
    - Use for: "mark follow-up done", "follow-up complete", "done following up"

41. **dismiss_followup**(message_id: str)
    - Dismiss a follow-up (mark as no longer needed)
    - Use for: "dismiss follow-up", "ignore follow-up", "cancel reminder"

42. **update_scheduled_email**(scheduled_id: str, send_time: str)
    - Reschedule a pending scheduled email to a new send time
    - Use for: "reschedule email", "change scheduled time", "update send time", "move scheduled email"

43. **suggest_vip_contacts**()
    - Return contacts with high interaction frequency (VIP)
    - Use for: "VIP contacts", "most important contacts", "key contacts", "top contacts VIP"

44. **export_contacts**(format: str = 'csv', limit: int = 100)
    - Export contact intelligence data to CSV or JSON
    - Use for: "export contacts", "download contacts", "save contacts to file", "contacts csv"

45. **calculate_response_time**(message_id: str)
    - Calculate how quickly you responded to a specific email
    - Use for: "response time", "how fast did I reply", "when did I respond to this"

46. **visualize_patterns**(days: int = 30)
    - Generate chart-ready data for email pattern visualization
    - Use for: "email charts", "visualize email patterns", "email graphs", "show email data chart"

47. **generate_weekly_report**()
    - Generate a comprehensive weekly email activity report
    - Use for: "weekly report", "email report", "weekly summary", "weekly email stats", "this week's email activity"

IMPORTANT TEMPORAL LOGIC:
- "today" / "today's" / "received today" → use get_todays_messages()
- "this week" / "last week" → use list_message with after: query
- "from [person]" → use list_message with query="from:email"
- "count" requests → use list_message with high max_results

Examples:
"Count emails I received today" → {"tool": "get_todays_messages", "params": {"max_results": 1000}, "reasoning": "User wants today's emails for counting"}
"List 5 unread emails" → {"tool": "list_message", "params": {"query": "is:unread", "max_results": 5}, "reasoning": "User wants unread messages"}
"Show me urgent emails" → {"tool": "detect_urgent_emails", "params": {"max_results": 20}, "reasoning": "User wants priority/urgent emails"}
"Schedule email to john@example.com for tomorrow 9am" → {"tool": "schedule_email", "params": {"to": "john@example.com", "subject": "", "body": "", "send_time": "tomorrow 9am"}, "reasoning": "User wants to schedule an email"}
"""


def _observation_from_result(result: Dict[str, Any], tool_name: str) -> str:
    """Convert a tool result dict into a readable observation string for the ReAct loop."""
    import json as _json

    if result.get("status") == "error":
        return f"Error: {result.get('message', 'Unknown error')}"

    # Email list results — include IDs so the LLM can chain tool calls
    emails = result.get("emails", [])
    if emails:
        lines = [f"Retrieved {len(emails)} email(s):"]
        for i, e in enumerate(emails[:20], 1):
            # key is 'sender' from list_emails, but fall back to 'from'
            sender = e.get('sender') or e.get('from') or 'Unknown'
            lines.append(
                f"[{i}] ID: {e.get('id', '?')} | "
                f"From: {sender} | "
                f"Subject: {e.get('subject', '(no subject)')} | "
                f"Date: {e.get('date', '?')}"
            )
            snippet = (e.get("snippet") or "")[:120]
            if snippet:
                lines.append(f"     Preview: {snippet}")
        return "\n".join(lines)

    # Simple count
    if "count" in result and len(result) <= 4:
        return f"Count: {result['count']} email(s)"

    # Inbox stats
    if "total_messages" in result:
        return (
            f"Inbox stats — Total: {result['total_messages']}, "
            f"Unread: {result.get('unread_messages', '?')}, "
            f"Threads: {result.get('total_threads', '?')}"
        )

    # Generic — serialise everything except large lists
    compact = {
        k: v for k, v in result.items()
        if k not in ("status",) and not isinstance(v, list)
    }
    list_summaries = {
        k: f"[{len(v)} items]"
        for k, v in result.items()
        if isinstance(v, list) and k != "emails"
    }
    compact.update(list_summaries)
    return _json.dumps(compact, default=str)[:600]


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str = None,
    max_operations: int = 100,
    artifacts_out: dict = None,
) -> Dict[str, Any]:
    """
    Execute email commands using a Thought-Action-Observation (ReAct) loop.

    ``artifacts_out`` — optional dict populated by the call with any produced
    artifacts (reserved for future use; email agent does not produce file paths).

    The LLM reasons freely across as many steps as needed:
      Thought -> Action (tool call) -> Observation (result) -> Thought -> ...
    until it produces a final_answer.  This handles multi-step tasks naturally,
    e.g. "reply to the most recent email from John" will:
      1. list emails from John  ->  observe ID
      2. call reply_to_message  ->  observe success
      3. write final_answer

    Args:
        user_query:     Natural language task from the user.
        agent_id:       Agent ID for memory context.
        max_operations: Safety cap on bulk API operations per tool call.
    """
    try:
        # ── Gmail auth preflight ─────────────────────────────────────────────
        # Verify credentials before starting the ReAct loop so auth errors
        # surface as a structured auth_error status the PA UI can act on.
        try:
            from src.email.gmail_service import _get_client as _gmail_client
            _gmail_client()  # raises if auth fails
        except Exception as _auth_exc:
            _msg = str(_auth_exc).lower()
            if any(p in _msg for p in ("authorization", "credentials", "token", "oauth", "auth")):
                return {
                    "status": "auth_error",
                    "message": (
                        "🔑 Gmail is not authorized yet (or the token has expired).\n\n"
                        "Click **Re-authorize Gmail** below to open a browser sign-in window, "
                        "then retry your request."
                    ),
                }
            raise  # unexpected error — let the outer except handle it

        # Skills are stateless — zero memory injection
        memory_context = ""

        # ── Tool executor used by the ReAct loop ────────────────────────────
        _ops_capped_note = ""

        def _clamp(value, fallback: int = 10) -> int:
            nonlocal _ops_capped_note
            try:
                v = int(value)
            except (TypeError, ValueError):
                v = fallback
            effective = min(v, max_operations)
            if effective < v:
                _ops_capped_note = (
                    f"\n\n⚠️ *Results capped at {effective} (max operations limit).*"
                )
            return effective

        def _dispatch(tool_name: str, params: dict) -> str:
            """Execute one Gmail tool and return a readable observation string."""
            result: Dict[str, Any] = {
                "status": "error", "message": f"Unknown tool: {tool_name}"
            }

            if tool_name == "get_todays_messages":
                emails = get_todays_emails(
                    max_results=_clamp(params.get("max_results", 1000), 1000))
                result = {"status": "success", "emails": emails, "count": len(emails)}

            elif tool_name == "list_message":
                emails = list_emails(
                    query=params.get("query", ""),
                    max_results=_clamp(params.get("max_results", 10), 10))
                result = {"status": "success", "emails": emails, "count": len(emails)}

            elif tool_name == "count_messages":
                emails = list_emails(
                    query=params.get("query", ""),
                    max_results=_clamp(1000, 1000))
                result = {"status": "success", "count": len(emails),
                          "query": params.get("query", "")}

            elif tool_name == "send_message":
                result = send_email(
                    to=params.get("to", ""),
                    subject=params.get("subject", "(No Subject)"),
                    message=params.get("message_text", ""),
                )

            elif tool_name == "extract_action_items":
                result = extract_action_items(params.get("message_id", ""))

            elif tool_name == "get_all_pending_actions":
                result = get_all_pending_actions(
                    _clamp(params.get("max_emails", 20), 20))

            elif tool_name == "generate_reply_suggestions":
                result = generate_reply_suggestions(
                    params.get("message_id", ""), params.get("tone", "all"))

            elif tool_name == "quick_reply":
                result = quick_reply(
                    params.get("message_id", ""),
                    params.get("reply_type", "acknowledged"))

            elif tool_name == "create_draft":
                result = create_draft(
                    params.get("to", ""), params.get("subject", ""),
                    params.get("body", ""))

            elif tool_name == "list_drafts":
                result = list_drafts(_clamp(params.get("max_results", 10), 10))

            elif tool_name == "send_draft":
                result = send_draft(params.get("draft_id", ""))

            elif tool_name == "delete_draft":
                result = delete_draft(params.get("draft_id", ""))

            elif tool_name == "list_attachments":
                result = list_attachments(params.get("message_id", ""))

            elif tool_name == "download_attachment":
                result = download_attachment(
                    params.get("message_id", ""),
                    params.get("attachment_id", ""),
                    params.get("filename", "attachment"),
                    params.get("save_path"),
                )

            elif tool_name == "search_emails_with_attachments":
                result = search_emails_with_attachments(
                    params.get("file_type", "all"),
                    _clamp(params.get("max_results", 10), 10))

            elif tool_name == "auto_categorize_email":
                result = auto_categorize_email(params.get("message_id", ""))

            elif tool_name == "apply_smart_labels":
                result = apply_smart_labels(
                    _clamp(params.get("batch_size", 20), 20))

            elif tool_name == "extract_calendar_events":
                result = extract_calendar_events(params.get("message_id", ""))

            elif tool_name == "suggest_calendar_entry":
                result = suggest_calendar_entry(params.get("message_id", ""))

            elif tool_name == "mark_for_followup":
                result = mark_for_followup(
                    params.get("message_id", ""),
                    params.get("days", 3),
                    params.get("note", ""))

            elif tool_name == "get_pending_followups":
                result = get_pending_followups()

            elif tool_name == "check_unanswered_emails":
                result = check_unanswered_emails(
                    params.get("older_than_days", 3))

            elif tool_name == "schedule_email":
                result = schedule_email(
                    params.get("to", ""), params.get("subject", ""),
                    params.get("body", ""), params.get("send_time", ""))

            elif tool_name == "list_scheduled_emails":
                result = list_scheduled_emails()

            elif tool_name == "cancel_scheduled_email":
                result = cancel_scheduled_email(
                    params.get("scheduled_id", ""))

            elif tool_name == "get_frequent_contacts":
                result = get_frequent_contacts(
                    _clamp(params.get("limit", 10), 10))

            elif tool_name == "get_contact_summary":
                result = get_contact_summary(params.get("email_address", ""))

            elif tool_name == "detect_urgent_emails":
                result = detect_urgent_emails(
                    _clamp(params.get("max_results", 20), 20))

            elif tool_name == "auto_prioritize":
                result = auto_prioritize(params.get("message_id", ""))

            elif tool_name == "detect_newsletters":
                result = detect_newsletters(
                    _clamp(params.get("max_results", 30), 30))

            elif tool_name == "extract_unsubscribe_link":
                result = extract_unsubscribe_link(params.get("message_id", ""))

            elif tool_name == "get_email_stats":
                result = get_email_stats(params.get("days", 30))

            elif tool_name == "get_productivity_insights":
                result = get_productivity_insights()

            elif tool_name == "mark_action_complete":
                result = mark_action_complete(params.get("task_id", ""))

            elif tool_name == "get_saved_tasks":
                result = get_saved_tasks(
                    params.get("status_filter", "pending"))

            elif tool_name == "create_category_rules":
                result = create_category_rules(
                    int(params.get("min_occurrences", 3)))

            elif tool_name == "export_to_calendar":
                result = export_to_calendar(
                    params.get("event_data", {}),
                    bool(params.get("save_ics", True)))

            elif tool_name == "send_followup_reminder":
                result = send_followup_reminder(params.get("message_id", ""))

            elif tool_name == "mark_followup_done":
                result = mark_followup_done(params.get("message_id", ""))

            elif tool_name == "dismiss_followup":
                result = dismiss_followup(params.get("message_id", ""))

            elif tool_name == "update_scheduled_email":
                result = update_scheduled_email(
                    params.get("scheduled_id", ""),
                    params.get("send_time", ""))

            elif tool_name == "suggest_vip_contacts":
                result = suggest_vip_contacts()

            elif tool_name == "export_contacts":
                result = export_contacts(
                    params.get("format", "csv"),
                    int(params.get("limit", 100)))

            elif tool_name == "calculate_response_time":
                result = calculate_response_time(params.get("message_id", ""))

            elif tool_name == "visualize_patterns":
                result = visualize_patterns(int(params.get("days", 30)))

            elif tool_name == "generate_weekly_report":
                result = generate_weekly_report()

            return _observation_from_result(result, tool_name)

        # ── Run the ReAct loop ───────────────────────────────────────────────
        llm = get_llm_client()
        final_answer = llm.reason_and_act(
            user_query,
            _GMAIL_TOOLS_DESCRIPTION,
            _dispatch,
            memory_context,
        )
        return {"status": "success", "action": "react_response",
                "message": final_answer}

    except Exception as e:
        logger.error(f"Error in ReAct orchestration: {e}")
        return {
            "status": "error",
            "message": "I had trouble completing that request. Please try rephrasing.",
        }

