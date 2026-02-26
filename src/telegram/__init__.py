"""
Telegram agent package for Octa Bot.

Exports all public tool functions so orchestrators and tests can import
from a single ``src.telegram`` namespace.

Usage:
    from src.telegram import send_message, get_unread_messages, summarize_chat
"""

from .features import (
    # Core messaging (10)
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
    # Chats & groups (6)
    list_chats,
    get_chat_info,
    get_chat_members,
    pin_message,
    unpin_message,
    leave_chat,
    # Media (4)
    send_media,
    send_media_group,
    get_file_url,
    get_media_messages,
    # Scheduler (3)
    schedule_message,
    list_scheduled_messages,
    cancel_scheduled_message,
    # Search (4)
    search_messages,
    get_messages_by_date,
    get_pinned_messages,
    get_message_stats,
    # Polls (2)
    send_poll,
    stop_poll,
    # AI Smart features (6)
    summarize_chat,
    detect_urgent_messages,
    draft_message,
    extract_action_items,
    translate_message,
    sentiment_analysis,
    # Cross-agent (2)
    forward_to_email,
    share_drive_file,
)
from .telegram_auth import credentials_configured, get_bot_token
from .polling.message_store import get_message_count

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
    # Auth & store
    "credentials_configured", "get_bot_token",
    "get_message_count",
]
