"""
Unit tests for:
  - src/whatsapp/whatsapp_service.py  (HTTP client layer)
  - src/whatsapp/webhook/message_store.py  (local JSON store)
  - src/whatsapp/whatsapp_auth.py  (credential loading)

All HTTP calls are mocked — no real API required.
All file I/O is redirected to a tmp_path — no real data files touched.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _mock_ok_response(body: dict):
    """Return a mock requests.Response with status 200."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = body
    return resp


def _mock_error_response(status_code: int, error_msg: str = "Bad request"):
    """Return a mock requests.Response that raises on raise_for_status."""
    import requests

    resp = MagicMock()
    resp.json.return_value = {"error": {"message": error_msg}}
    http_err = requests.HTTPError(response=resp)
    resp.raise_for_status.side_effect = http_err
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# whatsapp_auth
# ══════════════════════════════════════════════════════════════════════════════

class TestWhatsAppAuth:
    def test_env_var_takes_precedence_over_settings(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "env_token")
        from src.whatsapp.whatsapp_auth import get_access_token
        assert get_access_token() == "env_token"

    def test_phone_number_id_from_env(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "99999")
        from src.whatsapp.whatsapp_auth import get_phone_number_id
        assert get_phone_number_id() == "99999"

    def test_credentials_configured_returns_false_when_empty(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
        # Patch settings to return empty
        with patch(
            "src.whatsapp.whatsapp_auth._load_settings",
            return_value={},
        ):
            from src.whatsapp.whatsapp_auth import credentials_configured

            assert credentials_configured() is False

    def test_credentials_configured_returns_true_when_set(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "tok")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
        from src.whatsapp.whatsapp_auth import credentials_configured

        assert credentials_configured() is True


# ══════════════════════════════════════════════════════════════════════════════
# whatsapp_service — _unwrap
# ══════════════════════════════════════════════════════════════════════════════

class TestUnwrap:
    def test_returns_json_on_success(self):
        from src.whatsapp.whatsapp_service import _unwrap

        resp = _mock_ok_response({"messages": [{"id": "abc"}]})
        result = _unwrap(resp)
        assert result["messages"][0]["id"] == "abc"

    def test_raises_runtime_error_on_http_error(self):
        from src.whatsapp.whatsapp_service import _unwrap

        resp = _mock_error_response(400, "Invalid phone number")
        with pytest.raises(RuntimeError, match="Invalid phone number"):
            _unwrap(resp)

    def test_error_message_extracted_from_body(self):
        from src.whatsapp.whatsapp_service import _unwrap

        resp = _mock_error_response(401, "Access token expired")
        with pytest.raises(RuntimeError, match="Access token expired"):
            _unwrap(resp)


# ══════════════════════════════════════════════════════════════════════════════
# whatsapp_service — send_text
# ══════════════════════════════════════════════════════════════════════════════

class TestSendText:
    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="fake_token")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="12345")
    def test_sends_to_correct_url(self, mock_pid, mock_tok, mock_post):
        from src.whatsapp.whatsapp_service import send_text

        mock_post.return_value = _mock_ok_response(
            {"messages": [{"id": "wamid.001"}]}
        )
        send_text("919876543210", "Hello")

        url = mock_post.call_args[0][0]
        assert "12345/messages" in url

    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="t")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="1")
    def test_payload_contains_recipient_and_body(self, _pid, _tok, mock_post):
        from src.whatsapp.whatsapp_service import send_text

        mock_post.return_value = _mock_ok_response({"messages": [{"id": "x"}]})
        send_text("919876543210", "Test message")

        payload = mock_post.call_args[1]["json"]
        assert payload["to"] == "919876543210"
        assert payload["text"]["body"] == "Test message"
        assert payload["type"] == "text"

    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="t")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="1")
    def test_returns_message_id(self, _pid, _tok, mock_post):
        from src.whatsapp.whatsapp_service import send_text

        mock_post.return_value = _mock_ok_response(
            {"messages": [{"id": "wamid.XYZ"}]}
        )
        result = send_text("1234567890", "hi")
        assert result["messages"][0]["id"] == "wamid.XYZ"

    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="t")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="1")
    def test_raises_on_api_error(self, _pid, _tok, mock_post):
        from src.whatsapp.whatsapp_service import send_text

        mock_post.return_value = _mock_error_response(400, "Phone number invalid")
        with pytest.raises(RuntimeError, match="Phone number invalid"):
            send_text("invalid", "hi")

    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="tok")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="1")
    def test_auth_header_uses_bearer_token(self, _pid, _tok, mock_post):
        from src.whatsapp.whatsapp_service import send_text

        mock_post.return_value = _mock_ok_response({"messages": [{"id": "x"}]})
        send_text("1", "hi")
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer tok"


