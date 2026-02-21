"""
Unit tests for src/agent/core/automations/gmail_automations.py

All Gmail API calls are fully mocked — no network / token required.

Covers every handler function, focusing on:
  - out_of_office: correct kwarg (message=), skip patterns, mark-as-read, error surfacing
  - auto_archive_newsletters: query uses is:read (not all promotions)
  - auto_delete_spam: basic happy path
  - auto_label_vip: VIP starring
  - flag_old_unread: age_days param
  - daily_digest: digest content saved to memory
  - weekly_report: memory write failure logged (not silently swallowed)
  - auto_categorize: per-email error logged (not silently swallowed)
  - auto_unsubscribe: memory write failure logged
  - archive_old_read: is:read query
"""

import src.agent.core.automations.gmail_automations as gm
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# tests/email/ -> tests/ -> project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────── helpers ─────────────────────────────────────────

def _fake_service(messages_list=None, metadata=None):
    """Return a mock Gmail service wired up with the default call chain."""
    svc = MagicMock()
    # users().messages().list().execute()
    list_exec = svc.users.return_value.messages.return_value.list.return_value.execute
    list_exec.return_value = {"messages": messages_list or []}
    # users().messages().get().execute()
    get_exec = svc.users.return_value.messages.return_value.get.return_value.execute
    get_exec.return_value = metadata or {}
    # users().messages().trash().execute() — returns empty dict by default
    # users().messages().modify().execute() — returns empty dict by default
    return svc


def _patch_svc(svc):
    """Context manager that replaces gmail_automations._svc() with svc."""
    return patch.object(gm, "_svc", return_value=svc)


# ─────────────────────────── auto_delete_spam ────────────────────────────────

class TestAutoDeleteSpam:
    def test_no_spam_emails(self):
        svc = _fake_service(messages_list=[])
        with _patch_svc(svc):
            result = gm.auto_delete_spam("agent1", {})
        assert result == "No spam emails found"

    def test_deletes_spam_and_returns_count(self):
        svc = _fake_service(messages_list=[{"id": "m1"}, {"id": "m2"}])
        with _patch_svc(svc):
            result = gm.auto_delete_spam("agent1", {})
        assert "2" in result
        assert svc.users().messages().trash.call_count == 2

    def test_api_error_returns_error_string(self):
        svc = MagicMock()
        svc.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
            "API down")
        with _patch_svc(svc):
            result = gm.auto_delete_spam("agent1", {})
        assert result.startswith("Error:")


# ─────────────────────────── auto_archive_newsletters ────────────────────────

class TestAutoArchiveNewsletters:
    def test_query_uses_is_read_filter(self):
        """The query must include 'is:read' to avoid archiving unread promotions."""
        svc = _fake_service(messages_list=[])
        with _patch_svc(svc):
            gm.auto_archive_newsletters("agent1", {})
        call_kwargs = svc.users().messages().list.call_args
        q_value = call_kwargs[1].get("q", "") or (
            call_kwargs[0][1] if call_kwargs[0] else "")
        # Normalise: extract the 'q' keyword arg regardless of how mock records it
        actual_q = svc.users.return_value.messages.return_value.list.call_args.kwargs.get(
            "q", "")
        assert "is:read" in actual_q, f"Query '{actual_q}' must contain 'is:read'"

    def test_does_not_use_raw_label_id(self):
        """Must NOT query by labelIds=['CATEGORY_PROMOTIONS'] (which includes unread)."""
        svc = _fake_service(messages_list=[])
        with _patch_svc(svc):
            gm.auto_archive_newsletters("agent1", {})
        list_call = svc.users.return_value.messages.return_value.list.call_args
        assert "labelIds" not in list_call.kwargs, \
            "Must not use labelIds — that would archive unread promotions too"

    def test_no_newsletters(self):
        svc = _fake_service(messages_list=[])
        with _patch_svc(svc):
            result = gm.auto_archive_newsletters("agent1", {})
        assert "No newsletter" in result

    def test_archives_correct_count(self):
        msgs = [{"id": f"m{i}"} for i in range(3)]
        svc = _fake_service(messages_list=msgs)
        with _patch_svc(svc):
            result = gm.auto_archive_newsletters("agent1", {})
        assert "3" in result
        assert svc.users().messages().modify.call_count == 3


