"""
NLStepRunner — executes a single NLWorkflowStep by delegating to the
target agent's execute_with_llm_orchestration() with a resolved natural-
language instruction.

This replaces the old step_runner.py approach of calling raw API functions
directly.  Sub-agents now run their own ReAct loops, use their own tool
lists, and manage their own memory.

Artifact handoff
----------------
When one step produces a file (e.g. Drive downloads fashionable.xlsx),
the agent stores its local path in ``artifacts_out["file_path"]``.
The orchestrator then substitutes ``{output_key.file_path}`` references
in subsequent step instructions before calling the next agent.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional

from src.agent.workflows.workflow_context import NLWorkflowStep, WorkflowContext
from src.agent.workflows.agent_registry import get_executor

logger = logging.getLogger("workflows")

# Regex to fish out a file path from free-text agent responses as a fallback.
_FILE_PATH_RE = re.compile(
    r'(?:[A-Za-z]:\\|/tmp/|/var/tmp/|/home/|\./)[\w ./\\-]+\.(?:xlsx?|docx?|pdf|csv|zip|png|jpg|jpeg|txt|json|pptx?)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Instruction resolver
# ---------------------------------------------------------------------------

def _resolve_instruction(instruction: str, ctx: WorkflowContext) -> str:
    """
    Substitute ``{output_key}`` and ``{output_key.field}`` tokens in an
    instruction string with values from the workflow context.

    Examples:
        "{downloaded_file.file_path}"  → "/tmp/fashionable.xlsx"
        "{email_list}"                 → "3 emails found: ..."
    """
    def _replace(match: re.Match) -> str:
        ref = match.group(1)
        if "." in ref:
            key, field = ref.split(".", 1)
            val = ctx.get(key)
            if isinstance(val, dict):
                # Look in artifacts first, then top-level keys
                result = val.get("artifacts", {}).get(field) or val.get(field)
                if result is not None:
                    return str(result)
        else:
            val = ctx.get(ref)
            if val is not None:
                if isinstance(val, dict):
                    # Return the human-readable text summary
                    return val.get("text", str(val))
                return str(val)
        return match.group(0)  # leave unresolved placeholder intact

    return re.sub(r"\{([\w.]+)\}", _replace, instruction)


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------

def run_nl_step(
    step: NLWorkflowStep,
    ctx: WorkflowContext,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute one NLWorkflowStep.

    1. Resolve ``{key}`` / ``{key.field}`` references in the instruction.
    2. Delegate to the agent's execute_with_llm_orchestration().
    3. Capture any output artifacts (e.g. downloaded file paths).
    4. Store the result in the WorkflowContext under step.output_key.
    5. Return a result dict compatible with the existing UI rendering.
    """
    t0 = time.time()
    resolved_instruction = _resolve_instruction(step.instruction, ctx)

    logger.info(
        "NL step %d [%s]: %.120s…",
        step.step_num, step.agent, resolved_instruction,
    )

    executor = get_executor(step.agent)
    if executor is None:
        error_msg = f"No executor registered for agent '{step.agent}'"
        logger.error(error_msg)
        return {
            "step": step.step_num,
            "agent": step.agent,
            "tool": step.description or step.instruction[:60],
            "instruction": step.instruction,
            "status": "error",
            "error": error_msg,
            "result": None,
            "elapsed": time.time() - t0,
        }

    artifacts_out: Dict[str, Any] = {}
    try:
        raw_result = executor(
            user_query=resolved_instruction,
            agent_id=agent_id,
            artifacts_out=artifacts_out,
        )

        # Normalise result to string
        if isinstance(raw_result, dict):
            text = raw_result.get("message", str(raw_result))
            exec_status = raw_result.get("status", "success")
        else:
            text = str(raw_result)
            exec_status = "success"

        # Fallback: scan response text for file paths if not captured in artifacts
        if "file_path" not in artifacts_out:
            paths = _FILE_PATH_RE.findall(text)
            if paths:
                artifacts_out["file_path"] = paths[0]
                logger.debug("NL step %d: extracted file path from text: %s", step.step_num, paths[0])

        # Store structured result in context for downstream steps
        ctx.set(step.output_key, {"text": text, "artifacts": artifacts_out})

        logger.info(
            "NL step %d [%s] → %s (%.1fs)",
            step.step_num, step.agent, exec_status, time.time() - t0,
        )

        return {
            "step": step.step_num,
            "agent": step.agent,
            # Keep "tool" populated for backward-compat with existing UI renderer
            "tool": step.description or step.instruction[:60],
            "instruction": step.instruction,
            "status": exec_status,
            "result": {"message": text[:500], "artifacts": artifacts_out},
            "error": None,
            "elapsed": time.time() - t0,
        }

    except Exception as exc:
        logger.exception("NL step %d [%s] raised: %s", step.step_num, step.agent, exc)
        return {
            "step": step.step_num,
            "agent": step.agent,
            "tool": step.description or step.instruction[:60],
            "instruction": step.instruction,
            "status": "error",
            "result": None,
            "error": str(exc),
            "elapsed": time.time() - t0,
        }
