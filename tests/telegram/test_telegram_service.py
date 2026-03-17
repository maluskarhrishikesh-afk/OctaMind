"""
Unit tests for:
  - src/telegram/telegram_auth.py          (credential loading)
  - src/telegram/telegram_service.py       (HTTP client layer / _unwrap)
  - src/telegram/polling/message_store.py  (local JSON store)
  - src/telegram/polling/poller.py         (start/stop helpers)

All HTTP calls are mocked — no real Telegram API required.
All file I/O is redirected to tmp_path — no real data files touched.
Zero LLM calls made anywhere in this file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _mock_ok_response(result):
    """Return a mock requests.Response with ok=True and the given result."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"ok": True, "result": result}
    return resp


def _mock_error_response(description: str = "Bad Request", status_code: int = 400):
    """Return a mock requests.Response where ok=False (triggers RuntimeError)."""
    import requests as _req

    resp = MagicMock()
    resp.json.return_value = {"ok": False, "description": description}
    resp.raise_for_status.side_effect = _req.HTTPError(response=resp)
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# telegram_auth
# ══════════════════════════════════════════════════════════════════════════════

class TestTelegramAuth:
    def test_env_var_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env_tok_123")
        from src.telegram.telegram_auth import get_bot_token
        assert get_bot_token() == "env_tok_123"

    def test_no_settings_fallback_returns_empty(self, monkeypatch):
        """settings.json fallback was removed; without the env var the token is empty."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        from src.telegram.telegram_auth import get_bot_token
        assert get_bot_token() == ""

    def test_empty_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        from src.telegram.telegram_auth import get_bot_token
        assert get_bot_token() == ""

    def test_credentials_configured_true(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        from src.telegram.telegram_auth import credentials_configured
        assert credentials_configured() is True

    def test_credentials_configured_false(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        from src.telegram.telegram_auth import credentials_configured
        assert credentials_configured() is False


# ══════════════════════════════════════════════════════════════════════════════
# telegram_service._unwrap
# ══════════════════════════════════════════════════════════════════════════════

class TestUnwrap:
    def test_returns_result_on_success(self):
        from src.telegram.telegram_service import _unwrap
        resp = _mock_ok_response({"message_id": 42, "chat": {"id": 100}})
        result = _unwrap(resp)
        assert result["message_id"] == 42

    def test_raises_on_ok_false(self):
        from src.telegram.telegram_service import _unwrap
        resp = MagicMock()
        resp.raise_for_status = MagicMock()  # no HTTP error
        resp.json.return_value = {"ok": False, "description": "Bot blocked by user"}
        with pytest.raises(RuntimeError, match="Bot blocked by user"):
            _unwrap(resp)

    def test_raises_on_http_error(self):
        from src.telegram.telegram_service import _unwrap
        resp = _mock_error_response("Unauthorized", 401)
        with pytest.raises(RuntimeError, match="Telegram API error"):
            _unwrap(resp)

    def test_returns_empty_dict_when_no_result_key(self):
        from src.telegram.telegram_service import _unwrap
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"ok": True}  # no "result" key
        assert _unwrap(resp) == {}


# ══════════════════════════════════════════════════════════════════════════════
# telegram_service — send_text (mocked HTTP)
# ══════════════════════════════════════════════════════════════════════════════

class TestSendText:
    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_send_text_returns_message_dict(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response(
            {"message_id": 7, "chat": {"id": 123}}
        )
        from src.telegram.telegram_service import send_text
        result = send_text(123, "Hello Telegram!")
        assert result["message_id"] == 7
        mock_post.assert_called_once()

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_send_text_with_reply_includes_param(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response({"message_id": 8, "chat": {"id": 5}})
        from src.telegram.telegram_service import send_text
        send_text(5, "reply text", reply_to_message_id=3)
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["reply_to_message_id"] == 3

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_send_text_with_reply_markup_includes_payload(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response({"message_id": 8, "chat": {"id": 5}})
        from src.telegram.telegram_service import send_text
        reply_markup = {"inline_keyboard": [[{"text": "Yes", "callback_data": "x"}]]}
        send_text(5, "reply text", reply_markup=reply_markup)
        payload = mock_post.call_args[1]["json"]
        assert payload["reply_markup"] == reply_markup

    @patch(
        "src.telegram.telegram_service.requests.post",
        side_effect=Exception("connection refused"),
    )
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_send_text_propagates_network_error(self, _tok, mock_post):
        from src.telegram.telegram_service import send_text
        with pytest.raises(Exception, match="connection refused"):
            send_text(123, "hi")


# ══════════════════════════════════════════════════════════════════════════════
# telegram_service — forward, edit, delete (smoke tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestMessageMutations:
    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_forward_message_api(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response({"message_id": 9})
        from src.telegram.telegram_service import forward_message_api
        # Signature: forward_message_api(chat_id, from_chat_id, message_id)
        result = forward_message_api(chat_id=2, from_chat_id=1, message_id=5)
        assert result["message_id"] == 9

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_edit_message_text(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response({"message_id": 5, "text": "new"})
        from src.telegram.telegram_service import edit_message_text
        result = edit_message_text(chat_id=1, message_id=5, text="new")
        assert result["message_id"] == 5

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_edit_message_text_with_reply_markup(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response({"message_id": 5, "text": "new"})
        from src.telegram.telegram_service import edit_message_text
        reply_markup = {"inline_keyboard": [[{"text": "Yes", "callback_data": "x"}]]}
        edit_message_text(chat_id=1, message_id=5, text="new", reply_markup=reply_markup)
        payload = mock_post.call_args[1]["json"]
        assert payload["reply_markup"] == reply_markup

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_edit_message_reply_markup(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response({"message_id": 5})
        from src.telegram.telegram_service import edit_message_reply_markup
        result = edit_message_reply_markup(chat_id=1, message_id=5)
        assert result["message_id"] == 5

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_answer_callback_query_returns_true(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response(True)
        from src.telegram.telegram_service import answer_callback_query
        assert answer_callback_query("cbq-1", text="Done") is True

    @patch("src.telegram.telegram_service.requests.post")
    @patch("src.telegram.telegram_service.get_bot_token", return_value="FAKE_TOKEN")
    def test_delete_message_api_returns_true(self, _tok, mock_post):
        mock_post.return_value = _mock_ok_response(True)
        from src.telegram.telegram_service import delete_message_api
        result = delete_message_api(chat_id=1, message_id=5)
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# polling/message_store — redirect I/O to tmp_path
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Redirect all message store file I/O to a temp directory."""
    import src.telegram.polling.message_store as ms
    data_file = tmp_path / "telegram_messages.json"
    monkeypatch.setattr(ms, "_DATA_PATH", data_file)
    return tmp_path


