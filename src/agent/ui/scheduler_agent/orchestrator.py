"""
Scheduler / Smart Calendar skill orchestrator.

Uses the Google Calendar service to handle scheduling-specific tasks:
finding free slots, booking time blocks, suggesting meeting times, etc.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

from src.agent.workflows.skill_dag_engine import run_skill_dag


def _extract_session_state(user_query: str) -> Dict[str, Any]:
    marker = "## Session State"
    if marker not in user_query:
        return {}
    raw = user_query.split(marker, 1)[1].strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _load_skill_context() -> str:
    """Load the scheduler skill context from skill_context.md."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _build_all_tools(user_query: str = "") -> Dict[str, Any]:
    from src.calendar import calendar_service as cs  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_calendar_context, make_save_context_tool, write_context,
    )
    from datetime import date as _date, timedelta as _td

    session_vars = _extract_session_state(user_query)

    def _remember_event(result: dict) -> dict:
        if not isinstance(result, dict) or result.get("status") != "success":
            return result
        event = result.get("event")
        if not isinstance(event, dict):
            return result
        resolved_date = str(event.get("start", ""))[:10] if event.get("start") else session_vars.get("active_date", "")
        compact = {k: event.get(k) for k in ("id", "title", "start", "end", "location") if event.get(k)}
        try:
            write_context(
                agent="scheduler",
                topic="calendar_event",
                resolved_entities={
                    "resolved_date": resolved_date,
                    "selected_event": compact,
                    "events": [compact],
                },
                awaiting="event_selection",
            )
        except Exception:
            pass
        return result

    def _augment_quick_add_text(text: str) -> str:
        active_date = session_vars.get("active_date", "")
        if not active_date:
            return text
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
            return text
        if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", text, re.IGNORECASE):
            return text
        if re.search(r"\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.IGNORECASE):
            return text
        return f"{text} on {active_date}"

    def get_todays_events() -> dict:
        result = cs.get_todays_events()
        return auto_save_calendar_context(result, _date.today().isoformat(), "today", agent="scheduler")

    def get_tomorrows_events() -> dict:
        result = cs.get_tomorrows_events()
        tomorrow = (_date.today() + _td(days=1)).isoformat()
        return auto_save_calendar_context(result, tomorrow, "tomorrow", agent="scheduler")

    def get_upcoming_events(days: int = 7, max_results: int = 30) -> dict:
        result = cs.get_upcoming_events(days, max_results)
        return auto_save_calendar_context(result, _date.today().isoformat(), f"next {days} days", agent="scheduler")

    def get_events_for_date(date_str: str) -> dict:
        result = cs.get_events_for_date(date_str)
        return auto_save_calendar_context(result, date_str, agent="scheduler")

    return {
        "get_todays_events":    get_todays_events,
        "get_tomorrows_events": get_tomorrows_events,
        "get_upcoming_events":  get_upcoming_events,
        "get_events_for_date":  get_events_for_date,
        "search_events":  lambda query, days=30, max_results=10: cs.search_events(query, days, max_results),
        "create_event":   lambda title, start, end, description="", location="", attendees=None, calendar_id="primary": _remember_event(cs.create_event(title, start, end, description, location, attendees, calendar_id)),
        "quick_add_event": lambda text: _remember_event(cs.quick_add_event(_augment_quick_add_text(text))),
        "update_event":    lambda event_id, **kwargs: _remember_event(cs.update_event(event_id, **kwargs)),
        "delete_event":    lambda event_id: cs.delete_event(event_id),
        "list_calendars":  lambda: cs.list_calendars(),
        "save_context":    make_save_context_tool("scheduler"),
    }


def _get_tool_docs_for_dag() -> str:
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    return get_all_tool_docs("scheduler")


def _get_tool_docs_for_react(user_query: str) -> str:
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    return load_tool_docs(
        "scheduler",
        user_query,
        always_include=["save_context", "create_event", "quick_add_event"],
    )


def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415
        selected = select_tool_names(
            "scheduler",
            user_query,
            always_include=["save_context", "create_event", "quick_add_event"],
        )
        filtered = {name: all_tools[name] for name in selected if name in all_tools}
        if filtered:
            return filtered
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("scheduler.orchestrator").warning(
            "[tool-map] FAISS filtering failed (%s) — using full tool map", exc
        )
    return all_tools


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    all_tools = _build_all_tools(user_query)
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        return run_skill_dag(
            skill_name="scheduler",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("scheduler.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        return run_skill_react(
            skill_name="scheduler",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Scheduler skill error: {exc}",
            "action": "react_response",
        }
