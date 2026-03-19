from __future__ import annotations

import importlib


def test_callback_query_to_user_text_supports_generic_destructive_actions() -> None:
    from src.telegram.auto_responder import _callback_query_to_user_text

    assert (
        _callback_query_to_user_text("destructive_action:confirm:abc123def4567890")
        == "confirm action abc123def4567890"
    )
    assert (
        _callback_query_to_user_text("destructive_action:cancel:abc123def4567890")
        == "cancel action abc123def4567890"
    )


def test_maybe_auto_reply_suppresses_duplicate_processing(monkeypatch, tmp_path) -> None:
    auto_responder = importlib.import_module("src.telegram.auto_responder")

    monkeypatch.setattr(auto_responder, "_REPLY_CLAIMS_DIR", tmp_path / "claims")

    calls = []
    monkeypatch.setattr(auto_responder, "auto_reply_enabled", lambda: True)
    monkeypatch.setattr(auto_responder, "_generate_and_send", lambda chat_id, text: calls.append((chat_id, text)))

    message = {
        "chat_id": 123,
        "message_id": 456,
        "direction": "inbound",
        "text": "How many payslips are there on my computer?",
    }

    auto_responder.maybe_auto_reply(message)
    auto_responder.maybe_auto_reply(message)

    assert calls == [(123, "How many payslips are there on my computer?")]