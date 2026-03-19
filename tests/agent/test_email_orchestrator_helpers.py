import json
import importlib

from src.agent.ui.email_agent.orchestrator import _coerce_report_content, _extract_fast_path_query


def test_coerce_report_content_prefers_report_content_field() -> None:
    payload = {
        "status": "success",
        "report_content": "Executive Summary\n- Clean report body",
        "content": "Raw markdown body",
    }

    assert _coerce_report_content(payload) == "Executive Summary\n- Clean report body"


def test_coerce_report_content_parses_serialized_dict_payload() -> None:
    payload = json.dumps(
        {
            "status": "success",
            "report_content": "Insightful PDF body",
            "content": "Raw payload that should not win",
        }
    )

    assert _coerce_report_content(payload) == "Insightful PDF body"


def test_extract_fast_path_query_strips_pasted_cleanup_response() -> None:
    query = (
        "Issue - This did not work ->\n\n"
        "If in future any email comes from this id - hrishikesh.maluskar@zohomail.in "
        "then that email should be put to a folder named \"Hrishikesh Zoho\". Can you do that?\n\n"
        "Mailbox cleanup preview:\n\n"
        "Gmail filters: 0\n"
        "User labels: 0 This will permanently delete every Gmail filter and every user-created label. "
        "If you want to proceed, reply with: confirm delete all filters and labels"
    )

    extracted = _extract_fast_path_query(query)

    assert "hrishikesh.maluskar@zohomail.in" in extracted
    assert "Mailbox cleanup preview" not in extracted
    assert "confirm delete all filters and labels" not in extracted


def test_extract_fast_path_query_strips_injected_context_blocks() -> None:
    query = (
        "Can you delete all the rules applied to my mailbox, I do not want to keep any rules atm\n\n"
        "## Conversation Diary (recent turns - use for pronoun/context resolution)\n"
        "- [2026-03-15T14:51] email/delete_emails: Yes, delete them\n\n"
        "## Session State (structured - prefer these resolved values over raw text)\n"
        '{"current_date": "2026-03-15"}'
    )

    extracted = _extract_fast_path_query(query)

    assert extracted == "Can you delete all the rules applied to my mailbox, I do not want to keep any rules atm"


def test_email_orchestrator_deletes_all_filters_and_labels_without_llm(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "list_all_filters_and_labels": lambda: {
                "status": "success",
                "filters": [{"from": "boss@example.com"}],
                "user_labels": [{"name": "Finance"}],
            },
            "delete_all_filters_and_labels": lambda: {
                "status": "success",
                "filters_deleted": 3,
                "labels_deleted": 2,
                "message": "Deleted 3 Gmail filter(s) and 2 user label(s). System labels were preserved.",
            }
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox cleanup fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox cleanup fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "confirm delete all filters and labels in my mailbox"
    )

    assert result["status"] == "success"
    assert result["action"] == "delete_all_filters_and_labels"
    assert result["_fast_path"] == "mailbox_cleanup"
    assert result["filters_deleted"] == 3
    assert result["labels_deleted"] == 2


def test_email_orchestrator_requires_confirmation_before_mailbox_cleanup(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "list_all_filters_and_labels": lambda: {
                "status": "success",
                "filters": [{"from": "boss@example.com"}],
                "user_labels": [{"name": "Finance"}],
            },
            "delete_all_filters_and_labels": lambda: (_ for _ in ()).throw(AssertionError("Delete should not run without confirmation")),
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox cleanup confirmation fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox cleanup confirmation fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Can you delete all the rules and labels applied to my mailbox?"
    )

    assert result["status"] == "confirmation_required"
    assert result["action"] == "delete_all_filters_and_labels"
    assert result["_fast_path"] == "mailbox_cleanup_confirmation"
    assert "confirm delete all filters and labels" in result["message"]
    assert result["channel_payloads"]["telegram"]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Yes, delete"


