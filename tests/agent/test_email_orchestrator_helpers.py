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