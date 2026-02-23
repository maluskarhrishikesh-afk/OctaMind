"""
LLM-orchestrated WhatsApp command executor.

execute_with_llm_orchestration() lets the LLM pick the right WhatsApp tool
and runs it, applying the max_operations safety cap on bulk-fetch parameters.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

from src.agent.llm.llm_parser import get_llm_client
from src.whatsapp import (
    send_message, send_media, send_template, reply_to_message,
    get_messages, get_unread_messages, mark_as_read,
    list_contacts, get_contact_info, get_frequent_contacts, set_contact_name,
    list_groups, get_group_info, get_group_messages,
    search_messages, get_conversation, get_messages_by_date, get_media_messages,
    summarize_conversation, extract_action_items, draft_message, generate_reply,
    detect_urgent_messages, extract_key_info, translate_message, sentiment_analysis,
    schedule_message, list_scheduled_messages, cancel_scheduled_message,
    set_auto_reply, get_auto_reply_config,
    get_message_stats, get_response_time, get_activity_report, get_top_senders,
    forward_to_email, share_drive_file,
)

logger = logging.getLogger("whatsapp_agent")

# Optional memory integration
try:
    from src.agent.memory.agent_memory import get_agent_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False

# ── WhatsApp tool descriptions for LLM orchestration ─────────────────────────
_WHATSAPP_TOOLS_DESCRIPTION = """
## Core Messaging

1. **send_message**(to: str, body: str)
   - Send a plain text WhatsApp message
   - to: phone in E.164 format e.g. '919876543210' (country code + number, no + or spaces)
   - Use for: "send whatsapp to X", "message X saying Y", "text X"

2. **send_media**(to: str, media_type: str, url: str, caption: str = "", filename: str = "")
   - Send media: image, video, audio, document, sticker
   - media_type: 'image' | 'video' | 'audio' | 'document' | 'sticker'
   - url: Public HTTPS URL of the media file
   - Use for: "send image to X", "share document with Y", "send photo"

3. **send_template**(to: str, template_name: str, language_code: str = "en_US")
   - Send a pre-approved WhatsApp Business template message
   - Use for: "send template X to Y", "send business template"

4. **reply_to_message**(to: str, original_message_id: str, body: str)
   - Reply to a specific message (sends as a quoted reply)
   - Use for: "reply to message <id>", "respond to that message"

5. **get_messages**(limit: int = 20)
   - Get recent WhatsApp messages (inbound + outbound)
   - Use for: "show messages", "recent whatsapp messages", "what's in my whatsapp"

6. **get_unread_messages**(limit: int = 20)
   - Get unread inbound messages
   - Use for: "unread messages", "what did I miss", "new messages"

7. **mark_as_read**(message_id: str)
   - Mark a message as read (sends read receipt)
   - Use for: "mark message as read", "read receipt for <id>"

## Contacts & Groups

8. **list_contacts**(limit: int = 50)
   - List all known WhatsApp contacts
   - Use for: "show contacts", "list my whatsapp contacts", "who have I chatted with"

9. **get_contact_info**(phone: str)
   - Get details + recent messages for a specific contact
   - Use for: "info about <phone>", "contact details for X"

10. **get_frequent_contacts**(limit: int = 10)
    - Get most active contacts by message volume
    - Use for: "who do I message most", "frequent contacts", "top contacts"

11. **set_contact_name**(phone: str, name: str)
    - Set/update display name for a contact
    - Use for: "name <phone> as X", "label contact", "set name for X"

12. **list_groups**(limit: int = 50)
    - List all known WhatsApp groups
    - Use for: "show groups", "list my whatsapp groups"

13. **get_group_info**(group_id: str)
    - Get group metadata (subject, participants)
    - Use for: "info about group <id>", "group details"

14. **get_group_messages**(group_id: str, limit: int = 30)
    - Get recent messages from a group
    - Use for: "messages in group <id>", "what's in the group chat"

