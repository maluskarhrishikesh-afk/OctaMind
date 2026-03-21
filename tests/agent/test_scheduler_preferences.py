import importlib


def test_scheduler_template_preferences_flow_saves_markdown_defaults(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")
    calendar_preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr(calendar_preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    monkeypatch.setattr(orchestrator, "run_skill_dag", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for scheduler preference fast paths")))
    monkeypatch.setattr(orchestrator, "run_skill_react", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for scheduler preference fast paths")))
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr("src.agent.manifest.context_manifest.clear_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "scheduler-pref-test"}

    first = orchestrator.execute_with_llm_orchestration("edit my scheduler preferences", artifacts_out=artifacts)
    assert first["action"] == "scheduler_preferences_question"
    assert "Scheduler setup template:" in first["message"]

    final = orchestrator.execute_with_llm_orchestration(
        """Scheduler setup template:
Work hours: 08:30-18:15
Default focus block: 120 minutes
Meeting buffer: 15 minutes
Meeting reminder: 30 minutes
Planning style: deep_work_first
Constraint mode: hard
Protected windows:
- Lunch window | Weekdays | 13:00-14:00
- Focus mornings | Weekdays | 09:00-11:00
Recurring reminders:
- Gym | Daily | 20:00
- Meditation | Daily | 06:00
""",
        artifacts_out=artifacts,
    )

    saved = preferences.load_scheduler_preferences()
    synced_calendar = calendar_preferences.load_calendar_preferences()
    assert final["action"] == "scheduler_preferences_saved"
    assert saved["working_hours"]["start_hour"] == 8
    assert saved["working_hours"]["start_minute"] == 30
    assert saved["working_hours"]["end_hour"] == 18
    assert saved["working_hours"]["end_minute"] == 15
    assert saved["focus_block_minutes"] == 120
    assert saved["meeting_buffer_minutes"] == 15
    assert saved["default_meeting_reminder_minutes"] == 30
    assert saved["daily_planning_style"] == "deep_work_first"
    assert saved["constraint_mode"] == "hard"
    assert saved["no_meeting_windows"][0]["label"] == "Lunch window"
    assert saved["recurring_reminders"][0]["label"] == "Gym"
    assert synced_calendar["working_hours"]["start_hour"] == 8
    assert synced_calendar["working_hours"]["start_minute"] == 30
    assert synced_calendar["default_reminder_minutes"] == 30


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
    assert "Scheduler setup template:" in result["message"]


def test_scheduler_typoed_setup_phrase_enters_guided_preferences_flow(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration("Setup my schedular prefrences", artifacts_out={"_session_id": "telegram_scheduler_setup"})

    assert result["action"] == "scheduler_preferences_question"
    assert "Scheduler setup template:" in result["message"]


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
    assert "Scheduler setup template:" in result["message"]


def test_scheduler_unrelated_request_clears_pending_setup(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr(orchestrator, "run_skill_dag", lambda *args, **kwargs: {"status": "success", "action": "scheduled_event", "message": "scheduled"})

    artifacts = {"_session_id": "telegram_scheduler_setup"}
    orchestrator.execute_with_llm_orchestration("Setup scheduler prefrences", artifacts_out=artifacts)

    injected_reply = "Can you schedule a meeting tomorrow between 1 PM and 2 PM\n\n## Context from Previous Turn  [agent=scheduler | topic=scheduler_preferences | written just now]\n{\"session_key\": \"telegram_scheduler_setup\", \"scheduler_preferences\": {\"focus_block_minutes\": 90}}\n\n## Session State\n{}"
    result = orchestrator.execute_with_llm_orchestration(injected_reply, artifacts_out=artifacts)

    assert result["action"] == "scheduled_event"
    assert result["message"] == "scheduled"


def test_setup_my_schedule_returns_suggested_daily_schedule(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(orchestrator, "_SCHEDULER_SCHEDULE_DRAFT_PATH", tmp_path / "scheduler_schedule_draft.md")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration("Can you setup my schedule?", artifacts_out={"_session_id": "schedule-suggestion"})

    assert result["action"] == "schedule_setup_suggestion"
    assert "Here is a suggested daily schedule" in result["message"]
    assert '2. Say "looks good"' in result["message"]
    assert "Work hours: 9:30 AM -> 6:30 PM" in result["message"]
    assert "Lunch: 1:00 PM -> 2:00 PM" in result["message"]
    assert "- Meditation: 6:30 AM" in result["message"]


def test_suggested_schedule_looks_good_saves_seeded_defaults(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")
    calendar_preferences = importlib.import_module("src.calendar.calendar_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(orchestrator, "_SCHEDULER_SCHEDULE_DRAFT_PATH", tmp_path / "scheduler_schedule_draft.md")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr(calendar_preferences, "_CALENDAR_PREFERENCES_PATH", tmp_path / "calendar_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr("src.agent.manifest.context_manifest.clear_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "schedule-suggestion"}
    orchestrator.execute_with_llm_orchestration("Can you setup my schedule?", artifacts_out=artifacts)
    result = orchestrator.execute_with_llm_orchestration("looks good", artifacts_out=artifacts)

    saved = preferences.load_scheduler_preferences()
    assert result["action"] == "scheduler_preferences_saved"
    assert saved["working_hours"]["start_hour"] == 9
    assert saved["working_hours"]["start_minute"] == 30
    assert saved["working_hours"]["end_hour"] == 18
    assert saved["working_hours"]["end_minute"] == 30
    assert any(item["label"] == "Lunch window" for item in saved["no_meeting_windows"])
    assert any(item["label"] == "Focus time" for item in saved["no_meeting_windows"])
    assert any(item["label"] == "Gym" for item in saved["recurring_reminders"])
    assert any(item["label"] == "Meditation" for item in saved["recurring_reminders"])


def test_suggested_schedule_natural_language_edit_updates_preview(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(orchestrator, "_SCHEDULER_SCHEDULE_DRAFT_PATH", tmp_path / "scheduler_schedule_draft.md")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "schedule-suggestion"}
    orchestrator.execute_with_llm_orchestration("Can you setup my schedule?", artifacts_out=artifacts)
    result = orchestrator.execute_with_llm_orchestration("Move lunch to between 12:30 PM and 1:30 PM", artifacts_out=artifacts)

    assert result["action"] == "schedule_setup_suggestion"
    assert "Updated the suggested schedule." in result["message"]
    assert "Lunch: 12:30 PM -> 1:30 PM" in result["message"]


def test_schedule_followup_context_updates_draft_not_template(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(orchestrator, "_SCHEDULER_SCHEDULE_DRAFT_PATH", tmp_path / "scheduler_schedule_draft.md")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr("src.agent.manifest.context_manifest.clear_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "schedule-suggestion"}
    orchestrator.execute_with_llm_orchestration("Can you setup my schedule?", artifacts_out=artifacts)
    orchestrator._clear_pending_scheduler_preferences("schedule-suggestion")

    query = (
        "Can you change the following -\n\n"
        "Focus time - 10 AM to 11:30 AM\n"
        "Meeting Reminders - 10 minutes before\n"
        "No meetings allowed on Sunday\n\n"
        "## Context from Previous Turn  [agent=scheduler | topic=scheduler_preferences | written just now]\n"
        '{"session_key": "schedule-suggestion", "state_kind": "daily_schedule_setup"}'
    )
    result = orchestrator.execute_with_llm_orchestration(query, artifacts_out=artifacts)

    assert result["action"] == "schedule_setup_suggestion"
    assert "Scheduler setup template" not in result["message"]
    assert "Updated the suggested schedule." in result["message"]
    assert "Focus time (no meetings): 10:00 AM -> 11:30 AM" in result["message"]
    assert "Meeting reminder: 10 minutes before" in result["message"]
    assert "Avoid meetings all day on Sun" in result["message"]


def test_apply_schedule_changes_from_draft_context(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(orchestrator, "_PENDING_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_pending.json")
    monkeypatch.setattr(orchestrator, "_SCHEDULER_SCHEDULE_DRAFT_PATH", tmp_path / "scheduler_schedule_draft.md")
    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr("src.agent.manifest.context_manifest.clear_context", lambda **kwargs: {"status": "success"})

    artifacts = {"_session_id": "schedule-suggestion"}
    orchestrator.execute_with_llm_orchestration("Can you setup my schedule?", artifacts_out=artifacts)
    orchestrator.execute_with_llm_orchestration(
        "Focus time - 10 AM to 11:30 AM\nMeeting Reminders - 10 minutes before\nNo meetings allowed on Sunday",
        artifacts_out=artifacts,
    )
    orchestrator._clear_pending_scheduler_preferences("schedule-suggestion")

    apply_query = (
        "apply these changes to my schedule\n\n"
        "## Context from Previous Turn  [agent=scheduler | topic=scheduler_preferences | written just now]\n"
        '{"session_key": "schedule-suggestion", "state_kind": "daily_schedule_setup"}'
    )
    result = orchestrator.execute_with_llm_orchestration(apply_query, artifacts_out=artifacts)
    saved = preferences.load_scheduler_preferences()

    assert result["action"] == "scheduler_preferences_saved"
    assert saved["default_meeting_reminder_minutes"] == 10
    sunday_windows = [item for item in saved["no_meeting_windows"] if item["label"] == "No meetings"]
    assert sunday_windows
    assert sunday_windows[0]["days"] == ["sun"]


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


def test_scheduler_direct_preference_edit_expands_day_ranges_and_plural_days(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})

    result = orchestrator.execute_with_llm_orchestration(
        "Can you add some more things to the schedule prefrences - No meetings allowed on Sundays and also between 7:45 PM to 9:15 PM from Monday to Saturday as it's my gym time",
        artifacts_out={"_session_id": "telegram_scheduler_setup"},
    )

    saved = preferences.load_scheduler_preferences()
    assert result["action"] == "scheduler_preferences_saved"

    no_meetings = [item for item in saved["no_meeting_windows"] if item["label"] == "No meetings"]
    assert no_meetings
    assert no_meetings[0]["days"] == ["sun"]
    assert no_meetings[0]["start_hour"] == 0
    assert no_meetings[0]["start_minute"] == 0
    assert no_meetings[0]["end_hour"] == 23
    assert no_meetings[0]["end_minute"] == 59

    gym_windows = [item for item in saved["no_meeting_windows"] if item["label"] == "Gym time"]
    assert gym_windows
    assert gym_windows[0]["days"] == ["mon", "tue", "wed", "thu", "fri", "sat"]
    assert gym_windows[0]["start_hour"] == 19
    assert gym_windows[0]["start_minute"] == 45
    assert gym_windows[0]["end_hour"] == 21
    assert gym_windows[0]["end_minute"] == 15


def test_scheduler_apply_preferences_fast_path_accepts_preference_typos(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.scheduler_agent.orchestrator")
    preferences = importlib.import_module("src.calendar.scheduler_preferences")

    monkeypatch.setattr(preferences, "_SCHEDULER_PREFERENCES_PATH", tmp_path / "scheduler_preferences.md")
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr(orchestrator, "run_skill_dag", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for apply fast path")))

    preferences.save_scheduler_preferences({
        "working_hours": {"start_hour": 9, "start_minute": 0, "end_hour": 18, "end_minute": 0},
        "focus_block_minutes": 90,
        "meeting_buffer_minutes": 10,
        "default_meeting_reminder_minutes": 15,
        "daily_planning_style": "deep_work_first",
        "constraint_mode": "hard",
        "no_meeting_windows": [],
        "recurring_reminders": [],
    })

    result = orchestrator.execute_with_llm_orchestration("Apply these schedule prefrences")

    assert result["action"] == "apply_scheduler_preferences"
    assert "Scheduler preferences are active" in result["message"]