# ══════════════════════════════════════════════════════════════════════════════
# whatsapp_service — send_media_message
# ══════════════════════════════════════════════════════════════════════════════

class TestSendMediaMessage:
    def test_raises_if_no_link_or_media_id(self):
        from src.whatsapp.whatsapp_service import send_media_message

        with pytest.raises(ValueError, match="Either link or media_id"):
            send_media_message("919876543210", "image")

    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="t")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="1")
    def test_payload_includes_media_link(self, _pid, _tok, mock_post):
        from src.whatsapp.whatsapp_service import send_media_message

        mock_post.return_value = _mock_ok_response({"messages": [{"id": "m1"}]})
        send_media_message(
            "919876543210", "image", link="https://example.com/photo.jpg", caption="pic"
        )
        payload = mock_post.call_args[1]["json"]
        assert payload["type"] == "image"
        assert payload["image"]["link"] == "https://example.com/photo.jpg"
        assert payload["image"]["caption"] == "pic"

    @patch("src.whatsapp.whatsapp_service.requests.post")
    @patch("src.whatsapp.whatsapp_service.get_access_token", return_value="t")
    @patch("src.whatsapp.whatsapp_service.get_phone_number_id", return_value="1")
    def test_document_includes_filename(self, _pid, _tok, mock_post):
        from src.whatsapp.whatsapp_service import send_media_message

        mock_post.return_value = _mock_ok_response({"messages": [{"id": "d1"}]})
        send_media_message(
            "1234", "document",
            link="https://example.com/doc.pdf",
            filename="report.pdf",
        )
        payload = mock_post.call_args[1]["json"]
        assert payload["document"]["filename"] == "report.pdf"


# ══════════════════════════════════════════════════════════════════════════════
# message_store — using monkeypatched _DATA_PATH
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=False)
def isolated_store(tmp_path, monkeypatch):
    """Redirect all message-store file I/O to tmp_path."""
    import src.whatsapp.webhook.message_store as ms

    data_file = tmp_path / "whatsapp_messages.json"
    sched_file = tmp_path / "whatsapp_scheduled.json"
    auto_file = tmp_path / "whatsapp_auto_reply.json"

    monkeypatch.setattr(ms, "_DATA_PATH", data_file)
    monkeypatch.setattr(ms, "_SCHEDULED_PATH", sched_file)
    monkeypatch.setattr(ms, "_AUTO_REPLY_PATH", auto_file)
    return tmp_path


