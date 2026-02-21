"""
Result formatters for the Email Agent UI.

format_email_result()         — top-level dispatcher for all email actions.
_format_new_feature_result()  — Phase 4 / newer-feature formatter sub-dispatcher.
format_date()                 — human-friendly date string helper.
display_emails_gmail_style()  — Gmail-style Streamlit card renderer.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any

import dateutil.parser
import streamlit as st

logger = logging.getLogger("email_agent")


# ── Top-level formatter ───────────────────────────────────────────────────────

def format_email_result(result: Dict[str, Any], action: str) -> str:
    """Format the result dict for display in the chat window."""
    if result.get('status') == 'error':
        return f"❌ Error: {result.get('message', 'Unknown error')}"

    reasoning_note = ""
    if result.get('reasoning'):
        reasoning_note = f"\n\n💡 *{result.get('reasoning')}*"

    if action == 'count':
        return (
            f"📊 Inbox Statistics:\n\n"
            f"**Total Messages:** {result.get('total_messages', 0):,}\n"
            f"**Unread Messages:** {result.get('unread_messages', 0):,}\n"
            f"**Total Threads:** {result.get('total_threads', 0):,}\n"
            f"**Unread Threads:** {result.get('unread_threads', 0):,}\n"
        ) + reasoning_note

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
        return (
            f"✅ Email sent successfully!\n\n"
            f"**Message ID:** {result.get('messageId', 'N/A')}\n"
            f"**Thread ID:** {result.get('threadId', 'N/A')}\n"
        )

    elif action == 'delete':
        if result.get('deleted_count', 0) == 0:
            return "📭 No emails found to delete."

        output = (
            f"🗑️ Successfully moved {result['deleted_count']} email(s) to trash!\n\n"
            "**Deleted Emails:**\n"
        )
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

            body = email.get('body', '').strip()
            if body:
                if len(body) > 500:
                    body = body[:500] + "...\n\n*(Content truncated)*"
                output += "\n   📧 **Content:**\n"
                output += "   ```\n"
                indented_body = '\n'.join(
                    ['   ' + line for line in body.split('\n')])
                output += indented_body + "\n"
                output += "   ```\n"
            else:
                snippet = email.get('snippet', '')
                if snippet:
                    output += f"\n   📝 Snippet: _{snippet}_\n"

            output += "\n---\n\n"
        return output

    elif action == 'summarize':
        if result.get('status') == 'error':
            return f"❌ Error: {result.get('message', 'Unknown error')}"

        output = (
            f"📝 **Email Summary**\n\n"
            f"**Subject:** {result.get('subject', 'N/A')}\n"
            f"**From:** {result.get('sender', 'N/A')}\n"
            f"**Date:** {result.get('date', 'N/A')}\n"
            f"**Word Count:** {result.get('word_count', 0)}\n\n"
            f"**Summary:**\n{result.get('summary', 'No summary available')}\n"
        )

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

        output = (
            f"🧵 **Thread Summary**\n\n"
            f"**Subject:** {result.get('subject', 'N/A')}\n"
            f"**Messages:** {result.get('message_count', 0)}\n"
            f"**Participants:** {', '.join(result.get('participants', []))}\n\n"
            f"**Summary:**\n{result.get('summary', 'No summary available')}\n"
        )

        discussion_points = result.get('discussion_points', [])
        if discussion_points:
            output += "\n**Discussion Points:**\n"
            for point in discussion_points:
                output += f"• {point}\n"

        output += f"\n**Status:** {result.get('status_summary', 'ongoing')}"

        pending_actions = result.get('pending_actions', [])
        if pending_actions:
            output += "\n\n**Pending Actions:**\n"
            for a in pending_actions:
                output += f"⏳ {a}\n"

        if result.get('note'):
            output += f"\n\n*{result['note']}*"

        return output

    elif action == 'daily_digest':
        if result.get('status') == 'error':
            return f"❌ Error: {result.get('message', 'Unknown error')}"

        output = (
            f"📅 **Daily Email Digest**\n\n"
            f"**Date:** {result.get('date', 'N/A')}\n"
            f"**Total Emails:** {result.get('total_emails', 0)}\n\n"
            f"**Summary:**\n{result.get('summary', 'No emails today')}\n"
        )

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

    # Delegate to newer-feature formatters
    new_result = _format_new_feature_result(result, action)
    if new_result is not None:
        return new_result
    return "✅ Action completed successfully!"


# ── Phase 4 / newer-feature formatter ────────────────────────────────────────

def _format_new_feature_result(result: Dict[str, Any], action: str) -> str | None:
    """Format results for newer email features.  Returns None if action not handled."""
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
        return (
            f"🏷️ Smart labelling complete!\n\n"
            f"**Processed:** {processed} emails\n"
            f"**Labelled:** {labelled} emails"
        )

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
            return (
                f"⏰ Email scheduled!\n\n"
                f"**To:** {result.get('to', 'N/A')}\n"
                f"**Send time:** {result.get('send_time', 'N/A')}\n"
                f"**ID:** `{result.get('scheduled_id', '')}`"
            )
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

    # ── Phase 4 formatters ────────────────────────────────────────────────────
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
            out = "📅 **Calendar Event Exported!**\n\n"
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
            return (
                f"✅ Scheduled email updated!\n\n"
                f"**New send time:** {result.get('new_send_time', 'N/A')}\n"
                f"**ID:** `{result.get('scheduled_id', '')}`"
            )
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
            out = "📤 **Contacts Exported!**\n\n"
            out += f"**Format:** {result.get('format', 'N/A').upper()}\n"
            out += f"📁 **Saved to:** `{result.get('file_path', 'N/A')}`\n"
            return out
        return f"❌ Export failed: {result.get('message', '')}"

    if action == 'response_time':
        if not result.get('has_response'):
            return "⏳ No reply found for this email thread yet."
        out = "⏱️ **Response Time Analysis:**\n\n"
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


# ── Date helper ───────────────────────────────────────────────────────────────

def format_date(date_str: str) -> str:
    """Format a date string to a human-readable form similar to Gmail's display."""
    try:
        email_date = dateutil.parser.parse(date_str)
        now = datetime.now(email_date.tzinfo or None)
        diff = now - email_date

        if diff.days == 0:
            return email_date.strftime("%I:%M %p")
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return email_date.strftime("%A")
        elif diff.days < 365:
            return email_date.strftime("%b %d")
        else:
            return email_date.strftime("%b %d, %Y")
    except Exception:
        return date_str[:20] if len(date_str) > 20 else date_str


