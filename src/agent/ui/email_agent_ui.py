"""
Email Agent with LLM-orchestrated natural language interface

This agent uses LLM (GitHub Models GPT-4o-mini) to intelligently understand
natural language commands and execute email operations through tool orchestration.
"""

# Setup logging properly using Python's logging module
import logging
import os
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
import streamlit as st
from typing import Dict, Any
from datetime import datetime
import dateutil.parser
import base64 as _base64
from pathlib import Path
from src.agent.llm.llm_parser import get_llm_client
import sys

# Setup logger
logger = logging.getLogger("email_agent")
logger.setLevel(logging.DEBUG)

# Create handlers
log_file = Path(__file__).parent.parent.parent / "email_agent.log"
file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)

# Create console handler (will gracefully handle closed stdout)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Setup path FIRST before any imports
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

# Import LLM client for orchestration

# Try to import agent memory (optional)
try:
    from src.agent.memory.agent_memory import get_agent_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False


def handle_conversation(message: str, agent_id: str = None, agent_name: str = None) -> str | None:
    """
    Handle general conversational messages using LLM with memory context.
    Returns a response string if the message is conversational, or None if it should be treated as an email command.
    """
    msg = message.strip().lower()

    # If message contains email-specific actions, let the LLM orchestrator handle it
    has_action_word = any(keyword in msg for keyword in [
        'count', 'list', 'show', 'send', 'delete', 'summarize', 'digest',
        'fetch', 'get', 'retrieve', 'find', 'read', 'check', 'view', 'display',
        'draft', 'attachment', 'schedule', 'followup', 'follow-up', 'follow up',
        'categorize', 'category', 'label', 'calendar', 'meeting', 'event',
        'priority', 'urgent', 'reply', 'analytics', 'stats', 'statistics',
        'contact', 'unsubscribe', 'newsletter', 'action item', 'task',
        'remind', 'unanswered', 'pending', 'insight', 'download', 'attach',
        'vip', 'export', 'complete', 'mark done', 'filter', 'rule', 'ics',
        'report', 'weekly', 'patterns', 'chart', 'visualize', 'response time',
        'reschedule', 'dismiss', 'reminder',
        'frequent', 'most often', 'top sender', 'top contact',
    ])
    has_email_word = any(keyword in msg for keyword in [
                         'email', 'inbox', 'message', 'unread', 'gmail',
                         'mail', 'sent', 'received', 'draft', 'folder',
                         'contact', 'contacts', 'csv', 'json', 'sender', 'senders'])

    if has_action_word and has_email_word:
        return None  # Let command parser handle it

    # For conversational messages, use LLM
    try:
        # Get memory context if available
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
                # On-demand recall: if the user is trying to remember something,
                # search episodic memory now and inject the hits into this turn's
                # context so the LLM can answer with the actual recalled content.
                recalled = memory.recall_for_llm(message)
                if recalled:
                    memory_context += f"\n\n{recalled}"
                    logger.debug(
                        f"[Memory] Injected episodic recall ({len(recalled)} chars)")
            except Exception:
                pass

        # Get conversation history from session state
        conversation_history = []
        if 'chat_messages' in st.session_state:
            # Convert to LLM format (last 5 exchanges)
            for msg in st.session_state.chat_messages[-10:]:
                conversation_history.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

        # Get agent name
        if not agent_name:
            agent_name = os.getenv('AGENT_NAME', 'Email Assistant')

        # Use LLM for natural conversation
        llm = get_llm_client()
        response = llm.chat(
            user_message=message,
            agent_name=agent_name,
            agent_type="Email Agent",
            memory_context=memory_context,
            conversation_history=conversation_history
        )

        # Record conversational interaction to memory
        if agent_id and MEMORY_AVAILABLE and response:
            try:
                memory = get_agent_memory(agent_id)
                memory.add_interaction(
                    command=message,
                    action="conversation",
                    result={'status': 'success',
                            'message': 'Natural conversation'},
                    metadata={'response_preview': response[:100] if len(
                        response) > 100 else response},
                    importance="Low"  # Conversational interactions are typically low importance
                )
                logger.debug(f"Recorded conversational interaction to memory")
            except Exception as mem_error:
                logger.error(
                    f"Failed to record conversation to memory: {str(mem_error)}")
                pass  # Don't fail the conversation if memory recording fails

        return response

    except Exception as e:
        # Log error
        logger.error(f"LLM conversation error: {str(e)}")
        # Return generic error message
        return "I'm having trouble understanding that right now. Could you try rephrasing, or ask me to help with your emails?"


