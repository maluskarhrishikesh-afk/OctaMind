from src.agent.workflows.skill_dag_engine import _apply_email_followup_constraints


def test_apply_email_followup_constraints_uses_context_count(monkeypatch) -> None:
    def fake_read_context(agent=None):
        assert agent == "email"
        return {
            "agent": "email",
            "resolved_entities": {
                "query": "from:quora",
                "listed_emails": [
                    {"id": "1"},
                    {"id": "2"},
                    {"id": "3"},
                    {"id": "4"},
                ],
            },
        }

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        fake_read_context,
    )

    fetch_step = {"kwargs": {}}
    _apply_email_followup_constraints("Can you summarize them and send it to me?", fetch_step)

    assert fetch_step["kwargs"]["query"] == "from:quora"
    assert fetch_step["kwargs"]["max_results"] == 4