def _make_raw_message(chat_id: int = 1001, message_id: int = 1, text: str = "hi") -> dict:
    """Minimal Telegram update message object."""
    return {
        "message_id": message_id,
        "from": {"id": 555, "first_name": "Alice", "username": "alice"},
        "chat": {"id": chat_id, "type": "private", "first_name": "Alice"},
        "date": 1740000000,
        "text": text,
    }


class TestMessageStore:
    def test_offset_starts_at_zero(self, isolated_store):
        from src.telegram.polling.message_store import get_offset
        assert get_offset() == 0

    def test_set_and_get_offset(self, isolated_store):
        from src.telegram.polling.message_store import set_offset, get_offset
        set_offset(500)
        assert get_offset() == 500

    def test_store_inbound_message(self, isolated_store):
        from src.telegram.polling.message_store import store_inbound_message, get_all_messages
        stored = store_inbound_message(_make_raw_message(text="Hello"), update_id=10)
        msgs = get_all_messages()
        assert stored is True
        assert len(msgs) == 1
        assert msgs[0]["text"] == "Hello"
        assert msgs[0]["direction"] == "inbound"

    def test_inbound_message_marked_unread(self, isolated_store):
        from src.telegram.polling.message_store import store_inbound_message, get_unread_messages
        store_inbound_message(_make_raw_message(text="New"), update_id=11)
        unread = get_unread_messages()
        assert any(m["text"] == "New" for m in unread)

    def test_store_outbound_message(self, isolated_store):
        from src.telegram.polling.message_store import store_outbound_message, get_all_messages
        store_outbound_message(chat_id=1001, text="Sent!", message_id=99)
        msgs = get_all_messages()
        assert any(m["text"] == "Sent!" and m["direction"] == "outbound" for m in msgs)

    def test_composite_id_deduplication(self, isolated_store):
        """Storing the same composite ID twice should not create a duplicate."""
        from src.telegram.polling.message_store import store_inbound_message, get_all_messages
        raw = _make_raw_message(chat_id=1001, message_id=42, text="dup")
        assert store_inbound_message(raw, update_id=20) is True
        assert store_inbound_message(raw, update_id=20) is False
        msgs = [m for m in get_all_messages() if m["id"] == "1001:42"]
        assert len(msgs) == 1

    def test_get_messages_for_chat(self, isolated_store):
        from src.telegram.polling.message_store import store_inbound_message, get_messages_for_chat
        store_inbound_message(_make_raw_message(chat_id=111, text="chat A"), update_id=1)
        store_inbound_message(_make_raw_message(chat_id=222, text="chat B"), update_id=2)
        chat_a = get_messages_for_chat(111)
        assert all(m["chat_id"] == 111 for m in chat_a)
        assert any(m["text"] == "chat A" for m in chat_a)

    def test_mark_message_read(self, isolated_store):
        from src.telegram.polling.message_store import (
            store_inbound_message, mark_message_read, get_unread_messages,
        )
        store_inbound_message(_make_raw_message(chat_id=1001, message_id=5, text="read me"), update_id=30)
        mark_message_read("1001:5")
        unread = get_unread_messages()
        assert not any(m["id"] == "1001:5" for m in unread)

    def test_get_message_count(self, isolated_store):
        from src.telegram.polling.message_store import (
            store_inbound_message, store_outbound_message, get_message_count,
        )
        store_inbound_message(_make_raw_message(text="in"), update_id=40)
        store_outbound_message(1001, "out", message_id=200)
        counts = get_message_count()
        assert isinstance(counts, dict)
        assert counts["total"] >= 2
        assert counts["inbound"] >= 1
        assert counts["outbound"] >= 1
        assert "unread" in counts

    def test_get_all_chats_populated(self, isolated_store):
        from src.telegram.polling.message_store import store_inbound_message, get_all_chats
        store_inbound_message(_make_raw_message(chat_id=7777, text="hi"), update_id=50)
        chats = get_all_chats()   # returns Dict[str, Any] keyed by chat_id string
        assert isinstance(chats, dict)
        assert "7777" in chats

    def test_get_message_by_composite_id(self, isolated_store):
        from src.telegram.polling.message_store import (
            store_inbound_message, get_message_by_composite_id,
        )
        store_inbound_message(_make_raw_message(chat_id=999, message_id=1, text="find me"), update_id=60)
        msg = get_message_by_composite_id("999:1")
        assert msg is not None
        assert msg["text"] == "find me"