def execute_with_llm_orchestration(user_query: str, agent_id: str = None) -> Dict[str, Any]:
    """
    Execute email commands using LLM-orchestrated tool selection.
    The LLM decides which tool to call based on natural language understanding.

    Args:
        user_query: Natural language query from user
        agent_id: Agent ID for memory context

    Returns:
        Result dictionary from tool execution
    """
    try:
        # Get memory context if available
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
            except Exception:
                pass

        # Let LLM orchestrate which tool to call
        llm = get_llm_client()
        tool_decision = llm.orchestrate_mcp_tool(user_query, memory_context)

        tool_name = tool_decision.get('tool')
        params = tool_decision.get('params', {})
        reasoning = tool_decision.get('reasoning', '')

        # Debug log
        logger.debug(f"[LLM] Tool: {tool_name} | Params: {params}")

        # Execute the appropriate tool
        if tool_name == 'get_todays_messages':
            emails = get_todays_emails(
                max_results=params.get('max_results', 1000))
            return {
                'status': 'success',
                'action': 'list_todays',
                'emails': emails,
                'count': len(emails),
                'reasoning': reasoning
            }

        elif tool_name == 'list_message':
            emails = list_emails(
                query=params.get('query', ''),
                max_results=params.get('max_results', 10)
            )
            return {
                'status': 'success',
                'action': 'list',
                'emails': emails,
                'count': len(emails),
                'reasoning': reasoning
            }

        elif tool_name == 'send_message':
            result = send_email(
                to=params.get('to', ''),
                subject=params.get('subject', '(No Subject)'),
                message=params.get('message_text', '')
            )
            result['action'] = 'send'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'count_messages':
            # For count, use list with high max_results and return count
            query = params.get('query', '')
            emails = list_emails(query=query, max_results=1000)
            return {
                'status': 'success',
                'action': 'count_filtered',
                'count': len(emails),
                'query': query,
                'reasoning': reasoning
            }

        elif tool_name == 'extract_action_items':
            result = extract_action_items(params.get('message_id', ''))
            result['action'] = 'action_items'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_all_pending_actions':
            result = get_all_pending_actions(params.get('max_emails', 20))
            result['action'] = 'pending_actions'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'generate_reply_suggestions':
            result = generate_reply_suggestions(params.get(
                'message_id', ''), params.get('tone', 'all'))
            result['action'] = 'reply_suggestions'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'quick_reply':
            result = quick_reply(params.get('message_id', ''),
                                 params.get('reply_type', 'acknowledged'))
            result['action'] = 'quick_reply'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'create_draft':
            result = create_draft(params.get('to', ''), params.get(
                'subject', ''), params.get('body', ''))
            result['action'] = 'create_draft'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'list_drafts':
            result = list_drafts(params.get('max_results', 10))
            result['action'] = 'list_drafts'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'send_draft':
            result = send_draft(params.get('draft_id', ''))
            result['action'] = 'send_draft'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'delete_draft':
            result = delete_draft(params.get('draft_id', ''))
            result['action'] = 'delete_draft'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'list_attachments':
            result = list_attachments(params.get('message_id', ''))
            result['action'] = 'list_attachments'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'download_attachment':
            result = download_attachment(
                params.get('message_id', ''),
                params.get('attachment_id', ''),
                params.get('filename', 'attachment'),
                params.get('save_path')
            )
            result['action'] = 'download_attachment'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'search_emails_with_attachments':
            result = search_emails_with_attachments(params.get(
                'file_type', 'all'), params.get('max_results', 10))
            result['action'] = 'emails_with_attachments'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'auto_categorize_email':
            result = auto_categorize_email(params.get('message_id', ''))
            result['action'] = 'categorize'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'apply_smart_labels':
            result = apply_smart_labels(params.get('batch_size', 20))
            result['action'] = 'smart_labels'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'extract_calendar_events':
            result = extract_calendar_events(params.get('message_id', ''))
            result['action'] = 'calendar_events'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'suggest_calendar_entry':
            result = suggest_calendar_entry(params.get('message_id', ''))
            result['action'] = 'calendar_suggestion'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'mark_for_followup':
            result = mark_for_followup(
                params.get('message_id', ''),
                params.get('days', 3),
                params.get('note', '')
            )
            result['action'] = 'mark_followup'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_pending_followups':
            result = get_pending_followups()
            result['action'] = 'pending_followups'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'check_unanswered_emails':
            result = check_unanswered_emails(params.get('older_than_days', 3))
            result['action'] = 'unanswered_emails'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'schedule_email':
            result = schedule_email(
                params.get('to', ''),
                params.get('subject', ''),
                params.get('body', ''),
                params.get('send_time', '')
            )
            result['action'] = 'schedule_email'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'list_scheduled_emails':
            result = list_scheduled_emails()
            result['action'] = 'list_scheduled'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'cancel_scheduled_email':
            result = cancel_scheduled_email(params.get('scheduled_id', ''))
            result['action'] = 'cancel_scheduled'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_frequent_contacts':
            result = get_frequent_contacts(params.get('limit', 10))
            result['action'] = 'frequent_contacts'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_contact_summary':
            result = get_contact_summary(params.get('email_address', ''))
            result['action'] = 'contact_summary'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'detect_urgent_emails':
            result = detect_urgent_emails(params.get('max_results', 20))
            result['action'] = 'urgent_emails'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'auto_prioritize':
            result = auto_prioritize(params.get('message_id', ''))
            result['action'] = 'prioritize'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'detect_newsletters':
            result = detect_newsletters(params.get('max_results', 30))
            result['action'] = 'newsletters'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'extract_unsubscribe_link':
            result = extract_unsubscribe_link(params.get('message_id', ''))
            result['action'] = 'unsubscribe'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_email_stats':
            result = get_email_stats(params.get('days', 30))
            result['action'] = 'email_stats'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_productivity_insights':
            result = get_productivity_insights()
            result['action'] = 'productivity'
            result['reasoning'] = reasoning
            return result

        # --- Phase 4 tools ---
        elif tool_name == 'mark_action_complete':
            result = mark_action_complete(params.get('task_id', ''))
            result['action'] = 'action_complete'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'get_saved_tasks':
            result = get_saved_tasks(params.get('status_filter', 'pending'))
            result['action'] = 'saved_tasks'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'create_category_rules':
            result = create_category_rules(
                int(params.get('min_occurrences', 3)))
            result['action'] = 'category_rules'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'export_to_calendar':
            result = export_to_calendar(
                params.get('event_data', {}),
                bool(params.get('save_ics', True))
            )
            result['action'] = 'export_calendar'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'send_followup_reminder':
            result = send_followup_reminder(params.get('message_id', ''))
            result['action'] = 'followup_reminder'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'mark_followup_done':
            result = mark_followup_done(params.get('message_id', ''))
            result['action'] = 'followup_done'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'dismiss_followup':
            result = dismiss_followup(params.get('message_id', ''))
            result['action'] = 'followup_dismiss'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'update_scheduled_email':
            result = update_scheduled_email(
                params.get('scheduled_id', ''),
                params.get('send_time', '')
            )
            result['action'] = 'update_scheduled'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'suggest_vip_contacts':
            result = suggest_vip_contacts()
            result['action'] = 'vip_contacts'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'export_contacts':
            result = export_contacts(
                params.get('format', 'csv'),
                int(params.get('limit', 100))
            )
            result['action'] = 'export_contacts'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'calculate_response_time':
            result = calculate_response_time(params.get('message_id', ''))
            result['action'] = 'response_time'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'visualize_patterns':
            result = visualize_patterns(int(params.get('days', 30)))
            result['action'] = 'visualize'
            result['reasoning'] = reasoning
            return result

        elif tool_name == 'generate_weekly_report':
            result = generate_weekly_report()
            result['action'] = 'weekly_report'
            result['reasoning'] = reasoning
            return result

        elif tool_name is None or tool_name == '':
            return {
                'status': 'error',
                'message': f"Could not determine appropriate action. {reasoning}"
            }

        else:
            return {
                'status': 'error',
                'message': f"Unknown tool: {tool_name}"
            }

    except Exception as e:
        # Log error
        error_msg = str(e)
        logger.error(f"Error in LLM orchestration: {error_msg}")
        return {
            'status': 'error',
            'message': 'LLM orchestration failed. Please try rephrasing your request.'
        }