# ── Gmail-style renderer ──────────────────────────────────────────────────────

def display_emails_gmail_style(emails: list) -> None:
    """Display a list of emails in a Gmail-inspired Streamlit card layout."""
    if not emails:
        st.info("📭 No emails found matching your criteria.")
        return

    st.success(f"📬 Found {len(emails)} email(s)")

    for i, email in enumerate(emails):
        is_unread = 'UNREAD' in email.get('labels', [])

        with st.container():
            if is_unread:
                st.markdown(
                    """
                    <div style="background-color: #f0f4ff; padding: 15px; border-radius: 8px;
                                border-left: 4px solid #4285f4; margin-bottom: 10px;">
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div style="background-color: #fafafa; padding: 15px; border-radius: 8px;
                                border-left: 4px solid #e0e0e0; margin-bottom: 10px;">
                    """,
                    unsafe_allow_html=True,
                )

            col1, col2 = st.columns([4, 1])
            with col1:
                sender = email['sender']
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
                st.markdown(
                    f"<div style='text-align: right; color: #666;'>{date_formatted}</div>",
                    unsafe_allow_html=True,
                )

            subject = email['subject']
            if is_unread:
                st.markdown(f"### **{subject}**")
            else:
                st.markdown(f"### {subject}")

            snippet = email.get('snippet', '')
            if snippet:
                st.markdown(
                    f"<p style='color: #666; margin: 5px 0;'>{snippet[:150]}...</p>",
                    unsafe_allow_html=True,
                )

            body = email.get('body', '').strip()
            if body:
                with st.expander("📖 Read full message"):
                    st.text(body)

            labels = [lbl for lbl in email.get('labels', [])
                      if lbl not in ['INBOX', 'UNREAD', 'IMPORTANT', 'CATEGORY_PERSONAL']]
            if labels:
                st.caption(f"🏷️ Labels: {', '.join(labels)}")

            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
