"""
MasterOrchestrator — LLM-based planning + sequential step execution for
multi-agent workflows.

Flow:
    1. plan_workflow(command)  → LLM produces a list of WorkflowSteps (JSON)
    2. run_workflow(command, agent_ids) → execute steps, collect results, cleanup

The LLM receives a combined Drive+Email tools description and returns a JSON
array of steps, each specifying which agent/tool to call and with what params.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.agent.llm.llm_parser import get_llm_client
from src.agent.workflows.workflow_context import WorkflowContext, WorkflowPlan, WorkflowStep
from src.agent.workflows.step_runner import run_step
from src.agent.workflows import file_bridge as _file_bridge

logger = logging.getLogger("workflows")

# ---------------------------------------------------------------------------
# Combined tools description for the planning LLM prompt
# ---------------------------------------------------------------------------
_PLANNING_TOOLS = """
DRIVE AGENT tools (agent: "drive"):
- search_files(query: str, max_results: int=20) — search Drive by name/content
- list_files(max_results: int=20, query: str='', folder_id: str='root') — list files
- get_file_info(file_id: str) — get file metadata
- download_file(file_id: str, destination: str=None) — download file to disk
- upload_file(local_path: str, name: str=None, folder_id: str=None) — upload file
- create_folder(name: str, parent_id: str=None) — create folder
- move_file(file_id: str, destination_folder_id: str) — move file
- copy_file(file_id: str, name: str=None, folder_id: str=None) — copy file
- trash_file(file_id: str) — delete file
- share_file(file_id: str, email: str, role: str='reader') — share with someone
- summarize_file(file_id: str) — AI summary of a file
- get_storage_quota() — storage usage
- storage_breakdown() — breakdown by file type
- list_large_files(min_size_mb: float=50) — large files
- generate_drive_report() — full Drive health report

EMAIL AGENT tools (agent: "email"):
- send_email(to: str, subject: str, body: str, attachments: list=None) — send email
- list_emails(query: str='', max_results: int=10) — list/search emails
- get_todays_emails(max_results: int=10) — today's emails
- get_inbox_count() — inbox message count
- extract_action_items(message_id: str) — extract tasks from email
- get_all_pending_actions(max_emails: int=20) — all pending tasks
- generate_reply_suggestions(message_id: str) — AI reply suggestions
- create_draft(to: str, subject: str, body: str) — save draft
- list_attachments(message_id: str) — list email attachments
- download_attachment(message_id: str, attachment_id: str, save_path: str=None) — download attachment
- get_email_stats() — email statistics
- detect_urgent_emails(max_results: int=10) — find urgent emails
- export_contacts() — export frequent contacts

PARAMETER REFERENCES:
You may reference the output of a previous step using "{output_key}" syntax.
For example, if step 1 stores its result as output_key "found_file",
step 2 can use {"file_id": "{found_file}"} to pass that value forward.
The system resolves these references automatically at runtime.
"""

_PLANNING_SYSTEM_PROMPT = """You are a workflow planner for a multi-agent AI system.

Given a user command that requires BOTH a Google Drive agent AND a Gmail agent,
produce a step-by-step execution plan as a JSON array.

Each step must follow this schema:
{
  "step_num": <integer, starting at 1>,
  "agent": "<drive|email>",
  "tool": "<tool_name>",
  "params": { <param_name>: <value_or_reference> },
  "output_key": "<snake_case_key_to_store_result>",
  "description": "<one sentence explaining what this step does>"
}

Rules:
- Use "{output_key}" syntax to reference previous step outputs in params.
- Keep steps minimal — only include what is necessary.
- Use realistic param values inferred from the user command.
- Return ONLY the JSON array, no extra text.