# ══════════════════════════════════════════════════════════════════════════════
# poller — start/stop (no real network; thread starts are checked)
# ══════════════════════════════════════════════════════════════════════════════

class TestPoller:
    def test_stop_before_start_is_safe(self):
        """Calling stop_poller() before starting should not raise."""
        from src.telegram.polling.poller import stop_poller
        stop_poller()  # should be a no-op

    def test_stop_sets_stop_event(self):
        """stop_poller() should set the _stop_event."""
        import src.telegram.polling.poller as poller_mod
        poller_mod._stop_event.clear()
        poller_mod.stop_poller()
        assert poller_mod._stop_event.is_set()

    @patch("src.telegram.polling.poller._poll_loop", return_value=None)
    def test_start_returns_thread(self, mock_loop):
        """start_poller_in_background() should return a Thread."""
        import threading
        import src.telegram.polling.poller as poller_mod
        # Reset state
        poller_mod._poll_thread = None
        poller_mod._stop_event.clear()
        with patch("src.telegram.telegram_auth.get_bot_token", return_value="FAKE_TOKEN"):
            result = poller_mod.start_poller_in_background()
        assert isinstance(result, threading.Thread)
        poller_mod.stop_poller()
        poller_mod._poll_thread = None

    def test_process_update_dispatches_callback_queries(self):
        import src.telegram.polling.poller as poller_mod

        handled = []

        with patch("src.telegram.auto_responder.maybe_handle_callback_query", side_effect=lambda payload: handled.append(payload)):
            class _ImmediateThread:
                def __init__(self, target, args=(), daemon=None):
                    self._target = target
                    self._args = args

                def start(self):
                    self._target(*self._args)

            with patch("threading.Thread", _ImmediateThread):
                poller_mod._process_update(
                    {
                        "update_id": 77,
                        "callback_query": {
                            "id": "cbq-1",
                            "data": "mailbox_cleanup:confirm:delete_all_filters",
                            "message": {"message_id": 8, "chat": {"id": 123}},
                        },
                    }
                )

        assert handled and handled[0]["data"] == "mailbox_cleanup:confirm:delete_all_filters"

    def test_process_update_skips_duplicate_auto_reply(self, isolated_store):
        import src.telegram.polling.poller as poller_mod

        handled = []

        class _ImmediateThread:
            def __init__(self, target, args=(), daemon=None):
                self._target = target
                self._args = args

            def start(self):
                self._target(*self._args)

        update = {
            "update_id": 88,
            "message": _make_raw_message(chat_id=555, message_id=9, text="hello once"),
        }

        with patch("src.telegram.auto_responder.maybe_auto_reply", side_effect=lambda payload: handled.append(payload)):
            with patch("threading.Thread", _ImmediateThread):
                poller_mod._process_update(update)
                poller_mod._process_update(update)

        assert len(handled) == 1


