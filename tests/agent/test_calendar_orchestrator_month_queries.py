import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_get_events_for_month_uses_explicit_month_boundaries(monkeypatch):
    calendar_service = importlib.import_module("src.calendar.calendar_service")

    captured = {}

    def fake_list_events(time_min=None, time_max=None, max_results=20, calendar_id="primary", query=None):
        captured.update(
            {
                "time_min": time_min,
                "time_max": time_max,
                "max_results": max_results,
                "calendar_id": calendar_id,
                "query": query,
            }
        )
        return {"status": "success", "events": [], "count": 0}

    monkeypatch.setattr(calendar_service, "list_events", fake_list_events)

    result = calendar_service.get_events_for_month(2026, 3, max_results=200)

    assert result["status"] == "success"
    assert captured["time_min"].startswith("2026-03-01T00:00:00")
    assert captured["time_max"].startswith("2026-04-01T00:00:00")
    assert captured["max_results"] == 200
    assert captured["calendar_id"] == "primary"
    assert captured["query"] is None


def test_calendar_orchestrator_handles_this_month_count_without_llm(monkeypatch):
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    calendar_service = importlib.import_module("src.calendar.calendar_service")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    sample_events = [
        {
            "title": f"Event {index}",
            "start": f"2026-03-{index:02d}T10:00:00+05:30",
            "end": f"2026-03-{index:02d}T11:00:00+05:30",
        }
        for index in range(1, 13)
    ]

    monkeypatch.setattr(
        calendar_service,
        "get_events_for_month",
        lambda year, month, max_results=200, calendar_id="primary": {
            "status": "success",
            "events": sample_events,
            "results": sample_events,
            "count": 12,
            "message": "Found 12 event(s).",
        },
    )
    monkeypatch.setattr(
        context_manifest,
        "auto_save_calendar_context",
        lambda result, *args, **kwargs: result,
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for this month fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for this month fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "How many meetings do I have this month?\n\n"
        "## Session State\n"
        '{"current_date": "2026-03-14"}'
    )

    assert result["status"] == "success"
    assert result["_fast_path"] == "month_overview"
    assert "12 calendar events" in result["message"]
    assert "March 2026" in result["message"]
    assert "1. **Event 1**" in result["message"]
    assert "2 more event(s) are scheduled later in the month." in result["message"]


def test_calendar_month_overview_logs_fast_path_telemetry(monkeypatch):
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    calendar_service = importlib.import_module("src.calendar.calendar_service")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    telemetry_calls = []
    monkeypatch.setattr(
        orchestrator,
        "log_fast_path_hit",
        lambda agent, fast_path: telemetry_calls.append((agent, fast_path)),
    )
    monkeypatch.setattr(
        calendar_service,
        "get_events_for_month",
        lambda year, month, max_results=200, calendar_id="primary": {
            "status": "success",
            "events": [],
            "results": [],
            "count": 0,
            "message": "Found 0 event(s).",
        },
    )
    monkeypatch.setattr(context_manifest, "auto_save_calendar_context", lambda result, *args, **kwargs: result)

    result = orchestrator.execute_with_llm_orchestration(
        "How many meetings do I have this month?\n\n## Session State\n{\"current_date\": \"2026-03-14\"}"
    )

    assert result["status"] == "success"
    assert telemetry_calls == [("calendar", "month_overview")]