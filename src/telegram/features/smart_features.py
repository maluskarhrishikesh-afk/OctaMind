"""
Telegram AI-powered smart features.

Uses the system LLM to add intelligence on top of Telegram conversation data:
summarisation, urgency detection, reply drafting, action item extraction,
translation, and sentiment analysis.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..polling.message_store import (
    get_messages_for_chat,
    get_all_messages,
    get_unread_messages,
)

logger = logging.getLogger("telegram_agent")


def _llm():
    from src.agent.llm.llm_parser import get_llm_client
    return get_llm_client()


def _call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """Run a single LLM completion and return the response text."""
    client = _llm()
    resp = client.client.chat.completions.create(
        model=client.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful AI assistant specialized in analysing "
                    "Telegram conversations. Be concise and structured."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
        timeout=40,
    )
    return resp.choices[0].message.content.strip()


def _msgs_to_text(messages: List[Dict[str, Any]], limit: int = 30) -> str:
    """Convert message dicts to a readable conversation string."""
    lines = []
    for m in messages[:limit]:
        sender = "You" if m.get("direction") == "outbound" else m.get("from_user", "Them")
        ts = m.get("timestamp", "")[:16].replace("T", " ")
        body = m.get("text") or m.get("caption") or f"[{m.get('media_type', 'media')}]"
        lines.append(f"[{ts}] {sender}: {body}")
    return "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────────

def summarize_chat(chat_id: int | str, limit: int = 30) -> Dict[str, Any]:
    """
    Generate an AI summary of recent messages in a Telegram chat.

    Args:
        chat_id: Target chat ID or @username.
        limit:   Number of recent messages to include.
    """
    try:
        msgs = get_messages_for_chat(chat_id, limit=limit)
        if not msgs:
            return {"status": "error", "message": f"No messages found for chat {chat_id}."}

        conversation = _msgs_to_text(msgs, limit=limit)
        prompt = (
            "Summarize the following Telegram conversation in 3-5 bullet points. "
            "Focus on key topics, decisions, and action items.\n\n"
            f"Conversation:\n{conversation}"
        )
        summary = _call_llm(prompt)
        return {
            "status": "success",
            "chat_id": chat_id,
            "summary": summary,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("summarize_chat failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def detect_urgent_messages(limit: int = 50) -> Dict[str, Any]:
    """
    Scan recent messages and flag those that appear time-sensitive or urgent.

    Args:
        limit: Messages to scan.
    """
    try:
        msgs = get_all_messages(limit=limit)
        inbound = [m for m in msgs if m.get("direction") == "inbound"]
        if not inbound:
            return {"status": "error", "message": "No inbound messages to analyse."}

        conversation = _msgs_to_text(inbound, limit=limit)
        prompt = (
            "Review these Telegram messages and identify which ones are urgent, "
            "time-sensitive, or require an immediate reply.\n"
            "For each urgent message, output:\n"
            "  - Sender\n  - Preview of message\n  - Why it's urgent\n\n"
            "If none are urgent, say 'No urgent messages found.'\n\n"
            f"Messages:\n{conversation}"
        )
        result = _call_llm(prompt, max_tokens=800)
        return {
            "status": "success",
            "messages_scanned": len(inbound),
            "analysis": result,
        }
    except Exception as exc:
        logger.error("detect_urgent_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def draft_message(chat_id: int | str, context: str) -> Dict[str, Any]:
    """
    Generate a draft Telegram message based on intent and conversation history.

    Args:
        chat_id: Recipient chat.
        context: Description of what you want to convey.
    """
    try:
        recent = get_messages_for_chat(chat_id, limit=10)
        history = _msgs_to_text(recent, 10) if recent else "(no prior messages)"
        prompt = (
            f"Based on this Telegram conversation history:\n{history}\n\n"
            f"Draft a natural, concise Telegram message for this intent:\n'{context}'\n\n"
            "Return ONLY the message text — no quotes, no preamble."
        )
        draft = _call_llm(prompt, max_tokens=400)
        return {
            "status": "success",
            "chat_id": chat_id,
            "draft": draft,
            "context": context,
        }
    except Exception as exc:
        logger.error("draft_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def extract_action_items(chat_id: int | str, limit: int = 20) -> Dict[str, Any]:
    """
    Extract tasks, deadlines, and to-dos from recent messages in a chat.

    Args:
        chat_id: Target chat.
        limit:   Messages to scan.
    """
    try:
        msgs = get_messages_for_chat(chat_id, limit=limit)
        if not msgs:
            return {"status": "error", "message": f"No messages found for chat {chat_id}."}

        conversation = _msgs_to_text(msgs, limit=limit)
        prompt = (
            "Extract all action items, tasks, deadlines, and to-dos from this "
            "Telegram conversation. Format as a numbered list. "
            "If none found, say 'No action items detected.'\n\n"
            f"Conversation:\n{conversation}"
        )
        result = _call_llm(prompt)
        return {
            "status": "success",
            "chat_id": chat_id,
            "action_items": result,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("extract_action_items failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def translate_message(
    composite_id: str,
    target_language: str,
) -> Dict[str, Any]:
    """
    Translate a stored Telegram message to a target language.

    Args:
        composite_id:    Message id in format "chat_id:message_id".
        target_language: Language name or code (e.g. 'Hindi', 'Spanish', 'fr').
    """
    try:
        from ..polling.message_store import get_message_by_composite_id
        msg = get_message_by_composite_id(composite_id)
        if not msg:
            return {"status": "error", "message": f"Message '{composite_id}' not found."}

        text = msg.get("text") or msg.get("caption") or ""
        if not text:
            return {"status": "error", "message": "Message has no text to translate."}

        prompt = (
            f"Translate the following message to {target_language}. "
            "Return ONLY the translated text:\n\n" + text
        )
        translated = _call_llm(prompt, max_tokens=500)
        return {
            "status": "success",
            "message_id": composite_id,
            "original": text,
            "translated": translated,
            "target_language": target_language,
        }
    except Exception as exc:
        logger.error("translate_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def sentiment_analysis(chat_id: int | str, limit: int = 20) -> Dict[str, Any]:
    """
    Analyse the sentiment and tone of a Telegram conversation.

    Args:
        chat_id: Target chat.
        limit:   Messages to analyse.
    """
    try:
        msgs = get_messages_for_chat(chat_id, limit=limit)
        if not msgs:
            return {"status": "error", "message": f"No messages found for chat {chat_id}."}

        conversation = _msgs_to_text(msgs, limit=limit)
        prompt = (
            "Analyse the sentiment of this Telegram conversation. Provide:\n"
            "1. Overall tone (Positive / Neutral / Negative)\n"
            "2. Dominant emotions detected\n"
            "3. Conversation health score (1-10)\n"
            "4. Notable observations\n\n"
            f"Conversation:\n{conversation}"
        )
        result = _call_llm(prompt, max_tokens=600)
        return {
            "status": "success",
            "chat_id": chat_id,
            "analysis": result,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("sentiment_analysis failed: %s", exc)
        return {"status": "error", "message": str(exc)}