def format_email_result(result: Dict[str, Any], action: str) -> str:
    """Format the result for display"""
    if result.get('status') == 'error':
        return f"❌ Error: {result.get('message', 'Unknown error')}"

    # Add reasoning if present (from LLM orchestration)
    reasoning_note = ""
    if result.get('reasoning'):
        reasoning_note = f"\n\n💡 *{result.get('reasoning')}*"

    if action == 'count':
        return f"""📊 Inbox Statistics:

**Total Messages:** {result.get('total_messages', 0):,}
**Unread Messages:** {result.get('unread_messages', 0):,}
**Total Threads:** {result.get('total_threads', 0):,}
**Unread Threads:** {result.get('unread_threads', 0):,}
""" + reasoning_note

    elif action == 'count_filtered':
        query_text = f" matching '{result.get('query')}'" if result.get(
            'query') else ""
        return f"📊 Found **{result.get('count', 0):,}** emails{query_text}!" + reasoning_note

    elif action == 'list_todays':
        emails = result.get('emails', [])
        count = result.get('count', 0)

        if count == 0:
            return "📭 No emails received today." + reasoning_note

        output = f"📬 Today's Emails: **{count}** email(s) received\n\n"

        # Show first 10 emails in detail, mention if there are more
        display_limit = min(10, len(emails))
        for i, email in enumerate(emails[:display_limit], 1):
            output += f"**{i}. {email['subject']}**\n"
            output += f"   📤 From: {email['sender']}\n"
            output += f"   📅 Date: {email.get('date', 'N/A')}\n"
            output += f"   🆔 ID: `{email['id']}`\n"

            snippet = email.get('snippet', '')
            if snippet:
                output += f"   📝 Snippet: _{snippet[:100]}..._\n"
            output += "\n---\n\n"

        if count > display_limit:
            output += f"\n*... and {count - display_limit} more emails. Use filters to narrow down results.*\n"

        return output + reasoning_note

    elif action == 'send':
        return f"""✅ Email sent successfully!
        
**Message ID:** {result.get('messageId', 'N/A')}
**Thread ID:** {result.get('threadId', 'N/A')}
"""

    elif action == 'delete':
        if result.get('deleted_count', 0) == 0:
            return "📭 No emails found to delete."

        output = f"""🗑️ Successfully moved {result['deleted_count']} email(s) to trash!

**Deleted Emails:**\n"""

        for i, email in enumerate(result.get('deleted_details', []), 1):
            output += f"\n{i}. **{email['subject']}**"
            output += f"\n   📤 From: {email['sender']}"
            output += f"\n   🆔 ID: `{email['id']}`\n"

        output += "\n*Note: Emails are moved to Trash and can be recovered within 30 days.*"
        return output

    elif action == 'list':
        emails = result.get('emails', [])
        if not emails:
            return "📭 No emails found matching your criteria."

        output = f"📬 Found {result['count']} email(s):\n\n"
        for i, email in enumerate(emails, 1):
            output += f"**{i}. {email['subject']}**\n"
            output += f"   📤 From: {email['sender']}\n"
            output += f"   📅 Date: {email.get('date', 'N/A')}\n"
            output += f"   🆔 ID: `{email['id']}`\n"

            # Display email content/body
            body = email.get('body', '').strip()
            if body:
                # Truncate very long emails
                if len(body) > 500:
                    body = body[:500] + "...\n\n*(Content truncated)*"
                output += f"\n   📧 **Content:**\n"
                output += f"   ```\n"
                # Indent the body content
                indented_body = '\n'.join(
                    ['   ' + line for line in body.split('\n')])
                output += indented_body + "\n"
                output += f"   ```\n"
            else:
                # Show snippet if no body
                snippet = email.get('snippet', '')
                if snippet:
                    output += f"\n   📝 Snippet: _{snippet}_\n"

            output += "\n---\n\n"
        return output

    elif action == 'summarize':
        if result.get('status') == 'error':
            return f"❌ Error: {result.get('message', 'Unknown error')}"

        output = f"""📝 **Email Summary**

**Subject:** {result.get('subject', 'N/A')}
**From:** {result.get('sender', 'N/A')}
**Date:** {result.get('date', 'N/A')}
**Word Count:** {result.get('word_count', 0)}

**Summary:**
{result.get('summary', 'No summary available')}
"""

        key_points = result.get('key_points', [])
        if key_points:
            output += "\n**Key Points:**\n"
            for point in key_points:
                output += f"• {point}\n"

        action_items = result.get('action_items', [])
        if action_items:
            output += "\n**Action Items:**\n"
            for item in action_items:
                output += f"✅ {item}\n"

        sentiment = result.get('sentiment', 'neutral')
        sentiment_emoji = {'positive': '😊', 'negative': '😟',
                           'neutral': '😐'}.get(sentiment, '😐')
        output += f"\n**Sentiment:** {sentiment_emoji} {sentiment.capitalize()}"

        if result.get('note'):
            output += f"\n\n*{result['note']}*"

        return output

    elif action == 'summarize_thread':
        if result.get('status') == 'error':
            return f"❌ Error: {result.get('message', 'Unknown error')}"

        output = f"""🧵 **Thread Summary**

**Subject:** {result.get('subject', 'N/A')}
**Messages:** {result.get('message_count', 0)}
**Participants:** {', '.join(result.get('participants', []))}

**Summary:**
{result.get('summary', 'No summary available')}
"""

        discussion_points = result.get('discussion_points', [])
        if discussion_points:
            output += "\n**Discussion Points:**\n"
            for point in discussion_points:
                output += f"• {point}\n"

        output += f"\n**Status:** {result.get('status_summary', 'ongoing')}"

        pending_actions = result.get('pending_actions', [])
        if pending_actions:
            output += "\n\n**Pending Actions:**\n"
            for action in pending_actions:
                output += f"⏳ {action}\n"

        if result.get('note'):
            output += f"\n\n*{result['note']}*"

        return output

    elif action == 'daily_digest':
        if result.get('status') == 'error':
            return f"❌ Error: {result.get('message', 'Unknown error')}"

        output = f"""📅 **Daily Email Digest**

**Date:** {result.get('date', 'N/A')}
**Total Emails:** {result.get('total_emails', 0)}

**Summary:**
{result.get('summary', 'No emails today')}
"""

        highlights = result.get('highlights', [])
        if highlights:
            output += "\n**Highlights:**\n"
            for highlight in highlights:
                output += f"⭐ {highlight}\n"

        categories = result.get('categories', {})
        if categories:
            output += "\n**By Category:**\n"
            for category, count in categories.items():
                output += f"• {category}: {count}\n"

        top_senders = result.get('top_senders', [])
        if top_senders:
            output += "\n**Top Senders:**\n"
            for sender, count in top_senders:
                output += f"• {sender}: {count} email(s)\n"

        if result.get('note'):
            output += f"\n\n*{result['note']}*"

        return output

    # Delegate to new feature formatters
    new_result = _format_new_feature_result(result, action)
    if new_result is not None:
        return new_result
    return "✅ Action completed successfully!"


