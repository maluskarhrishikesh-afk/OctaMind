"""Automation sub-package — recurring background tasks for each agent type."""

from .automation_config import (
    AUTOMATION_CATALOG,
    load_automation_config,
    save_automation_config,
    update_automation_state,
    get_automations_for_agent_type,
)

__all__ = [
    "AUTOMATION_CATALOG",
    "load_automation_config",
    "save_automation_config",
    "update_automation_state",
    "get_automations_for_agent_type",
]
