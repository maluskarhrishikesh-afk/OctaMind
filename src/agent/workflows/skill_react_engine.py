"""
Shared ReACT execution engine for individual skill orchestrators.

Every skill (email, drive, files, calendar, …) runs the same loop:

  1. LLM received the user query + available tool descriptions.
  2. Each turn the LLM emits ONE JSON action:
       {"thought": "...", "action": "call_tool", "params": {"tool": "<name>", "kwargs": {...}}}
     or
       {"thought": "...", "action": "final_answer", "params": {"message": "<text>"}}
  3. Tool call result is fed back as an observation.
  4. Loop ends on final_answer or max_iterations.

Usage
-----
    from src.agent.workflows.skill_react_engine import run_skill_react

    result = run_skill_react(
        skill_name="email",
        skill_context="You are a Gmail skill …",
        tool_map={"send_email": send_email_fn, ...},
        tool_docs="send_email(to, subject, message) – sends an email\\n...",
        user_query="Send a test email to alice@example.com",
        artifacts_out={},     # optional mutable dict for file-path handoffs
        max_iterations=6,
    )
    # result = {"status": "success"|"error", "message": "...", "action": "react_response"}
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("workflows.skill_react")

_MAX_ITERATIONS_DEFAULT = 6


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

def run_skill_react(
    skill_name: str,
    skill_context: str,
    tool_map: Dict[str, Callable],
    tool_docs: str,
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]] = None,
    max_iterations: int = _MAX_ITERATIONS_DEFAULT,
) -> Dict[str, Any]:
    """
    Execute a single-skill ReACT loop.

    Parameters
    ----------
    skill_name:     Human-readable skill label used in log lines.
    skill_context:  System-level instructions specific to this skill.
    tool_map:       Mapping of tool_name → callable (no *args – only **kwargs).
    tool_docs:      Concise text listing every tool name + signature + purpose.
    user_query:     Natural-language instruction from the master orchestrator.
    artifacts_out:  Mutable dict; tool results are merged in so file paths can
                    be handed back to the master orchestrator.
    max_iterations: Safety cap on the ReACT loop (default 6).

    Returns
    -------
    dict with keys: status, message, action ("react_response")
    """
    from src.agent.llm.llm_parser import get_llm_client

    if artifacts_out is None:
        artifacts_out = {}

    llm = get_llm_client()
    _t0 = time.time()
    _llm_calls = 0
    _prompt_tokens = 0
    _completion_tokens = 0

    system_prompt = _build_system_prompt(skill_context, tool_docs)
    messages: list[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": f"Task: {user_query}"},
    ]

    final_message: Optional[str] = None
    status = "success"

    logger.info(
        "┌─ [%s] Skill ReAct START  query=%.100s  max_iters=%d",
        skill_name, user_query, max_iterations,
    )

    for iteration in range(max_iterations):
        logger.info("│  ▶ [%s] Iteration %d/%d", skill_name, iteration + 1, max_iterations)

        # ── LLM call ──────────────────────────────────────────────────────
        try:
            response = llm.client.chat.completions.create(
                model=llm.model,
                messages=messages,
                temperature=0.1,
                max_tokens=800,
            )
            raw = _strip_fences(response.choices[0].message.content.strip())
            _llm_calls += 1
            if hasattr(response, "usage") and response.usage:
                _prompt_tokens     += getattr(response.usage, "prompt_tokens", 0)
                _completion_tokens += getattr(response.usage, "completion_tokens", 0)
        except Exception as exc:
            logger.error("│  ✗ [%s] LLM call failed at iter %d: %s", skill_name, iteration + 1, exc)
            final_message = f"❌ LLM error: {exc}"
            status = "error"
            break

        messages.append({"role": "assistant", "content": raw})

        # ── Parse JSON ────────────────────────────────────────────────────
        turn = _parse_json(raw)
        thought = turn.get("thought", "")
        action  = turn.get("action",  "")
        params  = turn.get("params",  {})

        logger.info(
            "│    [%s] action=%-16s  thought=%.90s",
            skill_name, action, thought,
        )

        # ── final_answer ──────────────────────────────────────────────────
        if action == "final_answer":
            _elapsed = time.time() - _t0
            final_message = params.get("message", "✅ Done.")
            logger.info(
                "└─ [%s] Skill ReAct DONE ✅  iters=%d/%d  llm_calls=%d  "
                "prompt_tokens=%d  completion_tokens=%d  total_tokens=%d  elapsed=%.2fs",
                skill_name, iteration + 1, max_iterations,
                _llm_calls, _prompt_tokens, _completion_tokens,
                _prompt_tokens + _completion_tokens, _elapsed,
            )
            break

        # ── call_tool ─────────────────────────────────────────────────────
        elif action == "call_tool":
            tool_name = params.get("tool", "").strip()
            kwargs    = params.get("kwargs", {})

            if tool_name not in tool_map:
                obs = (
                    f"Error: unknown tool '{tool_name}'. "
                    f"Available tools: {list(tool_map.keys())}"
                )
                logger.warning("│  ⚠ [%s] Unknown tool '%s'", skill_name, tool_name)
                messages.append({"role": "user", "content": f"Observation: {obs}"})
                continue

            callable_fn = tool_map[tool_name]
            try:
                logger.info("│    [%s] → calling tool=%s  kwargs=%s", skill_name, tool_name, str(kwargs)[:120])
                result = callable_fn(**kwargs) if kwargs else callable_fn()
                # Merge any file path into artifacts_out for cross-agent handoff
                if isinstance(result, dict):
                    for key in ("file_path", "local_path", "path"):
                        if result.get(key):
                            artifacts_out[key] = result[key]
                obs = _format_observation(tool_name, result)
                logger.info("│    [%s] ✔ tool=%s  obs=%.120s", skill_name, tool_name, obs)
            except Exception as exc:
                logger.exception("│    [%s] ✗ tool=%s raised: %s", skill_name, tool_name, exc)
                obs = f"Error calling {tool_name}: {exc}"
                status = "error"

            messages.append({"role": "user", "content": f"Observation: {obs}"})

        # ── unknown action ────────────────────────────────────────────────
        else:
            obs = (
                f"Error: unknown action '{action}'. "
                "Use 'call_tool' or 'final_answer'."
            )
            logger.warning("│  ⚠ [%s] Unknown action '%s' at iter %d", skill_name, action, iteration + 1)
            messages.append({"role": "user", "content": f"Observation: {obs}"})

    # Exhausted iterations
    if final_message is None:
        _elapsed = time.time() - _t0
        logger.warning(
            "└─ [%s] Skill ReAct TIMEOUT ⚠  iters=%d/%d  llm_calls=%d  "
            "prompt_tokens=%d  completion_tokens=%d  total_tokens=%d  elapsed=%.2fs",
            skill_name, max_iterations, max_iterations,
            _llm_calls, _prompt_tokens, _completion_tokens,
            _prompt_tokens + _completion_tokens, _elapsed,
        )
        final_message = f"⚠️ {skill_name.title()} skill reached its iteration limit without completing."
        status = "error"

    return {
        "status": status,
        "message": final_message,
        "action": "react_response",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(skill_context: str, tool_docs: str) -> str:
    return f"""{skill_context}

