import importlib


def test_calendar_guided_preferences_flow_saves_markdown_defaults(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_pending.json")
    monkeypatch.setattr(preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    monkeypatch.setattr(orchestrator, "run_skill_dag", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for calendar preference fast paths")))
    monkeypatch.setattr(orchestrator, "run_skill_react", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for calendar preference fast paths")))
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr("src.agent.manifest.context_manifest.clear_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "calendar-pref-test"}

    first = orchestrator.execute_with_llm_orchestration("edit my calendar preferences", artifacts_out=artifacts)
    assert first["action"] == "calendar_preferences_question"
    assert "Calendar setup 1/4" in first["message"]

    orchestrator.execute_with_llm_orchestration("1", artifacts_out=artifacts)
    orchestrator.execute_with_llm_orchestration("2", artifacts_out=artifacts)
    orchestrator.execute_with_llm_orchestration("3", artifacts_out=artifacts)
    final = orchestrator.execute_with_llm_orchestration("1", artifacts_out=artifacts)

    saved = preferences.load_calendar_preferences()
    assert final["action"] == "calendar_preferences_saved"
    assert saved["working_hours"]["start_hour"] == 8
    assert saved["working_hours"]["end_hour"] == 18
    assert saved["default_meeting_minutes"] == 60
    assert saved["default_reminder_minutes"] == 10


def test_calendar_setup_phrase_enters_guided_preferences_flow(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_pending.json")
    monkeypatch.setattr(preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration("Setup my calendar prefrences", artifacts_out={"_session_id": "telegram_calendar_setup"})

    assert result["action"] == "calendar_preferences_question"
    assert "Calendar setup 1/4" in result["message"]


def test_calendar_numeric_reply_advances_when_context_is_injected(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_pending.json")
    monkeypatch.setattr(preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "telegram_calendar_setup"}
    orchestrator.execute_with_llm_orchestration("Setup my calendar prefrences", artifacts_out=artifacts)

    injected_reply = "2\n\n## Context from Previous Turn  [agent=calendar | topic=calendar_preferences | written just now]\n{\"session_key\": \"telegram_calendar_setup\", \"calendar_preferences\": {\"working_hours\": {\"start_hour\": 9, \"end_hour\": 18}}}\n\n## Session State\n{}"
    result = orchestrator.execute_with_llm_orchestration(injected_reply, artifacts_out=artifacts)

    assert result["action"] == "calendar_preferences_question"
    assert "Calendar setup 2/4" in result["message"]
    assert "Working-hours end" in result["message"]


def test_calendar_creation_defaults_apply_saved_duration(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    preferences.save_calendar_preferences({"default_meeting_minutes": 60, "default_reminder_minutes": 15, "working_hours": {"start_hour": 9, "end_hour": 18}})

    apply_creation_defaults = getattr(orchestrator, "_calendar_apply_creation_defaults")

    augmented = apply_creation_defaults(
        "Schedule a review with Priya at 4 PM",
        preferences.load_calendar_preferences(),
        "2026-03-21",
    )

    assert "on 2026-03-21" in augmented
    assert "for 60 minutes" in augmented


def test_calendar_tool_defaults_use_preference_values(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    preferences.save_calendar_preferences({"default_meeting_minutes": 45, "default_reminder_minutes": 15, "working_hours": {"start_hour": 10, "end_hour": 19}})

    calls = []

    monkeypatch.setattr("src.calendar.calendar_service.find_free_slots", lambda date_str, duration_minutes, working_start_hour, working_start_minute, working_end_hour, working_end_minute, buffer_minutes=0, calendar_id="primary": calls.append(("slots", date_str, duration_minutes, working_start_hour, working_start_minute, working_end_hour, working_end_minute, buffer_minutes, calendar_id)) or {"status": "success"})
    monkeypatch.setattr("src.calendar.calendar_service.set_reminder", lambda event_id, minutes_before=30, calendar_id="primary": calls.append(("reminder", event_id, minutes_before, calendar_id)) or {"status": "success"})

    build_all_tools = getattr(orchestrator, "_build_all_tools")
    tools = build_all_tools("show calendar")
    tools["find_free_slots"]("2026-03-22")
    tools["set_reminder"]("evt-1")

    assert calls[0] == ("slots", "2026-03-22", 45, 10, 0, 19, 0, 0, "primary")
    assert calls[1] == ("reminder", "evt-1", 15, "primary")


def test_calendar_unrelated_request_clears_pending_setup(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.calendar_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_pending.json")
    monkeypatch.setattr(preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr(orchestrator, "run_skill_dag", lambda *args, **kwargs: {"status": "success", "action": "calendar_request", "message": "calendar handled"})

    artifacts = {"_session_id": "telegram_calendar_setup"}
    orchestrator.execute_with_llm_orchestration("Setup my calendar prefrences", artifacts_out=artifacts)

    injected_reply = "Can you schedule a meeting tomorrow between 1 PM and 2 PM\n\n## Context from Previous Turn  [agent=calendar | topic=calendar_preferences | written just now]\n{\"session_key\": \"telegram_calendar_setup\", \"calendar_preferences\": {\"working_hours\": {\"start_hour\": 9, \"end_hour\": 18}}}\n\n## Session State\n{}"
    result = orchestrator.execute_with_llm_orchestration(injected_reply, artifacts_out=artifacts)

    assert result["action"] == "calendar_request"
    assert result["message"] == "calendar handled"