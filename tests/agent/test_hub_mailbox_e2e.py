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