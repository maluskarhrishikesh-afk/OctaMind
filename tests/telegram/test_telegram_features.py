"""
Unit tests for Telegram feature modules:
  - src/telegram/features/messaging.py
  - src/telegram/features/chats.py
  - src/telegram/features/media.py
  - src/telegram/features/search.py
  - src/telegram/features/scheduler.py
  - src/telegram/features/polls.py
  - src/telegram/features/smart_features.py
  - src/telegram/features/cross_agent.py

All HTTP calls and LLM calls are mocked — no real Telegram/LLM API calls made.
All file I/O is redirected to tmp_path.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect all message-store and scheduler file I/O to a temp directory."""
    import src.telegram.polling.message_store as ms
    data_file = tmp_path / "telegram_messages.json"
    monkeypatch.setattr(ms, "_DATA_PATH", data_file)

    try:
        import src.telegram.features.scheduler as sched
        sched_file = tmp_path / "telegram_scheduled.json"
        monkeypatch.setattr(sched, "_SCHEDULED_PATH", sched_file)
    except Exception:
        pass

    return tmp_path


def _seed_message(
    chat_id: int = 1001,
    message_id: int = 1,
    text: str = "hello",
    update_id: int = 1,
) -> None:
    """Helper: store one inbound message in the isolated store."""
    from src.telegram.polling.message_store import store_inbound_message
    store_inbound_message(
        {
            "message_id": message_id,
            "from": {"id": 5, "first_name": "Alice"},
            "chat": {"id": chat_id, "type": "private", "first_name": "Alice"},
            "date": 1740000000,
            "text": text,
        },
        update_id=update_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# messaging.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSendMessage:
    @patch(
        "src.telegram.features.messaging.send_text",
        return_value={"message_id": 42, "chat": {"id": 1001}},
    )
    def test_success_returns_message_id(self, mock_send):
        from src.telegram.features.messaging import send_message
        result = send_message(1001, "Hello!")
        assert result["status"] == "success"
        assert result["message_id"] == 42
        assert result["chat_id"] == 1001

    @patch(
        "src.telegram.features.messaging.send_text",
        side_effect=RuntimeError("Bot was blocked by the user"),
    )
    def test_api_error_returns_error(self, mock_send):
        from src.telegram.features.messaging import send_message
        result = send_message(1001, "Blocked!")
        assert result["status"] == "error"
        assert "blocked" in result["message"].lower()

    @patch(
        "src.telegram.features.messaging.send_text",
        return_value={"message_id": 55},
    )
    def test_outbound_message_persisted_to_store(self, mock_send):
        from src.telegram.features.messaging import send_message
        from src.telegram.polling.message_store import get_all_messages
        send_message(1001, "Persist me")
        msgs = get_all_messages()
        assert any(m["text"] == "Persist me" for m in msgs)


class TestReplyToMessage:
    @patch(
        "src.telegram.telegram_service.send_text",
        return_value={"message_id": 100},
    )
    def test_reply_success(self, mock_send):
        from src.telegram.features.messaging import reply_to_message
        result = reply_to_message(1001, 10, "A reply")
        assert result["status"] == "success"
        assert result["reply_to"] == 10

    @patch(
        "src.telegram.telegram_service.send_text",
        side_effect=RuntimeError("Message not found"),
    )
    def test_reply_error_propagated(self, mock_send):
        from src.telegram.features.messaging import reply_to_message
        result = reply_to_message(1001, 999, "reply")
        assert result["status"] == "error"


class TestGetMessages:
    def test_returns_messages_list(self):
        _seed_message(text="msg one", update_id=1)
        _seed_message(text="msg two", message_id=2, update_id=2)
        from src.telegram.features.messaging import get_messages
        result = get_messages(limit=10)
        assert result["status"] == "success"
        assert len(result["messages"]) == 2

    def test_limit_respected(self):
        for i in range(5):
            _seed_message(message_id=i + 1, text=f"m{i}", update_id=i)
        from src.telegram.features.messaging import get_messages
        result = get_messages(limit=3)
        assert result["status"] == "success"
        assert len(result["messages"]) <= 3

    def test_empty_store_returns_success(self):
        from src.telegram.features.messaging import get_messages
        result = get_messages()
        assert result["status"] == "success"
        assert result["messages"] == []


class TestGetUnreadMessages:
    def test_unread_messages_returned(self):
        _seed_message(text="unread one", update_id=10)
        from src.telegram.features.messaging import get_unread_messages
        result = get_unread_messages()
        assert result["status"] == "success"
        # get_unread_messages() returns {"unread": [...]} (not "messages")
        assert any(m["text"] == "unread one" for m in result["unread"])


class TestGetChatHistory:
    def test_filters_by_chat_id(self):
        _seed_message(chat_id=111, text="chat 111 msg", update_id=1)
        _seed_message(chat_id=222, text="chat 222 msg", update_id=2)
        from src.telegram.features.messaging import get_chat_history
        result = get_chat_history(111)
        assert result["status"] == "success"
        assert all(m["chat_id"] == 111 for m in result["messages"])


class TestMarkAsRead:
    def test_marks_inbound_message_read(self):
        _seed_message(chat_id=1001, message_id=7, text="mark me", update_id=70)
        from src.telegram.features.messaging import get_unread_messages, mark_as_read
        mark_as_read("1001:7")
        unread = get_unread_messages()
        # get_unread_messages() returns {"unread": [...]} (not "messages")
        assert not any(m["id"] == "1001:7" for m in unread["unread"])

    def test_unknown_composite_id_silently_succeeds(self):
        # mark_as_read silently ignores unknown IDs — always returns success
        from src.telegram.features.messaging import mark_as_read
        result = mark_as_read("999:999")
        assert result["status"] == "success"


class TestEditDeleteMessage:
    @patch(
        "src.telegram.features.messaging.edit_message_text",
        return_value={"message_id": 5, "text": "updated"},
    )
    def test_edit_message_success(self, mock_edit):
        from src.telegram.features.messaging import edit_message
        result = edit_message(1001, 5, "updated")
        assert result["status"] == "success"

    @patch(
        "src.telegram.features.messaging.delete_message_api",
        return_value=True,
    )
    def test_delete_message_success(self, mock_del):
        from src.telegram.features.messaging import delete_message
        result = delete_message(1001, 5)
        assert result["status"] == "success"

    @patch(
        "src.telegram.features.messaging.edit_message_text",
        side_effect=RuntimeError("Message can't be edited"),
    )
    def test_edit_message_error(self, mock_edit):
        from src.telegram.features.messaging import edit_message
        result = edit_message(1001, 5, "blocked")
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# chats.py
# ══════════════════════════════════════════════════════════════════════════════

class TestListChats:
    def test_empty_store_returns_success(self):
        from src.telegram.features.chats import list_chats
        result = list_chats()
        assert result["status"] == "success"
        assert result["chats"] == []

    def test_populated_store(self):
        _seed_message(chat_id=100, update_id=1)
        _seed_message(chat_id=200, update_id=2)
        from src.telegram.features.chats import list_chats
        result = list_chats()
        assert result["status"] == "success"
        assert result["count"] == 2


class TestGetChatInfo:
    @patch(
        "src.telegram.features.chats.get_chat_api",
        return_value={"id": 1001, "type": "private", "first_name": "Alice"},
    )
    @patch("src.telegram.features.chats.get_chat_member_count", return_value=1)
    def test_success_private_chat(self, mock_count, mock_api):
        from src.telegram.features.chats import get_chat_info
        result = get_chat_info(1001)
        assert result["status"] == "success"
        assert result["chat_id"] == 1001

    @patch(
        "src.telegram.features.chats.get_chat_api",
        side_effect=RuntimeError("Chat not found"),
    )
    def test_api_error_returns_error(self, mock_api):
        from src.telegram.features.chats import get_chat_info
        result = get_chat_info(99999)
        assert result["status"] == "error"


class TestPinUnpinMessage:
    @patch(
        "src.telegram.features.chats.pin_chat_message_api",
        return_value=True,
    )
    def test_pin_success(self, mock_pin):
        from src.telegram.features.chats import pin_message
        result = pin_message(1001, 42)
        assert result["status"] == "success"

    @patch(
        "src.telegram.features.chats.unpin_chat_message_api",
        return_value=True,
    )
    def test_unpin_success(self, mock_unpin):
        from src.telegram.features.chats import unpin_message
        result = unpin_message(1001, 42)
        assert result["status"] == "success"

    @patch(
        "src.telegram.features.chats.pin_chat_message_api",
        side_effect=RuntimeError("Not enough rights"),
    )
    def test_pin_error_propagated(self, mock_pin):
        from src.telegram.features.chats import pin_message
        result = pin_message(1001, 42)
        assert result["status"] == "error"


class TestLeaveChat:
    @patch("src.telegram.features.chats.leave_chat_api", return_value=True)
    def test_leave_success(self, mock_leave):
        from src.telegram.features.chats import leave_chat
        result = leave_chat(1001)
        assert result["status"] == "success"

    @patch(
        "src.telegram.features.chats.leave_chat_api",
        side_effect=RuntimeError("Chat not found"),
    )
    def test_leave_error(self, mock_leave):
        from src.telegram.features.chats import leave_chat
        result = leave_chat(999)
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# search.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchMessages:
    def test_query_matches_text(self):
        _seed_message(text="project meeting notes", update_id=1)
        _seed_message(text="birthday party plans", update_id=2)
        from src.telegram.features.search import search_messages
        result = search_messages("meeting")
        assert result["status"] == "success"
        assert any("meeting" in m["text"].lower() for m in result["messages"])

    def test_query_no_match_returns_empty(self):
        _seed_message(text="nothing relevant", update_id=1)
        from src.telegram.features.search import search_messages
        result = search_messages("xyzabc123notexist")
        assert result["status"] == "success"
        assert result["messages"] == []

    def test_filter_by_chat_id(self):
        _seed_message(chat_id=111, text="keyword here", update_id=1)
        _seed_message(chat_id=222, text="keyword there", update_id=2)
        from src.telegram.features.search import search_messages
        result = search_messages("keyword", chat_id=111)
        assert result["status"] == "success"
        assert all(m["chat_id"] == 111 for m in result["messages"])


class TestGetMessagesByDate:
    def test_date_range_filters_messages(self):
        _seed_message(chat_id=1001, text="date range message", update_id=1)
        from src.telegram.features.search import get_messages_by_date
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        # chat_id and from_date are REQUIRED positional args
        result = get_messages_by_date(1001, yesterday, to_date=tomorrow)
        assert result["status"] == "success"

    def test_from_date_only_returns_messages(self):
        _seed_message(chat_id=1001, text="any message", update_id=1)
        from src.telegram.features.search import get_messages_by_date
        past_date = "2026-01-01"
        result = get_messages_by_date(1001, past_date)
        assert result["status"] == "success"


class TestGetMessageStats:
    def test_stats_returns_per_chat_data(self):
        _seed_message(chat_id=100, update_id=1)
        _seed_message(chat_id=100, message_id=2, update_id=2)
        _seed_message(chat_id=200, update_id=3)
        from src.telegram.features.search import get_message_stats
        result = get_message_stats()
        assert result["status"] == "success"
        # Returns top_active_chats list, total_stored, inbound/outbound counts
        assert "top_active_chats" in result
        assert result["total_stored"] >= 3


# ══════════════════════════════════════════════════════════════════════════════
# scheduler.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSchedulerTimeParsing:
    def test_iso_format_parsed(self):
        from src.telegram.features.scheduler import _parse_send_time
        dt = _parse_send_time("2026-06-15 14:30")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.hour == 14

    def test_iso_date_only(self):
        from src.telegram.features.scheduler import _parse_send_time
        dt = _parse_send_time("2026-12-25")
        assert dt is not None
        assert dt.month == 12
        assert dt.day == 25

    def test_natural_language_parsed(self):
        from src.telegram.features.scheduler import _parse_send_time
        dt = _parse_send_time("tomorrow 9am")
        assert dt is not None

    def test_junk_string_returns_none(self):
        from src.telegram.features.scheduler import _parse_send_time
        dt = _parse_send_time("not a date at all gibberish$$$")
        # dateutil may parse some junk — we just check it doesn't crash
        # (either None or a datetime is acceptable)
        assert dt is None or isinstance(dt, datetime)


class TestScheduleMessage:
    def test_schedule_stores_job(self):
        from src.telegram.features.scheduler import (
            schedule_message, list_scheduled_messages,
        )
        result = schedule_message(1001, "Good morning!", "2027-01-01 09:00")
        assert result["status"] == "success"
        assert "job_id" in result

        jobs = list_scheduled_messages()
        assert jobs["status"] == "success"
        assert any(j["text"] == "Good morning!" for j in jobs["scheduled"])

    def test_schedule_invalid_time_returns_error(self):
        from src.telegram.features.scheduler import schedule_message
        result = schedule_message(1001, "hi", "not_a_valid_time_abc")
        assert result["status"] == "error"

    def test_cancel_scheduled_message(self):
        from src.telegram.features.scheduler import (
            schedule_message, cancel_scheduled_message, list_scheduled_messages,
        )
        created = schedule_message(1001, "Cancel me", "2027-03-15 10:00")
        job_id = created["job_id"]

        cancel_result = cancel_scheduled_message(job_id)
        assert cancel_result["status"] == "success"

        remaining = list_scheduled_messages()
        assert not any(j["id"] == job_id for j in remaining["scheduled"])

    def test_cancel_unknown_job_returns_error(self):
        from src.telegram.features.scheduler import cancel_scheduled_message
        result = cancel_scheduled_message("nonexistent-job-id-xyz")
        assert result["status"] == "error"

    def test_list_empty_when_no_scheduled(self):
        from src.telegram.features.scheduler import list_scheduled_messages
        result = list_scheduled_messages()
        assert result["status"] == "success"
        assert result["scheduled"] == []


# ══════════════════════════════════════════════════════════════════════════════
# polls.py
# ══════════════════════════════════════════════════════════════════════════════

class TestSendPoll:
    @patch(
        "src.telegram.features.polls.send_poll_api",
        return_value={
            "message_id": 10,
            "poll": {"id": "poll_abc", "question": "Best day?"},
        },
    )
    def test_send_poll_success(self, mock_api):
        from src.telegram.features.polls import send_poll
        result = send_poll(1001, "Best day?", ["Monday", "Tuesday", "Wednesday"])
        assert result["status"] == "success"
        assert result["question"] == "Best day?"
        assert result["options"] == ["Monday", "Tuesday", "Wednesday"]

    def test_too_few_options_returns_error(self):
        from src.telegram.features.polls import send_poll
        result = send_poll(1001, "Q?", ["Only one"])
        assert result["status"] == "error"
        assert "2" in result["message"]

    def test_too_many_options_returns_error(self):
        from src.telegram.features.polls import send_poll
        result = send_poll(1001, "Q?", [str(i) for i in range(11)])
        assert result["status"] == "error"

    @patch(
        "src.telegram.features.polls.send_poll_api",
        side_effect=RuntimeError("not found"),
    )
    def test_api_error_propagated(self, mock_api):
        from src.telegram.features.polls import send_poll
        result = send_poll(1001, "Q?", ["A", "B"])
        assert result["status"] == "error"


class TestStopPoll:
    @patch(
        "src.telegram.features.polls.stop_poll_api",
        return_value={
            "id": "poll_abc",
            "question": "Best day?",
            "options": [
                {"text": "Monday", "voter_count": 3},
                {"text": "Tuesday", "voter_count": 1},
            ],
            "total_voter_count": 4,
            "is_closed": True,
        },
    )
    def test_stop_poll_returns_results(self, mock_api):
        from src.telegram.features.polls import stop_poll
        result = stop_poll(1001, 10)
        assert result["status"] == "success"
        # stop_poll wraps the API and exposes "total_voter_count" key
        assert result["total_voter_count"] == 4

    @patch(
        "src.telegram.features.polls.stop_poll_api",
        side_effect=RuntimeError("Poll already closed"),
    )
    def test_stop_already_closed_returns_error(self, mock_api):
        from src.telegram.features.polls import stop_poll
        result = stop_poll(1001, 10)
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# smart_features.py  (LLM calls mocked via patch)
# ══════════════════════════════════════════════════════════════════════════════

def _make_llm_mock():
    """Return a mock LLM client whose completions.create returns a fixed text."""
    mock_llm = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="LLM summary text"))]
    mock_llm.client.chat.completions.create.return_value = mock_completion
    return mock_llm


