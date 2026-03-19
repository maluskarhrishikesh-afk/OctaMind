"""
Email skill orchestrator.

Exported function: execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag
from src.agent.runtime_paths import get_runtime_state_path
from src.agent.telemetry import log_fallback_to_react, log_fast_path_hit


_PENDING_MAILBOX_CLEANUP_PATH = get_runtime_state_path(
    "runtime_state",
    "email_mailbox_cleanup_pending.json",
    create_parent=True,
)

_EMAIL_ADDRESS_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_EMAIL_SUMMARY_INTENT_RE = re.compile(r"\b(summary|summarize|summarise)\b", re.IGNORECASE)
_EMAIL_SELECTION_RE = re.compile(
    r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last|latest)\b",
    re.IGNORECASE,
)
_EMAIL_LIST_ACTION_RE = re.compile(r"\b(list|show|display)\b", re.IGNORECASE)
_EMAIL_LIST_REFERENCE_RE = re.compile(
    r"\b(emails?|mails?|messages?|them|those|all\s+of\s+them|all\s+\d+)\b",
    re.IGNORECASE,
)
_EMAIL_COUNT_INTENT_RE = re.compile(
    r"\b(how\s+many|count|did\s+i\s+receive\s+only|only\s+\d+\s+emails?)\b",
    re.IGNORECASE,
)
_EMAIL_RELATIVE_DAY_RE = re.compile(r"\b(today|yesterday)\b", re.IGNORECASE)
_EXPLICIT_EMAIL_DELIVERY_PHRASES = (
    "email it to me",
    "mail it to me",
    "forward it to me",
    "email this to me",
    "mail this to me",
    "forward this to me",
    "email the summary to me",
    "mail the summary to me",
    "forward the summary to me",
)
_CURRENT_CHANNEL_DELIVERY_RE = re.compile(
    r"\b(send|share|show|tell)\b.{0,24}\b(it|this|that|me|here)\b",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL_REFERENCE_STOP_WORDS = frozenset(
    {
        "the",
        "email",
        "mail",
        "message",
        "messages",
        "one",
        "ones",
        "and",
        "from",
        "with",
        "about",
        "please",
        "send",
        "share",
        "show",
        "tell",
        "summarize",
        "summarise",
        "summary",
        "third",
        "second",
        "first",
        "last",
        "latest",
        "me",
        "it",
        "to",
        "here",
    }
)
_COUNT_WORD_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _return_fast_path_result(result: Dict[str, Any]) -> Dict[str, Any]:
    fast_path = str(result.get("_fast_path", "") or result.get("action", "unknown"))
    log_fast_path_hit("email", fast_path)
    return result
_ORDINAL_INDEX_MAP = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "last": -1,
    "latest": -1,
}


def _coerce_report_content(content: Any) -> str:
    if isinstance(content, dict):
        return (
            content.get("report_content")
            or content.get("summary")
            or content.get("content")
            or json.dumps(content, indent=2, ensure_ascii=False)
        )

    if isinstance(content, str):
        candidate = content.strip()
        if candidate.startswith(("{", "[")):
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(candidate)
                    return _coerce_report_content(parsed)
                except Exception:
                    continue
        return candidate

    return str(content)


def _normalize_query_text(user_query: str) -> str:
    return " ".join((user_query or "").lower().split())


def _extract_fast_path_query(user_query: str) -> str:
    text = str(user_query or "")
    if "->" in text:
        text = text.split("->", 1)[1]

    injected_block_markers = (
        "\n## Context from Previous Turn",
        "\n## Conversation Diary",
        "\n## Session State",
    )
    for marker in injected_block_markers:
        if marker in text:
            text = text.split(marker, 1)[0]

    assistant_response_markers = (
        "Mailbox cleanup preview:",
        "This will permanently delete every Gmail filter and every user-created label.",
        "If you want to proceed, reply with:",
    )
    for marker in assistant_response_markers:
        if marker in text:
            text = text.split(marker, 1)[0]

    return text.strip()


def _load_pending_mailbox_cleanup() -> Dict[str, Dict[str, Any]]:
    try:
        if _PENDING_MAILBOX_CLEANUP_PATH.exists():
            payload = json.loads(_PENDING_MAILBOX_CLEANUP_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def _save_pending_mailbox_cleanup(state: Dict[str, Dict[str, Any]]) -> None:
    _PENDING_MAILBOX_CLEANUP_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _get_pending_mailbox_cleanup(session_id: str) -> Dict[str, Any]:
    return _load_pending_mailbox_cleanup().get(session_id, {})


def _set_pending_mailbox_cleanup(session_id: str, preview: Dict[str, Any], action: str) -> None:
    if not session_id:
        return
    state = _load_pending_mailbox_cleanup()
    state[session_id] = {
        "preview": preview,
        "action": action,
    }
    _save_pending_mailbox_cleanup(state)


def _clear_pending_mailbox_cleanup(session_id: str) -> None:
    if not session_id:
        return
    state = _load_pending_mailbox_cleanup()
    if session_id in state:
        del state[session_id]
        _save_pending_mailbox_cleanup(state)


def _get_session_id(artifacts_out: Optional[Dict[str, Any]]) -> str:
    if not isinstance(artifacts_out, dict):
        return ""
    return str(artifacts_out.get("_session_id", "") or "").strip()


def _extract_ordinal_index(normalized_query: str) -> Optional[int]:
    for token, index in _ORDINAL_INDEX_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized_query):
            return index
    return None


def _extract_email_selection_indices(
    raw_query: str,
    normalized_query: str,
    available_count: int,
) -> List[int]:
    if available_count <= 0:
        return []
    if not _EMAIL_SUMMARY_INTENT_RE.search(normalized_query):
        return []
    if "email" not in normalized_query and "emails" not in normalized_query:
        return []

    selections: List[int] = []
    has_multi_separator = "," in raw_query or bool(re.search(r"\band\b", normalized_query))

    for token, index in _ORDINAL_INDEX_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized_query):
            resolved_index = available_count - 1 if index == -1 else index
            if 0 <= resolved_index < available_count and resolved_index not in selections:
                selections.append(resolved_index)

    if has_multi_separator:
        for match in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", normalized_query):
            resolved_index = int(match.group(1)) - 1
            if 0 <= resolved_index < available_count and resolved_index not in selections:
                selections.append(resolved_index)

    return selections


def _extract_requested_count(normalized_query: str) -> Optional[int]:
    digit_match = re.search(r"\b(\d{1,2})\b", normalized_query)
    if digit_match:
        return max(int(digit_match.group(1)), 1)
    for token, value in _COUNT_WORD_MAP.items():
        if re.search(rf"\b{token}\b", normalized_query):
            return value
    return None


def _read_email_context_entities() -> Dict[str, Any]:
    try:
        from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

        ctx = read_context(agent="email") or {}
        entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
        return entities if isinstance(entities, dict) else {}
    except Exception:
        return {}


def _read_files_context_entities() -> Dict[str, Any]:
    try:
        from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

        ctx = read_context(agent="files") or {}
        entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
        return entities if isinstance(entities, dict) else {}
    except Exception:
        return {}


def _read_listed_emails_from_context() -> List[Dict[str, Any]]:
    try:
        entities = _read_email_context_entities()
        listed = entities.get("listed_emails", []) if isinstance(entities, dict) else []
        return [item for item in listed if isinstance(item, dict) and str(item.get("id", "") or "").strip()]
    except Exception:
        return []


def _extract_relative_day(normalized_query: str) -> str:
    match = _EMAIL_RELATIVE_DAY_RE.search(str(normalized_query or ""))
    return str(match.group(1) or "").lower() if match else ""


def _build_relative_day_email_query(normalized_query: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    relative_day = _extract_relative_day(normalized_query)
    if relative_day not in {"today", "yesterday"}:
        return None

    current = now or datetime.now()
    target_day = current if relative_day == "today" else current - timedelta(days=1)
    start_of_day = target_day.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    query = f"after:{int(start_of_day.timestamp())} before:{int(end_of_day.timestamp())} in:inbox"
    return {
        "relative_day": relative_day,
        "query": query,
        "label": f"{target_day.strftime('%B')} {target_day.day}, {target_day.year}",
    }


def _looks_like_relative_day_listing_intent(normalized_query: str) -> bool:
    lowered = str(normalized_query or "").strip().lower()
    if not lowered or not _extract_relative_day(lowered):
        return False
    if _EMAIL_SUMMARY_INTENT_RE.search(lowered):
        return False
    if _EMAIL_COUNT_INTENT_RE.search(lowered):
        return False
    return bool(
        _EMAIL_LIST_ACTION_RE.search(lowered)
        or re.search(r"\bwhat\s+emails?\b", lowered)
        or re.search(r"\bwhich\s+emails?\b", lowered)
    )


def _looks_like_relative_day_count_intent(normalized_query: str) -> bool:
    lowered = str(normalized_query or "").strip().lower()
    if not lowered or not _extract_relative_day(lowered):
        return False
    return bool(_EMAIL_COUNT_INTENT_RE.search(lowered))


def _format_relative_day_email_list_message(
    emails: List[Dict[str, Any]],
    total_count: int,
    relative_day: str,
    date_label: str,
) -> str:
    shown = len(emails)
    if total_count <= 0:
        return f"There were no emails received {relative_day}."

    prefix = f"Here {'is' if shown == 1 else 'are'} {shown} of {total_count} email{'s' if total_count != 1 else ''} received {relative_day}"
    if date_label:
        prefix += f" ({date_label})"
    prefix += ":"
    lines = [prefix]
    for index, item in enumerate(emails, start=1):
        subject = str(item.get("subject", "No Subject") or "No Subject").strip()
        sender = str(item.get("sender", "Unknown") or "Unknown").strip()
        date = str(item.get("date", "") or "").strip()
        snippet = str(item.get("snippet", "") or "").strip()
        lines.append("")
        lines.append(f"{index}. Subject: {subject}")
        lines.append(f"   From: {sender}")
        if date:
            lines.append(f"   Date: {date}")
        if snippet:
            lines.append(f"   Preview: {snippet}")
    if shown < total_count:
        lines.append("")
        lines.append(f"Showing the first {shown} emails from that day.")
    return "\n".join(lines).strip()


def _try_relative_day_email_list_or_count(
    raw_query: str,
    normalized_query: str,
    all_tools: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    day_info = _build_relative_day_email_query(normalized_query)
    if not day_info:
        return None

    if not (_looks_like_relative_day_listing_intent(normalized_query) or _looks_like_relative_day_count_intent(normalized_query)):
        return None

    count_result = all_tools["count_matching_emails"](day_info["query"])
    if count_result.get("status") != "success":
        return count_result

    total_count = int(count_result.get("total_count", 0) or 0)
    if _looks_like_relative_day_count_intent(normalized_query):
        return {
            "status": "success",
            "action": "count_matching_emails",
            "_fast_path": "relative_day_email_count",
            "query": day_info["query"],
            "total_count": total_count,
            "message": f"You received {total_count} email{'s' if total_count != 1 else ''} {day_info['relative_day']}."
            + (f" ({day_info['label']})" if day_info["label"] else ""),
        }

    requested_count = _extract_requested_count(normalized_query)
    display_count = requested_count if requested_count is not None else min(total_count, 10)
    if "all" in normalized_query and requested_count is None:
        display_count = min(total_count, 10)
    if total_count <= 0:
        return {
            "status": "success",
            "action": "list_emails",
            "_fast_path": "relative_day_email_list",
            "query": day_info["query"],
            "emails": [],
            "count": 0,
            "total_count": 0,
            "message": f"There were no emails received {day_info['relative_day']}."
            + (f" ({day_info['label']})" if day_info["label"] else ""),
        }

    list_result = all_tools["list_emails"](query=day_info["query"], max_results=max(display_count, 1))
    if list_result.get("status") != "success":
        return list_result

    emails = list_result.get("results", []) if isinstance(list_result, dict) else []
    list_result["total_count"] = total_count
    try:
        from src.agent.manifest.context_manifest import auto_save_email_context  # noqa: PLC0415

        auto_save_email_context({
            "results": emails,
            "count": len(emails),
            "total_count": total_count,
        }, day_info["query"])
    except Exception:
        pass

    return {
        "status": "success",
        "action": "list_emails",
        "_fast_path": "relative_day_email_list",
        "query": day_info["query"],
        "emails": emails,
        "count": len(emails),
        "total_count": total_count,
        "message": _format_relative_day_email_list_message(
            emails,
            total_count,
            day_info["relative_day"],
            day_info["label"],
        ),
    }


def _email_reference_tokens(raw_query: str) -> List[str]:
    cleaned = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", " ", str(raw_query or ""), flags=re.IGNORECASE)
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]{3,}", cleaned.lower())
        if token not in _EMAIL_REFERENCE_STOP_WORDS
    ]
    return tokens


def _resolve_email_from_context(raw_query: str, normalized_query: str) -> Optional[Dict[str, Any]]:
    try:
        emails = _read_listed_emails_from_context()
        if not emails:
            return None

        ordinal_index = _extract_ordinal_index(normalized_query)
        if ordinal_index is not None:
            if ordinal_index == -1:
                return emails[-1]
            if 0 <= ordinal_index < len(emails):
                return emails[ordinal_index]

        tokens = _email_reference_tokens(raw_query)
        if not tokens:
            return None

        scored: List[tuple[int, Dict[str, Any]]] = []
        for item in emails:
            blob = " ".join(
                [
                    str(item.get("subject", "") or ""),
                    str(item.get("sender", "") or ""),
                    str(item.get("snippet", "") or ""),
                ]
            ).lower()
            score = sum(1 for token in tokens if token in blob)
            if score:
                scored.append((score, item))
        if not scored:
            return None
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_score = scored[0][0]
        top_items = [item for score, item in scored if score == top_score]
        return top_items[0] if len(top_items) == 1 else None
    except Exception:
        return None


def _resolve_email_selection_from_context(raw_query: str, normalized_query: str) -> List[Dict[str, Any]]:
    emails = _read_listed_emails_from_context()
    if not emails:
        return []

    indices = _extract_email_selection_indices(raw_query, normalized_query, len(emails))
    if indices:
        return [emails[index] for index in indices if 0 <= index < len(emails)]

    selected = _resolve_email_from_context(raw_query, normalized_query)
    return [selected] if selected else []


def _looks_like_listed_email_display_intent(normalized_query: str) -> bool:
    lowered = str(normalized_query or "").strip().lower()
    if not lowered:
        return False
    if _EMAIL_SUMMARY_INTENT_RE.search(lowered):
        return False
    if re.search(r"\b(reply|forward|delete|archive|send)\b", lowered):
        return False
    if not _EMAIL_LIST_ACTION_RE.search(lowered):
        return False
    return bool(_EMAIL_LIST_REFERENCE_RE.search(lowered))


def _format_listed_emails_message(emails: List[Dict[str, Any]]) -> str:
    count = len(emails)
    lines = [f"Here {'is' if count == 1 else 'are'} the {count} email{'s' if count != 1 else ''} from the current list:"]
    for index, item in enumerate(emails, start=1):
        subject = str(item.get("subject", "No Subject") or "No Subject").strip()
        sender = str(item.get("sender", "Unknown") or "Unknown").strip()
        date = str(item.get("date", "") or "").strip()
        snippet = str(item.get("snippet", "") or "").strip()
        lines.append("")
        lines.append(f"{index}. Subject: {subject}")
        lines.append(f"   From: {sender}")
        if date:
            lines.append(f"   Date: {date}")
        if snippet:
            lines.append(f"   Preview: {snippet}")
    return "\n".join(lines).strip()


def _try_listed_email_display_followup(normalized_query: str, all_tools: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _looks_like_listed_email_display_intent(normalized_query):
        return None

    entities = _read_email_context_entities()
    emails = _read_listed_emails_from_context()
    if not emails:
        return None

    requested_count = _extract_requested_count(normalized_query)
    total_count = int(entities.get("total_count", len(emails)) or len(emails))
    query = str(entities.get("query", "") or "").strip()

    if requested_count is not None and query and requested_count > len(emails):
        list_result = all_tools["list_emails"](query=query, max_results=requested_count)
        if list_result.get("status") == "success":
            refreshed = list_result.get("results", []) if isinstance(list_result, dict) else []
            if isinstance(refreshed, list) and refreshed:
                emails = refreshed
                try:
                    from src.agent.manifest.context_manifest import auto_save_email_context  # noqa: PLC0415

                    auto_save_email_context(
                        {
                            "results": emails,
                            "count": len(emails),
                            "total_count": max(total_count, len(emails)),
                        },
                        query,
                    )
                except Exception:
                    pass

    display_emails = emails[:requested_count] if requested_count is not None else emails
    if not display_emails:
        return None

    message = _format_listed_emails_message(display_emails)
    if requested_count is not None and total_count > len(display_emails):
        message = f"{message}\n\nShowing {len(display_emails)} of {total_count} emails from the current list."

    return {
        "status": "success",
        "action": "list_emails",
        "_fast_path": "listed_email_display",
        "message": message,
        "emails": display_emails,
        "count": len(display_emails),
        "total_count": max(total_count, len(display_emails)),
    }


def _looks_like_selected_email_summary_intent(normalized_query: str) -> bool:
    if not _EMAIL_SUMMARY_INTENT_RE.search(normalized_query):
        return False
    if _EMAIL_SELECTION_RE.search(normalized_query):
        return True
    if " email " in f" {normalized_query} ":
        return True
    return bool(
        re.search(
            r"\b\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*\d{1,2}(?:st|nd|rd|th)?)*(?:\s*(?:,?\s*and\s+\d{1,2}(?:st|nd|rd|th)?))?\s+emails?\b",
            normalized_query,
        )
    )


def _extract_delivery_recipient(raw_query: str) -> str:
    address_match = _EMAIL_ADDRESS_RE.search(str(raw_query or ""))
    if address_match:
        return address_match.group(0).strip()
    normalized_query = _normalize_query_text(raw_query)
    if any(phrase in normalized_query for phrase in _EXPLICIT_EMAIL_DELIVERY_PHRASES):
        return "me"
    return ""


def _resolve_file_attachment_from_context() -> str:
    entities = _read_files_context_entities()

    selected_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
    if isinstance(selected_paths, list):
        for raw_path in selected_paths:
            candidate = str(raw_path or "").strip()
            if candidate and Path(candidate).exists() and Path(candidate).is_file():
                return candidate

    listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []
    if isinstance(listed_files, list):
        for item in listed_files:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("path", "") or "").strip()
            if candidate and Path(candidate).exists() and Path(candidate).is_file():
                return candidate

    return ""


def _try_context_file_attachment_delivery(
    raw_query: str,
    normalized_query: str,
    all_tools: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if "send_email_with_attachment" not in all_tools:
        return None
    recipient = _extract_delivery_recipient(raw_query)
    if not recipient and re.search(r"\b(mail|email|forward|send)\b.{0,24}\b(it|this|that)\b.{0,24}\bto\s+me\b", normalized_query):
        recipient = "me"
    if not recipient:
        return None
    if _EMAIL_SUMMARY_INTENT_RE.search(normalized_query):
        return None
    if not any(token in normalized_query for token in ("mail", "email", "forward", "send")):
        return None

    attachment_path = _resolve_file_attachment_from_context()
    if not attachment_path:
        return None

    attachment_name = Path(attachment_path).name
    delivery_result = all_tools["send_email_with_attachment"](
        recipient,
        f"Requested file: {attachment_name}",
        f"Please find the attached file: {attachment_name}",
        attachment_path,
    )
    if delivery_result.get("status") != "success":
        return delivery_result

    return {
        "status": "success",
        "action": "send_email_with_attachment",
        "_fast_path": "context_file_attachment_delivery",
        "message": f"I emailed {attachment_name} to {recipient}.",
        "attachment_path": attachment_path,
        "delivery": delivery_result,
    }


def _format_email_summary_message(summary_result: Dict[str, Any]) -> str:
    subject = str(summary_result.get("subject", "No Subject") or "No Subject").strip()
    sender = str(summary_result.get("sender", "Unknown") or "Unknown").strip()
    date = str(summary_result.get("date", "") or "").strip()
    summary = str(summary_result.get("summary", "") or "").strip()
    key_points = summary_result.get("key_points", []) if isinstance(summary_result, dict) else []
    action_items = summary_result.get("action_items", []) if isinstance(summary_result, dict) else []

    lines = [
        f"Email Summary\nSubject: {subject}",
        f"From: {sender}",
    ]
    if date:
        lines.append(f"Date: {date}")
    if summary:
        lines.append("")
        lines.append(summary)
    if isinstance(key_points, list) and key_points:
        lines.append("")
        lines.append("Key points:")
        lines.extend(f"- {str(point).strip()}" for point in key_points if str(point).strip())
    if isinstance(action_items, list) and action_items:
        lines.append("")
        lines.append("Action items:")
        lines.extend(f"- {str(item).strip()}" for item in action_items if str(item).strip())
    return "\n".join(lines).strip()


def _format_email_summaries_message(summary_results: List[Dict[str, Any]]) -> str:
    if not summary_results:
        return ""
    if len(summary_results) == 1:
        return _format_email_summary_message(summary_results[0])

    sections: List[str] = []
    for index, result in enumerate(summary_results, start=1):
        sections.append(f"Email {index}\n{_format_email_summary_message(result)}")
    return "\n\n".join(sections).strip()


def _try_selected_email_summary_followup(
    raw_query: str,
    normalized_query: str,
    all_tools: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not _looks_like_selected_email_summary_intent(normalized_query):
        return None

    selected_emails = _resolve_email_selection_from_context(raw_query, normalized_query)
    if not selected_emails:
        return None

    summary_results: List[Dict[str, Any]] = []
    for selected_email in selected_emails:
        summary_result = all_tools["summarize_email"](selected_email.get("id", ""))
        if summary_result.get("status") != "success":
            return summary_result
        summary_results.append(summary_result)

    message = _format_email_summaries_message(summary_results)
    recipient = _extract_delivery_recipient(raw_query)
    if recipient:
        subject = (
            f"Email Summary: {summary_results[0].get('subject', 'Selected Email')}"
            if len(summary_results) == 1
            else f"Email Summaries: {len(summary_results)} selected emails"
        )
        email_result = all_tools["send_email"](
            recipient,
            subject,
            message,
        )
        if email_result.get("status") != "success":
            return email_result
        return {
            "status": "success",
            "action": "summarize_email",
            "_fast_path": "selected_email_summary",
            "message": f"{message}\n\nThe summary was emailed to {recipient}.",
            "summary_result": summary_results[0] if len(summary_results) == 1 else None,
            "summary_results": summary_results,
            "delivery": email_result,
        }

    if _CURRENT_CHANNEL_DELIVERY_RE.search(raw_query) or not recipient:
        return {
            "status": "success",
            "action": "summarize_email",
            "_fast_path": "selected_email_summary",
            "message": message,
            "summary_result": summary_results[0] if len(summary_results) == 1 else None,
            "summary_results": summary_results,
        }

    return None


def _mailbox_cleanup_scope(normalized_query: str) -> str:
    cleanup_verbs = ("delete", "remove", "clear", "wipe", "reset")
    filter_terms = ("rule", "rules", "filter", "filters")
    label_terms = ("label", "labels", "folder", "folders")
    mailbox_terms = ("mailbox", "gmail", "inbox")
    if not any(term in normalized_query for term in cleanup_verbs):
        return ""
    if not any(term in normalized_query for term in filter_terms):
        return ""
    if "all" not in normalized_query and not any(term in normalized_query for term in mailbox_terms) and "applied" not in normalized_query:
        return ""
    if any(term in normalized_query for term in label_terms):
        return "filters_and_labels"
    return "filters"


def _is_mailbox_cleanup_intent(normalized_query: str) -> bool:
    return bool(_mailbox_cleanup_scope(normalized_query))


def _is_mailbox_preview_intent(normalized_query: str) -> bool:
    preview_terms = ("show", "list", "preview", "what", "which", "check")
    filter_terms = ("rule", "rules", "filter", "filters")
    label_terms = ("label", "labels", "folder", "folders")
    mailbox_phrases = ("are there any", "do i have any")
    return (
        (
            any(term in normalized_query for term in preview_terms)
            or any(phrase in normalized_query for phrase in mailbox_phrases)
        )
        and any(term in normalized_query for term in filter_terms)
        and (
            any(term in normalized_query for term in label_terms)
            or "applied" in normalized_query
            or "mailbox" in normalized_query
        )
    )


def _has_mailbox_cleanup_confirmation(normalized_query: str) -> bool:
    confirmation_patterns = (
        r"\bconfirm(?:ed)?\b",
        r"\byes,? delete\b",
        r"\bgo ahead and delete\b",
        r"\bproceed to delete\b",
        r"\bdelete them now\b",
        r"\bdelete all of them now\b",
    )
    return any(re.search(pattern, normalized_query) for pattern in confirmation_patterns)


def _is_affirmative_reply(normalized_query: str) -> bool:
    reply_patterns = (
        r"^yes[.!?\s]*$",
        r"^yes,? delete(?: them| it| all(?: of them)?)?[.!?\s]*$",
        r"^delete (?:them|it|all(?: of them)?) now[.!?\s]*$",
        r"^go ahead(?: and delete(?: them| it| all(?: of them)?)?)?[.!?\s]*$",
        r"^proceed(?: to delete(?: them| it| all(?: of them)?)?)?[.!?\s]*$",
        r"^do it[.!?\s]*$",
        r"^confirm(?: delete(?: all)? filters(?: and labels)?)?[.!?\s]*$",
    )
    stripped = normalized_query.strip()
    return any(re.fullmatch(pattern, stripped) for pattern in reply_patterns)


def _is_negative_reply(normalized_query: str) -> bool:
    reply_patterns = (
        r"^no[.!?\s]*$",
        r"^cancel(?: it| that)?[.!?\s]*$",
        r"^don't delete(?: them| it| anything)?[.!?\s]*$",
        r"^do not delete(?: them| it| anything)?[.!?\s]*$",
        r"^stop[.!?\s]*$",
        r"^never mind[.!?\s]*$",
    )
    stripped = normalized_query.strip()
    return any(re.fullmatch(pattern, stripped) for pattern in reply_patterns)


def _mailbox_cleanup_action_description(action: str) -> str:
    if action == "delete_all_filters_and_labels":
        return "filter and label deletion"
    return "filter deletion"


def _build_mailbox_cleanup_reply_markup(action: str) -> Dict[str, Any]:
    return {
        "inline_keyboard": [[
            {
                "text": "Yes, delete",
                "callback_data": f"mailbox_cleanup:confirm:{action}",
            },
            {
                "text": "No, cancel",
                "callback_data": f"mailbox_cleanup:cancel:{action}",
            },
        ]]
    }


def _extract_sender_rule_request(raw_query: str) -> Dict[str, str]:
    query = str(raw_query or "")
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", query, flags=re.IGNORECASE)
    if not email_match:
        return {}

    label_match = re.search(
        r'(?:folder|label)\s+named\s+["\']([^"\']+)["\']',
        query,
        flags=re.IGNORECASE,
    )
    if not label_match:
        label_match = re.search(
            r'(?:folder|label)\s+named\s+([^\n\r\.!?]+)',
            query,
            flags=re.IGNORECASE,
        )
    if not label_match:
        return {}

    label_name = str(label_match.group(1)).strip().strip('"\'').strip()
    if not label_name:
        return {}

    return {
        "from_email": email_match.group(0).strip(),
        "label_name": label_name,
    }


def _is_sender_rule_creation_intent(normalized_query: str, raw_query: str) -> bool:
    future_terms = ("in future", "future", "automatically", "always")
    sender_terms = ("comes from", "from this id", "from this email", "from:", "from ")
    label_terms = ("folder named", "label named", "put to a folder", "put in a folder", "go to a folder")
    request = _extract_sender_rule_request(raw_query)
    return (
        bool(request)
        and any(term in normalized_query for term in future_terms)
        and any(term in normalized_query for term in sender_terms)
        and any(term in normalized_query for term in label_terms)
    )


def _format_mailbox_preview(preview: Dict[str, Any]) -> str:
    filters = preview.get("filters", []) if isinstance(preview, dict) else []
    user_labels = preview.get("user_labels", []) if isinstance(preview, dict) else []

    lines = [
        "Mailbox cleanup preview:",
        f"- Gmail filters: {len(filters)}",
        f"- User labels: {len(user_labels)}",
    ]

    if filters:
        lines.append("Filters:")
        for index, item in enumerate(filters[:10], 1):
            criteria_parts = []
            if item.get("from"):
                criteria_parts.append(f"from={item['from']}")
            if item.get("to"):
                criteria_parts.append(f"to={item['to']}")
            if item.get("subject"):
                criteria_parts.append(f"subject={item['subject']}")
            if item.get("query"):
                criteria_parts.append(f"query={item['query']}")
            criteria_text = ", ".join(criteria_parts) if criteria_parts else "no criteria"
            lines.append(f"{index}. {criteria_text}")
        if len(filters) > 10:
            lines.append(f"...and {len(filters) - 10} more filter(s).")

    if user_labels:
        label_names = [str(label.get("name", "")).strip() for label in user_labels if str(label.get("name", "")).strip()]
        if label_names:
            preview_names = ", ".join(label_names[:15])
            if len(label_names) > 15:
                preview_names += f", and {len(label_names) - 15} more"
            lines.append(f"User labels: {preview_names}")

    return "\n".join(lines)


def _format_sender_rule_result(result: Dict[str, Any], from_email: str, label_name: str) -> Dict[str, Any]:
    if result.get("status") != "success":
        return result

    emails_labeled = int(result.get("emails_labeled", 0) or 0)
    future_created = bool(result.get("future_rule_created"))
    filter_id = str(result.get("filter_id", "") or "").strip()
    future_text = (
        "Created a Gmail filter for future matching emails."
        if future_created
        else "A matching Gmail filter already exists for future emails."
        if filter_id
        else "Future Gmail filter status could not be confirmed."
    )
    result["action"] = "create_smart_label_rule"
    result["_fast_path"] = "sender_rule_creation"
    result["message"] = (
        f"Applied label '{label_name}' to {emails_labeled} existing email(s) from {from_email}. "
        f"{future_text}"
    )
    return result

# ---------------------------------------------------------------------------
# Tool builders (lazy so Gmail auth errors surface at call time not import time)
# ---------------------------------------------------------------------------

def _build_all_tools() -> Dict[str, Any]:
    from src.email.gmail_service import _get_client  # noqa: PLC0415
    from src.agent.manifest.context_manifest import auto_save_email_context  # noqa: PLC0415

    svc = _get_client()
    try:
        _profile = svc.gmail_service.users().getProfile(userId="me").execute()
        authenticated_email = str(_profile.get("emailAddress", "") or "").strip()
    except Exception:
        authenticated_email = ""

    def _wrap_email_listing(messages: Any, query: str, label: str) -> dict:
        emails = messages if isinstance(messages, list) else []
        auto_save_email_context(
            {
                "results": emails,
                "count": len(emails),
                "total_count": len(emails),
            },
            query,
        )
        return {
            "status": "success",
            "count": len(emails),
            "total_count": len(emails),
            "query": query,
            "results": emails,
            "emails": emails,
            "message": f"Found {len(emails)} {label}.",
        }

    def _coerce_message_id(message_id: Any) -> str:
        if isinstance(message_id, dict):
            return str(message_id.get("id", "")).strip()
        if isinstance(message_id, list):
            first = message_id[0] if message_id else {}
            return str(first.get("id", "")).strip() if isinstance(first, dict) else ""
        if not isinstance(message_id, str):
            return str(message_id or "").strip()

        candidate = message_id.strip()
        if not candidate:
            return ""
        if candidate.startswith(("[", "{")):
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(candidate)
                    return _coerce_message_id(parsed)
                except Exception:
                    continue
        return candidate

    def _normalize_recipient(recipient: str) -> str:
        normalized = str(recipient or "").strip()
        if normalized.lower() in {"me", "myself", "my email", "my email address"} and authenticated_email:
            return authenticated_email
        return normalized

    def send_email(to: str, subject: str, message: str) -> dict:
        return svc.send_email(_normalize_recipient(to), subject, message)

    def send_email_with_attachment(to: str, subject: str, message: str, attachment_path: str) -> dict:
        return svc.send_email_with_attachment(_normalize_recipient(to), subject, message, attachment_path)

    def list_emails(query: str = "in:inbox", max_results: int = 10) -> dict:
        result = svc.list_emails(query, max_results)
        return _wrap_email_listing(result, query, "email(s)")

    def get_latest_emails(n_emails: int = 10) -> dict:
        result = svc.list_emails("in:inbox", n_emails)
        return _wrap_email_listing(result, "in:inbox", "latest inbox email(s)")

    def get_inbox_count() -> dict:
        return svc.get_inbox_count()

    def count_matching_emails(query: str = "") -> dict:
        return svc.count_matching_emails(query)

    def get_todays_emails(n_emails: int = 50) -> dict:
        result = svc.get_todays_emails(max_results=n_emails)
        return _wrap_email_listing(result, "today", "email(s) received today")

    def delete_emails(query: str, max_results: int = 10) -> dict:
        return svc.delete_emails(query, max_results)

    def summarize_email(message_id: str) -> dict:
        resolved_id = _coerce_message_id(message_id)
        if not resolved_id:
            return {
                "status": "error",
                "message": "Could not resolve the selected email id for summarization.",
            }
        return svc.summarize_email(resolved_id)

    def generate_daily_digest() -> dict:
        return svc.generate_daily_digest()

    def create_draft(to: str, subject: str, body: str) -> dict:
        return svc.create_draft(to, subject, body)

    def list_drafts() -> dict:
        return svc.list_drafts()

    def send_draft(draft_id: str) -> dict:
        return svc.send_draft(draft_id)

    def extract_action_items(message_id: str) -> dict:
        return svc.extract_action_items(message_id)

    def get_all_pending_actions() -> dict:
        return svc.get_all_pending_actions()

    def detect_urgent_emails() -> dict:
        return svc.detect_urgent_emails()

    def get_email_stats(days: int = 7) -> dict:
        return svc.get_email_stats(days)

    def get_frequent_contacts() -> dict:
        return svc.get_frequent_contacts()

    def search_emails_with_attachments(file_type: str = "") -> dict:
        return svc.search_emails_with_attachments(file_type)

    def generate_weekly_report() -> dict:
        return svc.generate_weekly_report()

    def schedule_email(to: str, subject: str, body: str, send_time: str) -> dict:
        return svc.schedule_email(to, subject, body, send_time)

    def extract_calendar_events(message_id: str) -> dict:
        return svc.extract_calendar_events(message_id)

    def create_label(label_name: str) -> dict:
        return svc.create_label(label_name)

    def list_all_filters_and_labels() -> dict:
        return svc.list_all_filters_and_labels()

    def delete_all_filters() -> dict:
        return svc.delete_all_filters()

    def delete_all_filters_and_labels() -> dict:
        return svc.delete_all_filters_and_labels()

    def move_emails_to_label(query: str, label_name: str, max_results: int = 50) -> dict:
        return svc.move_emails_to_label(query, label_name, max_results)

    def set_vacation_responder(
        enabled: bool,
        subject: str = "",
        body: str = "",
        start_date: str = "",
        end_date: str = "",
        restrict_to_contacts: bool = False,
    ) -> dict:
        return svc.set_vacation_responder(enabled, subject, body, start_date, end_date, restrict_to_contacts)

    def get_vacation_responder() -> dict:
        return svc.get_vacation_responder()

    def sync_contacts() -> dict:
        from src.email.features.contacts_sync import sync_contacts as _sync
        return _sync()

    def search_contacts(query: str) -> dict:
        from src.email.features.contacts_sync import search_contacts as _search
        return _search(query)

    def list_contacts(limit: int = 50) -> dict:
        from src.email.features.contacts_sync import list_contacts as _list
        return _list(limit)

    def fetch_emails_to_markdown(
        query: str = "in:inbox",
        max_results: int = 5,
        cap: int = 20,
    ) -> dict:
        result = svc.fetch_emails_to_markdown(query, max_results, cap)
        # fetch_emails_to_markdown returns a dict with an 'emails' key
        msgs = result.get("emails", []) if isinstance(result, dict) else []
        auto_save_email_context(msgs, query)
        return result

    def unsubscribe_email(message_id: str) -> dict:
        return svc.unsubscribe_email(message_id)

    def archive_emails(query: str, max_results: int = 50) -> dict:
        return svc.archive_emails(query, max_results)

    def thread_mute(thread_id: str) -> dict:
        return svc.thread_mute(thread_id)

    def thread_archive(thread_id: str) -> dict:
        return svc.thread_archive(thread_id)

    def thread_delete(thread_id: str) -> dict:
        return svc.thread_delete(thread_id)

    def create_smart_label_rule(
        label_name: str,
        from_email: str = "",
        subject_contains: str = "",
        to_email: str = "",
        also_archive: bool = False,
    ) -> dict:
        return svc.create_smart_label_rule(
            label_name, from_email, subject_contains, to_email, also_archive
        )

    def delete_smart_label_rule(
        from_email: str = "",
        subject_contains: str = "",
        to_email: str = "",
        label_name: str = "",
    ) -> dict:
        return svc.delete_smart_label_rule(
            from_email, subject_contains, to_email, label_name
        )

    def find_unanswered_emails(days: int = 3, max_results: int = 20) -> dict:
        return svc.find_unanswered_emails(days, max_results)

    def empty_trash() -> dict:
        return svc.empty_trash()

    def batch_mark_spam(query: str, max_results: int = 50) -> dict:
        return svc.batch_mark_spam(query, max_results)

    def add_forwarding_address(forward_to: str) -> dict:
        return svc.add_forwarding_address(forward_to)

    def enable_email_forwarding(forward_to: str) -> dict:
        return svc.enable_email_forwarding(forward_to)

    def get_signature(send_as_email: str = "me") -> dict:
        return svc.get_signature(send_as_email)

    def set_signature(signature_html: str, send_as_email: str = "me") -> dict:
        return svc.set_signature(signature_html, send_as_email)

    def save_email_template(name: str, subject: str, body: str) -> dict:
        return svc.save_email_template(name, subject, body)

    def list_email_templates() -> dict:
        return svc.list_email_templates()

    def send_from_template(template_name: str, to: str, variables: dict = None) -> dict:
        return svc.send_from_template(template_name, to, variables)

    def recover_deleted_emails(query: str = "", max_results: int = 20) -> dict:
        return svc.recover_deleted_emails(query, max_results)

    def analyze_email_sentiment(message_id: str) -> dict:
        return svc.analyze_email_sentiment(message_id)

    def extract_urls_from_email(message_id: str) -> dict:
        return svc.extract_urls_from_email(message_id)

    def get_email_chains_summary(max_results: int = 10) -> dict:
        return svc.get_email_chains_summary(max_results)

    def send_completion_reminder(message_id: str, days: int = 3) -> dict:
        return svc.send_completion_reminder(message_id, days)

    def write_pdf_report(path: str, title: str, content: str) -> dict:
        from src.files.features.file_ops import write_pdf_report as _wpdf  # noqa: PLC0415
        content = _coerce_report_content(content)
        return _wpdf(path, title, content)

    def write_text_file(path: str, content: str) -> dict:
        try:
            from pathlib import Path as _Path
            _p = _Path(path).expanduser()
            _p.parent.mkdir(parents=True, exist_ok=True)
            _p.write_text(content, encoding="utf-8")
            return {"status": "success", "path": str(_p), "file_path": str(_p),
                    "message": f"Written {len(content)} chars to '{_p}'."}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def deliver_file(path: str) -> dict:
        from src.files.features.file_ops import deliver_file as _df  # noqa: PLC0415
        return _df(path)

    return {
        "send_email": send_email,
        "send_email_with_attachment": send_email_with_attachment,
        "list_emails": list_emails,
        "get_latest_emails": get_latest_emails,
        "get_inbox_count": get_inbox_count,
        "count_matching_emails": count_matching_emails,
        "get_todays_emails": get_todays_emails,
        "delete_emails": delete_emails,
        "summarize_email": summarize_email,
        "generate_daily_digest": generate_daily_digest,
        "create_draft": create_draft,
        "list_drafts": list_drafts,
        "send_draft": send_draft,
        "extract_action_items": extract_action_items,
        "get_all_pending_actions": get_all_pending_actions,
        "detect_urgent_emails": detect_urgent_emails,
        "get_email_stats": get_email_stats,
        "get_frequent_contacts": get_frequent_contacts,
        "search_emails_with_attachments": search_emails_with_attachments,
        "generate_weekly_report": generate_weekly_report,
        "schedule_email": schedule_email,
        "extract_calendar_events": extract_calendar_events,
        "create_label": create_label,
        "list_all_filters_and_labels": list_all_filters_and_labels,
        "delete_all_filters": delete_all_filters,
        "delete_all_filters_and_labels": delete_all_filters_and_labels,
        "move_emails_to_label": move_emails_to_label,
        "set_vacation_responder": set_vacation_responder,
        "get_vacation_responder": get_vacation_responder,
        "sync_contacts": sync_contacts,
        "search_contacts": search_contacts,
        "list_contacts": list_contacts,
        "fetch_emails_to_markdown": fetch_emails_to_markdown,
        "unsubscribe_email": unsubscribe_email,
        "archive_emails": archive_emails,
        "thread_mute": thread_mute,
        "thread_archive": thread_archive,
        "thread_delete": thread_delete,
        "create_smart_label_rule": create_smart_label_rule,
        "delete_smart_label_rule": delete_smart_label_rule,
        "find_unanswered_emails": find_unanswered_emails,
        "empty_trash": empty_trash,
        "batch_mark_spam": batch_mark_spam,
        "add_forwarding_address": add_forwarding_address,
        "enable_email_forwarding": enable_email_forwarding,
        "get_signature": get_signature,
        "set_signature": set_signature,
        "save_email_template": save_email_template,
        "list_email_templates": list_email_templates,
        "send_from_template": send_from_template,
        # ── NEW ────────────────────────────────────────────────────────
        "recover_deleted_emails": recover_deleted_emails,
        "analyze_email_sentiment": analyze_email_sentiment,
        "extract_urls_from_email": extract_urls_from_email,
        "get_email_chains_summary": get_email_chains_summary,
        "send_completion_reminder": send_completion_reminder,
        # ── Report / deliver (for PDF summaries) ─────────────────────────
        "write_pdf_report": write_pdf_report,
        "write_text_file": write_text_file,
        "deliver_file": deliver_file,
        # ── Context Manifest ──────────────────────────────────────────────
        "save_context": __import__(
            "src.agent.manifest.context_manifest", fromlist=["make_save_context_tool"]
        ).make_save_context_tool("email"),
    }

def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a FAISS-filtered tool map for the ReAct engine.

    Falls back to the full tool map if FAISS selection fails.
    """
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415
        selected = select_tool_names(
            "email", user_query,
            always_include=[
                "save_context",
                "deliver_file",
                "write_pdf_report",
                "fetch_emails_to_markdown",
                "send_email_with_attachment",
                "summarize_email",
            ],
        )
        filtered = {n: all_tools[n] for n in selected if n in all_tools}
        if filtered:
            return filtered
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("email.orchestrator").warning(
            "[tool-map] FAISS filtering failed (%s) — using full tool map", exc
        )
    return all_tools