class TestMessageStore:
    def test_store_inbound_message_persists(self, isolated_store):
        from src.whatsapp.webhook.message_store import store_inbound_message, _DATA_PATH

        store_inbound_message("wamid.001", "919876543210", "text", "Hello")
        data = json.loads(_DATA_PATH.read_text())
        assert len(data["messages"]) == 1
        assert data["messages"][0]["body"] == "Hello"
        assert data["messages"][0]["direction"] == "inbound"

    def test_store_inbound_creates_contact(self, isolated_store):
        from src.whatsapp.webhook.message_store import store_inbound_message, _DATA_PATH

        store_inbound_message(
            "wamid.002", "919111111111", "text", "Hi",
            sender_name="Alice",
        )
        data = json.loads(_DATA_PATH.read_text())
        contact = data["contacts"].get("919111111111")
        assert contact is not None
        assert contact["name"] == "Alice"
        assert contact["message_count"] == 1

    def test_store_inbound_increments_message_count(self, isolated_store):
        from src.whatsapp.webhook.message_store import store_inbound_message, _DATA_PATH

        for i in range(3):
            store_inbound_message(f"id{i}", "9191", "text", "msg")
        data = json.loads(_DATA_PATH.read_text())
        assert data["contacts"]["9191"]["message_count"] == 3

    def test_store_outbound_message_has_outbound_direction(self, isolated_store):
        from src.whatsapp.webhook.message_store import store_outbound_message, _DATA_PATH

        store_outbound_message("919876543210", "Bye")
        data = json.loads(_DATA_PATH.read_text())
        assert data["messages"][0]["direction"] == "outbound"
        assert data["messages"][0]["to"] == "919876543210"

    def test_get_all_messages_newest_first(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            get_all_messages,
        )

        store_inbound_message("id1", "1", "text", "first",
                              timestamp="2025-01-01T10:00:00")
        store_inbound_message("id2", "1", "text", "second",
                              timestamp="2025-01-02T10:00:00")

        msgs = get_all_messages(limit=10)
        assert msgs[0]["body"] == "second"
        assert msgs[1]["body"] == "first"

    def test_get_unread_messages_filters_correctly(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            store_outbound_message,
            get_unread_messages,
        )

        store_inbound_message("in1", "1", "text", "unread msg")
        store_outbound_message("2", "sent msg")  # outbound — should NOT appear

        unread = get_unread_messages()
        assert len(unread) == 1
        assert unread[0]["body"] == "unread msg"

    def test_mark_message_read_sets_flag(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            mark_message_read,
            get_unread_messages,
        )

        store_inbound_message("msg001", "123", "text", "hello")
        mark_message_read("msg001")

        unread = get_unread_messages()
        assert all(m["id"] != "msg001" for m in unread)

    def test_get_messages_for_contact(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            store_outbound_message,
            get_messages_for_contact,
        )

        store_inbound_message("a1", "919001", "text", "Hi from them")
        store_outbound_message("919001", "Hi back")
        store_inbound_message("b1", "999999", "text", "Other contact")

        msgs = get_messages_for_contact("919001")
        assert len(msgs) == 2
        assert all(
            m.get("from") == "919001" or m.get("to") == "919001" for m in msgs
        )

    def test_update_contact_name(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            update_contact_name,
            get_contact,
        )

        store_inbound_message("c1", "919002", "text", "Hello")
        update_contact_name("919002", "Bob")

        contact = get_contact("919002")
        assert contact["name"] == "Bob"

    def test_search_messages_finds_by_body(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            search_messages,
        )

        store_inbound_message("s1", "1", "text", "invoice due tomorrow")
        store_inbound_message("s2", "1", "text", "random stuff")

        results = search_messages("invoice")
        assert len(results) == 1
        assert "invoice" in results[0]["body"]

    def test_search_messages_case_insensitive(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            search_messages,
        )

        store_inbound_message("s3", "1", "text", "INVOICE")
        results = search_messages("invoice")
        assert len(results) >= 1

    def test_inbound_group_message_stored(self, isolated_store):
        from src.whatsapp.webhook.message_store import store_inbound_message, _DATA_PATH

        store_inbound_message(
            "g1", "919001", "text", "Group hello", group_id="grp123"
        )
        data = json.loads(_DATA_PATH.read_text())
        assert "grp123" in data["groups"]
        assert "919001" in data["groups"]["grp123"]["participants"]

    def test_get_message_count_structure(self, isolated_store):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message,
            store_outbound_message,
            get_message_count,
        )

        store_inbound_message("c1", "1", "text", "in1")
        store_inbound_message("c2", "2", "text", "in2")
        store_outbound_message("1", "out1")

        counts = get_message_count()
        assert counts["total"] == 3
        assert counts["inbound"] == 2
        assert counts["outbound"] == 1
        assert counts["unread"] == 2  # both inbound are unread