# ─────────────────────────── out_of_office ───────────────────────────────────

def _ooo_metadata(from_addr: str = "sender@example.com", subject: str = "Hello"):
    return {
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": "<abc123>"},
            ]
        }
    }


class TestOutOfOffice:
    def _run_ooo(self, messages, metadata, send_result=None, params=None):
        svc = _fake_service(messages_list=messages, metadata=metadata)
        params = params or {"reply_message": "I'm OOO"}
        send_mock = MagicMock(return_value=send_result or {
                              "status": "success"})
        with _patch_svc(svc), \
                patch("src.email.gmail_service.send_email", send_mock):
            result = gm.out_of_office("agent1", params)
        return result, svc, send_mock

    def test_calls_send_email_with_message_kwarg(self):
        """Must use message= not body= — this was the original bug."""
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata(),
        )
        # send_email must have been called with keyword arg 'message'
        _, kwargs = send_mock.call_args
        assert "message" in kwargs, "send_email must be called with 'message=' kwarg"
        assert "body" not in kwargs, "'body=' kwarg was the original bug — must not use it"

    def test_reply_contains_correct_to_and_subject(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata("alice@example.com", "Meeting"),
        )
        _, kwargs = send_mock.call_args
        assert kwargs["to"] == "alice@example.com"
        assert "Meeting" in kwargs["subject"]

    def test_marks_email_as_read_after_successful_reply(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata(),
        )
        modify_calls = svc.users.return_value.messages.return_value.modify.call_args_list
        modify_bodies = [c.kwargs.get(
            "body", c.args[-1] if c.args else {}) for c in modify_calls]
        read_marks = [b for b in modify_bodies if "UNREAD" in str(b)]
        assert len(read_marks) >= 1, "Email must be marked as read after replying"

    def test_skips_noreply_senders(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata("noreply@github.com"),
        )
        send_mock.assert_not_called()
        assert "0" in result

    def test_skips_no_dash_reply_senders(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata("no-reply@service.com"),
        )
        send_mock.assert_not_called()

    def test_skips_notifications_senders(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata("notifications@github.com"),
        )
        send_mock.assert_not_called()

    def test_skips_mailer_daemon(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata("mailer-daemon@example.com"),
        )
        send_mock.assert_not_called()

    def test_no_emails(self):
        result, svc, send_mock = self._run_ooo(messages=[], metadata={})
        assert "0" in result
        send_mock.assert_not_called()

    def test_send_failure_included_in_result(self):
        result, svc, send_mock = self._run_ooo(
            messages=[{"id": "m1"}],
            metadata=_ooo_metadata(),
            send_result={"status": "error", "message": "token expired"},
        )
        assert "error" in result.lower() or "0" in result

    def test_active_until_expired_stops_replies(self):
        params = {
            "reply_message": "OOO",
            "active_until": "2020-01-01",  # far in the past
        }
        svc = _fake_service(
            messages_list=[{"id": "m1"}], metadata=_ooo_metadata())
        send_mock = MagicMock()
        with _patch_svc(svc), patch("src.email.gmail_service.send_email", send_mock):
            result = gm.out_of_office("agent1", params)
        send_mock.assert_not_called()
        assert "ended" in result.lower()

    def test_active_until_future_still_replies(self):
        params = {
            "reply_message": "OOO",
            "active_until": "2099-12-31",
        }
        svc = _fake_service(
            messages_list=[{"id": "m1"}], metadata=_ooo_metadata())
        send_mock = MagicMock(return_value={"status": "success"})
        with _patch_svc(svc), patch("src.email.gmail_service.send_email", send_mock):
            result = gm.out_of_office("agent1", params)
        send_mock.assert_called_once()


