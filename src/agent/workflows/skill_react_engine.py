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
                # Always stored under "file_path" so {step_id.file_path} tokens resolve
                if isinstance(result, dict):
                    for key in ("file_path", "local_path", "path", "archive"):
                        if result.get(key):
                            artifacts_out["file_path"] = result[key]
                            break
                    # Also extract from search result lists (e.g. search_by_name returns
                    # {"results": [{"path": "...", "name": ...}], "count": N})
                    if not artifacts_out.get("file_path"):
                        first_results = result.get("results", [])
                        if isinstance(first_results, list) and first_results:
                            fp = first_results[0].get("file_path") or first_results[0].get("path")
                            if fp:
                                artifacts_out["file_path"] = fp
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
        "status":    status,
        "message":   final_message,
        "action":    "react_response",
        "llm_calls": _llm_calls,
        "file_path": artifacts_out.get("file_path", ""),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(skill_context: str, tool_docs: str) -> str:
    return f"""{skill_context}

You have access to the following tools:
{tool_docs}

Each turn output exactly ONE JSON object — NO markdown fences, NO extra text.

To call a tool:
{{
  "thought": "<your reasoning>",
  "action": "call_tool",
  "params": {{
    "tool": "<tool_name>",
    "kwargs": {{"<param1>": "<value1>", "<param2>": "<value2>"}}
  }}
}}

To give the final answer when the task is fully complete:
{{
  "thought": "<your reasoning>",
  "action": "final_answer",
  "params": {{
    "message": "<friendly markdown response to the user>"
  }}
}}

Example — calling quick_add_event with the required 'text' argument:
{{
  "thought": "I will use quick_add_event to create the calendar event.",
  "action": "call_tool",
  "params": {{
    "tool": "quick_add_event",
    "kwargs": {{"text": "Gym Session today at 8 PM for 1 hour"}}
  }}
}}

Example — calling create_event with explicit arguments:
{{
  "thought": "I will create the event with explicit ISO 8601 date/time.",
  "action": "call_tool",
  "params": {{
    "tool": "create_event",
    "kwargs": {{"title": "Team Meeting", "start": "2026-03-01T10:00:00+05:30", "end": "2026-03-01T11:00:00+05:30"}}
  }}
}}

Rules:
- Always include "thought" — explain your reasoning before acting.
- kwargs MUST include all required arguments with real values. NEVER output empty kwargs {{}}.
- Use call_tool to gather information or perform operations.
- Use final_answer ONLY when the task is fully complete.
- Write final_answer messages in friendly, markdown-formatted style (bold, bullets, emojis).
- If a tool returns an error, decide whether to retry, try a different approach, or report the error.
- IMPORTANT: Always output valid JSON. Use lowercase boolean values: true and false (NOT Python-style True or False).
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
    """Parse JSON from raw string; tolerates Python-style bools and minor wrapping."""
    # Some models emit Python literals (True/False/None) instead of JSON (true/false/null)
    normalized = re.sub(r'\bTrue\b', 'true', raw)
    normalized = re.sub(r'\bFalse\b', 'false', normalized)
    normalized = re.sub(r'\bNone\b', 'null', normalized)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', normalized, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def _format_observation(tool_name: str, result: Any) -> str:
    """Convert a tool result into an LLM-readable observation string.

    Lists are shown in full (not just the first 3 items) so the LLM can act
    on every element returned — e.g. all email IDs, not just the first two.
    Caps are generous enough to avoid losing information while still keeping
    the prompt manageable.
    """
    if result is None:
        return f"{tool_name} returned nothing."
    if isinstance(result, dict):
        status = result.get("status", "")
        message = result.get("message", "")
        if status == "error":
            return f"{tool_name} failed: {result.get('error', message)}"
        # Prefer structured JSON for dicts so IDs / fields are easy to read
        try:
            formatted = json.dumps(result, indent=2, default=str)
        except Exception:
            formatted = str(result)
        return formatted[:1200]
    if isinstance(result, list):
        count = len(result)
        # Show ALL items — truncate total length rather than item count.
        # Previously only showed result[:3] which caused the LLM to lose
        # track of items 4+ and loop over the same earlier items.
        try:
            full_repr = json.dumps(result, indent=2, default=str)
        except Exception:
            full_repr = str(result)
        preview = full_repr[:1500]
        if len(full_repr) > 1500:
            preview += f"\n… ({count} items total, truncated)"
        return f"{tool_name} returned {count} item(s):\n{preview}"
    return str(result)[:1200]
