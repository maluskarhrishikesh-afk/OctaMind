"""
OctaMind — Log Analysis Dashboard
==================================
Parses structured PA log files and renders a rich interactive viewer
with per-turn grouping, level filtering, search, LLM call stats, and
an auto-refresh mode for live tailing.

Log format (one line per record):
    [2026-02-26 14:32:11.123] INFO  | corr=x9y8z7 req=a1b2c3 | logger_name | Message

Turn-delimiter lines (box-drawing characters) are detected and used to
group log entries by conversation turn.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_LOGS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "logs"

_LOG_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]\s+"
    r"(?P<level>\w+)\s+\|\s+"
    r"corr=(?P<corr>\S+)\s+req=(?P<req>\S+)\s+\|\s+"
    r"(?P<logger>\S+)\s+\|\s+"
    r"(?P<message>.*)"
)

_TURN_START_RE    = re.compile(r"║\s+TURN START\s+corr=(\S+)\s+src=(\S+)")
_TURN_MSG_RE      = re.compile(r"║\s+MSG:\s+(.*)")
_TURN_END_LLM_RE  = re.compile(r"Turn END.*llm_calls=(\d+)")
_TURN_BOX_LLM_RE  = re.compile(r"║\s+LLM Calls:\s+(\d+)\s+total")
_COUNTER_RE       = re.compile(r"\[counter\]\s+event=(?P<event>[a-z_]+)\s+count=(?P<count>\d+)(?P<rest>.*)")
_COUNTER_FIELD_RE = re.compile(r"\b(?P<key>[a-z_]+)=(?P<value>[^\s]+)")
_TRACE_RE = re.compile(
    r"^\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<logger>[^:]+):\s+"
    r"(?P<message>.*)"
)

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}

_LEVEL_COLORS = {
    "DEBUG":    ("#475569", "#1e293b"),
    "INFO":     ("#93c5fd", "#1e3a5f"),
    "WARNING":  ("#fbbf24", "#3d2e00"),
    "ERROR":    ("#f87171", "#3d0000"),
    "CRITICAL": ("#ff0000", "#4d0000"),
}
_LEVEL_BADGES = {
    "DEBUG":    "background:#334155;color:#94a3b8",
    "INFO":     "background:#1d4ed8;color:#bfdbfe",
    "WARNING":  "background:#b45309;color:#fef3c7",
    "ERROR":    "background:#b91c1c;color:#fee2e2",
    "CRITICAL": "background:#7f1d1d;color:#fca5a5",
}

_IMPORTANT_LOGGERS = {
    "skill-loader", "hub_processor", "skill_dag_engine",
    "skill_react_engine", "llm.call", "llm.response",
}

_TRACE_CATEGORY_ORDER = [
    "Turn",
    "Intent",
    "Session",
    "DAG",
    "Thought",
    "Action",
    "Observation",
    "Tool Selection",
    "Error",
    "Other",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class LogEntry:
    line_no: int
    raw: str
    ts: Optional[str] = None
    level: str = "INFO"
    corr: str = "-"
    req: str = "-"
    logger: str = ""
    message: str = ""
    parsed: bool = False


@dataclass
class Turn:
    corr: str
    source: str = "?"
    message: str = ""
    entries: List[LogEntry] = field(default_factory=list)
    has_error: bool = False
    has_warning: bool = False
    llm_calls: int = 0
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None


@dataclass
class TraceEntry:
    line_no: int
    raw: str
    ts: str = ""
    level: str = "INFO"
    logger: str = ""
    message: str = ""
    category: str = "Other"


@dataclass
class CounterEntry:
    event: str
    count: int
    agent: str = ""
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class CounterTrend:
    corr: str
    source: str
    message: str
    start_ts: str
    llm_calls: int
    by_event: Dict[str, int] = field(default_factory=dict)
    by_agent: Dict[str, Dict[str, int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_line(raw: str, line_no: int) -> LogEntry:
    m = _LOG_RE.match(raw.rstrip())
    if not m:
        return LogEntry(line_no=line_no, raw=raw.rstrip())
    return LogEntry(
        line_no=line_no,
        raw=raw.rstrip(),
        ts=m.group("ts"),
        level=m.group("level").upper(),
        corr=m.group("corr"),
        req=m.group("req"),
        logger=m.group("logger"),
        message=m.group("message"),
        parsed=True,
    )


def load_log_file(path: Path, max_lines: int = 5000) -> List[LogEntry]:
    """Read up to *max_lines* lines from the end of *path*."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return [_parse_line(ln, i + 1) for i, ln in enumerate(lines)]
    except Exception:
        return []