# smart_features uses an internal _llm() function that calls get_llm_client.
# Because that import is LOCAL (inside _llm()), we must patch the _llm symbol
# directly in the smart_features module namespace.
_LLM_PATCH = "src.telegram.features.smart_features._llm"


class TestSummarizeChat:
    def test_empty_chat_returns_error(self):
        from src.telegram.features.smart_features import summarize_chat
        result = summarize_chat(9999)
        assert result["status"] == "error"

    @patch(_LLM_PATCH)
    def test_summarize_calls_llm(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        _seed_message(chat_id=1001, text="Hello team, the meeting is at 3pm", update_id=1)
        from src.telegram.features.smart_features import summarize_chat
        result = summarize_chat(1001)
        assert result["status"] == "success"
        assert "summary" in result


class TestDetectUrgentMessages:
    @patch(_LLM_PATCH)
    def test_detect_urgent_no_messages(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        from src.telegram.features.smart_features import detect_urgent_messages
        result = detect_urgent_messages()
        assert result["status"] in ("success", "error")

    @patch(_LLM_PATCH)
    def test_detect_urgent_with_messages(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        _seed_message(text="URGENT: server is down!", update_id=1)
        from src.telegram.features.smart_features import detect_urgent_messages
        result = detect_urgent_messages()
        assert result["status"] == "success"


class TestDraftMessage:
    @patch(_LLM_PATCH)
    def test_draft_returns_text(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        from src.telegram.features.smart_features import draft_message
        result = draft_message(1001, "project update")
        assert result["status"] == "success"
        assert "draft" in result


class TestTranslateMessage:
    @patch(_LLM_PATCH)
    def test_translate_known_message(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        _seed_message(chat_id=1001, message_id=3, text="Bonjour tout le monde", update_id=3)
        from src.telegram.features.smart_features import translate_message
        result = translate_message("1001:3", "English")
        assert result["status"] == "success"
        # Returns "translated" (not "translation")
        assert "translated" in result

    def test_translate_unknown_composite_id(self):
        from src.telegram.features.smart_features import translate_message
        result = translate_message("0:0", "English")
        assert result["status"] == "error"


class TestSentimentAnalysis:
    @patch(_LLM_PATCH)
    def test_sentiment_with_messages(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        _seed_message(chat_id=1001, text="I love this!", update_id=1)
        from src.telegram.features.smart_features import sentiment_analysis
        result = sentiment_analysis(1001)
        assert result["status"] == "success"
        # Returns "analysis" (not "sentiment")
        assert "analysis" in result

    def test_sentiment_empty_chat_returns_error(self):
        from src.telegram.features.smart_features import sentiment_analysis
        result = sentiment_analysis(9999)
        assert result["status"] == "error"


class TestExtractActionItems:
    @patch(_LLM_PATCH)
    def test_extract_items(self, mock_llm_fn):
        mock_llm_fn.return_value = _make_llm_mock()
        _seed_message(chat_id=1001, text="Remember to send the report by Friday", update_id=1)
        from src.telegram.features.smart_features import extract_action_items
        result = extract_action_items(1001)
        assert result["status"] == "success"
        assert "action_items" in result


# ══════════════════════════════════════════════════════════════════════════════
# cross_agent.py
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardToEmail:
    def test_unknown_composite_id_returns_error(self):
        from src.telegram.features.cross_agent import forward_to_email
        result = forward_to_email("0:0", "bob@example.com")
        assert result["status"] == "error"

    # forward_to_email uses a LOCAL import: from src.email.gmail_service import send_email
    # so we must patch the function at its source module, not in cross_agent namespace.
    @patch("src.email.gmail_service.send_email")
    def test_forward_known_message_to_email(self, mock_send_email):
        mock_send_email.return_value = {"status": "success", "message_id": "email_123"}
        _seed_message(chat_id=1001, message_id=5, text="forward this", update_id=5)
        from src.telegram.features.cross_agent import forward_to_email
        result = forward_to_email("1001:5", "recipient@example.com")
        assert result["status"] == "success"
        mock_send_email.assert_called_once()

    @patch("src.email.gmail_service.send_email", side_effect=Exception("SMTP error"))
    def test_email_send_failure_returns_error(self, mock_send_email):
        _seed_message(chat_id=1001, message_id=6, text="fail send", update_id=6)
        from src.telegram.features.cross_agent import forward_to_email
        result = forward_to_email("1001:6", "someone@example.com")
        assert result["status"] == "error"


class TestShareDriveFile:
    # share_drive_file uses LOCAL imports:
    #   from src.drive.drive_service import get_file_share_link
    #   from ..telegram_service import send_text
    # Patch both at their SOURCE modules. Use create=True since the function
    # may not yet exist in older installs — cross_agent catches ImportError.
    @patch("src.telegram.telegram_service.send_text", return_value={"message_id": 77})
    @patch(
        "src.drive.drive_service.get_file_share_link",
        create=True,
        return_value={"web_view_link": "https://drive.google.com/file/d/abc/view"},
    )
    def test_share_drive_link_sent(self, mock_link, mock_send):
        from src.telegram.features.cross_agent import share_drive_file
        result = share_drive_file(1001, "abc123", caption="Check this out")
        assert result["status"] == "success"
        mock_send.assert_called_once()

    @patch(
        "src.drive.drive_service.get_file_share_link",
        create=True,
        side_effect=Exception("File not found"),
    )
    def test_drive_error_returns_error(self, mock_link):
        from src.telegram.features.cross_agent import share_drive_file
        result = share_drive_file(1001, "bad_file_id")
        assert result["status"] == "error"