def _format_new_feature_result(result: Dict[str, Any], action: str) -> str | None:
    """Format results for newer email features. Returns None if action not handled."""
    if result.get('status') == 'error':
        return f"❌ Error: {result.get('message', 'Unknown error')}"

    if action == 'action_items':
        items = result.get('action_items', [])
        if not items:
            return "✅ No action items found in this email."
        out = f"📋 **Action Items Found ({len(items)}):**\n\n"
        for i, item in enumerate(items, 1):
            priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(
                str(item.get('priority', '')).lower(), '⚪')
            out += f"{i}. {priority_emoji} **{item.get('task', 'N/A')}**\n"
            if item.get('deadline'):
                out += f"   ⏰ Deadline: {item['deadline']}\n"
            if item.get('assigned_to'):
                out += f"   👤 Assigned to: {item['assigned_to']}\n"
        return out

    if action == 'pending_actions':
        emails = result.get('emails_with_actions', [])
        if not emails:
            return "✅ No pending action items found."
        out = f"📋 **Pending Actions Across {len(emails)} Email(s):**\n\n"
        for email in emails[:5]:
            out += f"**{email.get('subject', 'No Subject')}**\n"
            for item in email.get('action_items', [])[:3]:
                out += f"• {item.get('task', 'N/A')}\n"
            out += "\n"
        return out

    if action == 'reply_suggestions':
        suggestions = result.get('suggestions', [])
        if not suggestions:
            return "❌ Could not generate reply suggestions."
        out = "💬 **Reply Suggestions:**\n\n"
        for i, s in enumerate(suggestions, 1):
            out += f"**Option {i} — {s.get('tone', '').capitalize()}:**\n"
            out += f"> {s.get('text', '')}\n\n"
        return out

    if action == 'quick_reply':
        if result.get('status') == 'success':
            return f"✅ Quick reply sent!\n\n**Reply sent:** _{result.get('reply_text', '')}_"
        return f"❌ Failed to send reply: {result.get('message', '')}"

    if action == 'create_draft':
        if result.get('status') == 'success':
            return f"✅ Draft saved!\n\n**Draft ID:** `{result.get('draft_id', 'N/A')}`"
        return f"❌ Failed to create draft: {result.get('message', '')}"

    if action == 'list_drafts':
        drafts = result.get('drafts', [])
        if not drafts:
            return "📭 No drafts found."
        out = f"📝 **Drafts ({len(drafts)}):**\n\n"
        for d in drafts:
            out += f"• **{d.get('subject', '(No Subject)')}** — To: {d.get('to', 'N/A')}\n"
            out += f"  🆔 ID: `{d.get('id', '')}`\n"
        return out

    if action in ('send_draft', 'delete_draft'):
        verb = 'sent' if action == 'send_draft' else 'deleted'
        if result.get('status') == 'success':
            return f"✅ Draft {verb} successfully!"
        return f"❌ Could not {verb.replace('sent', 'send')} draft: {result.get('message', '')}"

    if action == 'list_attachments':
        atts = result.get('attachments', [])
        if not atts:
            return "📎 No attachments found in this email."
        out = f"📎 **Attachments ({len(atts)}):**\n\n"
        for a in atts:
            size_kb = round(a.get('size', 0) / 1024, 1)
            out += f"• **{a.get('filename', 'unknown')}** ({size_kb} KB)\n"
            out += f"  🆔 Attachment ID: `{a.get('attachment_id', '')}`\n"
        return out

    if action == 'download_attachment':
        if result.get('status') == 'success':
            return f"✅ Attachment downloaded!\n\n**Saved to:** `{result.get('save_path', 'N/A')}`"
        return f"❌ Download failed: {result.get('message', '')}"

    if action == 'emails_with_attachments':
        emails = result.get('emails', [])
        if not emails:
            return "📭 No emails with attachments found."
        out = f"📎 **Emails with Attachments ({len(emails)}):**\n\n"
        for e in emails[:10]:
            out += f"• **{e.get('subject', '(No Subject)')}** from {e.get('sender', 'N/A')}\n"
            out += f"  🆔 ID: `{e.get('id', '')}`\n"
        return out

    if action == 'categorize':
        cat = result.get('category', 'unknown')
        conf = result.get('confidence', '')
        out = f"🏷️ **Email Category:** {cat.capitalize()}"
        if conf:
            out += f" (confidence: {conf})"
        if result.get('label_applied'):
            out += f"\n✅ Gmail label applied: `{result.get('label_name', '')}`"
        return out

    if action == 'smart_labels':
        processed = result.get('processed', 0)
        labelled = result.get('labelled', 0)
        return f"🏷️ Smart labelling complete!\n\n**Processed:** {processed} emails\n**Labelled:** {labelled} emails"

    if action == 'calendar_events':
        events = result.get('events', [])
        if not events:
            return "📅 No calendar events found in this email."
        out = f"📅 **Calendar Events Found ({len(events)}):**\n\n"
        for e in events:
            out += f"**{e.get('title', 'Untitled Event')}**\n"
            if e.get('date'):
                out += f"📆 {e['date']}"
                if e.get('time'):
                    out += f" at {e['time']}"
                out += "\n"
            if e.get('location'):
                out += f"📍 {e['location']}\n"
            if e.get('participants'):
                out += f"👥 {', '.join(e['participants'][:3])}\n"
            out += "\n"
        return out

    if action == 'calendar_suggestion':
        hint = result.get('suggestion', '')
        return f"📅 **Calendar Suggestion:**\n\n{hint}" if hint else "📅 No clear calendar event found."

    if action == 'mark_followup':
        if result.get('status') == 'success':
            return f"⏰ Follow-up reminder set!\n\n**Due:** {result.get('due_date', 'N/A')}"
        return f"❌ Could not set follow-up: {result.get('message', '')}"

    if action == 'pending_followups':
        overdue = result.get('overdue', [])
        upcoming = result.get('upcoming', [])
        out = ""
        if overdue:
            out += f"🔴 **Overdue Follow-ups ({len(overdue)}):**\n"
            for f in overdue[:5]:
                out += f"• {f.get('subject', 'N/A')} — was due {f.get('due_date', 'N/A')}\n"
            out += "\n"
        if upcoming:
            out += f"🟡 **Upcoming Follow-ups ({len(upcoming)}):**\n"
            for f in upcoming[:5]:
                out += f"• {f.get('subject', 'N/A')} — due {f.get('due_date', 'N/A')}\n"
        if not overdue and not upcoming:
            out = "✅ No pending follow-ups!"
        return out

    if action == 'unanswered_emails':
        emails = result.get('unanswered', [])
        if not emails:
            return "✅ No unanswered emails found."
        out = f"📬 **Unanswered Emails ({len(emails)}):**\n\n"
        for e in emails[:10]:
            out += f"• **{e.get('subject', 'N/A')}** — Sent {e.get('days_ago', '?')} day(s) ago\n"
        return out

    if action == 'schedule_email':
        if result.get('status') == 'success':
            return (f"⏰ Email scheduled!\n\n"
                    f"**To:** {result.get('to', 'N/A')}\n"
                    f"**Send time:** {result.get('send_time', 'N/A')}\n"
                    f"**ID:** `{result.get('scheduled_id', '')}`")
        return f"❌ Scheduling failed: {result.get('message', '')}"

    if action == 'list_scheduled':
        emails = result.get('scheduled', [])
        if not emails:
            return "📭 No emails scheduled."
        out = f"⏰ **Scheduled Emails ({len(emails)}):**\n\n"
        for e in emails:
            out += f"• **To:** {e.get('to', 'N/A')} | **Subject:** {e.get('subject', 'N/A')}\n"
            out += f"  🕐 Send at: {e.get('send_time', 'N/A')} | ID: `{e.get('scheduled_id', '')}`\n"
        return out

    if action == 'cancel_scheduled':
        if result.get('status') == 'success':
            return "✅ Scheduled email cancelled."
        return f"❌ Could not cancel: {result.get('message', '')}"

    if action == 'frequent_contacts':
        contacts = result.get('contacts', [])
        if not contacts:
            return "📭 No frequent contacts found."
        out = f"👥 **Top Contacts ({len(contacts)}):**\n\n"
        for i, c in enumerate(contacts[:10], 1):
            count = c.get('interaction_count', c.get('total', 0))
            out += f"{i}. **{c.get('name', c.get('email', 'N/A'))}** — {count} interactions\n"
            out += f"   📧 {c.get('email', 'N/A')}\n"
        return out

    if action == 'contact_summary':
        total = result.get('total_interactions', result.get('total', 0))
        if total == 0 and result.get('status') != 'error':
            return f"📭 No emails found for **{result.get('email', result.get('email_address', 'N/A'))}**"
        email_addr = result.get('email', result.get('email_address', 'N/A'))
        out = f"👤 **Contact Summary: {email_addr}**\n\n"
        out += f"📧 Email: {email_addr}\n"
        out += f"📨 Total interactions: {total}\n"
        out += f"📤 Sent by you: {result.get('emails_sent_to', result.get('sent', 0))}\n"
        out += f"📥 Received: {result.get('emails_received_from', result.get('received', 0))}\n"
        if result.get('latest_email_subject'):
            out += f"📝 Latest email: _{result['latest_email_subject'][:60]}_\n"
        if result.get('is_vip'):
            out += "⭐ VIP Contact\n"
        return out

    if action == 'urgent_emails':
        emails = result.get('urgent_emails', [])
        if not emails:
            return "✅ No urgent emails found."
        out = f"🚨 **Urgent Emails ({len(emails)}):**\n\n"
        for e in emails[:10]:
            score = e.get('priority_score', 0)
            score_emoji = '🔴' if score >= 8 else '🟡' if score >= 5 else '🟢'
            out += f"{score_emoji} **{e.get('subject', 'N/A')}**\n"
            out += f"   From: {e.get('sender', 'N/A')} | Score: {score}/10\n"
            if e.get('reason'):
                out += f"   _{e['reason']}_\n"
            out += "\n"
        return out

    if action == 'prioritize':
        score = result.get('priority_score', 0)
        score_emoji = '🔴' if score >= 8 else '🟡' if score >= 5 else '🟢'
        out = f"{score_emoji} **Priority Score: {score}/10**\n\n"
        if result.get('reason'):
            out += f"**Reason:** {result['reason']}\n"
        keywords = result.get('urgency_keywords', [])
        if keywords:
            out += f"**Keywords:** {', '.join(keywords)}\n"
        return out

    if action == 'newsletters':
        newsletters = result.get('newsletters', [])
        count = result.get('count', 0)
        if not newsletters:
            return "📭 No newsletters detected in your inbox."
        out = f"📰 **Newsletters Detected ({count} unique senders):**\n\n"
        for n in newsletters[:15]:
            header_icon = "✅" if n.get('has_unsubscribe_header') else "📝"
            out += f"{header_icon} **{n.get('sender', 'N/A')}**\n"
            out += f"   Subject: _{n.get('subject', 'N/A')[:60]}_\n"
            out += f"   🆔 ID: `{n.get('id', '')}` (use to get unsubscribe link)\n"
        return out

    if action == 'unsubscribe':
        method = result.get('method', '')
        url = result.get('unsubscribe_url')
        mailto = result.get('mailto')
        if method == 'not_found':
            return f"📭 No unsubscribe link found in this email.\n\n_{result.get('message', '')}_"
        out = f"🔕 **Unsubscribe Info for:** _{result.get('sender', 'N/A')}_\n\n"
        if url:
            out += f"🔗 **Unsubscribe URL:** {url}\n"
        if mailto:
            out += f"📧 **Unsubscribe Email:** {mailto}\n"
        return out

    if action == 'email_stats':
        out = f"📊 **Email Statistics (Last {result.get('period_days', 30)} Days):**\n\n"
        out += f"📥 Received: **{result.get('total_received', 0)}** emails\n"
        out += f"📤 Sent: **{result.get('total_sent', 0)}** emails\n"
        out += f"📖 Unread: **{result.get('total_unread', 0)}** emails\n"
        out += f"📈 Avg/day: **{result.get('avg_received_per_day', 0)}**\n"
        out += f"📅 Busiest day: **{result.get('busiest_day', 'N/A')}**\n"
        out += f"⏰ Busiest hour: **{result.get('busiest_hour', 'N/A')}**\n"
        top = result.get('top_senders', [])
        if top:
            out += "\n**Top Senders:**\n"
            for s in top[:5]:
                out += f"• {s.get('name', s.get('email', 'N/A'))} — {s.get('count', 0)} emails\n"
        return out

    if action == 'productivity':
        insights = result.get('insights', [])
        suggestions = result.get('suggestions', [])
        out = "💡 **Productivity Insights:**\n\n"
        for insight in insights:
            out += f"{insight}\n"
        if suggestions:
            out += "\n**Suggestions:**\n"
            for s in suggestions:
                out += f"→ {s}\n"
        return out

    # --- Phase 4 formatters ---
    if action == 'action_complete':
        if result.get('status') == 'success':
            return f"✅ Task **{result.get('task_id', '')}** marked as complete!"
        return f"❌ Could not mark task complete: {result.get('message', '')}"

    if action == 'saved_tasks':
        tasks = result.get('tasks', [])
        if not tasks:
            return "📋 No saved tasks found."
        out = f"📋 **Saved Tasks ({len(tasks)}):**\n\n"
        for t in tasks:
            status_icon = '✅' if t.get('status') == 'complete' else '⏳'
            out += f"{status_icon} **[{t.get('task_id', '?')}]** {t.get('task', 'N/A')}\n"
            if t.get('deadline'):
                out += f"   ⏰ Deadline: {t['deadline']}\n"
            if t.get('priority'):
                priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(
                    str(t['priority']).lower(), '⚪')
                out += f"   {priority_emoji} Priority: {t['priority']}\n"
        return out

    if action == 'category_rules':
        rules = result.get('rules_created', [])
        skipped = result.get('skipped', 0)
        if not rules:
            return f"ℹ️ No new filter rules created (skipped {skipped} duplicates)."
        out = f"✅ **{len(rules)} Filter Rule(s) Created:**\n\n"
        for r in rules:
            out += f"• **{r.get('category', 'N/A')}** → emails from `{r.get('sender', 'N/A')}`\n"
        if skipped:
            out += f"\n_(Skipped {skipped} already-existing rules)_"
        return out

    if action == 'export_calendar':
        if result.get('ics_saved'):
            out = f"📅 **Calendar Event Exported!**\n\n"
            out += f"**Event:** {result.get('title', 'N/A')}\n"
            out += f"📁 **File saved:** `{result.get('ics_path', 'N/A')}`\n"
            if result.get('google_calendar_added'):
                out += "✅ Also added to Google Calendar\n"
            elif result.get('calendar_note'):
                out += f"ℹ️ {result['calendar_note']}\n"
            return out
        return f"❌ Calendar export failed: {result.get('message', '')}"

    if action == 'followup_reminder':
        if result.get('status') == 'success':
            return f"📧 **Follow-up reminder sent to yourself!**\n\n_{result.get('message', '')}_"
        return f"❌ Could not send reminder: {result.get('message', '')}"

    if action == 'followup_done':
        if result.get('status') == 'success':
            return "✅ Follow-up marked as done!"
        return f"❌ Could not mark done: {result.get('message', '')}"

    if action == 'followup_dismiss':
        if result.get('status') == 'success':
            return "🚫 Follow-up dismissed."
        return f"❌ Could not dismiss: {result.get('message', '')}"

    if action == 'update_scheduled':
        if result.get('status') == 'success':
            return (f"✅ Scheduled email updated!\n\n"
                    f"**New send time:** {result.get('new_send_time', 'N/A')}\n"
                    f"**ID:** `{result.get('scheduled_id', '')}`")
        return f"❌ Could not reschedule: {result.get('message', '')}"

    if action == 'vip_contacts':
        contacts = result.get('vip_contacts', [])
        if not contacts:
            return "📭 No VIP contact suggestions found yet (need more email history)."
        out = f"⭐ **Suggested VIP Contacts ({len(contacts)}):**\n\n"
        for i, c in enumerate(contacts[:10], 1):
            out += f"{i}. **{c.get('name', c.get('email', 'N/A'))}**\n"
            out += f"   📧 {c.get('email', 'N/A')} | 📨 {c.get('total', 0)} interactions\n"
        return out

    if action == 'export_contacts':
        if result.get('status') == 'success':
            out = f"📤 **Contacts Exported!**\n\n"
            out += f"**Format:** {result.get('format', 'N/A').upper()}\n"
            out += f"📁 **Saved to:** `{result.get('file_path', 'N/A')}`\n"
            return out
        return f"❌ Export failed: {result.get('message', '')}"

    if action == 'response_time':
        if not result.get('has_response'):
            return f"⏳ No reply found for this email thread yet."
        out = f"⏱️ **Response Time Analysis:**\n\n"
        out += f"**You responded in:** {result.get('response_time_readable', 'N/A')}\n"
        out += f"**Sent:** {result.get('sent_at', 'N/A')}\n"
        out += f"**Replied:** {result.get('replied_at', 'N/A')}\n"
        return out

    if action == 'visualize':
        charts = result.get('charts', {})
        if not charts:
            return "📊 No pattern data available yet."
        out = f"📊 **Email Patterns (Last {result.get('days', 30)} Days):**\n\n"
        summary = charts.get('volume_summary', {}).get('data', {})
        if summary:
            out += f"**Volume:** Received {summary.get('received', 0)}, Sent {summary.get('sent', 0)}\n\n"
        dow = charts.get('day_of_week', {}).get('data', {})
        if dow:
            out += "**Busiest day:** "
            busiest = max(dow, key=lambda k: dow[k].get(
                'received', 0)) if dow else 'N/A'
            out += f"{busiest}\n\n"
        top_senders = charts.get('top_senders', {}).get('data', [])
        if top_senders:
            out += "**Top Senders:**\n"
            for s in top_senders[:5]:
                out += f"• {s.get('label', 'N/A')} — {s.get('value', 0)} emails\n"
        out += "\n_(Chart data ready for visualization)_"
        return out

    if action == 'weekly_report':
        report_text = result.get('report_text', '')
        if report_text:
            return f"📊 **Weekly Email Report:**\n\n{report_text}"
        return "📊 Weekly report generated. No data available for the past 7 days."

    return None


