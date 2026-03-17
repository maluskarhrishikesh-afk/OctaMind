from __future__ import annotations


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