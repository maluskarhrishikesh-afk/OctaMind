import json

from src.agent.ui.email_agent.orchestrator import _coerce_report_content


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