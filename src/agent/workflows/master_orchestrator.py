"""
MasterOrchestrator — natural-language planning + sub-agent delegation.

Architecture (scalable to N agents):
    1. plan_nl_workflow(command)
         → LLM sees only per-agent capability summaries (~10 tokens/agent),
           not individual tool signatures.
         → Produces NLWorkflowPlan: a list of {agent, natural-language instruction}.

    2. run_workflow(command, agent_ids)
         → For each NLWorkflowStep, calls the agent's own
           execute_with_llm_orchestration(instruction).
         → Each sub-agent runs its own ReAct loop with its own full tool list,
           its own memory, and its own context window.
         → The orchestrator only tracks: working_memory + collective_consciousness.

Scaling:
    Adding a new agent = one line in agent_registry.py.
    Orchestrator context stays constant regardless of agent count or tool count.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from src.agent.llm.llm_parser import get_llm_client
from src.agent.workflows.workflow_context import WorkflowContext, NLWorkflowPlan, NLWorkflowStep
from src.agent.workflows.agent_registry import get_capabilities_text, get_executor, registered_agents
from src.agent.workflows.nl_step_runner import run_nl_step
from src.agent.workflows import file_bridge as _file_bridge

logger = logging.getLogger("workflows")


# ---------------------------------------------------------------------------
# Multi-Agent ReAct loop
# ---------------------------------------------------------------------------

_MAX_REACT_ITERATIONS = 8


def _react_system_prompt() -> str:
    from pathlib import Path as _Path
    home = _Path.home()
    path_ctx = (
        f"\nSystem path context (use in instructions to the files agent):\n"
        f"  Home: {home} | Downloads: {home / 'Downloads'} | "
        f"Desktop: {home / 'Desktop'} | Documents: {home / 'Documents'}\n"
        f"Always pass full absolute paths when delegating to the files agent.\n"
    )
    caps = get_capabilities_text()
    return f"""You are a multi-agent workflow orchestrator. Satisfy the user's request by coordinating specialized agents.

Available agents:
{caps}
{path_ctx}
Each turn output exactly one JSON object — no markdown code fences:
{{
  "thought": "<reasoning: what has been done so far, what is still needed>",
  "action": "delegate_to_agent" | "final_answer",
  "params": {{
    "agent": "<agent_name>",              // delegate_to_agent only
    "instruction": "<NL task for agent>", // delegate_to_agent only
    "message": "<final response to user>"  // final_answer only
  }}
}}

