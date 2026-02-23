"""WhatsApp features package — exports every public tool function."""

from .messaging import (
    send_message,
    send_media,
    send_template,
    reply_to_message,
    get_messages,
    get_unread_messages,
    mark_as_read,
)
from .contacts import (
    list_contacts,
    get_contact_info,
    get_frequent_contacts,
    set_contact_name,
)
from .groups import (
    list_groups,
    get_group_info,
    get_group_messages,
)
from .search import (
    search_messages,
    get_conversation,
    get_messages_by_date,
    get_media_messages,
)
from .smart_features import (
    summarize_conversation,
    extract_action_items,
    draft_message,
    generate_reply,
    detect_urgent_messages,
    extract_key_info,
    translate_message,
    sentiment_analysis,
)
from .scheduler import (
    schedule_message,
    list_scheduled_messages,
    cancel_scheduled_message,
    set_auto_reply,
    get_auto_reply_config,
)
from .analytics import (
    get_message_stats,
    get_response_time,
    get_activity_report,
    get_top_senders,
)
from .cross_agent import (
    forward_to_email,
    share_drive_file,
)

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
]
