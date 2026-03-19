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


def test_group_by_turns_reads_multiline_workflow_summary_llm_count() -> None:
    entries = [
        LogEntry(
            line_no=1,
            raw="start",
            ts="2026-03-18 11:29:36.404",
            level="INFO",
            corr="corr-3",
            req="-",
            logger="hub_processor",
            message="TURN START",
            parsed=True,
        ),
        LogEntry(
            line_no=2,
            raw="summary-start",
            ts="2026-03-18 11:29:49.721",
            level="INFO",
            corr="corr-3",
            req="-",
            logger="hub_processor",
            message="╔════════════════════════════════════════════╗",
            parsed=True,
        ),
        LogEntry(
            line_no=3,
            raw="║  LLM Calls: 2 total                         ║",
            parsed=False,
        ),
    ]

    turns = group_by_turns(entries)

    assert len(turns) == 1
    assert turns[0].llm_calls == 2


def test_parse_counter_entry_extracts_event_and_agent() -> None:
    entry = LogEntry(
        line_no=1,
        raw="counter",
        ts="2026-03-18 12:00:00.000",
        level="INFO",
        corr="abc",
        req="-",
        logger="agent.telemetry",
        message="[counter] event=fast_path_hit count=1 agent=email fast_path=relative_day_email_list",
        parsed=True,
    )

    parsed = log_viewer._parse_counter_entry(entry)

    assert parsed is not None
    assert parsed.event == "fast_path_hit"
    assert parsed.agent == "email"
    assert parsed.fields["fast_path"] == "relative_day_email_list"


def test_collect_counter_summary_groups_by_event_and_agent() -> None:
    entries = [
        LogEntry(
            line_no=1,
            raw="counter-1",
            ts="2026-03-18 12:00:00.000",
            level="INFO",
            corr="abc",
            req="-",
            logger="agent.telemetry",
            message="[counter] event=fast_path_hit count=1 agent=email fast_path=relative_day_email_list",
            parsed=True,
        ),
        LogEntry(
            line_no=2,
            raw="counter-2",
            ts="2026-03-18 12:00:01.000",
            level="INFO",
            corr="abc",
            req="-",
            logger="agent.telemetry",
            message="[counter] event=fell_back_to_react count=1 skill=files phase=files_orchestrator_exception",
            parsed=True,
        ),
        LogEntry(
            line_no=3,
            raw="counter-3",
            ts="2026-03-18 12:00:02.000",
            level="INFO",
            corr="abc",
            req="-",
            logger="agent.telemetry",
            message="[counter] event=context_saved count=1 agent=email topic=email_list awaiting=email_action",
            parsed=True,
        ),
    ]

    summary = log_viewer._collect_counter_summary(entries)

    assert summary["by_event"]["fast_path_hit"] == 1
    assert summary["by_event"]["fell_back_to_react"] == 1
    assert summary["by_agent"]["email"]["fast_path_hit"] == 1
    assert summary["by_agent"]["email"]["context_saved"] == 1


def test_collect_counter_trends_groups_events_by_turn() -> None:
    entries = [
        LogEntry(
            line_no=1,
            raw="start-1",
            ts="2026-03-18 12:00:00.000",
            level="INFO",
            corr="corr-1",
            req="-",
            logger="hub_processor",
            message="TURN START",
            parsed=True,
        ),
        LogEntry(
            line_no=2,
            raw="counter-1",
            ts="2026-03-18 12:00:00.500",
            level="INFO",
            corr="corr-1",
            req="-",
            logger="agent.telemetry",
            message="[counter] event=fast_path_hit count=1 agent=browser fast_path=price_comparison",
            parsed=True,
        ),
        LogEntry(
            line_no=3,
            raw="llm-1",
            ts="2026-03-18 12:00:01.000",
            level="INFO",
            corr="corr-1",
            req="-",
            logger="llm.call",
            message="provider=github-models",
            parsed=True,
        ),
        LogEntry(
            line_no=4,
            raw="start-2",
            ts="2026-03-18 12:01:00.000",
            level="INFO",
            corr="corr-2",
            req="-",
            logger="hub_processor",
            message="TURN START",
            parsed=True,
        ),
        LogEntry(
            line_no=5,
            raw="counter-2",
            ts="2026-03-18 12:01:00.500",
            level="INFO",
            corr="corr-2",
            req="-",
            logger="agent.telemetry",
            message="[counter] event=fast_path_hit count=1 agent=calendar fast_path=month_overview",
            parsed=True,
        ),
        LogEntry(
            line_no=6,
            raw="counter-3",
            ts="2026-03-18 12:01:01.000",
            level="INFO",
            corr="corr-2",
            req="-",
            logger="agent.telemetry",
            message="[counter] event=context_saved count=1 agent=calendar topic=calendar_query",
            parsed=True,
        ),
    ]

    turns = group_by_turns(entries)
    trends = log_viewer._collect_counter_trends(turns)

    assert len(trends) == 2
    assert trends[0].corr == "corr-1"
    assert trends[0].llm_calls == 1
    assert trends[0].by_event["fast_path_hit"] == 1
    assert trends[1].by_agent["calendar"]["fast_path_hit"] == 1
    assert trends[1].by_agent["calendar"]["context_saved"] == 1


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