def group_by_turns(entries: List[LogEntry]) -> List[Turn]:
    """Cluster log entries into conversation turns using corr IDs and ╔ delimiters."""
    turns: Dict[str, Turn] = {}
    orphan: Turn = Turn(corr="__orphan__", source="system", message="(pre-turn / system lines)")
    ordered: List[Turn] = [orphan]

    pending_corr: Optional[str] = None
    pending_src: str = "?"
    pending_msg: str = ""
    current_turn: Optional[Turn] = None

    for entry in entries:
        raw = entry.raw

        # Detect turn-start metadata in ║ lines
        m_start = _TURN_START_RE.search(raw)
        if m_start:
            pending_corr = m_start.group(1)
            pending_src  = m_start.group(2)
            pending_msg  = ""
            continue

        m_msg = _TURN_MSG_RE.search(raw)
        if m_msg and pending_corr:
            pending_msg = m_msg.group(1).strip()
            continue

        # Box-drawing lines: skip
        if raw.lstrip().startswith(("╔", "╚", "╠", "═")):
            continue

        # Assign entry to its turn
        corr = entry.corr if entry.parsed else (pending_corr or (current_turn.corr if current_turn else "__orphan__"))

        if corr not in turns:
            if corr == "__orphan__":
                turn = orphan
            else:
                src = pending_src if (pending_corr == corr) else "?"
                msg = pending_msg if (pending_corr == corr) else ""
                turn = Turn(corr=corr, source=src, message=msg)
                turns[corr] = turn
                ordered.append(turn)
                pending_corr = None
        else:
            turn = turns[corr]

        turn.entries.append(entry)
        current_turn = turn
        if entry.level in ("ERROR", "CRITICAL"):
            turn.has_error = True
        if entry.level == "WARNING":
            turn.has_warning = True
        if entry.logger == "llm.call":
            turn.llm_calls += 1
        m_llm = _TURN_END_LLM_RE.search(entry.message)
        if m_llm:
            turn.llm_calls = max(turn.llm_calls, int(m_llm.group(1)))
        m_box_llm = _TURN_BOX_LLM_RE.search(raw)
        if m_box_llm:
            turn.llm_calls = max(turn.llm_calls, int(m_box_llm.group(1)))
        if entry.ts:
            if turn.start_ts is None:
                turn.start_ts = entry.ts
            turn.end_ts = entry.ts

    # Remove empty orphan turn
    if not orphan.entries:
        ordered = [t for t in ordered if t.corr != "__orphan__"]

    return ordered


def _classify_trace_message(message: str, logger_name: str, level: str) -> str:
    lowered = message.lower()
    logger_lower = logger_name.lower()

    if "turn start" in lowered or "turn end" in lowered:
        return "Turn"
    if "[intent]" in lowered or "router [intent]" in lowered or "router [fast-path]" in lowered:
        return "Intent"
    if "[session state]" in lowered:
        return "Session"
    if "raw planning response" in lowered or "plan contains" in lowered:
        return "Thought"
    if "calling tool=" in lowered or ("step=" in lowered and "tool=" in lowered):
        return "Action"
    if "succeeded" in lowered or "returned" in lowered or "skill dag done" in lowered:
        return "Observation"
    if "skill_loader" in logger_lower or "loaded 54 tool skills" in lowered:
        return "Tool Selection"
    if "thought=" in lowered:
        return "Thought"
    if "skill dag start" in lowered or "plan contains" in lowered or "step=" in lowered:
        return "DAG"
    if level in {"ERROR", "CRITICAL"} or "error" in lowered or "failed" in lowered:
        return "Error"
    return "Other"


def _parse_trace_line(raw: str, line_no: int) -> TraceEntry:
    text = raw.rstrip()
    match = _TRACE_RE.match(text)
    if not match:
        return TraceEntry(line_no=line_no, raw=text, message=text)

    level = match.group("level").upper()
    logger_name = match.group("logger").strip()
    message = match.group("message")
    return TraceEntry(
        line_no=line_no,
        raw=text,
        ts=match.group("ts"),
        level=level,
        logger=logger_name,
        message=message,
        category=_classify_trace_message(message, logger_name, level),
    )


def load_trace_file(path: Path, max_lines: int = 3000) -> List[TraceEntry]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return [_parse_trace_line(line, idx + 1) for idx, line in enumerate(lines)]
    except Exception:
        return []


def _parse_counter_entry(entry: LogEntry) -> Optional[CounterEntry]:
    if not entry.parsed:
        return None
    if entry.logger != "agent.telemetry":
        return None
    match = _COUNTER_RE.search(entry.message)
    if not match:
        return None

    fields: Dict[str, str] = {}
    for field_match in _COUNTER_FIELD_RE.finditer(match.group("rest") or ""):
        fields[field_match.group("key")] = field_match.group("value")

    return CounterEntry(
        event=match.group("event"),
        count=int(match.group("count")),
        agent=fields.get("agent", ""),
        fields=fields,
    )


