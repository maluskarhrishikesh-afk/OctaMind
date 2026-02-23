"""
WhatsApp AI-powered smart features.

These tools use the system LLM to add intelligence on top of message data:
summarisation, action item extraction, reply drafting, sentiment analysis,
urgency detection, translation, and key info extraction.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..webhook.message_store import (
    get_messages_for_contact,
    get_all_messages,
    get_message_by_id,
    get_unread_messages,
)

logger = logging.getLogger("whatsapp_agent")


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
                    "WhatsApp conversations. Be concise and structured."
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
    """Convert a list of message dicts into a readable conversation string."""
    lines = []
    for m in messages[:limit]:
        direction = "You" if m.get("direction") == "outbound" else m.get("from", "Them")
        ts = m.get("timestamp", "")[:16].replace("T", " ")
        body = m.get("body", "")
        lines.append(f"[{ts}] {direction}: {body}")
    return "\n".join(lines)


# ─── Tools ────────────────────────────────────────────────────────────────────

def summarize_conversation(phone: str, limit: int = 30) -> Dict[str, Any]:
    """
    Generate an AI summary of your WhatsApp conversation with a contact.

    Args:
        phone: Contact phone (E.164) or group ID.
        limit: Number of recent messages to include in the summary.
    """
    try:
        msgs = get_messages_for_contact(phone, limit=limit)
        if not msgs:
            return {
                "status": "error",
                "message": f"No messages found for {phone}.",
            }
        conversation = _msgs_to_text(msgs, limit=limit)
        prompt = (
            f"Summarize the following WhatsApp conversation in 3-5 bullet points. "
            f"Focus on key topics, decisions, and action items.\n\n"
            f"Conversation:\n{conversation}"
        )
        summary = _call_llm(prompt)
        return {
            "status": "success",
            "phone": phone,
            "summary": summary,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("summarize_conversation failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def extract_action_items(phone: str, limit: int = 20) -> Dict[str, Any]:
    """
    Extract tasks, deadlines, and to-dos from recent messages with a contact.

    Args:
        phone: Contact phone (E.164).
        limit: Messages to scan.
    """
    try:
        msgs = get_messages_for_contact(phone, limit=limit)
        if not msgs:
            return {"status": "error", "message": f"No messages found for {phone}."}
        conversation = _msgs_to_text(msgs, limit=limit)
        prompt = (
            "Extract all action items, tasks, deadlines, and to-dos from this "
            "WhatsApp conversation. Format as a numbered list. "
            "If none found, say 'No action items detected.'\n\n"
            f"Conversation:\n{conversation}"
        )
        result = _call_llm(prompt)
        return {
            "status": "success",
            "phone": phone,
            "action_items": result,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("extract_action_items failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def draft_message(to: str, context: str) -> Dict[str, Any]:
    """
    Generate a draft WhatsApp message based on context and conversation history.

    Args:
        to:      Recipient phone (E.164).
        context: Description of what you want to say (e.g. 'tell her I'll be 10 min late').
    """
    try:
        recent = get_messages_for_contact(to, limit=10)
        history = _msgs_to_text(recent, limit=10) if recent else "(no prior messages)"
        prompt = (
            f"Based on this WhatsApp conversation history:\n{history}\n\n"
            f"Draft a natural, concise WhatsApp message for this intent:\n'{context}'\n\n"
            "Return ONLY the message text — no quotes, no preamble."
        )
        draft = _call_llm(prompt, max_tokens=400)
        return {
            "status": "success",
            "to": to,
            "draft": draft,
            "context": context,
        }
    except Exception as exc:
        logger.error("draft_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def generate_reply(message_id: str) -> Dict[str, Any]:
    """
    Suggest 3 reply options for a specific inbound WhatsApp message.

    Args:
        message_id: WhatsApp message ID (wamid.xxx).
    """
    try:
        msg = get_message_by_id(message_id)
        if not msg:
            return {"status": "error", "message": f"Message {message_id} not found."}
        phone = msg.get("from", "")
        recent = get_messages_for_contact(phone, limit=10)
        history = _msgs_to_text(recent, limit=10)
        prompt = (
            f"Given this WhatsApp conversation:\n{history}\n\n"
            f"The latest message is:\n\"{msg.get('body', '')}\"\n\n"
            "Suggest exactly 3 reply options:\n"
            "1. A brief/casual reply\n"
            "2. A professional/formal reply\n"
            "3. A detailed reply\n\n"
            "Format:\n1. [brief reply]\n2. [professional reply]\n3. [detailed reply]"
        )
        suggestions = _call_llm(prompt, max_tokens=600)
        return {
            "status": "success",
            "message_id": message_id,
            "original_message": msg.get("body", ""),
            "suggestions": suggestions,
        }
    except Exception as exc:
        logger.error("generate_reply failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def detect_urgent_messages(limit: int = 30) -> Dict[str, Any]:
    """
    Scan recent inbound messages and identify urgent ones using AI.

    Args:
        limit: Number of recent messages to scan.
    """
    try:
        msgs = get_unread_messages(limit=limit)
        if not msgs:
            msgs = get_all_messages(limit=limit)
            msgs = [m for m in msgs if m.get("direction") == "inbound"]

        if not msgs:
            return {
                "status": "success",
                "urgent_messages": [],
                "count": 0,
                "note": "No messages to analyse.",
            }

        msgs_text = _msgs_to_text(msgs, limit=limit)
        prompt = (
            "Review these WhatsApp messages and identify any that are URGENT "
            "(require immediate attention, contain deadlines, emergencies, "
            "or time-sensitive requests).\n\n"
            "For each urgent message, output:\n"
            "- From: [number]\n"
            "- Body: [message text]\n"
            "- Reason: [why it's urgent]\n\n"
            f"Messages:\n{msgs_text}\n\n"
            "If none are urgent, say 'No urgent messages found.'"
        )
        result = _call_llm(prompt, max_tokens=800)
        return {
            "status": "success",
            "urgent_analysis": result,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("detect_urgent_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def extract_key_info(message_id: str) -> Dict[str, Any]:
    """
    Extract structured key information from a specific message (names, dates,
    phone numbers, addresses, URLs, amounts).

    Args:
        message_id: WhatsApp message ID.
    """
    try:
        msg = get_message_by_id(message_id)
        if not msg:
            return {"status": "error", "message": f"Message {message_id} not found."}
        body = msg.get("body", "")
        prompt = (
            f"Extract all key information from this WhatsApp message:\n\"{body}\"\n\n"
            "Extract (if present):\n"
            "- Names\n- Dates/times\n- Phone numbers\n"
            "- Locations/addresses\n- URLs/links\n"
            "- Amounts/prices\n- Other important details\n\n"
            "Return as a structured list. If none found, say 'No key information detected.'"
        )
        result = _call_llm(prompt, max_tokens=600)
        return {
            "status": "success",
            "message_id": message_id,
            "message_body": body,
            "key_info": result,
        }
    except Exception as exc:
        logger.error("extract_key_info failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def translate_message(message_id: str, target_language: str = "English") -> Dict[str, Any]:
    """
    Translate a WhatsApp message to a target language.

    Args:
        message_id:       WhatsApp message ID.
        target_language:  Target language name (e.g. 'English', 'Hindi', 'Spanish').
    """
    try:
        msg = get_message_by_id(message_id)
        if not msg:
            return {"status": "error", "message": f"Message {message_id} not found."}
        body = msg.get("body", "")
        prompt = (
            f"Translate the following WhatsApp message to {target_language}. "
            f"Return ONLY the translated text, nothing else.\n\n"
            f"Message: \"{body}\""
        )
        translated = _call_llm(prompt, max_tokens=400)
        return {
            "status": "success",
            "message_id": message_id,
            "original": body,
            "translated": translated,
            "target_language": target_language,
        }
    except Exception as exc:
        logger.error("translate_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def sentiment_analysis(phone: str, limit: int = 20) -> Dict[str, Any]:
    """
    Analyse the sentiment of recent messages with a contact.

    Args:
        phone: Contact phone (E.164).
        limit: Messages to include in analysis.
    """
    try:
        msgs = get_messages_for_contact(phone, limit=limit)
        if not msgs:
            return {"status": "error", "message": f"No messages found for {phone}."}
        conversation = _msgs_to_text(msgs, limit=limit)
        prompt = (
            "Analyse the sentiment of this WhatsApp conversation.\n\n"
            f"Conversation:\n{conversation}\n\n"
            "Provide:\n"
            "1. Overall sentiment (Positive / Neutral / Negative)\n"
            "2. Sentiment score (1-10, 10 = very positive)\n"
            "3. Key emotional tones detected\n"
            "4. Brief explanation (2-3 sentences)"
        )
        result = _call_llm(prompt, max_tokens=500)
        return {
            "status": "success",
            "phone": phone,
            "sentiment_analysis": result,
            "messages_analysed": len(msgs),
        }
    except Exception as exc:
        logger.error("sentiment_analysis failed: %s", exc)
        return {"status": "error", "message": str(exc)}
