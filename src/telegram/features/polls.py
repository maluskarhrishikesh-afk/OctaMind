"""
Telegram poll tools.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..telegram_service import send_poll_api, stop_poll_api

logger = logging.getLogger("telegram_agent")


def send_poll(
    chat_id: int | str,
    question: str,
    options: List[str],
    is_anonymous: bool = True,
    allows_multiple_answers: bool = False,
) -> Dict[str, Any]:
    """
    Create a native Telegram poll.

    Args:
        chat_id:                  Target chat.
        question:                 Poll question (up to 300 characters).
        options:                  2–10 answer options.
        is_anonymous:             Whether voters are anonymous (default True).
        allows_multiple_answers:  Whether users can select multiple options.
    """
    try:
        if not (2 <= len(options) <= 10):
            return {
                "status": "error",
                "message": f"Polls require 2–10 options, got {len(options)}.",
            }

        resp = send_poll_api(
            chat_id,
            question,
            options,
            is_anonymous=is_anonymous,
            allows_multiple_answers=allows_multiple_answers,
        )
        msg_id = resp.get("message_id", 0)
        poll = resp.get("poll", {})

        return {
            "status": "success",
            "message_id": msg_id,
            "poll_id": poll.get("id", ""),
            "question": question,
            "options": options,
            "is_anonymous": is_anonymous,
            "chat_id": chat_id,
            "message": f"Poll '{question}' sent to {chat_id}.",
        }
    except Exception as exc:
        logger.error("send_poll failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def stop_poll(chat_id: int | str, message_id: int) -> Dict[str, Any]:
    """
    Stop an active poll (close voting and show final results).

    Args:
        chat_id:    Chat where the poll was sent.
        message_id: Message ID of the poll message.
    """
    try:
        poll = stop_poll_api(chat_id, message_id)
        options_summary = [
            f"{o['text']}: {o.get('voter_count', 0)} vote(s)"
            for o in poll.get("options", [])
        ]
        return {
            "status": "success",
            "poll_id": poll.get("id", ""),
            "question": poll.get("question", ""),
            "total_voter_count": poll.get("total_voter_count", 0),
            "results": options_summary,
            "message": f"Poll '{poll.get('question', '')}' closed. "
                       f"{poll.get('total_voter_count', 0)} total vote(s).",
        }
    except Exception as exc:
        logger.error("stop_poll failed: %s", exc)
        return {"status": "error", "message": str(exc)}