def _collect_counter_summary(entries: List[LogEntry]) -> Dict[str, Any]:
    by_event: Dict[str, int] = {}
    by_agent: Dict[str, Dict[str, int]] = {}

    for entry in entries:
        counter = _parse_counter_entry(entry)
        if counter is None:
            continue
        by_event[counter.event] = by_event.get(counter.event, 0) + counter.count
        if counter.agent:
            agent_bucket = by_agent.setdefault(counter.agent, {})
            agent_bucket[counter.event] = agent_bucket.get(counter.event, 0) + counter.count

    return {
        "by_event": dict(sorted(by_event.items())),
        "by_agent": {agent: dict(sorted(events.items())) for agent, events in sorted(by_agent.items())},
    }


def _render_counter_summary(entries: List[LogEntry]) -> None:
    summary = _collect_counter_summary(entries)
    by_event = summary["by_event"]
    by_agent = summary["by_agent"]
    if not by_event:
        return

    event_html = "".join(
        f'<span class="stat-chip" style="background:rgba(99,102,241,0.14);color:#c7d2fe;">{event}: {count}</span>'
        for event, count in by_event.items()
    )
    st.markdown(
        f'<div style="padding:10px 0 4px 0;">'
        f'<div style="color:#94a3b8;font-size:0.82rem;font-weight:700;margin-bottom:6px;">Telemetry counters</div>'
        f'<div>{event_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if by_agent:
        rows: List[str] = []
        for agent, event_counts in by_agent.items():
            cells = "  ·  ".join(f"{event}: {count}" for event, count in event_counts.items())
            rows.append(
                f'<tr>'
                f'<td style="padding:6px 10px;color:#cbd5e1;font-weight:700;border-bottom:1px solid rgba(255,255,255,0.06);">{agent}</td>'
                f'<td style="padding:6px 10px;color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);">{cells}</td>'
                f'</tr>'
            )
        table_html = (
            '<table style="width:100%;border-collapse:collapse;background:#0f172a;border-radius:8px;overflow:hidden;">'
            '<thead><tr>'
            '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Agent</th>'
            '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Events</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
        )
        with st.expander("Telemetry by agent", expanded=False):
            st.markdown(table_html, unsafe_allow_html=True)


def _collect_counter_trends(turns: List[Turn]) -> List[CounterTrend]:
    trends: List[CounterTrend] = []
    for turn in turns:
        by_event: Dict[str, int] = {}
        by_agent: Dict[str, Dict[str, int]] = {}
        for entry in turn.entries:
            counter = _parse_counter_entry(entry)
            if counter is None:
                continue
            by_event[counter.event] = by_event.get(counter.event, 0) + counter.count
            if counter.agent:
                bucket = by_agent.setdefault(counter.agent, {})
                bucket[counter.event] = bucket.get(counter.event, 0) + counter.count
        if not by_event:
            continue
        trends.append(
            CounterTrend(
                corr=turn.corr,
                source=turn.source,
                message=turn.message,
                start_ts=turn.start_ts or "",
                llm_calls=turn.llm_calls,
                by_event=dict(sorted(by_event.items())),
                by_agent={agent: dict(sorted(events.items())) for agent, events in sorted(by_agent.items())},
            )
        )
    return trends


def _render_counter_trends(turns: List[Turn]) -> None:
    trends = _collect_counter_trends(turns)
    if not trends:
        return

    rows: List[str] = []
    for trend in trends[-12:]:
        events_text = "  ·  ".join(f"{event}: {count}" for event, count in trend.by_event.items())
        agent_text = "  ·  ".join(
            f"{agent} ({', '.join(f'{event}: {count}' for event, count in event_counts.items())})"
            for agent, event_counts in trend.by_agent.items()
        ) or "-"
        rows.append(
            f'<tr>'
            f'<td style="padding:6px 10px;color:#cbd5e1;border-bottom:1px solid rgba(255,255,255,0.06);">{trend.start_ts or "-"}</td>'
            f'<td style="padding:6px 10px;color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);">{trend.source}</td>'
            f'<td style="padding:6px 10px;color:#cbd5e1;border-bottom:1px solid rgba(255,255,255,0.06);">{trend.llm_calls}</td>'
            f'<td style="padding:6px 10px;color:#93c5fd;border-bottom:1px solid rgba(255,255,255,0.06);">{events_text}</td>'
            f'<td style="padding:6px 10px;color:#94a3b8;border-bottom:1px solid rgba(255,255,255,0.06);">{agent_text}</td>'
            f'<td style="padding:6px 10px;color:#64748b;border-bottom:1px solid rgba(255,255,255,0.06);max-width:320px;">{trend.message or "-"}</td>'
            f'</tr>'
        )

    table_html = (
        '<table style="width:100%;border-collapse:collapse;background:#0f172a;border-radius:8px;overflow:hidden;">'
        '<thead><tr>'
        '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Turn</th>'
        '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Source</th>'
        '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">LLM</th>'
        '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Events</th>'
        '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Agents</th>'
        '<th style="text-align:left;padding:8px 10px;color:#64748b;font-size:0.72rem;text-transform:uppercase;">Message</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )
    with st.expander("Telemetry trends by turn", expanded=False):
        st.markdown(table_html, unsafe_allow_html=True)


def _safe_log_filename(pa_name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", pa_name)


def _load_active_log_sources() -> List[Dict[str, str]]:
    try:
        from src.agent.hub.pa_manager import load_assistants
        from src.telegram.pa_poller_manager import get_pa_poller_status
    except Exception:
        return []

    sources: List[Dict[str, str]] = []
    for assistant in load_assistants():
        pa_id = assistant.get("id", "")
        if not pa_id or get_pa_poller_status(pa_id) is None:
            continue
        pa_name = assistant.get("name", pa_id)
        log_path = _LOGS_DIR / f"{_safe_log_filename(pa_name)}.log"
        if not log_path.exists():
            continue
        sources.append(
            {
                "pa_id": pa_id,
                "name": pa_name,
                "log_path": str(log_path),
            }
        )

    return sorted(
        sources,
        key=lambda item: Path(item["log_path"]).stat().st_mtime,
        reverse=True,
    )


def _entry_to_trace_entry(entry: LogEntry) -> TraceEntry:
    if not entry.parsed:
        return TraceEntry(
            line_no=entry.line_no,
            raw=entry.raw,
            message=entry.raw,
            category="Other",
        )

    short_ts = entry.ts[11:23] if entry.ts and len(entry.ts) > 11 else (entry.ts or "")
    return TraceEntry(
        line_no=entry.line_no,
        raw=entry.raw,
        ts=short_ts,
        level=entry.level,
        logger=entry.logger,
        message=entry.message,
        category=_classify_trace_message(entry.message, entry.logger, entry.level),
    )


def _resolve_selected_log_source(sources: List[Dict[str, str]], selected_name: str) -> Dict[str, str]:
    return next(source for source in sources if source["name"] == selected_name)


# ---------------------------------------------------------------------------
# CSS for the log viewer
# ---------------------------------------------------------------------------

def _inject_log_css() -> None:
    st.markdown(
        """
        <style>
        .log-row {
            font-family: 'Menlo','Consolas','DejaVu Sans Mono',monospace;
            font-size: 0.78rem;
            line-height: 1.5;
            padding: 3px 8px;
            border-radius: 4px;
            margin-bottom: 1px;
            word-break: break-all;
        }
        .log-row:hover { filter: brightness(1.15); }
        .log-badge {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            margin-right: 6px;
            vertical-align: middle;
            min-width: 54px;
            text-align: center;
        }
        .log-ts    { color: #4b5563; font-size: 0.72rem; margin-right: 8px; }
        .log-corr  { color: #6366f1; font-size: 0.7rem; margin-right: 6px; }
        .log-logger{ color: #8b5cf6; font-size: 0.7rem; margin-right: 6px; font-weight:600; }
        .log-msg   { color: #e2e8f0; }
        .log-msg-err { color: #fca5a5; }
        .log-msg-warn{ color: #fde68a; }
        .log-msg-debug{ color: #64748b; }
        .turn-header {
            background: linear-gradient(90deg, rgba(99,102,241,0.18) 0%, rgba(139,92,246,0.08) 100%);
            border-left: 3px solid #6366f1;
            padding: 8px 12px;
            border-radius: 0 8px 8px 0;
            margin: 10px 0 4px 0;
            cursor: pointer;
        }
        .turn-header-error {
            border-left-color: #ef4444;
            background: linear-gradient(90deg, rgba(239,68,68,0.15) 0%, rgba(139,92,246,0.05) 100%);
        }
        .turn-header-warn {
            border-left-color: #f59e0b;
            background: linear-gradient(90deg, rgba(245,158,11,0.12) 0%, rgba(139,92,246,0.05) 100%);
        }
        .stat-chip {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 700;
            margin: 2px 4px;
        }
        .search-highlight { background: rgba(251,191,36,0.35); border-radius: 2px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _level_badge(level: str) -> str:
    style = _LEVEL_BADGES.get(level, "background:#334155;color:#94a3b8")
    return f'<span class="log-badge" style="{style}">{level}</span>'


def _msg_class(level: str) -> str:
    return {
        "DEBUG":    "log-msg-debug",
        "WARNING":  "log-msg-warn",
        "ERROR":    "log-msg-err",
        "CRITICAL": "log-msg-err",
    }.get(level, "log-msg")


def _highlight(text: str, query: str) -> str:
    if not query:
        return text
    escaped_query = re.escape(query)
    return re.sub(
        f"({escaped_query})",
        r'<mark class="search-highlight">\1</mark>',
        text,
        flags=re.IGNORECASE,
    )


def _render_entry(entry: LogEntry, search: str = "") -> str:
    if not entry.parsed:
        return (
            f'<div class="log-row" style="color:#374151;">'
            f'<span class="log-ts">L{entry.line_no}</span>'
            f'<span style="color:#4b5563;">{_highlight(entry.raw[:200], search)}</span>'
            f'</div>'
        )

    _, row_bg = _LEVEL_COLORS.get(entry.level, ("#475569", "#1e293b"))
    msg = _highlight(entry.message[:400], search)
    short_logger = entry.logger.split(".")[-1][:28]
    short_ts = entry.ts[11:23] if entry.ts and len(entry.ts) > 11 else (entry.ts or "")

    return (
        f'<div class="log-row" style="background:{row_bg};">'
        f'{_level_badge(entry.level)}'
        f'<span class="log-ts">{short_ts}</span>'
        f'<span class="log-logger">{short_logger}</span>'
        f'<span class="{_msg_class(entry.level)}">{msg}</span>'
        f'</div>'
    )


def _render_turn_header(turn: Turn, idx: int) -> str:
    icon = "❌" if turn.has_error else ("⚠️" if turn.has_warning else "✅")
    cls  = "turn-header-error" if turn.has_error else ("turn-header-warn" if turn.has_warning else "")
    src_badge = (
        f'<span style="background:rgba(34,158,217,0.2);color:#38bdf8;padding:2px 8px;'
        f'border-radius:10px;font-size:0.7rem;font-weight:700;margin-right:6px;">'
        f'{turn.source}</span>'
    )
    llm_badge = (
        f'<span style="background:rgba(99,102,241,0.2);color:#a5b4fc;padding:2px 8px;'
        f'border-radius:10px;font-size:0.7rem;font-weight:600;margin-right:6px;">'
        f'🤖 {turn.llm_calls} LLM</span>'
    ) if turn.llm_calls else ""
    lines_badge = (
        f'<span style="color:#6b7280;font-size:0.7rem;">{len(turn.entries)} lines</span>'
    )
    msg_preview = (turn.message[:90] + "…") if len(turn.message) > 90 else turn.message
    ts_range = ""
    if turn.start_ts and turn.end_ts:
        t0 = turn.start_ts[11:19]
        t1 = turn.end_ts[11:19]
        ts_range = f'<span style="color:#4b5563;font-size:0.7rem;margin-left:8px;">{t0} → {t1}</span>'

    return (
        f'<div class="turn-header {cls}">'
        f'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
        f'<span style="font-size:1rem;">{icon}</span>'
        f'<span style="color:#a5b4fc;font-weight:700;font-size:0.82rem;">Turn {idx}</span>'
        f'{src_badge}{llm_badge}{lines_badge}{ts_range}'
        f'</div>'
        f'<div style="color:#94a3b8;font-size:0.8rem;margin-top:4px;font-style:italic;">"{msg_preview}"</div>'
        f'<div style="color:#4b5563;font-size:0.68rem;margin-top:2px;">corr={turn.corr}</div>'
        f'</div>'
    )


def _trace_badge(category: str) -> str:
    colors = {
        "Turn": ("#1d4ed8", "#bfdbfe"),
        "Intent": ("#0f766e", "#99f6e4"),
        "Session": ("#7c3aed", "#ddd6fe"),
        "Tool Selection": ("#0369a1", "#bae6fd"),
        "DAG": ("#4f46e5", "#c7d2fe"),
        "Thought": ("#9333ea", "#e9d5ff"),
        "Action": ("#b45309", "#fde68a"),
        "Observation": ("#15803d", "#bbf7d0"),
        "Error": ("#b91c1c", "#fecaca"),
        "Other": ("#334155", "#cbd5e1"),
    }
    bg, fg = colors.get(category, colors["Other"])
    return f'<span class="log-badge" style="background:{bg};color:{fg};min-width:92px;">{category}</span>'


def _render_trace_entry(entry: TraceEntry, search: str = "") -> str:
    _, row_bg = _LEVEL_COLORS.get(entry.level, ("#475569", "#111827"))
    message = _highlight((entry.message or entry.raw)[:500], search)
    logger_name = _highlight(entry.logger[:32], search)
    return (
        f'<div class="log-row" style="background:{row_bg};">'
        f'{_trace_badge(entry.category)}'
        f'<span class="log-ts">{entry.ts or f"L{entry.line_no}"}</span>'
        f'<span class="log-logger">{logger_name}</span>'
        f'<span class="{_msg_class(entry.level)}">{message}</span>'
        f'</div>'
    )


def _show_reasoning_trace() -> None:
    trace_sources = _load_active_log_sources()
    if not trace_sources:
        st.info("No active Personal Assistants with live logs were found.")
        return

    trace_cols = st.columns([2.6, 1.6, 1.2, 1.2, 1])
    with trace_cols[0]:
        selected_pa = st.selectbox(
            "Personal Assistant",
            [source["name"] for source in trace_sources],
            label_visibility="collapsed",
            key="lv_trace_pa",
        )
    with trace_cols[1]:
        categories = st.multiselect(
            "Categories",
            _TRACE_CATEGORY_ORDER,
            default=["Turn", "Intent", "Session", "DAG", "Thought", "Action", "Observation", "Error"],
            label_visibility="collapsed",
            key="lv_trace_categories",
        )
    with trace_cols[2]:
        trace_tail = st.select_slider(
            "Trace lines",
            options=[300, 600, 1200, 3000],
            value=1200,
            label_visibility="collapsed",
            key="lv_trace_tail",
        )
    with trace_cols[3]:
        trace_search = st.text_input(
            "Trace search",
            placeholder="🔍 trace search…",
            label_visibility="collapsed",
            key="lv_trace_search",
        )
    with trace_cols[4]:
        interesting_only = st.checkbox("Key only", value=True, key="lv_trace_key_only")

    selected_source = _resolve_selected_log_source(trace_sources, selected_pa)
    trace_path = Path(selected_source["log_path"])
    try:
        trace_mtime = datetime.fromtimestamp(trace_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        trace_mtime = "?"

    st.markdown(
        f'<div style="padding:6px 10px;color:#475569;font-size:0.78rem;">'
        f'🧠 <b style="color:#64748b;">{selected_source["name"]}</b>'
        f'  &nbsp;·&nbsp;  <span style="color:#64748b;">{trace_path.name}</span>'
        f'  &nbsp;·&nbsp;  last modified <b style="color:#94a3b8;">{trace_mtime}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

    all_trace_entries = [_entry_to_trace_entry(entry) for entry in load_log_file(trace_path, max_lines=trace_tail)]
    if interesting_only:
        all_trace_entries = [entry for entry in all_trace_entries if entry.category != "Other"]

    selected_categories = set(categories) if categories else set(_TRACE_CATEGORY_ORDER)
    filtered_trace: List[TraceEntry] = []
    for entry in all_trace_entries:
        haystack = f"{entry.logger} {entry.message} {entry.raw}".lower()
        if entry.category not in selected_categories:
            continue
        if trace_search and trace_search.lower() not in haystack:
            continue
        filtered_trace.append(entry)

    if not filtered_trace:
        st.info("No reasoning-trace lines match the current filters.")
        return

    counts = {category: 0 for category in _TRACE_CATEGORY_ORDER}
    for entry in filtered_trace:
        counts[entry.category] = counts.get(entry.category, 0) + 1

    summary = "  ".join(
        f'<span class="stat-chip" style="background:rgba(255,255,255,0.05);color:#cbd5e1;">{category}: {counts[category]}</span>'
        for category in _TRACE_CATEGORY_ORDER
        if counts.get(category)
    )
    st.markdown(
        f'<div style="color:#475569;font-size:0.82rem;margin:4px 0 12px 0;">'
        f'Showing <b style="color:#a5b4fc;">{len(filtered_trace)}</b> reasoning lines</div>{summary}',
        unsafe_allow_html=True,
    )

    trace_rows = "".join(_render_trace_entry(entry, trace_search) for entry in filtered_trace[-500:])
    st.markdown(
        f'<div style="background:#0f172a;border-radius:8px;padding:10px;max-height:700px;overflow-y:auto;">{trace_rows}</div>',
        unsafe_allow_html=True,
    )
    if len(filtered_trace) > 500:
        st.caption(f"⚡ Showing last 500 of {len(filtered_trace)} matching reasoning lines.")


# ---------------------------------------------------------------------------
# Main viewer
# ---------------------------------------------------------------------------

def _stats_bar(entries: List[LogEntry], turns: List[Turn]) -> None:
    counts: Dict[str, int] = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
    for e in entries:
        if e.parsed:
            counts[e.level] = counts.get(e.level, 0) + 1
    llm_calls = max(
        sum(t.llm_calls for t in turns),
        len([entry for entry in entries if entry.parsed and entry.logger == "llm.call"]),
    )

    error_turns = sum(1 for t in turns if t.has_error)
    cols = st.columns(7)
    _metrics = [
        ("Total Lines", len(entries), "#94a3b8"),
        ("Turns", len(turns), "#a5b4fc"),
        ("LLM Calls", llm_calls, "#818cf8"),
        ("Debug", counts["DEBUG"], "#475569"),
        ("Warnings", counts["WARNING"], "#f59e0b"),
        ("Errors", counts["ERROR"] + counts["CRITICAL"], "#ef4444"),
        ("Error Turns", error_turns, "#b91c1c"),
    ]
    for col, (label, val, color) in zip(cols, _metrics):
        with col:
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
                f'border-radius:10px;padding:10px 8px;text-align:center;">'
                f'<div style="font-size:1.5rem;font-weight:800;color:{color};line-height:1;">{val}</div>'
                f'<div style="font-size:0.65rem;color:#475569;font-weight:600;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin-top:3px;">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def show_log_viewer() -> None:
    """Main entry point — renders the full log analysis screen."""
    _inject_log_css()

    st.markdown(
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">'
        '<span style="font-size:2rem;">📊</span>'
        '<div><div style="font-size:1.6rem;font-weight:800;background:linear-gradient(135deg,#a5b4fc,#e91e8c);'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">Log Analyser</div>'
        '<div style="color:#475569;font-size:0.85rem;">Live PA log viewer — turns, LLM calls, errors at a glance</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    _LOGS_DIR.mkdir(exist_ok=True)
    log_files = sorted(_LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

    refresh_cols = st.columns([1, 6, 1])
    with refresh_cols[0]:
        if st.button("🔄 Refresh", type="primary", use_container_width=True):
            st.rerun()
    with refresh_cols[1]:
        refresh_interval = st.selectbox(
            "Interval",
            [3, 5, 10, 30],
            index=1,
            label_visibility="collapsed",
            key="lv_interval",
        )
    with refresh_cols[2]:
        auto_refresh = st.checkbox("⟳ Auto", value=False, key="lv_auto")

    structured_tab, trace_tab = st.tabs(["Structured Logs", "Reasoning Trace"])

    with structured_tab:
        structured_sources = _load_active_log_sources()
        if not structured_sources:
            st.info("No active Personal Assistants with live logs were found.")
        else:
            pa_names = [source["name"] for source in structured_sources]
            ctrl_cols = st.columns([2.5, 1.2, 1.2, 1.2, 1, 1])

            with ctrl_cols[0]:
                selected_pa = st.selectbox(
                    "Personal Assistant",
                    pa_names,
                    label_visibility="collapsed",
                    key="lv_file",
                )

            with ctrl_cols[1]:
                level_filter = st.multiselect(
                    "Levels",
                    ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    default=["INFO", "WARNING", "ERROR", "CRITICAL"],
                    label_visibility="collapsed",
                    key="lv_levels",
                )

            with ctrl_cols[2]:
                tail_lines = st.select_slider(
                    "Lines",
                    options=[500, 1000, 2000, 5000],
                    value=2000,
                    label_visibility="collapsed",
                    key="lv_tail",
                )

            with ctrl_cols[3]:
                search = st.text_input(
                    "Search",
                    placeholder="🔍 search…",
                    label_visibility="collapsed",
                    key="lv_search",
                )

            with ctrl_cols[4]:
                view_mode = st.selectbox(
                    "View",
                    ["Turns", "Flat"],
                    label_visibility="collapsed",
                    key="lv_mode",
                )

            with ctrl_cols[5]:
                st.markdown("<div style='padding-top:8px;color:#64748b;font-size:0.78rem;'>structured</div>", unsafe_allow_html=True)

            selected_source = _resolve_selected_log_source(structured_sources, selected_pa)
            log_path = Path(selected_source["log_path"])
            try:
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                mtime = "?"

            st.markdown(
                f'<div style="padding:6px 10px;color:#475569;font-size:0.78rem;">'
                f'📄 <b style="color:#64748b;">{selected_source["name"]}</b>'
                f'  &nbsp;·&nbsp;  <span style="color:#64748b;">{log_path.name}</span>'
                f'  &nbsp;·&nbsp;  last modified <b style="color:#94a3b8;">{mtime}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )

            all_entries: List[LogEntry] = load_log_file(log_path, max_lines=tail_lines)
            level_set = set(level_filter) if level_filter else set(_LEVEL_ORDER.keys())
            filtered: List[LogEntry] = []
            for entry in all_entries:
                if entry.parsed:
                    if entry.level not in level_set:
                        continue
                    if search and search.lower() not in entry.message.lower() and search.lower() not in entry.logger.lower():
                        continue
                else:
                    if search and search.lower() not in entry.raw.lower():
                        continue
                filtered.append(entry)

            turns = group_by_turns(all_entries)
            _stats_bar(all_entries, turns)
            _render_counter_summary(all_entries)
            _render_counter_trends(turns)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            llm_entries = [entry for entry in all_entries if entry.parsed and entry.logger in ("llm.call", "llm.response")]
            if llm_entries:
                llm_call_count = len([entry for entry in llm_entries if entry.logger == "llm.call"])
                with st.expander(f"🤖 LLM Calls — {llm_call_count} calls", expanded=False):
                    html_rows = "".join(_render_entry(entry, search) for entry in llm_entries[-50:])
                    st.markdown(
                        f'<div style="background:#0f172a;border-radius:8px;padding:8px;max-height:300px;overflow-y:auto;">{html_rows}</div>',
                        unsafe_allow_html=True,
                    )

            error_entries = [entry for entry in all_entries if entry.parsed and entry.level in ("ERROR", "CRITICAL")]
            if error_entries:
                with st.expander(f"❌ Errors & Critical — {len(error_entries)} entries", expanded=True):
                    html_rows = "".join(_render_entry(entry, search) for entry in error_entries[-100:])
                    st.markdown(
                        f'<div style="background:#0f172a;border-radius:8px;padding:8px;max-height:300px;overflow-y:auto;">{html_rows}</div>',
                        unsafe_allow_html=True,
                    )

            st.divider()

            if view_mode == "Turns":
                visible_turns = []
                for turn in turns:
                    matching_entries = [
                        entry for entry in turn.entries
                        if (not entry.parsed or entry.level in level_set)
                        and (not search or search.lower() in entry.raw.lower())
                    ]
                    if matching_entries:
                        visible_turns.append((turn, matching_entries))

                if not visible_turns:
                    st.info("No entries match the current filters.")
                else:
                    st.markdown(
                        f'<div style="color:#475569;font-size:0.82rem;margin-bottom:12px;">'
                        f'Showing <b style="color:#a5b4fc;">{len(visible_turns)}</b> turn(s) — '
                        f'<b style="color:#94a3b8;">{len(filtered)}</b> matching log lines</div>',
                        unsafe_allow_html=True,
                    )

                    for idx, (turn, matching_entries) in enumerate(reversed(visible_turns), 1):
                        real_idx = len(visible_turns) - idx + 1
                        header_html = _render_turn_header(turn, real_idx)
                        st.markdown(header_html, unsafe_allow_html=True)
                        with st.expander(
                            f"{'🔴' if turn.has_error else '🟡' if turn.has_warning else '🟢'} {len(matching_entries)} lines  |  corr={turn.corr[:8]}",
                            expanded=idx <= 3,
                        ):
                            chunk = matching_entries[-200:]
                            html_rows = "".join(_render_entry(entry, search) for entry in chunk)
                            st.markdown(
                                f'<div style="background:#0f172a;border-radius:8px;padding:8px;max-height:500px;overflow-y:auto;">{html_rows}</div>',
                                unsafe_allow_html=True,
                            )
                            if len(matching_entries) > 200:
                                st.caption(f"⚡ Showing last 200 of {len(matching_entries)} lines in this turn.")
            else:
                st.markdown(
                    f'<div style="color:#475569;font-size:0.82rem;margin-bottom:12px;">'
                    f'Showing <b style="color:#a5b4fc;">{len(filtered)}</b> of '
                    f'<b style="color:#94a3b8;">{len(all_entries)}</b> lines</div>',
                    unsafe_allow_html=True,
                )
                chunk = filtered[-1000:]
                html_rows = "".join(_render_entry(entry, search) for entry in chunk)
                st.markdown(
                    f'<div style="background:#0f172a;border-radius:8px;padding:10px;max-height:700px;overflow-y:auto;">{html_rows}</div>',
                    unsafe_allow_html=True,
                )
                if len(filtered) > 1000:
                    st.caption(f"⚡ Showing last 1,000 of {len(filtered)} matching lines. Use the Lines slider to load more.")

    with trace_tab:
        _show_reasoning_trace()

    # ── Auto-refresh (must be last — otherwise Streamlit re-runs interrupt UI) ──
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()