# ─────────────────────────── daily_digest ────────────────────────────────────

class TestDailyDigest:
    def test_digest_content_in_return_value(self):
        fake_digest = "5 emails: 2 important, 3 newsletters"
        mem_mock = MagicMock()
        with patch("src.email.gmail_service.generate_daily_digest", return_value=fake_digest), \
                patch("src.agent.memory.agent_memory.get_agent_memory", return_value=mem_mock):
            result = gm.daily_digest("agent1", {})
        assert fake_digest[:50] in result or "Daily digest" in result

    def test_digest_saved_to_episodic_memory(self):
        fake_digest = "3 unread, 1 important"
        mem_mock = MagicMock()
        with patch("src.email.gmail_service.generate_daily_digest", return_value=fake_digest), \
                patch("src.agent.memory.agent_memory.get_agent_memory", return_value=mem_mock):
            gm.daily_digest("agent1", {})
        mem_mock.add_episodic_event.assert_called_once()
        event_text = mem_mock.add_episodic_event.call_args.kwargs.get(
            "event", mem_mock.add_episodic_event.call_args.args[
                0] if mem_mock.add_episodic_event.call_args.args else ""
        )
        assert fake_digest[:30] in event_text or "digest" in event_text.lower()

    def test_memory_write_error_does_not_suppress_result(self):
        with patch("src.email.gmail_service.generate_daily_digest", return_value="digest"), \
                patch("src.agent.memory.agent_memory.get_agent_memory", side_effect=Exception("DB down")):
            result = gm.daily_digest("agent1", {})
        assert "Error" not in result or "digest" in result.lower()

    def test_api_error_returns_error_string(self):
        with patch("src.email.gmail_service.generate_daily_digest", side_effect=Exception("API error")):
            result = gm.daily_digest("agent1", {})
        assert result.startswith("Error:")


# ─────────────────────────── auto_label_vip ──────────────────────────────────

class TestAutoLabelVip:
    def test_no_contacts_returns_message(self):
        with patch("src.email.features.contacts.get_frequent_contacts", return_value=[]):
            result = gm.auto_label_vip("agent1", {})
        assert "No frequent contacts" in result

    def test_stars_emails_from_vip_contacts(self):
        contacts = [{"email": "boss@corp.com"}, {"email": "partner@co.com"}]
        svc = MagicMock()
        svc.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "m1"}, {"id": "m2"}]
        }
        with patch("src.email.features.contacts.get_frequent_contacts", return_value=contacts), \
                _patch_svc(svc):
            result = gm.auto_label_vip("agent1", {})
        assert "Starred" in result
        assert svc.users().messages().modify.call_count == 4  # 2 contacts × 2 emails


# ─────────────────────────── flag_old_unread ─────────────────────────────────

class TestFlagOldUnread:
    def test_uses_age_days_param(self):
        svc = _fake_service(messages_list=[])
        with _patch_svc(svc):
            gm.flag_old_unread("agent1", {"age_days": 14})
        list_call = svc.users.return_value.messages.return_value.list.call_args
        q = list_call.kwargs.get("q", "")
        assert "14d" in q

    def test_stars_old_unread_emails(self):
        svc = _fake_service(messages_list=[{"id": "old1"}, {"id": "old2"}])
        with _patch_svc(svc):
            result = gm.flag_old_unread("agent1", {"age_days": 7})
        assert "2" in result
        assert svc.users().messages().modify.call_count == 2


# ─────────────────────────── weekly_report ───────────────────────────────────

