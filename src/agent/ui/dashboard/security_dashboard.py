"""
OctaMind Security Dashboard
===========================
Operational dashboard for the shared security control plane.

Surfaces:
- inbound security audit events
- active per-session rate-limit state
- pending destructive confirmations
- live runtime tool risk manifests
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from src.agent.runtime_paths import get_runtime_state_path

_SECURITY_EVENTS_PATH = get_runtime_state_path(
    "runtime_state",
    "security_events.jsonl",
    create_parent=True,
)
_RATE_LIMIT_STATE_PATH = get_runtime_state_path(
    "runtime_state",
    "security_rate_limits.json",
    create_parent=True,
)
_PENDING_CONFIRMATIONS_PATH = get_runtime_state_path(
    "runtime_state",
    "destructive_action_pending.json",
    create_parent=True,
)


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}


def load_security_events(limit: int = 500) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    try:
        if not _SECURITY_EVENTS_PATH.exists():
            return []
        lines = _SECURITY_EVENTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    parsed: List[Dict[str, Any]] = []
    for raw in lines[-limit:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(entry, dict):
            parsed.append(entry)
    parsed.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return parsed


def load_rate_limit_state() -> Dict[str, Dict[str, List[float]]]:
    payload = _read_json_file(_RATE_LIMIT_STATE_PATH)
    return payload if isinstance(payload, dict) else {}


def load_pending_confirmations() -> Dict[str, Dict[str, Any]]:
    payload = _read_json_file(_PENDING_CONFIRMATIONS_PATH)
    return payload if isinstance(payload, dict) else {}


def summarize_security_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    event_counter = Counter(str(item.get("event_type", "unknown") or "unknown") for item in events)
    decision_counter = Counter(str(item.get("decision", "unknown") or "unknown") for item in events)
    source_counter = Counter(str(item.get("source", "unknown") or "unknown") for item in events)

    latest_ts = ""
    if events:
        latest_ts = str(events[0].get("timestamp", "") or "")

    blocked_count = sum(1 for item in events if str(item.get("decision", "")).lower() == "blocked")
    rate_limit_count = event_counter.get("rate_limit_exceeded", 0)
    suspicious_count = event_counter.get("prompt_injection_suspected", 0)

    return {
        "total_events": len(events),
        "blocked_events": blocked_count,
        "rate_limit_events": rate_limit_count,
        "suspicious_events": suspicious_count,
        "latest_timestamp": latest_ts,
        "events_by_type": dict(event_counter),
        "events_by_decision": dict(decision_counter),
        "events_by_source": dict(source_counter),
    }


def build_rate_limit_rows(state: Dict[str, Dict[str, List[float]]], now_ts: float | None = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    current_ts = float(now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp())
    for scope_key, payload in (state or {}).items():
        source, _, session_id = str(scope_key).partition("::")
        minute_hits = [float(item) for item in payload.get("minute", []) if current_ts - float(item) <= 60]
        hour_hits = [float(item) for item in payload.get("hour", []) if current_ts - float(item) <= 3600]
        rows.append(
            {
                "source": source or "unknown",
                "session_id": session_id or scope_key,
                "minute_count": len(minute_hits),
                "hour_count": len(hour_hits),
                "last_seen": datetime.fromtimestamp(max(hour_hits or minute_hits or [0]), timezone.utc).isoformat()
                if (hour_hits or minute_hits)
                else "",
            }
        )
    rows.sort(key=lambda item: (int(item["hour_count"]), int(item["minute_count"]), item["session_id"]), reverse=True)
    return rows


def build_confirmation_rows(pending: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for session_id, payload in (pending or {}).items():
        rows.append(
            {
                "session_id": session_id,
                "skill": str(payload.get("skill_name", "") or ""),
                "tool": str(payload.get("tool_name", "") or ""),
                "action_key": str(payload.get("action_key", "") or ""),
                "message": str(payload.get("message", "") or ""),
                "original_message": str(payload.get("original_message", "") or ""),
                "source": str(payload.get("source", "") or ""),
            }
        )
    rows.sort(key=lambda item: (item["source"], item["session_id"]), reverse=True)
    return rows


def build_tool_risk_rows() -> List[Dict[str, Any]]:
    try:
        from src.agent.workflows.agent_registry import registered_agents
        from src.agent.security.tool_manifest import build_runtime_tool_security_manifest
    except ImportError:
        return []

    rows: List[Dict[str, Any]] = []
    for agent_name in registered_agents():
        manifest = build_runtime_tool_security_manifest(agent_name)
        for tool_name, meta in manifest.items():
            rows.append(
                {
                    "agent": agent_name,
                    "tool": tool_name,
                    "risk_level": str(meta.get("risk_level", "low")),
                    "approval_required": bool(meta.get("approval_required")),
                    "policy_tags": ", ".join(meta.get("policy_tags", [])),
                    "default_rate_limit": json.dumps(meta.get("default_rate_limit", {}), ensure_ascii=False),
                }
            )

    risk_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    rows.sort(key=lambda item: (risk_rank.get(item["risk_level"], -1), item["agent"], item["tool"]), reverse=True)
    return rows


def _render_metric_card(title: str, value: str, detail: str, accent: str) -> None:
    st.markdown(
        f"""
        <div style="background:rgba(15,23,42,0.82);border:1px solid {accent};border-radius:16px;padding:16px 18px;
                    box-shadow:0 14px 34px rgba(15,23,42,0.18);min-height:118px;">
            <div style="font-size:0.76rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;">{title}</div>
            <div style="font-size:2rem;font-weight:900;color:#f8fafc;line-height:1.15;margin-top:10px;">{value}</div>
            <div style="font-size:0.84rem;color:#64748b;margin-top:8px;">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_overview(events: List[Dict[str, Any]], rate_limit_rows: List[Dict[str, Any]], confirmation_rows: List[Dict[str, Any]], tool_rows: List[Dict[str, Any]]) -> None:
    summary = summarize_security_events(events)
    critical_tools = sum(1 for item in tool_rows if item.get("risk_level") == "critical")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _render_metric_card("Security Events", str(summary["total_events"]), "Total audit entries currently loaded", "rgba(59,130,246,0.28)")
    with col2:
        _render_metric_card("Blocked Requests", str(summary["blocked_events"]), "High-confidence inbound attacks stopped", "rgba(239,68,68,0.32)")
    with col3:
        _render_metric_card("Rate-Limited Sessions", str(len([row for row in rate_limit_rows if row.get('minute_count') or row.get('hour_count')])), "Active throttling state across channels", "rgba(245,158,11,0.30)")
    with col4:
        _render_metric_card("Critical Tools", str(critical_tools), "Live tools classified as critical risk", "rgba(168,85,247,0.28)")

    overview_left, overview_right = st.columns([1.15, 0.85])
    with overview_left:
        st.markdown("### Event Breakdown")
        if summary["events_by_type"]:
            breakdown_rows = [
                {"event_type": key, "count": count}
                for key, count in sorted(summary["events_by_type"].items(), key=lambda item: (-item[1], item[0]))
            ]
            st.dataframe(breakdown_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No security events recorded yet.")

    with overview_right:
        st.markdown("### Live State")
        state_rows = [
            {"signal": "Pending destructive confirmations", "count": len(confirmation_rows)},
            {"signal": "Suspicious-but-allowed events", "count": int(summary["suspicious_events"])},
            {"signal": "Rate-limit violations", "count": int(summary["rate_limit_events"])},
            {"signal": "Latest audit timestamp", "count": summary["latest_timestamp"] or "n/a"},
        ]
        st.dataframe(state_rows, use_container_width=True, hide_index=True)


def show_security_dashboard() -> None:
    st.markdown(
        "<div style='font-size:1.5rem;font-weight:800;color:#e2e8f0;margin:8px 0 6px 0;'>🛡️ Security Dashboard</div>"
        "<div style='color:#64748b;font-size:0.88rem;margin-bottom:16px;'>Shared visibility over inbound security events, throttling state, destructive confirmations, and live tool-risk posture.</div>",
        unsafe_allow_html=True,
    )

    refresh_col, details_col = st.columns([0.22, 0.78])
    with refresh_col:
        auto_refresh = st.checkbox("Auto refresh", value=False, key="security_dashboard_auto_refresh")
    with details_col:
        st.caption(
            f"Audit file: {_SECURITY_EVENTS_PATH.name} · Rate limits: {_RATE_LIMIT_STATE_PATH.name} · Pending approvals: {_PENDING_CONFIRMATIONS_PATH.name}"
        )

    events = load_security_events(limit=500)
    rate_limit_rows = build_rate_limit_rows(load_rate_limit_state())
    confirmation_rows = build_confirmation_rows(load_pending_confirmations())
    tool_rows = build_tool_risk_rows()

    overview_tab, events_tab, limits_tab, tools_tab = st.tabs(["Overview", "Audit Events", "Rate Limits", "Tool Risk"])

    with overview_tab:
        _render_overview(events, rate_limit_rows, confirmation_rows, tool_rows)
        st.markdown("### Pending Confirmations")
        if confirmation_rows:
            st.dataframe(confirmation_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No destructive actions are currently waiting for confirmation.")

    with events_tab:
        st.markdown("### Recent Security Audit Events")
        if events:
            st.dataframe(events, use_container_width=True, hide_index=True)
        else:
            st.info("No security audit events recorded yet.")

    with limits_tab:
        st.markdown("### Active Rate-Limit State")
        if rate_limit_rows:
            st.dataframe(rate_limit_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No active rate-limit state found.")

    with tools_tab:
        st.markdown("### Runtime Tool Risk Manifest")
        if tool_rows:
            st.dataframe(tool_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No runtime tool manifests could be built.")

    if auto_refresh:
        time_left = st.empty()
        time_left.caption("Refreshing in 5 seconds…")
        time.sleep(5)
        st.rerun()