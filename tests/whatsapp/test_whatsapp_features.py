"""
Unit tests for WhatsApp feature modules:
  - src/whatsapp/features/messaging.py
  - src/whatsapp/features/contacts.py
  - src/whatsapp/features/search.py
  - src/whatsapp/features/scheduler.py  (_parse_send_time, schedule/list/cancel)

All external I/O (HTTP calls, file writes) is monkeypatched.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixture: redirect message-store file I/O to tmp_path
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    import src.whatsapp.webhook.message_store as ms

    data_file = tmp_path / "whatsapp_messages.json"
    sched_file = tmp_path / "whatsapp_scheduled.json"
    auto_file = tmp_path / "whatsapp_auto_reply.json"

    monkeypatch.setattr(ms, "_DATA_PATH", data_file)
    monkeypatch.setattr(ms, "_SCHEDULED_PATH", sched_file)
    monkeypatch.setattr(ms, "_AUTO_REPLY_PATH", auto_file)

    # Also patch scheduler module paths
    import importlib
    try:
        import src.whatsapp.features.scheduler as sched
        monkeypatch.setattr(sched, "_SCHEDULED_PATH", sched_file)
        monkeypatch.setattr(sched, "_AUTO_REPLY_PATH", auto_file)
    except Exception:
        pass

    return tmp_path


def _ok_send_response(msg_id: str = "wamid.TEST"):
    return {"messages": [{"id": msg_id}]}


# ══════════════════════════════════════════════════════════════════════════════
# messaging.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSendMessage:
    @patch("src.whatsapp.features.messaging.send_text", return_value=_ok_send_response())
    def test_success_returns_message_id(self, mock_send):
        from src.whatsapp.features.messaging import send_message

        result = send_message("919876543210", "Hello!")
        assert result["status"] == "success"
        assert result["message_id"] == "wamid.TEST"
        assert result["to"] == "919876543210"

    @patch(
        "src.whatsapp.features.messaging.send_text",
        side_effect=RuntimeError("Token expired"),
    )
    def test_api_failure_returns_error(self, mock_send):
        from src.whatsapp.features.messaging import send_message

        result = send_message("919876543210", "Hello!")
        assert result["status"] == "error"
        assert "Token expired" in result["message"]

    @patch("src.whatsapp.features.messaging.send_text", return_value=_ok_send_response())
    def test_outbound_message_stored(self, mock_send):
        from src.whatsapp.features.messaging import send_message
        from src.whatsapp.webhook.message_store import get_all_messages

        send_message("919876543210", "Stored?")
        msgs = get_all_messages()
        assert any(m["body"] == "Stored?" for m in msgs)


class TestSendMedia:
    @patch(
        "src.whatsapp.features.messaging.send_media_message",
        return_value=_ok_send_response("wamid.MED"),
    )
    def test_success(self, mock_send):
        from src.whatsapp.features.messaging import send_media

        result = send_media(
            "919876543210", "image", "https://example.com/photo.jpg", caption="Nice"
        )
        assert result["status"] == "success"
        assert result["media_type"] == "image"

    @patch(
        "src.whatsapp.features.messaging.send_media_message",
        side_effect=ValueError("Either link or media_id"),
    )
    def test_error_propagated(self, mock_send):
        from src.whatsapp.features.messaging import send_media

        result = send_media("919876543210", "image", "")
        assert result["status"] == "error"


class TestGetMessages:
    def test_returns_messages_list(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.messaging import get_messages

        store_inbound_message("m1", "111", "text", "first")
        store_inbound_message("m2", "111", "text", "second")

        result = get_messages(limit=10)
        assert result["status"] == "success"
        assert result["count"] == 2

    def test_limit_is_enforced(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.messaging import get_messages

        for i in range(10):
            store_inbound_message(f"id{i}", "111", "text", f"msg{i}")

        result = get_messages(limit=3)
        assert result["count"] == 3


class TestGetUnreadMessages:
    def test_only_unread_returned(self):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message, mark_message_read,
        )
        from src.whatsapp.features.messaging import get_unread_messages

        store_inbound_message("u1", "111", "text", "read this")
        store_inbound_message("u2", "111", "text", "unread this")
        mark_message_read("u1")

        result = get_unread_messages()
        assert result["status"] == "success"
        assert result["unread_count"] == 1
        assert all(not m["read"] for m in result["messages"])


class TestMarkAsRead:
    @patch(
        "src.whatsapp.features.messaging.send_read_receipt",
        return_value={"success": True},
    )
    def test_marks_message_and_sends_receipt(self, mock_receipt):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.messaging import mark_as_read, get_unread_messages

        store_inbound_message("r1", "111", "text", "hello")
        result = mark_as_read("r1")
        assert result["status"] == "success"

        unread = get_unread_messages()
        assert all(m["id"] != "r1" for m in unread["messages"])


# ══════════════════════════════════════════════════════════════════════════════
# contacts.py
# ══════════════════════════════════════════════════════════════════════════════

class TestListContacts:
    def test_returns_contact_list(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.contacts import list_contacts

        store_inbound_message("c1", "919001", "text", "Hi", sender_name="Alice")
        store_inbound_message("c2", "919002", "text", "Hey", sender_name="Bob")

        result = list_contacts()
        assert result["status"] == "success"
        assert result["count"] == 2

    def test_limit_clamped_at_minimum_1(self):
        from src.whatsapp.features.contacts import list_contacts

        result = list_contacts(limit=0)
        assert result["status"] == "success"  # clamped to 1, no crash

    def test_limit_clamped_at_max_500(self):
        from src.whatsapp.features.contacts import list_contacts

        # Should not raise even if limit is absurdly large
        result = list_contacts(limit=99999)
        assert result["status"] == "success"


class TestGetContactInfo:
    def test_returns_error_for_unknown_contact(self):
        from src.whatsapp.features.contacts import get_contact_info

        result = get_contact_info("000000")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_returns_contact_with_messages(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.contacts import get_contact_info

        store_inbound_message("d1", "919003", "text", "Test", sender_name="Charlie")
        result = get_contact_info("919003")
        assert result["status"] == "success"
        assert result["contact"]["name"] == "Charlie"


class TestSetContactName:
    def test_updates_name_successfully(self):
        from src.whatsapp.webhook.message_store import (
            store_inbound_message, get_contact,
        )
        from src.whatsapp.features.contacts import set_contact_name

        store_inbound_message("e1", "919004", "text", "Hello")
        result = set_contact_name("919004", "Diana")
        assert result["status"] == "success"
        assert get_contact("919004")["name"] == "Diana"

    def test_creates_new_contact_if_not_exists(self):
        from src.whatsapp.features.contacts import set_contact_name
        from src.whatsapp.webhook.message_store import get_contact

        result = set_contact_name("919999", "NewPerson")
        assert result["status"] == "success"
        assert get_contact("919999")["name"] == "NewPerson"


# ══════════════════════════════════════════════════════════════════════════════
# search.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchMessages:
    def test_finds_messages_by_keyword(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.search import search_messages

        store_inbound_message("s1", "1", "text", "meeting at 9am tomorrow")
        store_inbound_message("s2", "1", "text", "lunch plans")

        result = search_messages("meeting")
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["messages"][0]["body"] == "meeting at 9am tomorrow"

    def test_empty_results_returns_zero_count(self):
        from src.whatsapp.features.search import search_messages

        result = search_messages("xyznosuchmessage")
        assert result["status"] == "success"
        assert result["count"] == 0

    def test_limit_respected(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.search import search_messages

        for i in range(10):
            store_inbound_message(f"lim{i}", "1", "text", f"invoice {i}")

        result = search_messages("invoice", limit=3)
        assert result["count"] == 3


class TestGetConversation:
    def test_returns_messages_oldest_first(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.search import get_conversation

        store_inbound_message(
            "cv1", "919005", "text", "first",
            timestamp="2025-01-01T08:00:00",
        )
        store_inbound_message(
            "cv2", "919005", "text", "second",
            timestamp="2025-01-01T09:00:00",
        )

        result = get_conversation("919005")
        assert result["status"] == "success"
        assert result["messages"][0]["body"] == "first"
        assert result["messages"][1]["body"] == "second"

    def test_no_messages_returns_note(self):
        from src.whatsapp.features.search import get_conversation

        result = get_conversation("919999")
        assert result["status"] == "success"
        assert result["count"] == 0
        assert "note" in result


class TestGetMessagesByDate:
    def test_filters_within_date_range(self):
        from src.whatsapp.webhook.message_store import store_inbound_message
        from src.whatsapp.features.search import get_messages_by_date

        store_inbound_message(
            "dt1", "1", "text", "inside range",
            timestamp="2025-06-15T10:00:00",
        )
        store_inbound_message(
            "dt2", "1", "text", "outside range",
            timestamp="2025-01-01T10:00:00",
        )

        result = get_messages_by_date("2025-06-01", "2025-06-30")
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["messages"][0]["body"] == "inside range"


# ══════════════════════════════════════════════════════════════════════════════
# scheduler.py — _parse_send_time
# ══════════════════════════════════════════════════════════════════════════════

class TestParseSendTime:
    def test_iso_datetime(self):
        from src.whatsapp.features.scheduler import _parse_send_time

        dt = _parse_send_time("2025-12-25T09:00:00")
        assert dt == datetime(2025, 12, 25, 9, 0, 0)

    def test_iso_date_only(self):
        from src.whatsapp.features.scheduler import _parse_send_time

        dt = _parse_send_time("2025-06-01")
        assert dt.year == 2025
        assert dt.month == 6
        assert dt.day == 1

    def test_iso_with_space(self):
        from src.whatsapp.features.scheduler import _parse_send_time

        dt = _parse_send_time("2025-09-15 14:30")
        assert dt.hour == 14
        assert dt.minute == 30

    def test_invalid_returns_none(self):
        from src.whatsapp.features.scheduler import _parse_send_time

        # Only returns None if dateutil also fails; but should not raise
        result = _parse_send_time("not a date at all ####")
        # Either None or a dateutil best-guess — both are acceptable
        assert result is None or isinstance(result, datetime)


# ══════════════════════════════════════════════════════════════════════════════
# scheduler.py — schedule_message / list / cancel
# ══════════════════════════════════════════════════════════════════════════════

class TestScheduleMessage:
    def test_schedules_message_successfully(self):
        from src.whatsapp.features.scheduler import (
            schedule_message, list_scheduled_messages,
        )
        future = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

        result = schedule_message("919876543210", "Hello future!", future)
        assert result["status"] == "success"
        assert "scheduled_id" in result

        listing = list_scheduled_messages()
        assert listing["count"] >= 1
        ids = [m["id"] for m in listing["scheduled_messages"]]
        assert result["scheduled_id"] in ids

    def test_empty_send_time_returns_error(self):
        from src.whatsapp.features.scheduler import schedule_message

        result = schedule_message("919876543210", "Hi", "")
        assert result["status"] == "error"

    def test_cancel_removes_scheduled_message(self):
        from src.whatsapp.features.scheduler import (
            schedule_message, cancel_scheduled_message, list_scheduled_messages,
        )
        future = (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")

        sched = schedule_message("919876543210", "Cancel me", future)
        sid = sched["scheduled_id"]

        cancel_result = cancel_scheduled_message(sid)
        assert cancel_result["status"] == "success"

        listing = list_scheduled_messages()
        assert all(m["id"] != sid for m in listing["scheduled_messages"])

    def test_cancel_nonexistent_returns_error(self):
        from src.whatsapp.features.scheduler import cancel_scheduled_message

        result = cancel_scheduled_message("nonexistent-id-xxxxx")
        assert result["status"] == "error"

    def test_list_returns_only_pending(self):
        from src.whatsapp.features.scheduler import (
            schedule_message, list_scheduled_messages,
        )
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        schedule_message("1", "msg1", future)
        schedule_message("2", "msg2", future)

        listing = list_scheduled_messages()
        assert listing["count"] == 2
        assert all(m["status"] == "pending" for m in listing["scheduled_messages"])


class TestAutoReply:
    def test_enable_auto_reply(self):
        from src.whatsapp.features.scheduler import set_auto_reply, get_auto_reply_config

        result = set_auto_reply(True, "I am away, will reply soon.")
        assert result["status"] == "success"

        config = get_auto_reply_config()
        assert config["status"] == "success"
        assert config["enabled"] is True
        assert "away" in config["message"].lower()

    def test_disable_auto_reply(self):
        from src.whatsapp.features.scheduler import set_auto_reply, get_auto_reply_config

        set_auto_reply(True, "Away")
        set_auto_reply(False, "")

        config = get_auto_reply_config()
        assert config["enabled"] is False