You have access to the following tools:
{tool_docs}

Each turn you MUST output exactly ONE JSON object — no markdown code fences:
{{
  "thought": "<reasoning about what to do next>",
  "action": "call_tool" | "final_answer",
  "params": {{
    "tool": "<tool_name>",   // only when action = call_tool
    "kwargs": {{}}           // keyword arguments for the tool
    // OR when action = final_answer:
    "message": "<friendly markdown response to the user>"
  }}
}}

Rules:
- Always include "thought" — explain your reasoning before acting.
- Use call_tool to gather information or perform operations.
- Use final_answer ONLY when the task is fully complete or you have all needed info.
- Write final_answer messages in friendly, markdown-formatted style (bold, bullets, emojis).
- If a tool returns an error, decide whether to retry, try a different approach, or report the error.
- Never hallucinate tool names or results.
"""


def _strip_fences(raw: str) -> str:
    """Remove optional ```json ... ``` fences from LLM output."""
    if "```" in raw:
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) >= 2 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _parse_json(raw: str) -> dict:
    """Parse JSON from raw string; tolerates minor wrapping."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def _format_observation(tool_name: str, result: Any) -> str:
    """Convert a tool result into a short, LLM-readable observation string."""
    if result is None:
        return f"{tool_name} returned nothing."
    if isinstance(result, dict):
        status = result.get("status", "")
        message = result.get("message", "")
        if status == "error":
            return f"{tool_name} failed: {result.get('error', message)}"
        # Return the first 600 chars of the JSON
        return str(result)[:600]
    if isinstance(result, list):
        count = len(result)
        preview = str(result[:3])[:400]
        return f"{tool_name} returned {count} item(s). Preview: {preview}"
    return str(result)[:600]