## Search & Retrieval

15. **search_messages**(query: str, limit: int = 20)
    - Full-text search across all messages
    - Use for: "search for X in messages", "find messages about Y", "messages containing X"

16. **get_conversation**(phone: str, limit: int = 30)
    - Get full conversation thread with a contact
    - Use for: "conversation with <phone>", "chat history with X", "thread with X"

17. **get_messages_by_date**(start_date: str, end_date: str = None, limit: int = 50)
    - Get messages within a date range (YYYY-MM-DD format)
    - Use for: "messages from last week", "messages between X and Y date", "messages on Monday"

18. **get_media_messages**(limit: int = 30)
    - Get messages containing media attachments
    - Use for: "media messages", "images received", "videos in whatsapp", "documents shared"

## AI Smart Features

19. **summarize_conversation**(phone: str, limit: int = 30)
    - AI summary of conversation with a contact
    - Use for: "summarize chat with X", "what did we talk about with X", "conversation summary"

20. **extract_action_items**(phone: str, limit: int = 20)
    - Extract tasks and to-dos from recent messages
    - Use for: "action items from X", "tasks in chat with X", "what do I need to do from conversation"

21. **draft_message**(to: str, context: str)
    - AI-draft a WhatsApp message based on context
    - Use for: "draft message to X about Y", "write a message saying Z", "help me write to X"

22. **generate_reply**(message_id: str)
    - Suggest 3 reply options for a specific message
    - Use for: "how should I reply to <id>", "suggest reply", "reply options for message"

23. **detect_urgent_messages**(limit: int = 30)
    - Identify urgent messages using AI
    - Use for: "urgent messages", "what needs attention", "important unread", "priority messages"

24. **extract_key_info**(message_id: str)
    - Extract names, dates, phones, links from a message
    - Use for: "key info in message <id>", "extract details", "what's in this message"

25. **translate_message**(message_id: str, target_language: str = "English")
    - Translate a message to another language
    - Use for: "translate message <id>", "translate to Hindi", "what does this say in English"

26. **sentiment_analysis**(phone: str, limit: int = 20)
    - Analyse sentiment of recent messages with a contact
    - Use for: "sentiment of chat with X", "is X happy with me", "mood in conversation"

## Scheduling

27. **schedule_message**(to: str, body: str, send_time: str)
    - Schedule a message for future delivery
    - send_time: ISO string or natural language ('tomorrow 9am', 'Friday 3pm')
    - Use for: "schedule message to X for tomorrow", "send at 9am", "message X later"

28. **list_scheduled_messages**()
    - Show all pending scheduled messages
    - Use for: "show scheduled messages", "what messages are queued", "pending sends"

29. **cancel_scheduled_message**(scheduled_id: str)
    - Cancel a pending scheduled message
    - Use for: "cancel scheduled message <id>", "don't send that message"

30. **set_auto_reply**(enabled: bool, message: str = "")
    - Enable/disable automatic reply to all inbound messages
    - Use for: "enable auto-reply", "set auto-reply to X", "turn off auto-reply"

## Analytics

31. **get_message_stats**(days: int = 30)
    - Message volume statistics for past N days
    - Use for: "whatsapp stats", "message count", "analytics", "how many messages"

32. **get_response_time**(phone: str)
    - Calculate average response time to a specific contact
    - Use for: "how fast do I reply to X", "response time for X", "reply speed"

33. **get_activity_report**(days: int = 7)
    - Activity patterns by hour and day of week
    - Use for: "activity report", "when am I most active", "busy hours", "messaging patterns"

34. **get_top_senders**(limit: int = 10)
    - Most active senders
    - Use for: "who messages me most", "top senders", "busiest contacts"

## Cross-Agent

35. **forward_to_email**(message_id: str, to_email: str, subject: str = None)
    - Forward a WhatsApp message to an email address
    - Use for: "forward to email", "email this message to X", "send to email"