Available tools:
""" + _PLANNING_TOOLS


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def plan_workflow(command: str) -> Optional[WorkflowPlan]:
    """
    Ask the LLM to produce a WorkflowPlan for *command*.

    Returns a WorkflowPlan on success, or None if planning fails.
    """
    llm = get_llm_client()
    logger.info("Planning workflow for: %s", command)

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": _PLANNING_SYSTEM_PROMPT},
                {"role": "user", "content": f"User command: {command}"},
            ],
            temperature=0.2,
            max_tokens=800,
            timeout=40,
        )
        raw = response.choices[0].message.content.strip()
        # Strip code fences if any
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        steps_data: List[Dict[str, Any]] = json.loads(raw)
        if not isinstance(steps_data, list):
            raise ValueError("LLM returned non-list plan")

        steps = [
            WorkflowStep(
                step_num=s.get("step_num", idx + 1),
                agent=s["agent"],
                tool=s["tool"],
                params=s.get("params", {}),
                output_key=s.get("output_key", f"step{idx + 1}_result"),
                description=s.get("description", ""),
            )
            for idx, s in enumerate(steps_data)
        ]

        plan = WorkflowPlan(command=command, agents_needed=[], steps=steps)
        # Derive agents_needed from steps
        plan.agents_needed = sorted({s.agent for s in steps})
        logger.info("Planned %d steps: %s", len(steps), [s.tool for s in steps])
        return plan

    except Exception as exc:
        logger.exception("Workflow planning failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _summarize_results(steps_results: List[Dict[str, Any]]) -> str:
    """Build a human-readable summary of completed steps."""
    lines = []
    for r in steps_results:
        if r["status"] == "success":
            lines.append(f"✅ Step {r['step']}: [{r['agent']}] {r['tool']} — completed")
        else:
            lines.append(f"❌ Step {r['step']}: {r.get('tool', '?')} — {r.get('error', 'failed')}")
    return "\n".join(lines)


def run_workflow(
    command: str,
    agent_ids: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Plan and execute a multi-agent workflow.

    Args:
        command:    The natural language command from the user.
        agent_ids:  Optional mapping of agent type → agent_id strings
                    (e.g. {"drive": "abc123", "email": "xyz789"}).
                    Not used for direct tool calls yet but logged for tracing.

    Returns:
        {
          "status":   "success" | "partial" | "error",
          "summary":  str,
          "steps":    list of per-step result dicts,
          "elapsed":  float (seconds),
          "plan":     WorkflowPlan | None,
        }
    """
    ctx = WorkflowContext()
    agent_ids = agent_ids or {}

    # Step 1 — plan
    plan = plan_workflow(command)
    if plan is None:
        return {
            "status": "error",
            "summary": "Could not create a workflow plan for this command.",
            "steps": [],
            "elapsed": ctx.elapsed_seconds(),
            "plan": None,
        }

    # Step 2 — execute steps sequentially
    steps_results: List[Dict[str, Any]] = []
    failed = False

    for step in plan.steps:
        logger.info("Executing step %d/%d: %s.%s", step.step_num, len(plan.steps), step.agent, step.tool)
        result = run_step(step, ctx)
        steps_results.append(result)

        if result["status"] == "error":
            logger.warning("Step %d failed — stopping workflow", step.step_num)
            failed = True
            break  # abort on first failure

    # Step 3 — cleanup temp files
    _file_bridge.cleanup_all()
    ctx.cleanup()

    # Step 4 — build response
    success_count = sum(1 for r in steps_results if r["status"] == "success")
    total = len(plan.steps)

    if failed and success_count == 0:
        status = "error"
    elif failed:
        status = "partial"
    else:
        status = "success"

    summary = _summarize_results(steps_results)
    elapsed = ctx.elapsed_seconds()

    logger.info(
        "Workflow complete: %s (%d/%d steps in %.1fs)",
        status,
        success_count,
        total,
        elapsed,
    )

    return {
        "status": status,
        "summary": summary,
        "steps": steps_results,
        "elapsed": elapsed,
        "plan": plan,
    }
