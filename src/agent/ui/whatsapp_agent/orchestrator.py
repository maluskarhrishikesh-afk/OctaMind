"""
WhatsApp skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
send_text(to, body) – Send a plain text WhatsApp message. 'to' must be E.164 format (e.g. "+14155238886").
send_media_message(to, media_type, media_id_or_url, caption="") – Send an image/audio/video/document. media_type: "image"|"audio"|"video"|"document".
send_template_message(to, template_name, language_code, components=None) – Send an approved WhatsApp template message.
send_reaction(to, message_id, emoji) – React to a message with an emoji.
send_read_receipt(message_id) – Mark a message as read.
get_media_url(media_id) – Retrieve the download URL for a media item.
get_business_profile() – Retrieve your WhatsApp Business profile info.
""".strip()

_SKILL_CONTEXT = """
You are the WhatsApp Skill Agent connected to the WhatsApp Business API.
Help the user send messages, media, templates and reactions via WhatsApp.
Always validate that phone numbers are in E.164 format before calling send tools.
Warn the user that message delivery depends on their WhatsApp Business API setup.
After successfully resolving a contact name to a phone number, call save_context(topic="contact_resolved",
resolved_entities={"resolved_contact": "<E.164>", "contact_name": "<name>"}, awaiting="whatsapp_action")
so follow-up turns ('send another message to him') can reuse the resolved number without re-asking.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.whatsapp import whatsapp_service as ws  # noqa: PLC0415
    from src.agent.manifest.context_manifest import make_save_context_tool  # noqa: PLC0415

    return {
        "send_text": lambda to, body: ws.send_text(to, body),
        "send_media_message": lambda to, media_type, media_id_or_url, caption="": ws.send_media_message(to, media_type, media_id_or_url, caption),
        "send_template_message": lambda to, template_name, language_code, components=None: ws.send_template_message(to, template_name, language_code, components),
        "send_reaction": lambda to, message_id, emoji: ws.send_reaction(to, message_id, emoji),
        "send_read_receipt": lambda message_id: ws.send_read_receipt(message_id),
        "get_media_url": lambda media_id: ws.get_media_url(media_id),
        "get_business_profile": lambda: ws.get_business_profile(),
        # ── Context manifest ────────────────────────────────────────────
        "save_context": make_save_context_tool("whatsapp"),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="whatsapp",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ WhatsApp skill error: {exc}",
            "action": "react_response",
        }
