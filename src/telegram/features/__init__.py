"""Telegram features package — exports every public tool function."""

from .messaging import (
    send_message,
    reply_to_message,
    forward_message,
    edit_message,
    delete_message,
    get_messages,
    get_unread_messages,
    get_chat_history,
    mark_as_read,
    send_chat_action,
)
from .chats import (
    list_chats,
    get_chat_info,
    get_chat_members,
    pin_message,
    unpin_message,
    leave_chat,
)
from .media import (
    send_media,
    send_media_group,
    get_file_url,
    get_media_messages,
)
from .scheduler import (
    schedule_message,
    list_scheduled_messages,
    cancel_scheduled_message,
)
from .search import (
    search_messages,
    get_messages_by_date,
    get_pinned_messages,
    get_message_stats,
)
from .polls import (
    send_poll,
    stop_poll,
)
from .smart_features import (
    summarize_chat,
    detect_urgent_messages,
    draft_message,
    extract_action_items,
    translate_message,
    sentiment_analysis,
)
from .cross_agent import (
    forward_to_email,
    share_drive_file,
)

__all__ = [
    # Messaging
    "send_message", "reply_to_message", "forward_message",
    "edit_message", "delete_message", "get_messages", "get_unread_messages",
    "get_chat_history", "mark_as_read", "send_chat_action",
    # Chats
    "list_chats", "get_chat_info", "get_chat_members",
    "pin_message", "unpin_message", "leave_chat",
    # Media
    "send_media", "send_media_group", "get_file_url", "get_media_messages",
    # Scheduler
    "schedule_message", "list_scheduled_messages", "cancel_scheduled_message",
    # Search
    "search_messages", "get_messages_by_date", "get_pinned_messages",
    "get_message_stats",
    # Polls
    "send_poll", "stop_poll",
    # AI Smart Features
    "summarize_chat", "detect_urgent_messages", "draft_message",
    "extract_action_items", "translate_message", "sentiment_analysis",
    # Cross-agent
    "forward_to_email", "share_drive_file",
]
