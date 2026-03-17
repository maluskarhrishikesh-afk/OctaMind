from __future__ import annotations

from typing import Any, Dict

from src.agent.workflows.agent_registry import get_runtime_tool_map
from src.agent.workflows.confirmation_policy import destructive_tool_requires_confirmation

_CRITICAL_KEYWORDS = ("delete", "trash", "remove", "empty", "revoke", "purge")
_HIGH_KEYWORDS = ("send", "share", "publish", "upload", "post", "forward", "move")
_MEDIUM_KEYWORDS = ("create", "update", "write", "copy", "download", "export", "schedule")


def classify_tool_risk(tool_name: str) -> str:
    normalized = str(tool_name or "").strip().lower()
    if any(token in normalized for token in _CRITICAL_KEYWORDS):
        return "critical"
    if any(token in normalized for token in _HIGH_KEYWORDS):
        return "high"
    if any(token in normalized for token in _MEDIUM_KEYWORDS):
        return "medium"
    return "low"


def _default_rate_limit_for_risk(risk_level: str) -> Dict[str, int]:
    if risk_level == "critical":
        return {"per_hour": 10}
    if risk_level == "high":
        return {"per_hour": 30}
    if risk_level == "medium":
        return {"per_hour": 120}
    return {"per_hour": 300}


def _policy_tags(tool_name: str, risk_level: str) -> list[str]:
    normalized = str(tool_name or "").strip().lower()
    tags = [risk_level]
    if destructive_tool_requires_confirmation(normalized):
        tags.append("destructive")
    if any(token in normalized for token in ("send", "share", "publish", "forward")):
        tags.append("external_side_effect")
    if any(token in normalized for token in ("read", "search", "list", "get", "download")):
        tags.append("data_access")
    return tags


def build_runtime_tool_security_manifest(agent_name: str, user_query: str = "") -> Dict[str, Dict[str, Any]]:
    manifest: Dict[str, Dict[str, Any]] = {}
    for tool_name in sorted(get_runtime_tool_map(agent_name, user_query=user_query)):
        risk_level = classify_tool_risk(tool_name)
        manifest[tool_name] = {
            "risk_level": risk_level,
            "approval_required": destructive_tool_requires_confirmation(tool_name),
            "default_rate_limit": _default_rate_limit_for_risk(risk_level),
            "policy_tags": _policy_tags(tool_name, risk_level),
        }
    return manifest