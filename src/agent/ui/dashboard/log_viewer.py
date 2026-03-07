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
from typing import Dict, List, Optional

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

_TURN_START_RE = re.compile(r"║\s+TURN START\s+corr=(\S+)\s+src=(\S+)")
_TURN_MSG_RE   = re.compile(r"║\s+MSG:\s+(.*)")

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
        corr = entry.corr if entry.parsed else (pending_corr or "__orphan__")

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
        if entry.level in ("ERROR", "CRITICAL"):
            turn.has_error = True
        if entry.level == "WARNING":
            turn.has_warning = True
        if entry.logger == "llm.call":
            turn.llm_calls += 1
        if entry.ts:
            if turn.start_ts is None:
                turn.start_ts = entry.ts
            turn.end_ts = entry.ts

    # Remove empty orphan turn
    if not orphan.entries:
        ordered = [t for t in ordered if t.corr != "__orphan__"]

    return ordered


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


# ---------------------------------------------------------------------------
# Main viewer
# ---------------------------------------------------------------------------

def _stats_bar(entries: List[LogEntry], turns: List[Turn]) -> None:
    counts: Dict[str, int] = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
    llm_calls = 0
    for e in entries:
        if e.parsed:
            counts[e.level] = counts.get(e.level, 0) + 1
            if e.logger == "llm.call":
                llm_calls += 1

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

    # ── Header + Home button ─────────────────────────────────────────────
    hdr_col, home_col = st.columns([5, 1])
    with hdr_col:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">'
            '<span style="font-size:2rem;">📊</span>'
            '<div><div style="font-size:1.6rem;font-weight:800;background:linear-gradient(135deg,#a5b4fc,#e91e8c);'
            '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">Log Analyser</div>'
            '<div style="color:#475569;font-size:0.85rem;">Live PA log viewer — turns, LLM calls, errors at a glance</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
    with home_col:
        st.markdown("<div style='padding-top:6px;'></div>", unsafe_allow_html=True)
        if st.button("🏠 Home", use_container_width=True, type="secondary", key="lv_home"):
            st.session_state.show_log_viewer = False
            st.rerun()

    # ── Discover log files ────────────────────────────────────────────────
    _LOGS_DIR.mkdir(exist_ok=True)
    log_files = sorted(_LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not log_files:
        st.info("No log files found in the `logs/` directory. Start a Personal Assistant to generate logs.")
        return

    file_names = [p.name for p in log_files]

    # ── Control row ───────────────────────────────────────────────────────
    ctrl_cols = st.columns([2.5, 1.2, 1.2, 1.2, 1, 1])

    with ctrl_cols[0]:
        selected_file = st.selectbox(
            "Log file",
            file_names,
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
        auto_refresh = st.checkbox("⟳ Auto", value=False, key="lv_auto")

    # ── Manual refresh button ─────────────────────────────────────────────
    r_col1, r_col2, r_col3 = st.columns([1, 6, 1])
    with r_col1:
        if st.button("🔄 Refresh", type="primary", use_container_width=True):
            st.rerun()

    # ── Load file ─────────────────────────────────────────────────────────
    log_path = _LOGS_DIR / selected_file
    try:
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        mtime = "?"

    with r_col2:
        st.markdown(
            f'<div style="padding:6px 10px;color:#475569;font-size:0.78rem;">'
            f'📄 <b style="color:#64748b;">{selected_file}</b>'
            f'  &nbsp;·&nbsp;  last modified <b style="color:#94a3b8;">{mtime}</b>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with r_col3:
        refresh_interval = st.selectbox(
            "Interval",
            [3, 5, 10, 30],
            index=1,
            label_visibility="collapsed",
            key="lv_interval",
            disabled=not auto_refresh,
        )

    all_entries: List[LogEntry] = load_log_file(log_path, max_lines=tail_lines)

    # ── Apply filters ─────────────────────────────────────────────────────
    level_set = set(level_filter) if level_filter else set(_LEVEL_ORDER.keys())
    filtered: List[LogEntry] = []
    for e in all_entries:
        if e.parsed:
            if e.level not in level_set:
                continue
            if search and search.lower() not in e.message.lower() and search.lower() not in e.logger.lower():
                continue
        else:
            if search and search.lower() not in e.raw.lower():
                continue
        filtered.append(e)

    # ── Stats bar ─────────────────────────────────────────────────────────
    turns = group_by_turns(all_entries)
    _stats_bar(all_entries, turns)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── LLM call summary (collapsible) ────────────────────────────────────
    llm_entries = [e for e in all_entries if e.parsed and e.logger in ("llm.call", "llm.response")]
    if llm_entries:
        with st.expander(f"🤖 LLM Calls — {len([e for e in llm_entries if e.logger == 'llm.call'])} calls", expanded=False):
            html_rows = "".join(_render_entry(e, search) for e in llm_entries[-50:])
            st.markdown(
                f'<div style="background:#0f172a;border-radius:8px;padding:8px;'
                f'max-height:300px;overflow-y:auto;">{html_rows}</div>',
                unsafe_allow_html=True,
            )

    # ── Error summary (collapsible) ───────────────────────────────────────
    error_entries = [e for e in all_entries if e.parsed and e.level in ("ERROR", "CRITICAL")]
    if error_entries:
        with st.expander(f"❌ Errors & Critical — {len(error_entries)} entries", expanded=len(error_entries) > 0):
            html_rows = "".join(_render_entry(e, search) for e in error_entries[-100:])
            st.markdown(
                f'<div style="background:#0f172a;border-radius:8px;padding:8px;'
                f'max-height:300px;overflow-y:auto;">{html_rows}</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Main log view ─────────────────────────────────────────────────────
    if view_mode == "Turns":
        # --- Turn-by-Turn view ---
        # Filter turns to only those matching the level/search criteria
        visible_turns: List[Turn] = []
        for turn in turns:
            matching = [
                e for e in turn.entries
                if (not e.parsed or e.level in level_set)
                and (not search or search.lower() in e.raw.lower())
            ]
            if matching:
                visible_turns.append((turn, matching))

        if not visible_turns:
            st.info("No entries match the current filters.")
            return

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

            # Expand the last 3 turns by default; collapse older ones
            expand_default = idx <= 3
            with st.expander(
                f"{'🔴' if turn.has_error else '🟡' if turn.has_warning else '🟢'} "
                f"{len(matching_entries)} lines  |  corr={turn.corr[:8]}",
                expanded=expand_default,
            ):
                chunk = matching_entries[-200:]  # cap per-turn rendering
                html_rows = "".join(_render_entry(e, search) for e in chunk)
                st.markdown(
                    f'<div style="background:#0f172a;border-radius:8px;padding:8px;'
                    f'max-height:500px;overflow-y:auto;">{html_rows}</div>',
                    unsafe_allow_html=True,
                )
                if len(matching_entries) > 200:
                    st.caption(f"⚡ Showing last 200 of {len(matching_entries)} lines in this turn.")

    else:
        # --- Flat view ---
        st.markdown(
            f'<div style="color:#475569;font-size:0.82rem;margin-bottom:12px;">'
            f'Showing <b style="color:#a5b4fc;">{len(filtered)}</b> of '
            f'<b style="color:#94a3b8;">{len(all_entries)}</b> lines</div>',
            unsafe_allow_html=True,
        )

        chunk = filtered[-1000:]
        html_rows = "".join(_render_entry(e, search) for e in chunk)
        st.markdown(
            f'<div style="background:#0f172a;border-radius:8px;padding:10px;'
            f'max-height:700px;overflow-y:auto;">{html_rows}</div>',
            unsafe_allow_html=True,
        )
        if len(filtered) > 1000:
            st.caption(f"⚡ Showing last 1,000 of {len(filtered)} matching lines. Use the Lines slider to load more.")

    # ── Auto-refresh (must be last — otherwise Streamlit re-runs interrupt UI) ──
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()
