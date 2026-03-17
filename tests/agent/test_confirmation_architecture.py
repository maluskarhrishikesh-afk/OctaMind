from __future__ import annotations

import json
import importlib


def test_hub_processor_replays_pending_confirmation(monkeypatch, tmp_path) -> None:
    processor_mod = importlib.import_module("src.agent.hub.processor")
    confirmation_mod = importlib.import_module("src.agent.workflows.confirmation_policy")

    pending_path = tmp_path / "destructive_action_pending.json"
    monkeypatch.setattr(confirmation_mod, "_PENDING_CONFIRMATIONS_PATH", pending_path)
    pending_path.write_text(
        json.dumps(
            {
                "telegram_1": {
                    "action_key": "abc123def4567890",
                    "message": "files::delete file",
                    "original_message": "Delete the temporary file",
                    "source": "telegram",
                    "agent_id": "pa_1",
                    "agent_name": "octa-001",
                }
            }
        ),
        encoding="utf-8",
    )

    captured = {}

    def fake_dispatch(self, req, history, on_progress=None, confirmed_action_keys=None):
        captured["message"] = req.message
        captured["confirmed_action_keys"] = confirmed_action_keys
        return ("Deleted.", [], "success", [], [], {})

    monkeypatch.setattr(processor_mod.HubProcessor, "_dispatch", fake_dispatch)

    response = processor_mod.HubProcessor().process(
        message="confirm action abc123def4567890",
        session_id="telegram_1",
        source="telegram",
        agent_id="pa_1",
        agent_name="octa-001",
    )

    assert response.status == "success"
    assert captured["message"] == "Delete the temporary file"
    assert captured["confirmed_action_keys"] == ["abc123def4567890"]
    assert json.loads(pending_path.read_text(encoding="utf-8")) == {}


def test_hub_processor_stores_pending_confirmation(monkeypatch, tmp_path) -> None:
    processor_mod = importlib.import_module("src.agent.hub.processor")
    confirmation_mod = importlib.import_module("src.agent.workflows.confirmation_policy")

    pending_path = tmp_path / "destructive_action_pending.json"
    monkeypatch.setattr(confirmation_mod, "_PENDING_CONFIRMATIONS_PATH", pending_path)

    monkeypatch.setattr(
        processor_mod.HubProcessor,
        "_dispatch",
        lambda self, req, history, on_progress=None, confirmed_action_keys=None: (
            "Please confirm delete.",
            [{
                "agent": "files",
                "status": "confirmation_required",
                "confirmation": {
                    "action_key": "abc123def4567890",
                    "skill_name": "files",
                    "tool_name": "delete_file",
                    "kwargs": {"path": "C:/Temp/demo.txt"},
                    "message": "files::delete file",
                },
            }],
            "confirmation_required",
            [],
            [],
            {"telegram": {"reply_markup": {"inline_keyboard": []}}},
        ),
    )

    response = processor_mod.HubProcessor().process(
        message="Delete the temporary file",
        session_id="telegram_1",
        source="telegram",
        agent_id="pa_1",
        agent_name="octa-001",
    )

    assert response.status == "confirmation_required"
    stored = json.loads(pending_path.read_text(encoding="utf-8"))
    assert stored["telegram_1"]["original_message"] == "Delete the temporary file"
    assert stored["telegram_1"]["action_key"] == "abc123def4567890"