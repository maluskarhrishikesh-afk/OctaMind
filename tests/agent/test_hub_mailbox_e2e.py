from __future__ import annotations

import importlib


def test_hub_processor_routes_organize_mailbox_to_email(monkeypatch) -> None:
    processor_mod = importlib.import_module("src.agent.hub.processor")
    monkeypatch.setattr("src.agent.manifest.context_manifest.read_context", lambda *args, **kwargs: None)

    calls = []

    def _fake_run_single_agent(self, agent, req, query=None, confirmed_action_keys=None):
        calls.append((agent, query or req.message))
        assert agent == "email"
        assert "organize my mailbox" in (query or req.message).lower()
        return ("Mailbox setup entry", [{"agent": "email", "status": "success", "llm_calls": 0}], [], [], {})

    monkeypatch.setattr(processor_mod.HubProcessor, "_run_single_agent", _fake_run_single_agent)
    monkeypatch.setattr(processor_mod, "evaluate_inbound_request", lambda **kwargs: type("Decision", (), {"decision": "allow", "user_message": "", "to_dict": lambda self: {}})())

    response = processor_mod.HubProcessor().process(
        message="please organize my mailbox",
        session_id="telegram_mailbox",
        source="telegram",
        agent_id="pa_test",
        agent_name="Test PA",
    )

    assert response.status == "success"
    assert response.response == "Mailbox setup entry"
    assert len(calls) == 1
    assert calls[0][0] == "email"
    assert "please organize my mailbox" in calls[0][1].lower()


def test_hub_processor_routes_apply_cleanup_now_to_email_with_mailbox_context(monkeypatch) -> None:
    processor_mod = importlib.import_module("src.agent.hub.processor")
    monkeypatch.setattr(
        "src.agent.workflows.run_routing_pipeline",
        lambda *args, **kwargs: type(
            "Pipeline",
            (),
            {
                "intent": type("Intent", (), {"is_chat": False, "is_context_followup": True, "agents": ["email"], "category": "context_followup", "reason": "test"})(),
                "classification": type("Classification", (), {"category": "context_followup", "source": "test", "reason": "test"})(),
                "context_resolution": type("ContextResolution", (), {"category": "context_followup", "context_agent": "email", "default_agents": ["email"], "reason": "test"})(),
                "planning": type("Planning", (), {"source": "test", "reason": "test"})(),
            },
        )(),
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda *args, **kwargs: {
            "agent": "email",
            "topic": "mailbox_review",
            "awaiting": "email_action",
            "resolved_entities": {
                "followup_kind": "review",
                "mailbox_preferences": {"promotions_action": "archive"},
            },
        },
    )

    calls = []

    def _fake_run_single_agent(self, agent, req, query=None, confirmed_action_keys=None):
        calls.append((agent, query or req.message))
        assert agent == "email"
        assert "apply cleanup now" in (query or req.message).lower()
        return ("Applied mailbox preferences", [{"agent": "email", "status": "success", "llm_calls": 0}], [], [], {})

    monkeypatch.setattr(processor_mod.HubProcessor, "_run_single_agent", _fake_run_single_agent)
    monkeypatch.setattr(processor_mod, "evaluate_inbound_request", lambda **kwargs: type("Decision", (), {"decision": "allow", "user_message": "", "to_dict": lambda self: {}})())

    response = processor_mod.HubProcessor().process(
        message="Apply cleanup now",
        session_id="telegram_mailbox",
        source="telegram",
        agent_id="pa_test",
        agent_name="Test PA",
    )

    assert response.status == "success"
    assert response.response == "Applied mailbox preferences"
    assert len(calls) == 1
    assert calls[0][0] == "email"


def test_hub_processor_clarifies_ambiguous_cleanup_when_stale_file_context_exists(monkeypatch) -> None:
    processor_mod = importlib.import_module("src.agent.hub.processor")
    monkeypatch.setattr(
        "src.agent.workflows.run_routing_pipeline",
        lambda *args, **kwargs: type(
            "Pipeline",
            (),
            {
                "intent": type("Intent", (), {"is_chat": False, "is_context_followup": True, "agents": ["file_organizer"], "category": "context_followup", "reason": "test"})(),
                "classification": type("Classification", (), {"category": "context_followup", "source": "test", "reason": "test"})(),
                "context_resolution": type("ContextResolution", (), {"category": "context_followup", "context_agent": "file_organizer", "default_agents": ["file_organizer"], "reason": "test"})(),
                "planning": type("Planning", (), {"source": "test", "reason": "test"})(),
            },
        )(),
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda *args, **kwargs: {
            "agent": "file_organizer",
            "topic": "folder_cleanup_plan",
            "awaiting": "file_action",
            "resolved_entities": {"path": "C:/Temp/Downloads"},
        },
    )
    monkeypatch.setattr(processor_mod, "evaluate_inbound_request", lambda **kwargs: type("Decision", (), {"decision": "allow", "user_message": "", "to_dict": lambda self: {}})())

    response = processor_mod.HubProcessor().process(
        message="Apply cleanup now",
        session_id="telegram_mailbox",
        source="telegram",
        agent_id="pa_test",
        agent_name="Test PA",
    )

    assert response.status == "success"
    assert "I need to clarify what you want to clean up" in response.response
    assert "apply mailbox cleanup now" in response.response.lower()