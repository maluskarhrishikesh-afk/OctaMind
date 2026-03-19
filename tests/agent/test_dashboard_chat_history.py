import importlib
import json


def test_load_dashboard_chat_prefers_dashboard_session_without_duplicate_linked_history(tmp_path, monkeypatch) -> None:
    app = importlib.import_module("src.agent.ui.personal_assistant.app")

    conversation_path = tmp_path / "hub_conversations.json"
    conversation_path.write_text(
        json.dumps(
            {
                "sessions": {
                    "dashboard_pa_123": {
                        "source": "dashboard",
                        "session_id": "dashboard_pa_123",
                        "agent_id": "pa_123",
                        "messages": [
                            {
                                "role": "user",
                                "content": "How many payslips are there?",
                                "ts": "2026-03-18T10:00:00+00:00",
                                "channel_source": "telegram",
                            },
                            {
                                "role": "assistant",
                                "content": "I found 22 payslips.",
                                "ts": "2026-03-18T10:00:00+00:00",
                                "channel_source": "telegram",
                            },
                        ],
                    },
                    "telegram_999": {
                        "source": "telegram",
                        "session_id": "telegram_999",
                        "agent_id": "pa_123",
                        "messages": [
                            {
                                "role": "user",
                                "content": "How many payslips are there?",
                                "ts": "2026-03-18T10:00:00+00:00",
                            },
                            {
                                "role": "assistant",
                                "content": "I found 22 payslips.",
                                "ts": "2026-03-18T10:00:00+00:00",
                            },
                        ],
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app, "_CONV_PATH", conversation_path)
    monkeypatch.setattr(app, "_load_pa_telegram_chat_ids", lambda pa_id: {"999"})

    restored = app._load_dashboard_chat("pa_123")

    assert len(restored) == 2
    assert restored[0]["channel_source"] == "telegram"
    assert restored[1]["content"] == "I found 22 payslips."