def format_date(date_str: str) -> str:
    """Format date string to be more readable like Gmail"""
    try:
        email_date = dateutil.parser.parse(date_str)
        now = datetime.now(email_date.tzinfo or None)

        # Calculate difference
        diff = now - email_date

        if diff.days == 0:
            # Today - show time
            return email_date.strftime("%I:%M %p")
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return email_date.strftime("%A")  # Day name
        elif diff.days < 365:
            return email_date.strftime("%b %d")  # Month Day
        else:
            return email_date.strftime("%b %d, %Y")  # Full date
    except:
        return date_str[:20] if len(date_str) > 20 else date_str


def display_emails_gmail_style(emails: list):
    """Display emails in a Gmail-like interface"""
    if not emails:
        st.info("📭 No emails found matching your criteria.")
        return

    st.success(f"📬 Found {len(emails)} email(s)")

    # Display each email in a card-like container
    for i, email in enumerate(emails):
        is_unread = 'UNREAD' in email.get('labels', [])

        # Main container for email (card-like)
        with st.container():
            # Create a box with border using custom styling
            if is_unread:
                st.markdown(f"""
                <div style="background-color: #f0f4ff; padding: 15px; border-radius: 8px; 
                            border-left: 4px solid #4285f4; margin-bottom: 10px;">
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background-color: #fafafa; padding: 15px; border-radius: 8px; 
                            border-left: 4px solid #e0e0e0; margin-bottom: 10px;">
                """, unsafe_allow_html=True)

            # Header row: Sender and Date
            col1, col2 = st.columns([4, 1])
            with col1:
                sender = email['sender']
                # Extract just name or email
                if '<' in sender:
                    sender_name = sender.split('<')[0].strip()
                    sender_email = sender.split(
                        '<')[1].replace('>', '').strip()
                    if is_unread:
                        st.markdown(f"**📧 {sender_name}** `{sender_email}`")
                    else:
                        st.markdown(f"📧 {sender_name} `{sender_email}`")
                else:
                    if is_unread:
                        st.markdown(f"**📧 {sender}**")
                    else:
                        st.markdown(f"📧 {sender}")

            with col2:
                date_formatted = format_date(email.get('date', ''))
                st.markdown(f"<div style='text-align: right; color: #666;'>{date_formatted}</div>",
                            unsafe_allow_html=True)

            # Subject line
            subject = email['subject']
            if is_unread:
                st.markdown(f"### **{subject}**")
            else:
                st.markdown(f"### {subject}")

            # Snippet (preview)
            snippet = email.get('snippet', '')
            if snippet:
                st.markdown(f"<p style='color: #666; margin: 5px 0;'>{snippet[:150]}...</p>",
                            unsafe_allow_html=True)

            # Expandable full content
            body = email.get('body', '').strip()
            if body:
                with st.expander("📖 Read full message"):
                    st.text(body)

            # Labels/metadata in small text
            labels = [l for l in email.get('labels', []) if l not in [
                'INBOX', 'UNREAD', 'IMPORTANT', 'CATEGORY_PERSONAL']]
            if labels:
                st.caption(f"🏷️ Labels: {', '.join(labels)}")

            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)


