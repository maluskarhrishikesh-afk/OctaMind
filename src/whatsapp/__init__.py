"""
WhatsApp agent package for OctaMind.

Exports all public tool functions so orchestrators and tests can import
from a single ``src.whatsapp`` namespace.

Usage:
    from src.whatsapp import send_message, get_unread_messages, summarize_conversation
"""

from .features import (
    # Messaging (7)
    send_message,
    send_media,
    send_template,
    reply_to_message,
    get_messages,
    get_unread_messages,
    mark_as_read,
    # Contacts (4)
    list_contacts,
    get_contact_info,
    get_frequent_contacts,
    set_contact_name,
    # Groups (3)
    list_groups,
    get_group_info,
    get_group_messages,
    # Search (4)
    search_messages,
    get_conversation,
    get_messages_by_date,
    get_media_messages,
    # AI Smart Features (8)
    summarize_conversation,
    extract_action_items,
    draft_message,
    generate_reply,
    detect_urgent_messages,
    extract_key_info,
    translate_message,
    sentiment_analysis,
    # Scheduler (5)
    schedule_message,
    list_scheduled_messages,
    cancel_scheduled_message,
    set_auto_reply,
    get_auto_reply_config,
    # Analytics (4)
    get_message_stats,
    get_response_time,
    get_activity_report,
    get_top_senders,
    # Cross-agent (2)
    forward_to_email,
    share_drive_file,
)
from .whatsapp_auth import credentials_configured, get_phone_number_id
from .webhook.receiver import start_webhook_in_background

__all__ = [
    # Messaging
    "send_message", "send_media", "send_template", "reply_to_message",
    "get_messages", "get_unread_messages", "mark_as_read",
    # Contacts
    "list_contacts", "get_contact_info", "get_frequent_contacts", "set_contact_name",
    # Groups
    "list_groups", "get_group_info", "get_group_messages",
    # Search
    "search_messages", "get_conversation", "get_messages_by_date", "get_media_messages",
    # Smart features
    "summarize_conversation", "extract_action_items", "draft_message", "generate_reply",
    "detect_urgent_messages", "extract_key_info", "translate_message", "sentiment_analysis",
    # Scheduler
    "schedule_message", "list_scheduled_messages", "cancel_scheduled_message",
    "set_auto_reply", "get_auto_reply_config",
    # Analytics
    "get_message_stats", "get_response_time", "get_activity_report", "get_top_senders",
    # Cross-agent
    "forward_to_email", "share_drive_file",
    # Auth / webhook
    "credentials_configured", "get_phone_number_id", "start_webhook_in_background",
]
