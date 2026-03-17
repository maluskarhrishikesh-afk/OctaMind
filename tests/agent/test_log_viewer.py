import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.ui.dashboard import log_viewer
from src.agent.ui.dashboard.log_viewer import LogEntry, group_by_turns


def test_group_by_turns_counts_llm_call_entries_without_turn_end_summary() -> None:
    entries = [
        LogEntry(
            line_no=1,
            raw="start",
            ts="2026-03-16 22:58:39.439",
            level="INFO",
            corr="corr-1",
            req="-",
            logger="hub_processor",
            message="TURN START",
            parsed=True,
        ),
        LogEntry(
            line_no=2,
            raw="llm",
            ts="2026-03-16 22:58:40.000",
            level="INFO",
            corr="corr-1",
            req="-",
            logger="llm.call",
            message="provider=github-models",
            parsed=True,
        ),
        LogEntry(
            line_no=3,
            raw="done",
            ts="2026-03-16 22:58:41.000",
            level="INFO",
            corr="corr-1",
            req="-",
            logger="workflows",
            message="Skill DAG DONE",
            parsed=True,
        ),
    ]

    turns = group_by_turns(entries)

    assert len(turns) == 1
    assert turns[0].llm_calls == 1


def test_group_by_turns_prefers_explicit_turn_end_count_when_present() -> None:
    entries = [
        LogEntry(
            line_no=1,
            raw="start",
            ts="2026-03-16 22:58:39.439",
            level="INFO",
            corr="corr-2",
            req="-",
            logger="llm.call",
            message="provider=github-models",
            parsed=True,
        ),
        LogEntry(
            line_no=2,
            raw="end",
            ts="2026-03-16 22:58:41.000",
            level="INFO",
            corr="corr-2",
            req="-",
            logger="hub_processor",
            message="Turn END corr=corr-2 llm_calls=2",
            parsed=True,
        ),
    ]

    turns = group_by_turns(entries)

    assert len(turns) == 1
    assert turns[0].llm_calls == 2


def test_load_active_log_sources_returns_only_running_assistants(tmp_path, monkeypatch):
    active_log = tmp_path / "octa-001.log"
    active_log.write_text("[2026-03-15 12:40:48.908] INFO  | corr=x req=y | telegram_agent | test\n", encoding="utf-8")

    monkeypatch.setattr(log_viewer, "_LOGS_DIR", tmp_path)

    pa_manager = types.ModuleType("src.agent.hub.pa_manager")
    pa_manager.load_assistants = lambda: [
        {"id": "pa_active", "name": "octa-001"},
        {"id": "pa_inactive", "name": "octa-002"},
    ]
    poller_manager = types.ModuleType("src.telegram.pa_poller_manager")
    poller_manager.get_pa_poller_status = lambda pa_id: {"running": True} if pa_id == "pa_active" else None

    monkeypatch.setitem(sys.modules, "src.agent.hub.pa_manager", pa_manager)
    monkeypatch.setitem(sys.modules, "src.telegram.pa_poller_manager", poller_manager)

    sources = log_viewer._load_active_log_sources()

    assert sources == [
        {
            "pa_id": "pa_active",
            "name": "octa-001",
            "log_path": str(active_log),
        }
    ]


def test_entry_to_trace_entry_uses_structured_log_message_category():
    entry = log_viewer.LogEntry(
        line_no=1,
        raw="raw",
        ts="2026-03-15 12:45:24.729",
        level="INFO",
        corr="abc",
        req="-",
        logger="hub_processor",
        message="│  [INTENT] category=fresh_task agents=['email']",
        parsed=True,
    )

    trace_entry = log_viewer._entry_to_trace_entry(entry)

    assert trace_entry.ts == "12:45:24.729"
    assert trace_entry.category == "Intent"
    assert trace_entry.logger == "hub_processor"


def test_entry_to_trace_entry_classifies_raw_planning_as_thought():
    entry = log_viewer.LogEntry(
        line_no=1,
        raw="raw",
        ts="2026-03-15 13:04:10.978",
        level="DEBUG",
        corr="abc",
        req="-",
        logger="workflows.skill_dag",
        message="│  [email] raw planning response: [{\"id\":\"s1\",\"tool\":\"create_smart_label_rule\"}]",
        parsed=True,
    )

    trace_entry = log_viewer._entry_to_trace_entry(entry)

    assert trace_entry.category == "Thought"