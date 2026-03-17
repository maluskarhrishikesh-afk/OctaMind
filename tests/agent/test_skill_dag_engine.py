from src.agent.workflows.skill_dag_engine import _repair_email_pdf_delivery_plan
from src.agent.workflows.skill_dag_engine import run_skill_dag


def test_repair_email_pdf_delivery_plan_inserts_pdf_and_attachment_steps() -> None:
    plan = [
        {
            "id": "s1",
            "tool": "fetch_emails_to_markdown",
            "kwargs": {"query": "from:quora", "max_results": 4},
            "depends_on": [],
            "description": "Fetch matching emails.",
        },
        {
            "id": "s2",
            "tool": "send_email",
            "kwargs": {
                "to": "me",
                "subject": "Summary of last 4 emails from Quora",
                "message": "{s1.report_content}",
            },
            "depends_on": ["s1"],
            "description": "Email the summary.",
        },
    ]

    repaired = _repair_email_pdf_delivery_plan(
        skill_name="email",
        user_query="Summarize the last 4 emails from Quora, create a PDF report, and send it to me.",
        plan=plan,
        user_email="owner@example.com",
    )

    assert [step["tool"] for step in repaired] == [
        "fetch_emails_to_markdown",
        "write_pdf_report",
        "send_email_with_attachment",
    ]
    assert repaired[1]["kwargs"]["content"] == "{s1.report_content}"
    assert repaired[2]["kwargs"]["attachment_path"] == f"{{{repaired[1]['id']}.path}}"
    assert repaired[2]["kwargs"]["to"] == "me"


def test_repair_email_pdf_delivery_plan_leaves_non_pdf_requests_unchanged() -> None:
    plan = [
        {
            "id": "s1",
            "tool": "fetch_emails_to_markdown",
            "kwargs": {"query": "from:quora", "max_results": 4},
            "depends_on": [],
            "description": "Fetch matching emails.",
        },
        {
            "id": "s2",
            "tool": "send_email",
            "kwargs": {"to": "me", "subject": "Summary", "message": "Short summary"},
            "depends_on": ["s1"],
            "description": "Email the summary.",
        },
    ]

    repaired = _repair_email_pdf_delivery_plan(
        skill_name="email",
        user_query="Summarize the last 4 emails from Quora and send me the summary.",
        plan=plan,
        user_email="owner@example.com",
    )

    assert repaired == plan


def test_run_skill_dag_requires_confirmation_for_destructive_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agent.workflows.skill_dag_engine._plan_steps",
        lambda *args, **kwargs: ([
            {
                "id": "s1",
                "tool": "delete_file",
                "kwargs": {"path": "C:/Temp/demo.txt"},
                "depends_on": [],
                "description": "Delete file",
            }
        ], 1),
    )
    result = run_skill_dag(
        skill_name="files",
        skill_context="You are a files skill.",
        tool_map={"delete_file": lambda path: {"status": "success", "path": path}},
        tool_docs="delete_file(path) - delete a file",
        user_query="delete the file",
        artifacts_out={},
        react_tool_map={},
        react_tool_docs="",
    )

    assert result["status"] == "confirmation_required"
    assert result["action"] == "delete_file"
    assert result["confirmation"]["tool_name"] == "delete_file"
    assert result["channel_payloads"]["telegram"]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Yes, confirm"


def test_run_skill_dag_executes_destructive_tool_after_confirmation(monkeypatch) -> None:
    calls = []

    def delete_file(path: str) -> dict:
        calls.append(path)
        return {"status": "success", "path": path, "message": "Deleted."}

    def fake_plan(*args, **kwargs):
        return ([{"id": "s1", "tool": "delete_file", "kwargs": {"path": "C:/Temp/demo.txt"}, "depends_on": [], "description": "Delete file"}], 1)

    monkeypatch.setattr("src.agent.workflows.skill_dag_engine._plan_steps", fake_plan)
    monkeypatch.setattr("src.agent.workflows.skill_dag_engine._synthesize", lambda *args, **kwargs: ("Deleted.", 1))

    from src.agent.workflows.confirmation_policy import build_confirmation_action_key

    action_key = build_confirmation_action_key("files", "delete_file", {"path": "C:/Temp/demo.txt"})
    result = run_skill_dag(
        skill_name="files",
        skill_context="You are a files skill.",
        tool_map={"delete_file": delete_file},
        tool_docs="delete_file(path) - delete a file",
        user_query="delete the file",
        artifacts_out={"_confirmed_action_keys": [action_key]},
        react_tool_map={},
        react_tool_docs="",
    )

    assert result["status"] == "success"
    assert calls == ["C:/Temp/demo.txt"]
