from __future__ import annotations

import importlib
import json


def test_load_security_events_sorts_newest_first(monkeypatch, tmp_path) -> None:
    dashboard_mod = importlib.import_module("src.agent.ui.dashboard.security_dashboard")
    events_path = tmp_path / "security_events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-03-15T10:00:00+00:00", "event_type": "prompt_injection_suspected", "decision": "allow"}),
                json.dumps({"timestamp": "2026-03-15T11:00:00+00:00", "event_type": "prompt_injection_blocked", "decision": "blocked"}),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_mod, "_SECURITY_EVENTS_PATH", events_path)

    events = dashboard_mod.load_security_events(limit=10)

    assert [event["event_type"] for event in events] == ["prompt_injection_blocked", "prompt_injection_suspected"]


def test_summarize_security_events_counts_blocked_and_rate_limit() -> None:
    dashboard_mod = importlib.import_module("src.agent.ui.dashboard.security_dashboard")

    summary = dashboard_mod.summarize_security_events(
        [
            {"timestamp": "2026-03-15T11:00:00+00:00", "event_type": "prompt_injection_blocked", "decision": "blocked", "source": "telegram"},
            {"timestamp": "2026-03-15T10:00:00+00:00", "event_type": "rate_limit_exceeded", "decision": "rate_limited", "source": "telegram"},
            {"timestamp": "2026-03-15T09:00:00+00:00", "event_type": "prompt_injection_suspected", "decision": "allow", "source": "dashboard"},
        ]
    )

    assert summary["total_events"] == 3
    assert summary["blocked_events"] == 1
    assert summary["rate_limit_events"] == 1
    assert summary["suspicious_events"] == 1
    assert summary["events_by_source"]["telegram"] == 2


def test_build_rate_limit_rows_orders_heaviest_sessions_first() -> None:
    dashboard_mod = importlib.import_module("src.agent.ui.dashboard.security_dashboard")

    state = {
        "telegram::session_a": {"minute": [9999999999.0], "hour": [9999999999.0, 9999999998.0]},
        "dashboard::session_b": {"minute": [9999999999.0], "hour": [9999999999.0]},
    }

    rows = dashboard_mod.build_rate_limit_rows(state, now_ts=9999999999.0)

    assert rows[0]["session_id"] == "session_a"
    assert rows[0]["hour_count"] >= rows[1]["hour_count"]


def test_build_confirmation_rows_extracts_operator_view() -> None:
    dashboard_mod = importlib.import_module("src.agent.ui.dashboard.security_dashboard")

    rows = dashboard_mod.build_confirmation_rows(
        {
            "telegram_1": {
                "skill_name": "files",
                "tool_name": "delete_file",
                "action_key": "abc123",
                "message": "files::delete file",
                "original_message": "delete it",
                "source": "telegram",
            }
        }
    )

    assert rows == [
        {
            "session_id": "telegram_1",
            "skill": "files",
            "tool": "delete_file",
            "action_key": "abc123",
            "message": "files::delete file",
            "original_message": "delete it",
            "source": "telegram",
        }
    ]


def test_build_tool_risk_rows_uses_runtime_manifest(monkeypatch) -> None:
    dashboard_mod = importlib.import_module("src.agent.ui.dashboard.security_dashboard")

    monkeypatch.setattr("src.agent.workflows.agent_registry.registered_agents", lambda: ["files"])
    monkeypatch.setattr(
        "src.agent.security.tool_manifest.build_runtime_tool_security_manifest",
        lambda agent_name: {
            "delete_file": {
                "risk_level": "critical",
                "approval_required": True,
                "policy_tags": ["critical", "destructive"],
                "default_rate_limit": {"per_hour": 10},
            },
            "list_files": {
                "risk_level": "low",
                "approval_required": False,
                "policy_tags": ["low", "data_access"],
                "default_rate_limit": {"per_hour": 300},
            },
        },
    )

    rows = dashboard_mod.build_tool_risk_rows()

    assert rows[0]["tool"] == "delete_file"
    assert rows[0]["risk_level"] == "critical"
    assert rows[0]["approval_required"] is True