class TestAutoResponderDirectCommands:
    def test_send_welcome_logs_direct_turn(self):
        import src.telegram.auto_responder as auto_responder

        sent = []
        logged = []

        with patch("src.telegram.telegram_service.send_text", side_effect=lambda chat_id, text: sent.append((chat_id, text)) or {"message_id": 12}):
            with patch("src.telegram.polling.message_store.store_outbound_message"):
                with patch("src.agent.hub.processor.log_external_turn", side_effect=lambda **kwargs: logged.append(kwargs)):
                    with patch.object(auto_responder, "_resolve_current_pa", return_value=("pa-1", "Assistant")):
                        auto_responder._send_welcome(321)

        assert sent and sent[0][0] == 321
        assert logged and logged[0]["session_id"] == "telegram_321"
        assert logged[0]["agent_id"] == "pa-1"
        assert logged[0]["user_message"] == "/start"

    def test_status_command_reports_keep_awake_state(self):
        import src.telegram.auto_responder as auto_responder

        sent = []
        logged = []

        with patch("src.telegram.telegram_service.send_text", side_effect=lambda chat_id, text: sent.append((chat_id, text)) or {"message_id": 55}):
            with patch("src.telegram.polling.message_store.store_outbound_message"):
                with patch("src.agent.hub.processor.log_external_turn", side_effect=lambda **kwargs: logged.append(kwargs)):
                    with patch("src.agent.system.runtime_status.get_keep_awake_status", return_value={
                        "label": "Active",
                        "detail": "Idle sleep prevention is active while OctaMind is running.",
                        "hard_limit": "If Windows enters real sleep or hibernation, Telegram cannot reach OctaMind until the laptop wakes.",
                    }):
                        with patch("src.telegram.pa_poller_manager.get_pa_poller_status", return_value={"running": True}):
                            with patch.object(auto_responder, "_resolve_current_pa", return_value=("pa-1", "Assistant")):
                                auto_responder._handle_status(321)

        assert sent and sent[0][0] == 321
        assert "Sleep protection: Active" in sent[0][1]
        assert "Telegram bot: Running" in sent[0][1]
        assert logged and logged[0]["user_message"] == "/status"