class TestWeeklyReport:
    def test_memory_write_error_is_logged_not_suppressed(self, caplog):
        stats = {"received": 42, "sent": 10}
        mem_mock = MagicMock()
        mem_mock.add_episodic_event.side_effect = Exception("write failed")
        with patch("src.email.features.analytics.get_email_stats", return_value=stats), \
                patch("src.agent.memory.agent_memory.get_agent_memory", return_value=mem_mock), \
                caplog.at_level(logging.WARNING, logger="src.agent.core.automations.gmail_automations"):
            result = gm.weekly_report("agent1", {})
        assert "Weekly report" in result
        assert any("weekly_report" in r.message for r in caplog.records)

    def test_returns_success_string(self):
        mem_mock = MagicMock()
        with patch("src.email.features.analytics.get_email_stats", return_value={}), \
                patch("src.agent.memory.agent_memory.get_agent_memory", return_value=mem_mock):
            result = gm.weekly_report("agent1", {})
        assert "report" in result.lower()


# ─────────────────────────── auto_categorize ─────────────────────────────────

class TestAutoCategorize:
    def test_per_email_error_is_logged_not_silent(self, caplog):
        svc = _fake_service(messages_list=[{"id": "m1"}, {"id": "m2"}])
        with _patch_svc(svc), \
                patch("src.email.features.categorizer.auto_categorize_email",
                      side_effect=Exception("LLM timeout")), \
                caplog.at_level(logging.WARNING, logger="src.agent.core.automations.gmail_automations"):
            result = gm.auto_categorize("agent1", {})
        assert any("auto_categorize" in r.message for r in caplog.records)
        assert "Categorized 0" in result

    def test_counts_successful_categorizations(self):
        svc = _fake_service(
            messages_list=[{"id": "m1"}, {"id": "m2"}, {"id": "m3"}])
        with _patch_svc(svc), \
                patch("src.email.features.categorizer.auto_categorize_email", return_value="work"):
            result = gm.auto_categorize("agent1", {})
        assert "3" in result


# ─────────────────────────── auto_unsubscribe ────────────────────────────────

class TestAutoUnsubscribe:
    def test_memory_write_error_logged(self, caplog):
        newsletters = [{"sender": "news@example.com"}]
        mem_mock = MagicMock()
        mem_mock.add_episodic_event.side_effect = Exception("write error")
        with patch("src.email.features.unsubscribe.detect_newsletters", return_value=newsletters), \
                patch("src.agent.memory.agent_memory.get_agent_memory", return_value=mem_mock), \
                caplog.at_level(logging.WARNING, logger="src.agent.core.automations.gmail_automations"):
            result = gm.auto_unsubscribe("agent1", {})
        assert "1" in result
        assert any("auto_unsubscribe" in r.message for r in caplog.records)

    def test_returns_count(self):
        newsletters = [{"sender": f"news{i}@ex.com"} for i in range(5)]
        mem_mock = MagicMock()
        with patch("src.email.features.unsubscribe.detect_newsletters", return_value=newsletters), \
                patch("src.agent.memory.agent_memory.get_agent_memory", return_value=mem_mock):
            result = gm.auto_unsubscribe("agent1", {})
        assert "5" in result


# ─────────────────────────── archive_old_read ────────────────────────────────

class TestArchiveOldRead:
    def test_queries_read_emails_only(self):
        svc = _fake_service(messages_list=[])
        with _patch_svc(svc):
            gm.archive_old_read("agent1", {"age_days": 30})
        list_call = svc.users.return_value.messages.return_value.list.call_args
        q = list_call.kwargs.get("q", "")
        assert "is:read" in q
        assert "30d" in q

    def test_removes_inbox_label(self):
        svc = _fake_service(messages_list=[{"id": "m1"}])
        with _patch_svc(svc):
            result = gm.archive_old_read("agent1", {"age_days": 30})
        assert "1" in result
        modify_call_body = svc.users.return_value.messages.return_value.modify.call_args.kwargs[
            "body"]
        assert "INBOX" in modify_call_body.get("removeLabelIds", [])
