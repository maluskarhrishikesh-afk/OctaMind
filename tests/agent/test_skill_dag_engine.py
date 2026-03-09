from src.agent.workflows.skill_dag_engine import _repair_email_pdf_delivery_plan


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