def test_email_orchestrator_lists_filters_and_labels_without_llm(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "list_all_filters_and_labels": lambda: {
                "status": "success",
                "filters": [{"from": "boss@example.com"}],
                "user_labels": [{"name": "Finance"}],
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox preview fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox preview fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Show me all filters and labels first"
    )

    assert result["status"] == "success"
    assert result["action"] == "list_all_filters_and_labels"
    assert result["_fast_path"] == "mailbox_cleanup_preview"
    assert "Mailbox cleanup preview:" in result["message"]


def test_email_orchestrator_does_not_trigger_cleanup_fast_path_for_pasted_cleanup_response(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})
    monkeypatch.setattr(
        orchestrator,
        "_load_skill_context",
        lambda: "email skill context",
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_tool_docs_for_dag",
        lambda: "dag docs",
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_tool_docs_for_react",
        lambda _query: "react docs",
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_tool_map_for_react",
        lambda _query, _all_tools=None: {},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: {"status": "success", "action": "dag_called"},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run when DAG succeeds")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Issue - This did not work ->\n\n"
        "If in future any email comes from this id - hrishikesh.maluskar@zohomail.in "
        "then that email should be put to a folder named \"Hrishikesh Zoho\". Can you do that?\n\n"
        "Mailbox cleanup preview:\n\n"
        "Gmail filters: 0\n"
        "User labels: 0 This will permanently delete every Gmail filter and every user-created label. "
        "If you want to proceed, reply with: confirm delete all filters and labels"
    )

    assert result["status"] == "success"
    assert result["action"] == "dag_called"


def test_email_orchestrator_creates_sender_rule_without_llm(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "create_smart_label_rule": lambda **kwargs: {
                "status": "success",
                "emails_labeled": 8,
                "future_rule_created": True,
                "filter_id": "FILTER1",
                **kwargs,
            }
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for sender rule fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for sender rule fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        'If in future any email comes from this id - hrishikesh.maluskar@zohomail.in then that email should be put to a folder named "Hrishikesh Zoho". Can you do that?'
    )

    assert result["status"] == "success"
    assert result["action"] == "create_smart_label_rule"
    assert result["_fast_path"] == "sender_rule_creation"
    assert "Hrishikesh Zoho" in result["message"]