36. **share_drive_file**(to: str, file_id: str, message: str = None)
    - Share a Google Drive file link via WhatsApp
    - Use for: "share drive file with X", "send google drive link", "whatsapp the file"

IMPORTANT ROUTING HINTS:
- Phone numbers must be in E.164 format: country code + number, no + or spaces
  e.g. '919876543210' for India, '14155552671' for US
- "unread" → use get_unread_messages()
- "recent/latest/new" → use get_messages()
- "chat/conversation/thread with X" → use get_conversation(phone=X)
- "search/find" → use search_messages(query=...)
- "summary/summarize" → use summarize_conversation()
- "draft/write/help me say" → use draft_message()
- "translate" → use translate_message()
- "urgent/important" → use detect_urgent_messages()
- "stats/analytics/count" → use get_message_stats()

Examples:
"Send hi to 919876543210" → {"tool": "send_message", "params": {"to": "919876543210", "body": "hi"}}
"Show unread messages" → {"tool": "get_unread_messages", "params": {"limit": 20}}
"Summarize my chat with 919876543210" → {"tool": "summarize_conversation", "params": {"phone": "919876543210"}}
"Schedule message to 14155552671 for tomorrow 9am saying Good morning" → {"tool": "schedule_message", "params": {"to": "14155552671", "body": "Good morning", "send_time": "tomorrow 9am"}}
"""


def _observation_from_result(result: Dict[str, Any], tool_name: str) -> str:
    """Convert a tool result dict into a readable observation string for the ReAct loop."""
    import json as _json

    if result.get("status") == "error":
        return f"Error: {result.get('message', 'Unknown error')}"

    # Message list results
    messages = result.get("messages", [])
    if messages and isinstance(messages, list):
        count = result.get("count", len(messages))
        lines = [f"Retrieved {count} message(s):"]
        for i, m in enumerate(messages[:20], 1):
            direction = "→" if m.get("direction") == "outbound" else "←"
            phone = m.get("from") or m.get("to") or "?"
            ts = m.get("timestamp", "")[:16].replace("T", " ")
            body = (m.get("body") or "")[:100]
            msg_type = m.get("type", "text")
            lines.append(
                f"[{i}] ID: {m.get('id', '?')} | "
                f"{direction} {phone} | "
                f"Type: {msg_type} | "
                f"Time: {ts}"
            )
            if body:
                lines.append(f"     Body: {body}")
        return "\n".join(lines)

    # Contact list results
    contacts = result.get("contacts", [])
    if contacts and isinstance(contacts, list):
        lines = [f"Retrieved {len(contacts)} contact(s):"]
        for i, c in enumerate(contacts[:20], 1):
            lines.append(
                f"[{i}] {c.get('name', c.get('phone', '?'))} | "
                f"Phone: {c.get('phone', '?')} | "
                f"Messages: {c.get('message_count', 0)} | "
                f"Last seen: {c.get('last_seen', '?')[:10]}"
            )
        return "\n".join(lines)

    # Groups list
    groups = result.get("groups", [])
    if groups and isinstance(groups, list):
        lines = [f"Retrieved {len(groups)} group(s):"]
        for i, g in enumerate(groups[:10], 1):
            lines.append(
                f"[{i}] ID: {g.get('id', '?')} | "
                f"Subject: {g.get('subject', '?')} | "
                f"First seen: {g.get('first_seen', '?')[:10]}"
            )
        return "\n".join(lines)

    # AI text results (summary, analysis, etc.)
    for key in ("summary", "action_items", "urgent_analysis", "sentiment_analysis",
                "key_info", "translated", "suggestions", "draft"):
        if key in result:
            return str(result[key])

    # Simple success messages
    if "message" in result and len(result) <= 5:
        return result["message"]

    # Generic — serialise compactly
    compact = {
        k: v for k, v in result.items()
        if k not in ("status", "messages", "contacts", "groups")
        and not isinstance(v, (list, dict))
    }
    list_summaries = {
        k: f"[{len(v)} items]"
        for k, v in result.items()
        if isinstance(v, list) and k not in ("messages", "contacts", "groups")
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
    Execute WhatsApp commands using a Thought-Action-Observation (ReAct) loop.

    The LLM reasons and selects the right WhatsApp tool, executes it,
    observes the result, and continues until a final_answer is produced.

    Args:
        user_query:     Natural language task from the user.
        agent_id:       Agent ID for memory context.
        max_operations: Safety cap on bulk API operations per tool call.
    """
    try:
        # ── Memory context ──────────────────────────────────────────────────
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
            except Exception:
                pass

        # ── Safety cap helper ────────────────────────────────────────────────
        _ops_capped_note = ""

        def _clamp(value, fallback: int = 20) -> int:
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

        # ── Tool dispatcher ──────────────────────────────────────────────────
        def _dispatch(tool_name: str, params: dict) -> str:
            result: Dict[str, Any] = {
                "status": "error", "message": f"Unknown tool: {tool_name}"
            }

            # ── Core Messaging ──────────────────────────────────────────────
            if tool_name == "send_message":
                result = send_message(
                    to=params.get("to", ""),
                    body=params.get("body", ""),
                )

            elif tool_name == "send_media":
                result = send_media(
                    to=params.get("to", ""),
                    media_type=params.get("media_type", "image"),
                    url=params.get("url", ""),
                    caption=params.get("caption", ""),
                    filename=params.get("filename", ""),
                )

            elif tool_name == "send_template":
                result = send_template(
                    to=params.get("to", ""),
                    template_name=params.get("template_name", ""),
                    language_code=params.get("language_code", "en_US"),
                )

            elif tool_name == "reply_to_message":
                result = reply_to_message(
                    to=params.get("to", ""),
                    original_message_id=params.get("original_message_id", ""),
                    body=params.get("body", ""),
                )

            elif tool_name == "get_messages":
                result = get_messages(
                    limit=_clamp(params.get("limit", 20), 20),
                )

            elif tool_name == "get_unread_messages":
                result = get_unread_messages(
                    limit=_clamp(params.get("limit", 20), 20),
                )

            elif tool_name == "mark_as_read":
                result = mark_as_read(
                    message_id=params.get("message_id", ""),
                )

            # ── Contacts ────────────────────────────────────────────────────
            elif tool_name == "list_contacts":
                result = list_contacts(
                    limit=_clamp(params.get("limit", 50), 50),
                )

            elif tool_name == "get_contact_info":
                result = get_contact_info(
                    phone=params.get("phone", ""),
                )

            elif tool_name == "get_frequent_contacts":
                result = get_frequent_contacts(
                    limit=_clamp(params.get("limit", 10), 10),
                )

            elif tool_name == "set_contact_name":
                result = set_contact_name(
                    phone=params.get("phone", ""),
                    name=params.get("name", ""),
                )

            # ── Groups ──────────────────────────────────────────────────────
            elif tool_name == "list_groups":
                result = list_groups(
                    limit=_clamp(params.get("limit", 50), 50),
                )

            elif tool_name == "get_group_info":
                result = get_group_info(
                    group_id=params.get("group_id", ""),
                )

            elif tool_name == "get_group_messages":
                result = get_group_messages(
                    group_id=params.get("group_id", ""),
                    limit=_clamp(params.get("limit", 30), 30),
                )

            # ── Search ──────────────────────────────────────────────────────
            elif tool_name == "search_messages":
                result = search_messages(
                    query=params.get("query", ""),
                    limit=_clamp(params.get("limit", 20), 20),
                )

            elif tool_name == "get_conversation":
                result = get_conversation(
                    phone=params.get("phone", ""),
                    limit=_clamp(params.get("limit", 30), 30),
                )

            elif tool_name == "get_messages_by_date":
                result = get_messages_by_date(
                    start_date=params.get("start_date", ""),
                    end_date=params.get("end_date"),
                    limit=_clamp(params.get("limit", 50), 50),
                )

            elif tool_name == "get_media_messages":
                result = get_media_messages(
                    limit=_clamp(params.get("limit", 30), 30),
                )

            # ── Smart Features ──────────────────────────────────────────────
            elif tool_name == "summarize_conversation":
                result = summarize_conversation(
                    phone=params.get("phone", ""),
                    limit=_clamp(params.get("limit", 30), 30),
                )

            elif tool_name == "extract_action_items":
                result = extract_action_items(
                    phone=params.get("phone", ""),
                    limit=_clamp(params.get("limit", 20), 20),
                )

            elif tool_name == "draft_message":
                result = draft_message(
                    to=params.get("to", ""),
                    context=params.get("context", ""),
                )

            elif tool_name == "generate_reply":
                result = generate_reply(
                    message_id=params.get("message_id", ""),
                )

            elif tool_name == "detect_urgent_messages":
                result = detect_urgent_messages(
                    limit=_clamp(params.get("limit", 30), 30),
                )

            elif tool_name == "extract_key_info":
                result = extract_key_info(
                    message_id=params.get("message_id", ""),
                )

            elif tool_name == "translate_message":
                result = translate_message(
                    message_id=params.get("message_id", ""),
                    target_language=params.get("target_language", "English"),
                )

            elif tool_name == "sentiment_analysis":
                result = sentiment_analysis(
                    phone=params.get("phone", ""),
                    limit=_clamp(params.get("limit", 20), 20),
                )

            # ── Scheduler ───────────────────────────────────────────────────
            elif tool_name == "schedule_message":
                result = schedule_message(
                    to=params.get("to", ""),
                    body=params.get("body", ""),
                    send_time=params.get("send_time", ""),
                )

            elif tool_name == "list_scheduled_messages":
                result = list_scheduled_messages()

            elif tool_name == "cancel_scheduled_message":
                result = cancel_scheduled_message(
                    scheduled_id=params.get("scheduled_id", ""),
                )

            elif tool_name == "set_auto_reply":
                result = set_auto_reply(
                    enabled=bool(params.get("enabled", False)),
                    message=params.get("message", ""),
                )

            # ── Analytics ───────────────────────────────────────────────────
            elif tool_name == "get_message_stats":
                result = get_message_stats(
                    days=int(params.get("days", 30)),
                )

            elif tool_name == "get_response_time":
                result = get_response_time(
                    phone=params.get("phone", ""),
                )

            elif tool_name == "get_activity_report":
                result = get_activity_report(
                    days=int(params.get("days", 7)),
                )

            elif tool_name == "get_top_senders":
                result = get_top_senders(
                    limit=_clamp(params.get("limit", 10), 10),
                )

            # ── Cross-Agent ─────────────────────────────────────────────────
            elif tool_name == "forward_to_email":
                result = forward_to_email(
                    message_id=params.get("message_id", ""),
                    to_email=params.get("to_email", ""),
                    subject=params.get("subject"),
                )

            elif tool_name == "share_drive_file":
                result = share_drive_file(
                    to=params.get("to", ""),
                    file_id=params.get("file_id", ""),
                    message=params.get("message"),
                )

            return _observation_from_result(result, tool_name)

        # ── Run the ReAct loop ───────────────────────────────────────────────
        llm = get_llm_client()
        final_answer = llm.reason_and_act(
            user_query,
            _WHATSAPP_TOOLS_DESCRIPTION,
            _dispatch,
            memory_context,
        )
        return {
            "status": "success",
            "action": "react_response",
            "message": final_answer,
        }

    except Exception as e:
        logger.error("Error in WhatsApp ReAct orchestration: %s", e)
        return {
            "status": "error",
            "message": "I had trouble completing that request. Please try rephrasing.",
        }
