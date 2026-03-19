import importlib


def test_parse_month_overview_ignores_injected_context_and_session_state() -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")

    query = (
        "How many meetings do I have this month?\n\n"
        "## Context from Previous Turn  [agent=calendar | topic=calendar_query | written just now]\n"
        '{"resolved_date": "2026-03-01", "events": [{"id": "evt-1", "title": "Team Sync"}]}\n\n'
        "CONTEXT INSTRUCTION (awaiting=event_selection):\n"
        "The user is referring to a specific calendar event from `events` in the context.\n\n"
        "## Session State\n"
        '{"current_date": "2026-03-14"}'
    )

    parsed = orchestrator._parse_month_overview_query(query)

    assert parsed is not None
    assert parsed["mode"] == "count"
    assert parsed["year"] == 2026
    assert parsed["month"] == 3


def test_handle_ordinal_event_delete_query_uses_saved_event_positions(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")

    saved_payloads = []

    def fake_read_context(agent=None):
        assert agent == "calendar"
        return {
            "agent": "calendar",
            "topic": "calendar_query",
            "resolved_entities": {
                "resolved_date": "2026-03-01",
                "events": [
                    {"id": f"evt-{idx}", "title": f"Meeting {idx}", "start": f"2026-03-{idx:02d}T10:00:00"}
                    for idx in range(1, 23)
                ],
            },
        }

    def fake_write_context(**kwargs):
        saved_payloads.append(kwargs)
        return {"status": "success"}

    deleted_ids = []

    def fake_delete_event(event_id):
        deleted_ids.append(event_id)
        return {"status": "success", "message": f"Deleted {event_id}"}

    monkeypatch.setattr("src.agent.manifest.context_manifest.read_context", fake_read_context)
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", fake_write_context)

    result = orchestrator._handle_ordinal_event_delete_query(
        "Can you cancel 9th and 10th meeting in the list?",
        {"delete_event": fake_delete_event},
    )

    assert result is not None
    assert result["status"] == "success"
    assert deleted_ids == ["evt-10", "evt-9"]
    assert "9. Meeting 9" in result["message"]
    assert "10. Meeting 10" in result["message"]
    assert saved_payloads
    updated_events = saved_payloads[-1]["resolved_entities"]["events"]
    assert len(updated_events) == 20
    assert all(event["id"] not in {"evt-9", "evt-10"} for event in updated_events)


def test_calendar_ordinal_delete_logs_fast_path_telemetry(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")

    telemetry_calls = []

    def fake_read_context(agent=None):
        assert agent == "calendar"
        return {
            "agent": "calendar",
            "topic": "calendar_query",
            "resolved_entities": {
                "events": [
                    {"id": "evt-1", "title": "Meeting 1", "start": "2026-03-01T10:00:00"},
                    {"id": "evt-2", "title": "Meeting 2", "start": "2026-03-02T10:00:00"},
                ],
            },
        }

    monkeypatch.setattr(orchestrator, "log_fast_path_hit", lambda agent, fast_path: telemetry_calls.append((agent, fast_path)))
    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda user_query="": {
            "delete_event": lambda event_id: {"status": "success", "message": f"Deleted {event_id}"},
            "get_events_for_month": lambda year, month: {"status": "success", "events": [], "count": 0},
        },
    )
    monkeypatch.setattr("src.agent.manifest.context_manifest.read_context", fake_read_context)
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration(
        "Can you delete the 2nd meeting from the list?"
    )

    assert result["status"] == "success"
    assert result["_fast_path"] == "ordinal_event_delete"
    assert telemetry_calls == [("calendar", "ordinal_event_delete")]