def test_email_orchestrator_sends_context_file_attachment_without_llm(tmp_path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    archive_path = tmp_path / "payslips_last_3_months.zip"
    archive_path.write_text("zip", encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "send_email_with_attachment": lambda to, subject, message, attachment_path: {
                "status": "success",
                "to": to,
                "subject": subject,
                "message": message,
                "attachment_path": attachment_path,
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for context attachment delivery")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for context attachment delivery")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_read_files_context_entities",
        lambda: {
            "selected_paths": [str(archive_path)],
            "listed_files": [{"path": str(archive_path), "name": archive_path.name, "type": "file"}],
        },
    )

    result = orchestrator.execute_with_llm_orchestration("Can you mail that to me?")

    assert result["status"] == "success"
    assert result["action"] == "send_email_with_attachment"
    assert result["_fast_path"] == "context_file_attachment_delivery"
    assert result["attachment_path"] == str(archive_path)


def test_email_orchestrator_skips_raw_attachment_fast_path_for_report_request(tmp_path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    image_path = tmp_path / "sample.png"
    image_path.write_text("png", encoding="utf-8")

    monkeypatch.setattr(orchestrator, "_resolve_file_attachment_from_context", lambda: str(image_path))
    result = orchestrator._try_context_file_attachment_delivery(
        "Can you create a list of all image files and email it to me? It should contain the image file name, path and type.",
        "can you create a list of all image files and email it to me? it should contain the image file name, path and type.",
        {
            "send_email_with_attachment": lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("raw attachment fast path should not run for generated reports")),
        },
    )

    assert result is None


def test_email_orchestrator_lists_rules_for_are_there_any_query(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "list_all_filters_and_labels": lambda: {
                "status": "success",
                "filters": [{"from": "boss@example.com"}],
                "user_labels": [{"name": "Finance"}],
            }
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox preview fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox preview fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Are there any rules applied in my mailbox?"
    )

    assert result["status"] == "success"
    assert result["action"] == "list_all_filters_and_labels"
    assert result["_fast_path"] == "mailbox_cleanup_preview"


def test_email_orchestrator_routes_todays_emails_through_dag(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "count_matching_emails": lambda query="": {"status": "success", "total_count": 2, "query": query},
            "list_emails": lambda query="", max_results=10: {
                "status": "success",
                "results": [
                    {"id": "msg-1", "subject": "Standup", "sender": "team@example.com", "date": "2026-03-18", "snippet": "Daily sync"},
                    {"id": "msg-2", "subject": "Invoice", "sender": "finance@example.com", "date": "2026-03-18", "snippet": "Attached invoice"},
                ][:max_results],
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for relative-day email list fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for relative-day email list fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_relative_day_email_query",
        lambda normalized_query, now=None: {
            "relative_day": "today",
            "query": "after:100 before:200 in:inbox",
            "label": "March 18, 2026",
        },
    )

    result = orchestrator.execute_with_llm_orchestration(
        "List all the email that I received today?"
    )

    assert result["status"] == "success"
    assert result["action"] == "list_emails"
    assert result["_fast_path"] == "relative_day_email_list"
    assert "Here are 2 of 2 emails received today" in result["message"]


def test_email_orchestrator_counts_yesterdays_emails_without_dag(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "count_matching_emails": lambda query="": {"status": "success", "total_count": 201, "query": query},
            "list_emails": lambda query="", max_results=10: (_ for _ in ()).throw(AssertionError("List should not run for pure count fast path")),
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for relative-day email count fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for relative-day email count fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_relative_day_email_query",
        lambda normalized_query, now=None: {
            "relative_day": "yesterday",
            "query": "after:300 before:400 in:inbox",
            "label": "March 17, 2026",
        },
    )

    result = orchestrator.execute_with_llm_orchestration("Did I receive only 1 email yesterday")

    assert result["status"] == "success"
    assert result["_fast_path"] == "relative_day_email_count"
    assert result["total_count"] == 201
    assert "201 emails yesterday" in result["message"]


def test_email_orchestrator_summarizes_selected_email_from_context_without_unwanted_email(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    calls = {"summarize": [], "send": []}

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "summarize_email": lambda message_id: calls["summarize"].append(message_id) or {
                "status": "success",
                "subject": "Is a heart attack a painful death?",
                "sender": "Quora Digest <digest@quora.com>",
                "date": "Tue, 17 Mar 2026 16:34:04 +0000",
                "summary": "This email contains a Quora digest article preview.",
                "key_points": ["Digest-style content", "Health-related topic"],
                "action_items": [],
            },
            "send_email": lambda to, subject, message: calls["send"].append((to, subject, message)) or {
                "status": "success",
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_resolve_email_from_context",
        lambda raw_query, normalized_query: {
            "id": "msg-3",
            "subject": "Is a heart attack a painful death?",
            "sender": "Quora Digest <digest@quora.com>",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for selected email summary fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for selected email summary fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Can you summarize the 3rd email and send it to me?"
    )

    assert result["status"] == "success"
    assert result["_fast_path"] == "selected_email_summary"
    assert calls["summarize"] == ["msg-3"]
    assert calls["send"] == []
    assert "Is a heart attack a painful death?" in result["message"]


def test_email_orchestrator_lists_saved_emails_deterministically(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "list_emails": lambda query="", max_results=10: {
                "status": "success",
                "results": [
                    {
                        "id": f"msg-{index}",
                        "subject": f"Email {index}",
                        "sender": f"sender{index}@example.com",
                        "date": "2026-03-17",
                        "snippet": f"Snippet {index}",
                    }
                    for index in range(1, max_results + 1)
                ],
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_read_email_context_entities",
        lambda: {
            "query": "after:300 before:400 in:inbox",
            "total_count": 201,
            "listed_emails": [
                {
                    "id": "msg-1",
                    "subject": "Quarterly review",
                    "sender": "Boss <boss@example.com>",
                    "date": "2026-03-17",
                    "snippet": "Please review the attached numbers before noon.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_read_listed_emails_from_context",
        lambda: [
            {
                "id": "msg-1",
                "subject": "Quarterly review",
                "sender": "Boss <boss@example.com>",
                "date": "2026-03-17",
                "snippet": "Please review the attached numbers before noon.",
            }
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for listed email display fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for listed email display fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration("Can you list 10 emails out of them?")

    assert result["status"] == "success"
    assert result["_fast_path"] == "listed_email_display"
    assert "1. Subject: Email 1" in result["message"]
    assert "10. Subject: Email 10" in result["message"]
    assert "Showing 10 of 201 emails from the current list." in result["message"]
    assert result["count"] == 10


def test_email_orchestrator_emails_selected_email_summary_only_when_explicit(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    calls = {"summarize": [], "send": []}

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "summarize_email": lambda message_id: calls["summarize"].append(message_id) or {
                "status": "success",
                "subject": "Quarterly update",
                "sender": "finance@example.com",
                "date": "Tue, 17 Mar 2026 09:00:00 +0000",
                "summary": "Finance update summary.",
                "key_points": [],
                "action_items": [],
            },
            "send_email": lambda to, subject, message: calls["send"].append((to, subject, message)) or {
                "status": "success",
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_resolve_email_from_context",
        lambda raw_query, normalized_query: {"id": "msg-2", "subject": "Quarterly update", "sender": "finance@example.com"},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for selected email summary fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for selected email summary fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Summarize the second email and email it to me"
    )

    assert result["status"] == "success"
    assert calls["summarize"] == ["msg-2"]
    assert calls["send"]
    assert calls["send"][0][0] == "me"


def test_email_orchestrator_summarizes_multiple_selected_emails_from_context(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    calls = {"summarize": [], "send": []}

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "summarize_email": lambda message_id: calls["summarize"].append(message_id) or {
                "status": "success",
                "subject": f"Subject {message_id}",
                "sender": f"sender-{message_id}@example.com",
                "date": "Tue, 17 Mar 2026 09:00:00 +0000",
                "summary": f"Summary for {message_id}",
                "key_points": [],
                "action_items": [],
            },
            "send_email": lambda to, subject, message: calls["send"].append((to, subject, message)) or {
                "status": "success",
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_read_listed_emails_from_context",
        lambda: [
            {"id": "msg-1", "subject": "Email 1", "sender": "one@example.com"},
            {"id": "msg-2", "subject": "Email 2", "sender": "two@example.com"},
            {"id": "msg-3", "subject": "Email 3", "sender": "three@example.com"},
            {"id": "msg-4", "subject": "Email 4", "sender": "four@example.com"},
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for multi-email summary fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for multi-email summary fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Can you summarize 1, 2 and 4 emails and send it to me?"
    )

    assert result["status"] == "success"
    assert result["_fast_path"] == "selected_email_summary"
    assert calls["summarize"] == ["msg-1", "msg-2", "msg-4"]
    assert calls["send"] == []
    assert "Email 1" in result["message"]
    assert "Summary for msg-4" in result["message"]


def test_email_orchestrator_executes_pending_cleanup_on_yes_delete_them(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    pending_path = tmp_path / "email_mailbox_cleanup_pending.json"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_CLEANUP_PATH", pending_path)
    pending_path.write_text(
        json.dumps(
            {
                "telegram_123": {
                    "action": "delete_all_filters",
                    "preview": {"filters": [{"from": "hrishikesh.maluskar@zohomail.in"}], "user_labels": [{"name": "Hrishikesh Zoho"}]},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "delete_all_filters": lambda: {
                "status": "success",
                "filters_deleted": 1,
                "message": "Deleted 1 Gmail filter(s). Existing labels were preserved.",
            }
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for pending confirmation fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for pending confirmation fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Yes, delete them",
        artifacts_out={"_session_id": "telegram_123"},
    )

    assert result["status"] == "success"
    assert result["action"] == "delete_all_filters"
    assert result["_fast_path"] == "mailbox_cleanup"
    assert result["filters_deleted"] == 1
    assert json.loads(pending_path.read_text(encoding="utf-8")) == {}


def test_email_orchestrator_requires_confirmation_for_rules_only_cleanup(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    pending_path = tmp_path / "email_mailbox_cleanup_pending.json"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_CLEANUP_PATH", pending_path)

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "list_all_filters_and_labels": lambda: {
                "status": "success",
                "filters": [{"from": "hrishikesh.maluskar@zohomail.in"}],
                "user_labels": [{"name": "Hrishikesh Zoho"}],
            },
            "delete_all_filters": lambda: (_ for _ in ()).throw(AssertionError("Delete should not run before confirmation")),
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for rules-only cleanup fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for rules-only cleanup fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        "Can you delete all the rules applied to my mailbox, I don't want to keep any rules atm",
        artifacts_out={"_session_id": "telegram_123"},
    )

    assert result["status"] == "confirmation_required"
    assert result["action"] == "delete_all_filters"
    assert "every Gmail filter" in result["message"]
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending["telegram_123"]["action"] == "delete_all_filters"


def test_email_orchestrator_clears_stale_pending_cleanup_for_sender_rule(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    pending_path = tmp_path / "email_mailbox_cleanup_pending.json"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_CLEANUP_PATH", pending_path)
    pending_path.write_text(
        json.dumps(
            {
                "telegram_123": {
                    "action": "delete_all_filters",
                    "preview": {"filters": [{"from": "boss@example.com"}], "user_labels": []},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "create_smart_label_rule": lambda **kwargs: {
                "status": "success",
                "emails_labeled": 2,
                "future_rule_created": True,
                "filter_id": "FILTER1",
                **kwargs,
            },
            "delete_all_filters": lambda: (_ for _ in ()).throw(AssertionError("Pending cleanup should not be consumed for a new sender-rule intent")),
            "list_all_filters_and_labels": lambda: {"status": "success", "filters": [], "user_labels": []},
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for sender rule fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for sender rule fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration(
        'If in future any email comes from this id - hrishikesh.maluskar@zohomail.in then that email should be put to a folder named "Hrishikesh Zoho". Can you do that?',
        artifacts_out={"_session_id": "telegram_123"},
    )

    assert result["status"] == "success"
    assert result["action"] == "create_smart_label_rule"
    assert result["_fast_path"] == "sender_rule_creation"
    assert json.loads(pending_path.read_text(encoding="utf-8")) == {}


def test_email_orchestrator_starts_mailbox_preferences_setup_for_organize_request(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    pending_path = tmp_path / "email_mailbox_preferences_pending.json"
    prefs_path = tmp_path / "mailbox_preferences.md"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_PREFERENCES_PATH", pending_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox preference entry fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox preference entry fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration("Please organize my mailbox properly")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_preferences_entry"
    assert "Guided setup for mailbox preferences" in result["message"]
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending["__default__"]["kind"] == "entry"


def test_email_orchestrator_guided_mailbox_setup_saves_markdown_preferences(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    pending_path = tmp_path / "email_mailbox_preferences_pending.json"
    prefs_path = tmp_path / "mailbox_preferences.md"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_PREFERENCES_PATH", pending_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run during mailbox setup fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run during mailbox setup fast path")),
    )

    first = orchestrator.execute_with_llm_orchestration("Organize my inbox")
    assert first["_fast_path"] == "mailbox_preferences_entry"

    question_1 = orchestrator.execute_with_llm_orchestration("1")
    assert question_1["_fast_path"] == "mailbox_preferences_question"
    assert "Mailbox setup 1/7" in question_1["message"]

    question_2 = orchestrator.execute_with_llm_orchestration("2")
    assert "Mailbox setup 2/7" in question_2["message"]

    question_3 = orchestrator.execute_with_llm_orchestration("2")
    assert "Mailbox setup 3/7" in question_3["message"]

    question_4 = orchestrator.execute_with_llm_orchestration("3")
    assert "Mailbox setup 4/7" in question_4["message"]

    question_5 = orchestrator.execute_with_llm_orchestration("1")
    assert "Mailbox setup 5/7" in question_5["message"]

    question_6 = orchestrator.execute_with_llm_orchestration("1")
    assert "Mailbox setup 6/7" in question_6["message"]

    question_7 = orchestrator.execute_with_llm_orchestration("2")
    assert "Mailbox setup 7/7" in question_7["message"]

    final = orchestrator.execute_with_llm_orchestration("2")

    assert final["status"] == "success"
    assert final["_fast_path"] == "mailbox_preferences_saved"
    assert prefs_path.exists()
    saved_text = prefs_path.read_text(encoding="utf-8")
    assert "# Mailbox Preferences" in saved_text
    assert '"operation_mode": "confirm_before_action"' in saved_text
    assert '"promotions_action": "archive"' in saved_text
    assert '"newsletters_action": "summarize_then_archive"' in saved_text
    assert '"review_schedule": "daily"' in saved_text
    assert '"continuous_cleanup": {' in saved_text
    assert '"enabled": true' in saved_text


def test_email_orchestrator_organize_mailbox_builds_plan_from_saved_preferences(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    pending_path = tmp_path / "email_mailbox_preferences_pending.json"
    prefs_path = tmp_path / "mailbox_preferences.md"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_PREFERENCES_PATH", pending_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    mailbox_prefs.save_mailbox_preferences(
        {
            "operation_mode": "confirm_before_action",
            "promotions_action": "archive",
            "newsletters_action": "summarize_then_archive",
            "task_extraction": True,
            "draft_replies": "suggest",
        }
    )

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "get_inbox_count": lambda: {"status": "success", "count": 17},
            "count_matching_emails": lambda query="": {
                "status": "success",
                "total_count": 6 if query.startswith("category:promotions") else 4,
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox organization plan fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox organization plan fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration("Organize my mailbox properly")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_organization_plan"
    assert "Archive up to 6 promotion email(s)" in result["message"]
    assert "Summarize then archive up to 4 newsletter-style email(s)" in result["message"]
    assert "Current unread inbox count: 17" in result["message"]


def test_email_orchestrator_applies_saved_mailbox_preferences(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    pending_path = tmp_path / "email_mailbox_preferences_pending.json"
    prefs_path = tmp_path / "mailbox_preferences.md"
    monkeypatch.setattr(orchestrator, "_PENDING_MAILBOX_PREFERENCES_PATH", pending_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    mailbox_prefs.save_mailbox_preferences(
        {
            "operation_mode": "confirm_before_action",
            "promotions_action": "archive",
            "newsletters_action": "archive",
            "task_extraction": True,
            "draft_replies": "suggest",
        }
    )

    calls = []

    def _archive_all(query: str, batch_size: int = 200, max_total: int = 0):
        calls.append((query, batch_size, max_total))
        if "category:promotions" in query:
            return {"status": "success", "archived_count": 201}
        return {"status": "success", "archived_count": 3}

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "get_inbox_count": lambda: {"status": "success", "unread_messages": 14},
            "count_matching_emails": lambda query="": {
                "status": "success",
                "total_count": 201 if "category:promotions" in query else 3,
            },
            "archive_all_matching_emails": _archive_all,
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for mailbox preference apply fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for mailbox preference apply fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration("Apply my mailbox preferences")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_preferences_apply"
    assert "Applied mailbox preferences:" in result["message"]
    assert "Done: 201 archived." in result["message"]
    assert len(calls) == 2
    assert calls[0][0] == "category:promotions in:inbox"
    assert "unsubscribe OR newsletter" in calls[1][0]


def test_email_orchestrator_updates_newsletter_preference_from_conversational_edit(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    prefs_path = tmp_path / "mailbox_preferences.md"
    history_path = tmp_path / "email_mailbox_review_history.json"
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_REVIEW_HISTORY_PATH", history_path)
    mailbox_prefs.save_mailbox_preferences(mailbox_prefs.default_mailbox_preferences())

    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})

    result = orchestrator.execute_with_llm_orchestration("change newsletters to archive")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_preferences_edit"
    assert "Newsletters will be archived." in result["message"]
    assert '"newsletters_action": "archive"' in prefs_path.read_text(encoding="utf-8")


def test_email_orchestrator_syncs_mailbox_scheduler_settings_from_direct_edit(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    prefs_path = tmp_path / "mailbox_preferences.md"
    history_path = tmp_path / "email_mailbox_review_history.json"
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_REVIEW_HISTORY_PATH", history_path)
    mailbox_prefs.save_mailbox_preferences(mailbox_prefs.default_mailbox_preferences())

    sync_calls = []
    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})
    monkeypatch.setattr(
        orchestrator,
        "sync_mailbox_automation_config",
        lambda agent_id, preferences: sync_calls.append((agent_id, preferences)) or {"status": "success", "message": "Daily review enabled."},
    )

    result = orchestrator.execute_with_llm_orchestration("set mailbox review to daily", agent_id="pa_test")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_preferences_edit"
    assert "Automation sync: Daily review enabled." in result["message"]
    assert sync_calls and sync_calls[0][0] == "pa_test"
    assert sync_calls[0][1]["review_schedule"] == "daily"


def test_email_orchestrator_saves_and_applies_mailbox_rule(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    prefs_path = tmp_path / "mailbox_preferences.md"
    history_path = tmp_path / "email_mailbox_review_history.json"
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_REVIEW_HISTORY_PATH", history_path)

    calls = []
    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "create_smart_label_rule": lambda **kwargs: calls.append(kwargs) or {"status": "success", "future_rule_created": True},
        },
    )

    result = orchestrator.execute_with_llm_orchestration("always move recruiter mail to Jobs")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_rule_saved"
    assert calls and calls[0]["label_name"] == "Jobs"
    assert calls[0]["from_email"] == "recruiter"
    assert calls[0]["also_archive"] is True
    saved_text = prefs_path.read_text(encoding="utf-8")
    assert '"match_value": "recruiter"' in saved_text
    assert '"label_name": "Jobs"' in saved_text


def test_email_orchestrator_builds_mailbox_review_digest(monkeypatch, tmp_path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")
    mailbox_prefs = importlib.import_module("src.email.features.mailbox_preferences")

    prefs_path = tmp_path / "mailbox_preferences.md"
    history_path = tmp_path / "email_mailbox_review_history.json"
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_PREFERENCES_PATH", prefs_path)
    monkeypatch.setattr(mailbox_prefs, "_MAILBOX_REVIEW_HISTORY_PATH", history_path)
    mailbox_prefs.save_mailbox_preferences(
        {
            "operation_mode": "confirm_before_action",
            "promotions_action": "archive",
            "newsletters_action": "summarize_then_archive",
            "task_extraction": True,
            "draft_replies": "suggest",
        }
    )
    mailbox_prefs.record_mailbox_review_event(
        {
            "kind": "mailbox_apply",
            "promotions_archived": 10,
            "newsletter_archived": 4,
            "rules_applied": 1,
            "recorded_at": "2026-03-19T10:00:00",
        }
    )
    mailbox_prefs.record_mailbox_review_event({"kind": "manual_triage", "recorded_at": "2026-03-19T11:00:00"})
    mailbox_prefs.record_mailbox_review_event({"kind": "manual_triage", "recorded_at": "2026-03-19T12:00:00"})
    mailbox_prefs.record_mailbox_review_event({"kind": "manual_triage", "recorded_at": "2026-03-19T13:00:00"})

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "get_inbox_count": lambda: {"status": "success", "count": 82},
            "count_matching_emails": lambda query="": {"status": "success", "total_count": 9 if query.startswith("category:promotions") else 5},
        },
    )

    result = orchestrator.execute_with_llm_orchestration("review my mailbox")

    assert result["status"] == "success"
    assert result["_fast_path"] == "mailbox_review_digest"
    assert "Mailbox review digest:" in result["message"]
    assert "Last cleanup run: 2026-03-19T10:00:00" in result["message"]
    assert "Your inbox looks overloaded." in result["message"]