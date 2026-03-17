"""
StepRunner — executes a single WorkflowStep by calling the correct tool
directly (bypassing the LLM for the actual call, since the planning phase
already determined which tool + params to use).

Supports parameter *references*: a param value of the form
``"{output_key}"`` is resolved from WorkflowContext before the call.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from src.agent.workflows.agent_registry import get_runtime_tool_map
from src.agent.workflows.workflow_context import WorkflowContext, WorkflowStep
from src.agent.workflows import file_bridge

logger = logging.getLogger("workflows")

_TOOL_REGISTRIES: Dict[str, Dict[str, Callable]] = {}
_DRIVE_REGISTRY: Optional[Dict[str, Callable]] = None
_EMAIL_REGISTRY: Optional[Dict[str, Callable]] = None


def _get_registry(agent_name: str) -> Dict[str, Callable]:
    registry = _TOOL_REGISTRIES.get(agent_name)
    if registry is None:
        registry = get_runtime_tool_map(agent_name)
        _TOOL_REGISTRIES[agent_name] = registry
    return registry


def _get_drive_registry() -> Dict[str, Callable]:
    global _DRIVE_REGISTRY
    if _DRIVE_REGISTRY is None:
        _DRIVE_REGISTRY = _get_registry("drive")
    return _DRIVE_REGISTRY


def _get_email_registry() -> Dict[str, Callable]:
    global _EMAIL_REGISTRY
    if _EMAIL_REGISTRY is None:
        _EMAIL_REGISTRY = _get_registry("email")
    return _EMAIL_REGISTRY


# ---------------------------------------------------------------------------
# Parameter resolution
# ---------------------------------------------------------------------------

def _value_to_str(value: Any) -> str:
    """
    Convert a tool output value (often a dict) to a human-readable string
    suitable for use as an email message body.

    Priority:
        1. If dict has 'report_markdown' → use it (Drive report)
        2. If dict has 'text' / 'message' / 'content' / 'summary' → use it
        3. If dict has 'status'+'error' → format error
        4. Fallback: pretty-print as JSON
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("report_markdown", "text", "content", "summary", "message", "result", "output"):
            if key in value and isinstance(value[key], str) and value[key].strip():
                return value[key]
        # Format as readable key: value lines, skipping 'status'
        lines = []
        for k, v in value.items():
            if k == "status":
                continue
            if isinstance(v, (list, dict)):
                continue
            lines.append(f"{k}: {v}")
        return "\n".join(lines) if lines else json.dumps(value, indent=2)
    if isinstance(value, list):
        parts = []
        for item in value[:20]:  # cap at 20 items
            if isinstance(item, dict):
                name = item.get("name") or item.get(
                    "title") or item.get("subject") or str(item)
                parts.append(f"- {name}")
            else:
                parts.append(f"- {item}")
        return "\n".join(parts)
    return str(value)


def _extract_file_id(raw: Any) -> Optional[str]:
    """
    Given the stored result of a search_files / list_files call, extract the
    first file's Drive ID string.  Returns None if extraction fails.
    """
    if isinstance(raw, str):
        return None
    # dict with a 'files' list: {"status":"success", "files": [{"id":"..."}]}
    if isinstance(raw, dict):
        files = raw.get("files") or raw.get("results") or []
        if files and isinstance(files, list):
            first = files[0]
            if isinstance(first, dict):
                return first.get("id") or first.get("file_id")
    # plain list of file dicts
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            return first.get("id") or first.get("file_id")
    return None


def _resolve_params(params: Dict[str, Any], ctx: WorkflowContext) -> Dict[str, Any]:
    """
    Walk *params* and replace any string value that looks like ``"{key}"``
    with the actual value from the WorkflowContext.

    Smart extractions:
    - ``file_id`` param + list/dict result from search → first file's Drive ID
    - ``attachment_path`` / any ``*path*`` / ``*attachment*`` param + download result → local_path
    """
    resolved: Dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str):
            if v.startswith("{") and v.endswith("}"):
                ctx_key = v[1:-1]
                raw = ctx.get(ctx_key, v)  # fallback: keep literal

                # Smart: file_id from search/list result
                if k == "file_id" and raw != v:
                    file_id = _extract_file_id(raw)
                    if file_id:
                        resolved[k] = file_id
                        continue

                # Smart: local path from download result
                if isinstance(raw, dict) and raw.get("local_path") and (
                    "path" in k or "attachment" in k
                ):
                    resolved[k] = str(raw["local_path"])

                # Default: serialise dict/list to readable string
                elif isinstance(raw, (dict, list)):
                    resolved[k] = _value_to_str(raw)
                else:
                    resolved[k] = raw
            elif v.startswith("$bridge:"):
                handle = v[len("$bridge:"):]
                path = file_bridge.resolve(handle)
                resolved[k] = str(path) if path else v
            else:
                resolved[k] = v
        else:
            resolved[k] = v
    return resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_step(step: WorkflowStep, ctx: WorkflowContext) -> Dict[str, Any]:
    """
    Execute one WorkflowStep.

    1. Select the correct tool registry based on step.agent.
    2. Look up the callable by step.tool.
    3. Resolve context references in step.params.
    4. Call the tool with resolved params.
    5. Store the result in ctx under step.output_key.
    6. Return a result dict with status + data.
    """
    logger.info(
        "Step %d: [%s] %s(%s)",
        step.step_num,
        step.agent,
        step.tool,
        list(step.params.keys()),
    )

    registry = _get_registry(step.agent)
    if not registry:
        return {
            "status": "error",
            "error": f"Unknown agent type or empty runtime tool map: '{step.agent}'",
            "step": step.step_num,
        }

    # Look up tool
    tool_fn = registry.get(step.tool)
    if tool_fn is None:
        return {
            "status": "error",
            "error": f"Tool '{step.tool}' not found in {step.agent} registry",
            "step": step.step_num,
        }

    # Resolve params
    resolved = _resolve_params(step.params, ctx)

    # Execute
    try:
        result = tool_fn(**resolved)
    except Exception as exc:
        logger.exception("Step %d failed: %s", step.step_num, exc)
        return {
            "status": "error",
            "error": str(exc),
            "step": step.step_num,
            "tool": step.tool,
        }

    # Store in context
    if step.output_key:
        ctx.set(step.output_key, result)

    return {
        "status": "success",
        "step": step.step_num,
        "agent": step.agent,
        "tool": step.tool,
        "output_key": step.output_key,
        "result": result,
    }