Rules:
- Read each observation carefully before deciding the next step.
- If a step fails, decide whether to retry with a different approach, skip it, or report the error.
- Observations include the exact downloaded file paths — copy them literally into the next instruction.
- Write the final_answer message in friendly, markdown-formatted style (bold, bullets, emojis).
- Call final_answer ONLY when the user's full request is correctly and completely satisfied.
- Base final_answer strictly on what the observations report — never hallucinate results.
"""


def react_workflow(
    command: str,
    agent_ids: Dict[str, str],
    ctx: WorkflowContext,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Run the multi-agent ReAct loop.

    Each iteration the orchestrator LLM sees the original command plus all
    prior observations, then picks one of two actions:
      - delegate_to_agent(agent, instruction): call a sub-agent's ReAct loop
      - final_answer(message)              : emit the final user-facing response

    The loop adapts dynamically — it can retry failed steps, reorder tasks, or
    decide it's done early.  Sub-agents still run their own full ReAct loops.

    Returns:
        (steps_results, final_answer_text)
    """
    llm = get_llm_client()
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": _react_system_prompt()},
        {"role": "user",   "content": f"User request: {command}"},
    ]

    steps_results: List[Dict[str, Any]] = []
    step_counter = 0
    final_answer_text: Optional[str] = None

    for iteration in range(_MAX_REACT_ITERATIONS):
        logger.info("ReAct iteration %d/%d", iteration + 1, _MAX_REACT_ITERATIONS)

        # ── LLM reasoning turn ────────────────────────────────────────────
        try:
            response = llm.client.chat.completions.create(
                model=llm.model,
                messages=messages,
                temperature=0.2,
                max_tokens=800,
                timeout=40,
            )
            raw = _strip_code_fences(response.choices[0].message.content.strip())
        except Exception as exc:
            logger.error("ReAct LLM call failed at iteration %d: %s", iteration + 1, exc)
            break

        messages.append({"role": "assistant", "content": raw})

        # Parse JSON — tolerate minor wrapping
        try:
            turn = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            try:
                turn = json.loads(m.group(0)) if m else {}
            except Exception:
                turn = {}

        thought = turn.get("thought", "")
        action  = turn.get("action",  "")
        params  = turn.get("params",  {})

        logger.info(
            "ReAct [iter %d] action=%s  thought=%.120s",
            iteration + 1, action, thought,
        )

        # ── final_answer ──────────────────────────────────────────────────
        if action == "final_answer":
            final_answer_text = params.get("message", "✅ Workflow complete.")
            logger.info("ReAct final_answer after %d iteration(s)", iteration + 1)
            break

        # ── delegate_to_agent ─────────────────────────────────────────────
        elif action == "delegate_to_agent":
            agent_name  = params.get("agent", "").strip()
            instruction = params.get("instruction", "").strip()

            if not agent_name or not instruction:
                obs = "Error: delegate_to_agent requires non-empty 'agent' and 'instruction'."
                messages.append({"role": "user", "content": f"Observation: {obs}"})
                continue

            step_counter += 1
            t0 = time.time()
            executor = get_executor(agent_name)

            if executor is None:
                obs = (
                    f"Error: No agent named '{agent_name}' is registered. "
                    f"Available agents: {registered_agents()}"
                )
                steps_results.append({
                    "step": step_counter, "agent": agent_name,
                    "tool": instruction[:60], "instruction": instruction,
                    "status": "error", "result": None, "error": obs,
                    "elapsed": time.time() - t0,
                })
                messages.append({"role": "user", "content": f"Observation: {obs}"})
                continue

            artifacts_out: Dict[str, Any] = {}
            try:
                raw_result = executor(
                    user_query=instruction,
                    agent_id=agent_ids.get(agent_name),
                    artifacts_out=artifacts_out,
                )

                if isinstance(raw_result, dict):
                    text        = raw_result.get("message", str(raw_result))
                    exec_status = raw_result.get("status", "success")
                else:
                    text        = str(raw_result)
                    exec_status = "success"

                # Rich observation — LLM copies the file path literally into the
                # next instruction (no token substitution needed in ReAct mode)
                obs_parts = [
                    f"Agent '{agent_name}' completed successfully.",
                    text[:800],
                ]
                if artifacts_out.get("file_path"):
                    obs_parts.append(
                        f"Downloaded file local path: {artifacts_out['file_path']}"
                    )
                observation = "\n".join(obs_parts)

                steps_results.append({
                    "step": step_counter, "agent": agent_name,
                    "tool": instruction[:60], "instruction": instruction,
                    "status": exec_status,
                    "result": {"message": text[:500], "artifacts": artifacts_out},
                    "error": None, "elapsed": time.time() - t0,
                })

            except Exception as exc:
                logger.exception(
                    "ReAct delegate error [%s] iter %d: %s", agent_name, iteration + 1, exc
                )
                observation = f"Agent '{agent_name}' raised an error: {exc}"
                steps_results.append({
                    "step": step_counter, "agent": agent_name,
                    "tool": instruction[:60], "instruction": instruction,
                    "status": "error", "result": None,
                    "error": str(exc), "elapsed": time.time() - t0,
                })

            messages.append({"role": "user", "content": f"Observation: {observation}"})

        # ── unknown action ────────────────────────────────────────────────
        else:
            obs = (
                f"Error: Unknown action '{action}'. "
                "You must respond with 'delegate_to_agent' or 'final_answer'."
            )
            messages.append({"role": "user", "content": f"Observation: {obs}"})

    # Max iterations exhausted without final_answer
    if final_answer_text is None:
        logger.warning(
            "ReAct loop hit max iterations (%d) without final_answer", _MAX_REACT_ITERATIONS
        )
        summary = _summarize_results(steps_results) if steps_results else "No steps were executed."
        final_answer_text = f"⚠️ Workflow reached its iteration limit.\n\n{summary}"

    return steps_results, final_answer_text


# ---------------------------------------------------------------------------
# Planning prompt — compact: ~10 tokens/agent regardless of tool count
# Dynamically built from agent_registry so new agents auto-appear here.
# ---------------------------------------------------------------------------