@st.cache_resource
def _logo_b64() -> str:
    """Return the base64 data URL for octopus.png. Cached for the process lifetime."""
    img_path = Path(__file__).parent.parent / "assets" / "octopus.png"
    data = img_path.read_bytes()
    return "data:image/png;base64," + _base64.b64encode(data).decode()


def _logo_icon():
    """Return a PIL Image of octopus.png for page_icon, or emoji fallback."""
    try:
        from PIL import Image as _PILImage
        return _PILImage.open(Path(__file__).parent.parent / "assets" / "octopus.png")
    except Exception:
        return "\U0001f419"


@st.cache_resource
def _start_browser_watchdog(agent_id: str) -> bool:
    """
    Background thread that detects browser disconnection and exits the process.
    Uses Streamlit's internal session manager — no forced UI reruns needed.
    @st.cache_resource ensures this only starts once per process lifetime.
    """
    import threading
    import time as _t

    def _watch():
        _t.sleep(20)  # Grace period for initial browser connection
        while True:
            _t.sleep(8)
            try:
                from streamlit.runtime import get_instance
                rt = get_instance()
                if rt is not None:
                    active = list(rt._session_mgr.list_active_session_info())
                    if len(active) == 0:
                        try:
                            from src.agent.core.process_manager import remove_agent_from_state
                            remove_agent_from_state(agent_id)
                        except Exception:
                            pass
                        os._exit(0)
            except Exception:
                pass  # Fail-safe: if internal API changes, keep running

    threading.Thread(target=_watch, daemon=True).start()
    return True


