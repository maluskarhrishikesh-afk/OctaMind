import importlib


def test_scheduler_guided_preferences_flow_saves_markdown_defaults(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr(orchestrator, "run_skill_dag", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for scheduler preference fast paths")))
    monkeypatch.setattr(orchestrator, "run_skill_react", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for scheduler preference fast paths")))
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr("src.agent.manifest.context_manifest.clear_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "scheduler-pref-test"}

    first = orchestrator.execute_with_llm_orchestration("edit my scheduler preferences", artifacts_out=artifacts)
    assert first["action"] == "scheduler_preferences_question"
    assert "Scheduler setup 1/5" in first["message"]

    orchestrator.execute_with_llm_orchestration("2", artifacts_out=artifacts)
    orchestrator.execute_with_llm_orchestration("3", artifacts_out=artifacts)
    orchestrator.execute_with_llm_orchestration("1", artifacts_out=artifacts)
    orchestrator.execute_with_llm_orchestration("2", artifacts_out=artifacts)
    final = orchestrator.execute_with_llm_orchestration("3", artifacts_out=artifacts)

    saved = preferences.load_scheduler_preferences()
    assert final["action"] == "scheduler_preferences_saved"
    assert saved["focus_block_minutes"] == 90
    assert saved["meeting_buffer_minutes"] == 15
    assert saved["daily_planning_style"] == "balanced"
    assert saved["constraint_mode"] == "hard"
    assert saved["no_meeting_windows"][0]["label"] == "Focus mornings"


def test_scheduler_review_digest_uses_saved_preferences(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    preferences.save_scheduler_preferences(
        {
            "focus_block_minutes": 45,
            "meeting_buffer_minutes": 5,
            "daily_planning_style": "meeting_friendly",
            "constraint_mode": "soft",
            "no_meeting_windows": [],
        }
    )

    result = orchestrator.execute_with_llm_orchestration("review my scheduler")

    assert result["action"] == "scheduler_review_digest"
    assert "Focus block length: 45 minutes" in result["message"]
    assert "Your focus block default is short" in result["message"]


def test_scheduler_setup_phrase_enters_guided_preferences_flow(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration("Setup scheduler prefrences", artifacts_out={"_session_id": "telegram_scheduler_setup"})

    assert result["action"] == "scheduler_preferences_question"
    assert "Scheduler setup 1/5" in result["message"]


def test_scheduler_typoed_setup_phrase_enters_guided_preferences_flow(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration("Setup my schedular prefrences", artifacts_out={"_session_id": "telegram_scheduler_setup"})

    assert result["action"] == "scheduler_preferences_question"
    assert "Scheduler setup 1/5" in result["message"]


def test_scheduler_followup_phrase_reopens_preferences_setup(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    preferences.save_scheduler_preferences({"focus_block_minutes": 90, "meeting_buffer_minutes": 10, "daily_planning_style": "balanced", "constraint_mode": "soft", "no_meeting_windows": []})

    query = "Want to add new ones\n\n## Context from Previous Turn  [agent=scheduler | topic=scheduler_preferences | written just now]\n{\"session_key\": \"telegram_scheduler_setup\", \"followup_kind\": \"show\", \"scheduler_preferences\": {\"focus_block_minutes\": 90}}"
    result = orchestrator.execute_with_llm_orchestration(query, artifacts_out={"_session_id": "telegram_scheduler_setup"})

    assert result["action"] == "scheduler_preferences_question"
    assert "Scheduler setup 1/5" in result["message"]


def test_scheduler_numeric_reply_advances_when_context_is_injected(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "telegram_scheduler_setup"}
    orchestrator.execute_with_llm_orchestration("Setup scheduler prefrences", artifacts_out=artifacts)

    injected_reply = "2\n\n## Context from Previous Turn  [agent=scheduler | topic=scheduler_preferences | written just now]\n{\"session_key\": \"telegram_scheduler_setup\", \"scheduler_preferences\": {\"focus_block_minutes\": 90}}\n\n## Session State\n{}"
    result = orchestrator.execute_with_llm_orchestration(injected_reply, artifacts_out=artifacts)

    assert result["action"] == "scheduler_preferences_question"
    assert "Scheduler setup 2/5" in result["message"]
    assert "Meeting buffer" in result["message"]


def test_scheduler_direct_preference_edit_adds_custom_gym_window(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration(
        "Can you add a new preference - no meetings between 7:45 PM to 9:15 PM as that is my gym time?",
        artifacts_out={"_session_id": "telegram_scheduler_setup"},
    )

    saved = preferences.load_scheduler_preferences()
    assert result["action"] == "scheduler_preferences_saved"
    assert "Gym time" in result["message"]
    assert saved["no_meeting_windows"][-1]["label"] == "Gym time"
    assert saved["no_meeting_windows"][-1]["start_hour"] == 19
    assert saved["no_meeting_windows"][-1]["start_minute"] == 45
    assert saved["no_meeting_windows"][-1]["end_hour"] == 21
    assert saved["no_meeting_windows"][-1]["end_minute"] == 15