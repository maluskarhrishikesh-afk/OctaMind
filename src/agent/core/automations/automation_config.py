"""
Automation Configuration — per-agent automation settings.

Configs are kept in  memory/<agent_id>/automation_config.json
Structure of each entry:
  {
    "<automation_id>": {
      "enabled": false,
      "params":  { ... },   # overrides from catalog defaults
      "last_run": null      # ISO-8601 utc string or null
    },
    ...
  }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


# ── Automation catalogs (one per agent type) ─────────────────────────────────

GMAIL_AUTOMATIONS: Dict[str, Dict[str, Any]] = {
    "auto_delete_spam": {
        "label": "🗑 Auto-delete spam",
        "description": "Automatically trash emails sitting in the Spam folder",
        "interval_minutes": 15,
        "default_params": {},
        "param_schema": {},          # no configurable params
    },
    "auto_archive_newsletters": {
        "label": "📁 Auto-archive newsletters",
        "description": "Move Promotions / newsletters out of the inbox automatically",
        "interval_minutes": 30,
        "default_params": {"label_name": "Archives/Newsletters"},
        "param_schema": {
            "label_name": {"type": "text", "label": "Archive Label"},
        },
    },
    "daily_digest": {
        "label": "📋 Daily email digest",
        "description": "Summarise today's emails and log them to agent memory",
        "interval_minutes": 1440,    # every 24 h
        "default_params": {},
        "param_schema": {},
    },
    "auto_label_vip": {
        "label": "⭐ Auto-label VIP emails",
        "description": "Star incoming emails from your most frequent contacts",
        "interval_minutes": 15,
        "default_params": {},
        "param_schema": {},
    },
    "flag_old_unread": {
        "label": "🚩 Flag old unread emails",
        "description": "Star unread emails that have been sitting for N+ days",
        "interval_minutes": 1440,
        "default_params": {"age_days": 7},
        "param_schema": {
            "age_days": {"type": "number", "label": "Age threshold (days)", "min": 1, "max": 90},
        },
    },
    "weekly_report": {
        "label": "📊 Weekly productivity report",
        "description": "Write a 7-day email productivity report to agent memory",
        "interval_minutes": 10_080,  # every 7 days
        "default_params": {},
        "param_schema": {},
    },
    "auto_categorize": {
        "label": "🗂 Auto-categorize by sender domain",
        "description": "Apply Octa Bot Gmail labels to new emails automatically",
        "interval_minutes": 30,
        "default_params": {},
        "param_schema": {},
    },
    "auto_unsubscribe": {
        "label": "🔕 Detect & report promotional senders",
        "description": "Scan inbox weekly and report newsletters / promotional senders",
        "interval_minutes": 10_080,
        "default_params": {"confidence_threshold": 0.8},
        "param_schema": {
            "confidence_threshold": {
                "type": "slider",
                "label": "Detection confidence",
                "min": 0.5,
                "max": 1.0,
                "step": 0.05,
            },
        },
    },
    "out_of_office": {
        "label": "💬 Auto-reply (Out of Office)",
        "description": "Send an automatic reply to incoming emails (limited to 5/run)",
        "interval_minutes": 15,
        "default_params": {
            "reply_message": "I'm currently out of the office and will respond shortly.",
            "active_until": "",
        },
        "param_schema": {
            "reply_message": {"type": "textarea", "label": "Reply message"},
            "active_until": {
                "type": "text",
                "label": "Active until (YYYY-MM-DD, leave blank for always-on)",
            },
        },
    },
    "archive_old_read": {
        "label": "🧹 Archive old read emails",
        "description": "Move read emails older than N days out of the inbox",
        "interval_minutes": 1440,
        "default_params": {"age_days": 30},
        "param_schema": {
            "age_days": {
                "type": "number",
                "label": "Age threshold (days)",
                "min": 7,
                "max": 180,
            },
        },
    },
}


AUTOMATION_CATALOG: Dict[str, Dict[str, Dict[str, Any]]] = {
    "gmail": GMAIL_AUTOMATIONS,
    # Future: "google_drive": DRIVE_AUTOMATIONS, "slack": SLACK_AUTOMATIONS, …
}


# ── Config I/O ────────────────────────────────────────────────────────────────

def _config_path(agent_id: str) -> Path:
    return Path("memory") / agent_id / "automation_config.json"


def load_automation_config(agent_id: str) -> Dict[str, Any]:
    """Return the raw config dict for an agent (may be empty {})."""
    path = _config_path(agent_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_automation_config(agent_id: str, config: Dict[str, Any]) -> None:
    """Persist the full config dict for an agent."""
    path = _config_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def update_automation_state(
    agent_id: str,
    automation_id: str,
    enabled: bool,
    params: Optional[Dict[str, Any]] = None,
    interval_minutes: Optional[float] = None,
) -> None:
    """Enable/disable one automation and optionally update its params and run interval."""
    config = load_automation_config(agent_id)
    entry = config.get(automation_id, {})
    entry["enabled"] = enabled
    if params is not None:
        entry["params"] = params
    if interval_minutes is not None:
        entry["interval_minutes"] = interval_minutes
    entry.setdefault("last_run", None)
    config[automation_id] = entry
    save_automation_config(agent_id, config)


def get_automations_for_agent_type(agent_type: str) -> Dict[str, Any]:
    """Return the automation catalog entries relevant to the given agent type."""
    return AUTOMATION_CATALOG.get(agent_type, {})