def main():
    logger.debug("=== MAIN() CALLED ===")
    # Get agent_id and name from environment or use defaults
    agent_id = os.getenv('AGENT_ID', 'gmail_agent_default')
    agent_name = os.getenv('AGENT_NAME', 'Email Assistant')

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide"
    )

    # Start browser-close watchdog (once per process)
    _start_browser_watchdog(agent_id)

    # Start automation scheduler (once per process, runs in background thread)
    try:
        from src.agent.core.automation_scheduler import start_scheduler
        _sched = start_scheduler(agent_id)  # noqa: F841 — kept alive by reference
    except Exception as _sched_err:
        logger.warning("Automation scheduler could not start: %s", _sched_err)

    if 'agent_id' not in st.session_state:
        st.session_state.agent_id = agent_id

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(156,39,176,0.18) 0%, rgba(233,30,140,0.12) 100%);
                   border:1.5px solid rgba(233,30,140,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(233,30,140,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(233,30,140,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;color:#e91e8c;line-height:1.1;background:linear-gradient(135deg, #e91e8c 0%, #c5068e 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">OctaMind</div>
              <div style="font-size:1.05rem;color:#000;margin-top:6px;font-weight:600;">
                📧 {agent_name} &nbsp;•&nbsp; Gmail Agent
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#000;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(233,30,140,0.3);">
            Give me commands in natural language, and I'll handle your emails! ️✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar with examples
    with st.sidebar:
        # Guide reference — clickable file link
        _guide_path = (Path(__file__).parent.parent.parent.parent /
                       "documentation" / "EMAIL_AGENT_USAGE_GUIDE.md").resolve()
        st.link_button(
            "📖 Full Usage Guide",
            url=_guide_path.as_uri(),
            use_container_width=True,
        )

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 4px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>⚡ Quick Commands</p>",
            unsafe_allow_html=True,
        )

        with st.expander("📥 Read & Search"):
            st.markdown("""
- `List 5 unread emails`
- `Show emails from john@example.com`
- `What emails did I get today?`
- `Find emails with subject "invoice"`
- `Show emails with label:starred`
""")

        with st.expander("✉️ Send & Draft"):
            st.markdown("""
- `Send email to alice@example.com subject "Hi" body "Hello"`
- `Draft an email to bob@example.com about project update`
- `Show my drafts` · `Send draft <draft_id>`
""")

        with st.expander("🗑️ Delete"):
            st.markdown("""
- `Delete 5 emails`
- `Remove 3 unread emails`
- `Delete emails from spam@example.com`
- `Trash all emails from LinkedIn`
""")

        with st.expander("🧠 Summarize & Tasks"):
            st.markdown("""
- `Summarize email <message_id>`
- `Generate my daily email digest`
- `What tasks do I have in email <id>?`
- `Show my saved tasks`
- `Mark task <task_id> as complete`
""")

        with st.expander("💬 Reply & Smart Labels"):
            st.markdown("""
- `Suggest how I should reply to email <id>`
- `Reply yes to email <message_id>`
- `Auto-label my recent emails`
- `Show me urgent emails`
""")

        with st.expander("📅 Calendar & Follow-ups"):
            st.markdown("""
- `Extract calendar events from email <id>`
- `Remind me to follow up on email <id> in 3 days`
- `What follow-ups do I have pending?`
- `Export the event from email <id> to ICS`
""")

        with st.expander("⏰ Scheduling"):
            st.markdown("""
- `Schedule email to alice@example.com for tomorrow 9am`
- `Show my scheduled emails`
- `Reschedule email <id> to Monday 10am`
- `Cancel scheduled email <id>`
""")

        with st.expander("👥 Contacts & Newsletters"):
            st.markdown("""
- `Who do I email most frequently?`
- `Export my contacts to CSV`
- `Give me a summary for john@example.com`
- `Find newsletters in my inbox`
- `How do I unsubscribe from email <id>?`
""")

        with st.expander("📊 Analytics & Reports"):
            st.markdown("""
- `Show my email stats for the last 30 days`
- `Give me email productivity insights`
- `Generate my weekly email report`
- `Show email patterns for the last 30 days`
""")

        st.markdown(
            "<p style='font-size:0.72rem;color:#666;margin:6px 0 0 0;'>💡 Include <b>email</b> / <b>inbox</b> / <b>message</b> in queries so I know it's an email task.</p>",
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown(
            "<span style='font-size:0.85rem;'>🟢 <b>Ready</b></span>",
            unsafe_allow_html=True,
        )

        # Display inbox statistics
        st.divider()
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 8px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>📊 Inbox Statistics</p>",
            unsafe_allow_html=True,
        )
        try:
            inbox_info = get_inbox_count()
            if inbox_info['status'] == 'success':
                total = inbox_info['total_messages']
                unread = inbox_info['unread_messages']
                threads = inbox_info['total_threads']
                unread_pct = round(unread / total * 100) if total else 0
                st.markdown(
                    f"""
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px;">
                      <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#e91e8c;">{total:,}</div>
                        <div style="font-size:0.7rem;color:#888;">Total</div>
                      </div>
                      <div style="background:#1a1a2e;border:1px solid #e91e8c55;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#ff6b6b;">{unread:,}</div>
                        <div style="font-size:0.7rem;color:#888;">Unread</div>
                      </div>
                      <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#a8dadc;">{threads:,}</div>
                        <div style="font-size:0.7rem;color:#888;">Threads</div>
                      </div>
                      <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#95e1d3;">{unread_pct}%</div>
                        <div style="font-size:0.7rem;color:#888;">Unread %</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.warning("Could not load inbox stats.")
        except Exception as e:
            st.error(f"Stats error: {str(e)}")

    # Initialize session state for chat messages
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []
        # Add welcome message
        st.session_state.chat_messages.append({
            'role': 'assistant',
            'content': f'👋 Hello! I\'m **{agent_name}**, your AI Email Agent. I can help you manage your emails with natural language commands. Try asking me to count your emails, list unread messages, or send an email!'
        })

    if 'history' not in st.session_state:
        st.session_state.history = []

    # Add processing flag to prevent concurrent execution
    if 'is_processing' not in st.session_state:
        st.session_state.is_processing = False

    # Add pending command queue to handle rapid successive questions
    if 'pending_command' not in st.session_state:
        st.session_state.pending_command = None

    # Initialize interaction counter for memory consolidation
    if 'interaction_count' not in st.session_state:
        st.session_state.interaction_count = 0

    # Track last consolidation check
    if 'last_consolidation_check' not in st.session_state:
        st.session_state.last_consolidation_check = datetime.now()

        # On startup, check if 24 hours have passed since last consolidation
        # This ensures consolidation runs after restart if needed
        if MEMORY_AVAILABLE:
            try:
                agent_id = st.session_state.get(
                    'agent_id', os.getenv('AGENT_ID', 'gmail_agent_default'))
                memory = get_agent_memory(agent_id)
                consolidator = memory.get_consolidator()

                # Check 24-hour trigger (works because state is persisted)
                if consolidator.last_consolidation:
                    hours_since = (
                        datetime.now() - consolidator.last_consolidation).total_seconds() / 3600
                    if hours_since >= 24:
                        logger.info(
                            f"Startup consolidation check: {hours_since:.1f} hours since last consolidation")
                        logger.info(
                            "Triggering consolidation after agent restart (24+ hours passed)")
                        memory.run_consolidation()
                        logger.info("Startup consolidation completed")
            except Exception as e:
                logger.error(f"Startup consolidation check error: {str(e)}")

    # Display chat messages
    # ── Chat section header + inline clear button ─────────────────────────
    _hdr_col, _clr_col = st.columns([11, 1])
    with _hdr_col:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;">
              <div style="width:4px;height:28px;background:linear-gradient(180deg,#e91e8c,#9c27b0);
                          border-radius:2px;flex-shrink:0;"></div>
              <span style="font-size:1.3rem;font-weight:700;color:#f0f0f0;letter-spacing:0.01em;">
                💬 Chat with Your Email Agent
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with _clr_col:
        # Inject CSS once to make this button look like a ghost icon pill
        st.markdown(
            """
            <style>
            div[data-testid="stColumns"] button[kind="secondary"] {
                background: transparent !important;
                border: 1px solid rgba(255,255,255,0.1) !important;
                border-radius: 50% !important;
                color: #888 !important;
                padding: 4px !important;
                font-size: 1rem !important;
                min-height: 0 !important;
                height: 36px !important;
                width: 36px !important;
                transition: border-color 0.2s, color 0.2s;
            }
            div[data-testid="stColumns"] button[kind="secondary"]:hover {
                border-color: #e91e8c !important;
                color: #e91e8c !important;
                background: rgba(233,30,140,0.08) !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        _do_clear = st.button(
            "🗑", help="Clear chat history", use_container_width=False)

    # ── Fancy chat bubble styling ──────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* General bubble card */
        [data-testid="stChatMessage"] {
            border-radius: 18px !important;
            padding: 14px 18px !important;
            margin-bottom: 10px !important;
            border: 1px solid rgba(255,255,255,0.05) !important;
            transition: box-shadow 0.2s ease;
        }
        [data-testid="stChatMessage"]:hover {
            box-shadow: 0 4px 20px rgba(0,0,0,0.25) !important;
        }

        /* User bubble — warm pink tint */
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            background: rgba(233,30,140,0.07) !important;
            border-color: rgba(233,30,140,0.2) !important;
        }

        /* Assistant bubble — subtle dark card */
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
            background: rgba(255,255,255,0.03) !important;
            border-color: rgba(255,255,255,0.08) !important;
        }

        /* User avatar — gradient purple-pink pill */
        [data-testid="chatAvatarIcon-user"] {
            background: linear-gradient(135deg, #e91e8c 0%, #9c27b0 100%) !important;
            border-radius: 50% !important;
            box-shadow: 0 2px 10px rgba(233,30,140,0.4) !important;
            font-size: 1.1rem !important;
        }

        /* Assistant avatar — dark base + pink glow ring */
        [data-testid="chatAvatarIcon-assistant"] {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%) !important;
            border-radius: 50% !important;
            box-shadow: 0 0 0 2px rgba(233,30,140,0.45),
                        0 3px 12px rgba(0,0,0,0.5) !important;
            overflow: hidden !important;
        }

        /* Assistant avatar image (octopus PNG) */
        [data-testid="chatAvatarIcon-assistant"] img {
            border-radius: 50% !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Create a container for chat messages with custom styling
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_messages:
            _chat_avatar = _logo_icon(
            ) if message['role'] == 'assistant' else "🧑‍💻"
            with st.chat_message(message['role'], avatar=_chat_avatar):
                st.markdown(message['content'])

    # Clear chat — driven by the icon button in the header row
    if _do_clear:
        st.session_state.chat_messages = [{
            'role': 'assistant',
            'content': f'👋 Hello! I\'m **{agent_name}**, your AI Email Agent. I can help you manage your emails with natural language commands. Try asking me to count your emails, list unread messages, or send an email!'
        }]
        st.session_state.history = []
        st.rerun()

    # Chat input at the bottom
    user_command = st.chat_input(
        "Type your command here... (e.g., 'count my emails' or 'list 5 unread emails')")

    # Debug logging
    logger.debug(
        f"RERUN: user_command={user_command}, is_processing={st.session_state.is_processing}, pending={st.session_state.pending_command}")

    # If user enters command while processing, save it for next run
    if user_command and st.session_state.is_processing:
        st.session_state.pending_command = user_command
        st.info("⏳ Your command is queued. Processing current request...")
        st.stop()  # Stop execution here to prevent duplicate processing

    # Process pending command if exists and not currently processing
    if st.session_state.pending_command and not st.session_state.is_processing:
        user_command = st.session_state.pending_command
        st.session_state.pending_command = None
        # Don't stop here - let it continue to processing

    # Only process if not already processing (prevent concurrent execution)
    if user_command and not st.session_state.is_processing:
        logger.debug(f"START PROCESSING: '{user_command[:50]}'")

        # Set processing flag
        st.session_state.is_processing = True

        # Add user message to chat
        st.session_state.chat_messages.append({
            'role': 'user',
            'content': user_command
        })

        with st.status("Processing...", expanded=False) as _status:
            try:
                # Check for conversational messages first
                agent_id = st.session_state.get(
                    'agent_id', os.getenv('AGENT_ID', 'gmail_agent_default'))
                logger.debug("Calling handle_conversation()")
                convo_response = handle_conversation(
                    user_command, agent_id, agent_name)
                logger.debug(
                    f"handle_conversation returned: {bool(convo_response)}")
                if convo_response:
                    st.session_state.chat_messages.append({
                        'role': 'assistant',
                        'content': convo_response
                    })

                    # Increment interaction counter and check consolidation for conversations too
                    if MEMORY_AVAILABLE:
                        try:
                            st.session_state.interaction_count += 1
                            memory = get_agent_memory(agent_id)
                            consolidator = memory.get_consolidator()
                            if consolidator.should_consolidate(st.session_state.interaction_count):
                                logger.info(
                                    f"Triggering memory consolidation after conversation (interactions: {st.session_state.interaction_count})")
                                memory.run_consolidation()
                                st.session_state.interaction_count = 0
                                st.session_state.last_consolidation_check = datetime.now()
                                logger.info("Memory consolidation completed")
                        except Exception as e:
                            logger.error(
                                f"Consolidation check error: {str(e)}")
                else:
                    # Use LLM orchestration to intelligently execute email commands
                    result = execute_with_llm_orchestration(
                        user_command, agent_id)

                    if result.get('status') == 'error':
                        error_msg = f"❌ {result.get('message', 'Unknown error')}\n\n"
                        error_msg += ("💡 **Try commands like:**\n"
                                      "- `count emails I received today`\n"
                                      "- `list 5 unread emails`\n"
                                      "- `show emails from john@example.com`\n"
                                      "- `send email to someone@example.com`\n"
                                      "- `delete emails from newsletter@example.com`")
                        st.session_state.chat_messages.append({
                            'role': 'assistant',
                            'content': error_msg
                        })
                    else:
                        # Format response for chat
                        action = result.get('action', 'unknown')
                        formatted_result = format_email_result(result, action)

                        # Add assistant response to chat
                        st.session_state.chat_messages.append({
                            'role': 'assistant',
                            'content': formatted_result
                        })

                        # Store in agent memory
                        if MEMORY_AVAILABLE:
                            try:
                                memory = get_agent_memory(agent_id)
                                memory.add_interaction(
                                    command=user_command,
                                    action=action,
                                    result={'count': result.get(
                                        'count', 0), 'status': 'success'},
                                    metadata={'reasoning': result.get(
                                        'reasoning', '')}
                                )

                                # Increment interaction counter
                                st.session_state.interaction_count += 1

                                # Check if consolidation should run
                                consolidator = memory.get_consolidator()
                                if consolidator.should_consolidate(st.session_state.interaction_count):
                                    logger.info(
                                        f"Triggering memory consolidation (interactions: {st.session_state.interaction_count})")
                                    memory.run_consolidation()
                                    st.session_state.interaction_count = 0  # Reset counter
                                    st.session_state.last_consolidation_check = datetime.now()
                                    logger.info(
                                        "Memory consolidation completed")
                            except Exception as e:
                                logger.error(
                                    f"Memory storage/consolidation error: {str(e)}")
                                pass  # Silently fail memory storage

                        # Add to history
                        st.session_state.history.append({
                            'command': user_command,
                            'action': action,
                            'result': result,
                            'timestamp': datetime.now().isoformat()
                        })

            except Exception as e:
                _status.update(label="Something went wrong",
                               state="error", expanded=False)
                error_msg = f"❌ Error executing command: {str(e)}"
                st.session_state.chat_messages.append({
                    'role': 'assistant',
                    'content': error_msg
                })
            finally:
                # Always reset processing flag
                st.session_state.is_processing = False
                logger.debug("RESET is_processing = False")

        # Rerun to display the new messages
        logger.debug("Calling st.rerun()")
        st.rerun()

    # Optionally display detailed history in sidebar
    if st.session_state.history:
        with st.sidebar:
            st.divider()
            st.header("📜 Detailed History")
            with st.expander("View Command Details", expanded=False):
                for i, item in enumerate(reversed(st.session_state.history), 1):
                    st.markdown(f"**#{i}:** {item['command'][:40]}...")
                    st.caption(
                        f"Action: `{item['action']}` | Time: {item.get('timestamp', 'N/A')[:19]}")
                    st.divider()


if __name__ == "__main__":
    main()