def _build_planning_prompt() -> str:
    caps = get_capabilities_text()
    return f"""You are a workflow orchestrator for a multi-agent AI system.

Given a user command, produce a minimal step-by-step plan as a JSON array.
Each step contains a NATURAL LANGUAGE instruction for exactly one agent.

Available agents:
{caps}

SPECIAL CONTEXT VALUES always available in instructions:
- {{__user_email__}} — the authenticated user's own Gmail address.
  Use it when the user says "email me", "send it to me", "email myself", etc.

Each step schema:
{{
  "step_num": <int, starting at 1>,
  "agent": "<agent_name>",
  "instruction": "<natural language task for this agent — be specific>",
  "output_key": "<snake_case key to store the result>",
  "description": "<one-line UI label>"
}}

Rules:
- Write instructions the way you would write them to a capable human assistant.
- For file handoff between agents: tell the first agent to download and report
  the local path, then use {{output_key.file_path}} in the second agent's instruction.
  Example step 2 instruction: "Attach the file at {{downloaded_file.file_path}} and
  send it to bob@example.com with subject \\"Requested file\\"."
- Keep the plan minimal — only generate steps that are directly needed.
- Return ONLY the JSON array, no surrounding text or code fences.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_email() -> Optional[str]:
    """Return the authenticated Gmail user's email address, or None on failure."""
    try:
        from src.email.gmail_auth import get_gmail_service
        svc = get_gmail_service()
        profile = svc.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception as exc:
        logger.warning("Could not fetch user email: %s", exc)
        return None


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences from an LLM response."""
    if "```" in raw:
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) >= 2 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def plan_nl_workflow(command: str) -> Optional[NLWorkflowPlan]:
    """
    Ask the LLM to produce a NLWorkflowPlan for *command*.

    Context cost: ~10 tokens/agent (capability summaries only, not tool schemas).
    Supports any number of registered agents without touching this function.
    """
    llm = get_llm_client()
    system_prompt = _build_planning_prompt()
    logger.info("NL planning workflow for: %s", command)

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User command: {command}"},
            ],
            temperature=0.2,
            max_tokens=1500,
            timeout=40,
        )
        raw = _strip_code_fences(response.choices[0].message.content.strip())
        steps_data: List[Dict[str, Any]] = json.loads(raw)
        if not isinstance(steps_data, list):
            raise ValueError("LLM returned non-list plan")

        steps = [
            NLWorkflowStep(
                step_num=s.get("step_num", idx + 1),
                agent=s["agent"],
                instruction=s["instruction"],
                output_key=s.get("output_key", f"step{idx + 1}_result"),
                description=s.get("description", ""),
            )
            for idx, s in enumerate(steps_data)
        ]

        agents_needed = sorted({s.agent for s in steps})
        plan = NLWorkflowPlan(command=command, agents_needed=agents_needed, steps=steps)
        logger.info("NL plan: %d steps for agents: %s", len(steps), agents_needed)
        return plan

    except Exception as exc:
        logger.exception("NL workflow planning failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _summarize_results(steps_results: List[Dict[str, Any]]) -> str:
    """Build a human-readable summary of completed steps."""
    lines = []
    for r in steps_results:
        label = r.get("description") or r.get("tool") or r.get("instruction", "")[:60]
        if r["status"] == "success":
            lines.append(f"✅ Step {r['step']}: [{r['agent']}] {label} — completed")
        else:
            lines.append(f"❌ Step {r['step']}: {label} — {r.get('error', 'failed')}")
    return "\n".join(lines)


def run_workflow(
    command: str,
    agent_ids: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Plan and execute a multi-agent workflow using natural-language sub-agent delegation.

    The orchestrator:
      1. Plans using compact agent capability descriptions (~10 tokens/agent).
      2. Calls each sub-agent's execute_with_llm_orchestration() with a natural-
         language instruction. Each sub-agent runs its own ReAct loop.
      3. Resolves {output_key.field} cross-step references (e.g. file paths).
      4. Returns the same result dict format as before for UI compatibility.

    Args:
        command:    The natural language command from the user.
        agent_ids:  Optional mapping of agent type → agent_id string for memory.

    Returns:
        {"status", "summary", "steps", "elapsed", "plan"}
    """
    ctx = WorkflowContext(command=command)
    agent_ids = agent_ids or {}

    # Pre-populate authenticated user email
    user_email = _get_user_email()
    if user_email:
        ctx.set("__user_email__", user_email)
        logger.info("Workflow context: __user_email__ = %s", user_email)
    else:
        logger.warning("Could not resolve user email — 'email me' commands may fail")

    # ── ReAct loop ────────────────────────────────────────────────────────
    steps_results, final_answer_text = react_workflow(command, agent_ids, ctx)

    # Cleanup
    _file_bridge.cleanup_all()
    ctx.cleanup()

    # Build response
    success_count = sum(1 for r in steps_results if r["status"] == "success")
    total         = len(steps_results)
    failed        = any(r["status"] == "error" for r in steps_results)
    status        = "error" if (failed and success_count == 0) else ("partial" if failed else "success")
    summary       = _summarize_results(steps_results) if steps_results else final_answer_text
    elapsed       = ctx.elapsed_seconds()

    logger.info(
        "ReAct workflow complete: %s (%d/%d steps in %.1fs)",
        status, success_count, total, elapsed,
    )

    return {
        "status": status,
        "summary": summary,
        "steps": steps_results,
        "elapsed": elapsed,
        "plan": None,          # ReAct is dynamic — no upfront plan object
        "final_answer": final_answer_text,  # LLM-composed; rendered directly by app
    }