def _load_skill_context() -> str:
    """Load the email skill context from skill_context.md (next to this file)."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()

# ---------------------------------------------------------------------------
# Required entry-point
# ---------------------------------------------------------------------------

def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner (needs all tools to plan)."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    docs = get_all_tool_docs("email")
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("email.orchestrator").error(
            "[email-agent] skills.md returned no tools — check ui/email_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs

def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine (cosine-similarity top-K)."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    docs = load_tool_docs(
        "email", user_query,
        always_include=[
            "save_context",
            "deliver_file",
            "write_pdf_report",
            "fetch_emails_to_markdown",
            "send_email_with_attachment",
            "summarize_email",
        ],
    )
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("email.orchestrator").error(
            "[email-agent] FAISS returned no tool docs for query=%r — "
            "check ui/email_agent/skills.md", user_query[:60]
        )
    return docs

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat.

    Primary path: DAG planner (2 LLM calls regardless of task length).
    Fallback:      ReAct loop (1 LLM call per step, up to 10 iterations).
    """
    all_tools = _build_all_tools()
    fast_path_query = _extract_fast_path_query(user_query)
    normalized_query = _normalize_query_text(fast_path_query)
    session_id = _get_session_id(artifacts_out)
    is_sender_rule_intent = _is_sender_rule_creation_intent(normalized_query, fast_path_query)
    is_mailbox_preview = _is_mailbox_preview_intent(normalized_query)
    is_mailbox_cleanup = _is_mailbox_cleanup_intent(normalized_query)

    pending_cleanup = _get_pending_mailbox_cleanup(session_id) if session_id else {}
    if pending_cleanup:
        # A fresh explicit intent should not be interpreted as a reply to an older
        # mailbox-cleanup confirmation prompt.
        if is_sender_rule_intent or is_mailbox_preview or is_mailbox_cleanup:
            _clear_pending_mailbox_cleanup(session_id)
            pending_cleanup = {}
        if _is_negative_reply(normalized_query):
            action = str(pending_cleanup.get("action", "delete_all_filters") or "delete_all_filters")
            _clear_pending_mailbox_cleanup(session_id)
            return {
                "status": "success",
                "action": action,
                "_fast_path": "mailbox_cleanup_cancelled",
                "message": f"Mailbox-wide {_mailbox_cleanup_action_description(action)} was canceled.",
            }
        if _is_affirmative_reply(normalized_query):
            pending_action = str(pending_cleanup.get("action", "delete_all_filters") or "delete_all_filters")
            result = all_tools[pending_action]()
            _clear_pending_mailbox_cleanup(session_id)
            result.setdefault("action", pending_action)
            result.setdefault("_fast_path", "mailbox_cleanup")
            result["preview"] = pending_cleanup.get("preview", {})
            return _return_fast_path_result(result)

    if is_sender_rule_intent and "create_smart_label_rule" in all_tools:
        request = _extract_sender_rule_request(fast_path_query)
        result = all_tools["create_smart_label_rule"](
            label_name=request["label_name"],
            from_email=request["from_email"],
        )
        return _return_fast_path_result(
            _format_sender_rule_result(result, request["from_email"], request["label_name"])
        )

    if is_mailbox_preview:
        preview = all_tools["list_all_filters_and_labels"]()
        if preview.get("status") != "success":
            return preview
        preview.setdefault("action", "list_all_filters_and_labels")
        preview.setdefault("_fast_path", "mailbox_cleanup_preview")
        preview["message"] = _format_mailbox_preview(preview)
        return _return_fast_path_result(preview)

    if is_mailbox_cleanup:
        cleanup_scope = _mailbox_cleanup_scope(normalized_query)
        cleanup_action = (
            "delete_all_filters_and_labels"
            if cleanup_scope == "filters_and_labels"
            else "delete_all_filters"
        )
        preview = all_tools["list_all_filters_and_labels"]()
        if preview.get("status") != "success":
            return preview
        preview.setdefault("action", "list_all_filters_and_labels")
        preview.setdefault("_fast_path", "mailbox_cleanup_preview")
        preview_message = _format_mailbox_preview(preview)

        if not _has_mailbox_cleanup_confirmation(normalized_query):
            _set_pending_mailbox_cleanup(session_id, preview, cleanup_action)
            delete_scope_text = (
                "every Gmail filter and every user-created label"
                if cleanup_action == "delete_all_filters_and_labels"
                else "every Gmail filter"
            )
            return {
                "status": "confirmation_required",
                "action": cleanup_action,
                "_fast_path": "mailbox_cleanup_confirmation",
                "preview": preview,
                "channel_payloads": {
                    "telegram": {
                        "reply_markup": _build_mailbox_cleanup_reply_markup(cleanup_action),
                    }
                },
                "message": (
                    f"{preview_message}\n"
                    f"This will permanently delete {delete_scope_text}. "
                    f"If you want to proceed, reply with: confirm {cleanup_action.replace('_', ' ')}"
                ),
            }

        result = all_tools[cleanup_action]()
        result.setdefault("action", cleanup_action)
        result.setdefault("_fast_path", "mailbox_cleanup")
        result["preview"] = preview
        return _return_fast_path_result(result)

    attachment_delivery = _try_context_file_attachment_delivery(
        fast_path_query,
        normalized_query,
        all_tools,
    )
    if attachment_delivery is not None:
        return _return_fast_path_result(attachment_delivery)

    relative_day_email_result = _try_relative_day_email_list_or_count(
        fast_path_query,
        normalized_query,
        all_tools,
    )
    if relative_day_email_result is not None:
        return _return_fast_path_result(relative_day_email_result)

    selected_email_summary = _try_selected_email_summary_followup(
        fast_path_query,
        normalized_query,
        all_tools,
    )
    if selected_email_summary is not None:
        return _return_fast_path_result(selected_email_summary)

    listed_email_display = _try_listed_email_display_followup(normalized_query, all_tools)
    if listed_email_display is not None:
        return _return_fast_path_result(listed_email_display)

    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        result = run_skill_dag(
            skill_name="email",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
        # If DAG itself fell back internally that's already handled; just return.
        return result
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("email.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
        log_fallback_to_react("email", "email_orchestrator_exception")
    try:
        return run_skill_react(
            skill_name="email",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            max_iterations=10,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Email skill error: {exc}",
            "action": "react_response",
        }
