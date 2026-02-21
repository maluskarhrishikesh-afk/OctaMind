"""
Email Features Package

Modular feature implementations for the Gmail Email Agent.
Each module handles a specific email capability.
"""

from .action_items import (
    ActionItemExtractor, extract_action_items, get_all_pending_actions,
    get_saved_tasks, mark_action_complete
)
from .smart_reply import SmartReplyGenerator, generate_reply_suggestions, quick_reply
from .drafts import DraftManager, create_draft, list_drafts, get_draft, update_draft, send_draft, delete_draft
from .attachments import AttachmentManager, list_attachments, download_attachment, search_emails_with_attachments
from .categorizer import EmailCategorizer, auto_categorize_email, apply_smart_labels, create_category_rules
from .calendar_detect import CalendarDetector, extract_calendar_events, suggest_calendar_entry, export_to_calendar
from .followup import (
    FollowupTracker, mark_for_followup, get_pending_followups, check_unanswered_emails,
    mark_followup_done, dismiss_followup, send_followup_reminder
)
from .scheduler import EmailScheduler, schedule_email, list_scheduled_emails, cancel_scheduled_email, update_scheduled_email
from .contacts import ContactIntelligence, get_frequent_contacts, get_contact_summary, suggest_vip_contacts, export_contacts
from .priority import PriorityDetector, detect_urgent_emails, auto_prioritize
from .unsubscribe import UnsubscribeDetector, detect_newsletters, extract_unsubscribe_link
from .analytics import (
    EmailAnalytics, get_email_stats, get_productivity_insights,
    calculate_response_time, visualize_patterns, generate_weekly_report
)

__all__ = [
    # Action Items
    'ActionItemExtractor', 'extract_action_items', 'get_all_pending_actions',
    'get_saved_tasks', 'mark_action_complete',
    # Smart Reply
    'SmartReplyGenerator', 'generate_reply_suggestions', 'quick_reply',
    # Drafts
    'DraftManager', 'create_draft', 'list_drafts', 'get_draft', 'update_draft', 'send_draft', 'delete_draft',
    # Attachments
    'AttachmentManager', 'list_attachments', 'download_attachment', 'search_emails_with_attachments',
    # Categorizer
    'EmailCategorizer', 'auto_categorize_email', 'apply_smart_labels', 'create_category_rules',
    # Calendar
    'CalendarDetector', 'extract_calendar_events', 'suggest_calendar_entry', 'export_to_calendar',
    # Follow-up
    'FollowupTracker', 'mark_for_followup', 'get_pending_followups', 'check_unanswered_emails',
    'mark_followup_done', 'dismiss_followup', 'send_followup_reminder',
    # Scheduler
    'EmailScheduler', 'schedule_email', 'list_scheduled_emails', 'cancel_scheduled_email', 'update_scheduled_email',
    # Contacts
    'ContactIntelligence', 'get_frequent_contacts', 'get_contact_summary',
    'suggest_vip_contacts', 'export_contacts',
    # Priority
    'PriorityDetector', 'detect_urgent_emails', 'auto_prioritize',
    # Unsubscribe
    'UnsubscribeDetector', 'detect_newsletters', 'extract_unsubscribe_link',
    # Analytics
    'EmailAnalytics', 'get_email_stats', 'get_productivity_insights',
    'calculate_response_time', 'visualize_patterns', 'generate_weekly_report',
]
