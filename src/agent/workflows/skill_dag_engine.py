"""
Sub-agent DAG execution engine.

Instead of a multi-turn ReAct loop (one LLM call per tool step),
``run_skill_dag()`` uses just **two** LLM calls for any task:

  1. **Plan** – produce a structured, ordered list of tool steps as JSON (1 call).
  2. **Synthesize** – turn all accumulated tool results into a friendly final
     answer (1 call).

Between those two calls every tool is executed deterministically — zero
orchestration LLM calls regardless of how many tools the task requires.

Typical LLM-call savings versus the ReAct loop
-----------------------------------------------
| Task steps | ReAct calls | DAG calls | Savings |
|:---:|:---:|:---:|:---:|
| 1 | 2–3 | 2 | ~0% |
| 2 | 3–4 | 2 | ~40% |
| 3 | 4–6 | 2 | ~55% |
| 5 | 6–10 | 2 | ~70% |

The function falls back gracefully to ``run_skill_react()`` when planning
fails or the plan contains unknown tools — so correctness is never
sacrificed.

Token substitution in kwargs
-----------------------------
Kwargs values can reference prior step results with ``{step_id}`` or
``{step_id.field}`` tokens:

    "kwargs": {"message_id": "{s1.results.0.id}"}

The resolver walks dot-separated paths through the nested dict/list result
of the referenced step.

Session state tokens
--------------------
Kwargs values can also reference the parsed ## Session State block with
``{__session__.field}`` tokens.  If the resolved value is a Python list
(e.g. last_found_paths) the **entire kwarg** is replaced with the real list
object — not a stringified version.  This lets the LLM plan reference up to
hundreds of file paths without embedding them verbatim in the JSON plan:

    "kwargs": {"file_paths": "{__session__.last_found_paths}", "destination": "C:\\..."}

Usage
-----
    from src.agent.workflows.skill_dag_engine import run_skill_dag

    result = run_skill_dag(
        skill_name="email",
        skill_context="You are a Gmail skill …",
        tool_map={"list_emails": list_emails_fn, ...},
        tool_docs="list_emails(query, max_results) – …",
        user_query="List today's emails and send me a summary",
        artifacts_out={},
    )
    # result = {"status": "success"|"error", "message": "...", "action": "react_response",
    #           "llm_calls": 2}
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("workflows.skill_dag")

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _extract_session_state(user_query: str) -> Dict[str, Any]:
    """Parse the optional '## Session State' JSON block appended to the user query.

    Returns a dict (possibly empty) with keys like last_found_paths,
    last_found_folder, last_found_file_path, etc.
    """
    marker = "## Session State"
    if marker not in user_query:
        return {}
    raw = user_query.split(marker, 1)[1].strip()
    # The block is the JSON object that follows the marker
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        # Try to find just the first {...} block
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return {}


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def run_skill_dag(
    skill_name: str,
    skill_context: str,
    tool_map: Dict[str, Callable],
    tool_docs: str,
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a skill task using a two-call DAG approach.

    Parameters
    ----------
    skill_name:    Human-readable skill label used in log lines.
    skill_context: System-level instructions specific to this skill.
    tool_map:      Mapping of tool_name → callable (keyword args only).
    tool_docs:     Concise text listing every tool name + signature + purpose.
    user_query:    Natural-language instruction from the master orchestrator.
    artifacts_out: Mutable dict; tool results (file paths etc.) are merged
                   in for cross-agent handoff.

    Returns
    -------
    dict with keys: status, message, action (``"react_response"``), llm_calls
    """
    from src.agent.workflows.skill_react_engine import run_skill_react  # local import to avoid circular deps

    if artifacts_out is None:
        artifacts_out = {}

    t0 = time.time()
    llm_calls = 0

    # ── Extract session state from enriched query (## Session State block) ──
    # Used to resolve {__session__.field} tokens in LLM-planned kwargs.
    session_vars = _extract_session_state(user_query)
    if session_vars:
        logger.debug("│  [%s] Session state extracted: %s", skill_name, str(session_vars)[:200])

    logger.info("┌─ [%s] Skill DAG START  query=%.100s", skill_name, user_query)

    # ── Step 1: Planning call ──────────────────────────────────────────────
    plan, plan_calls = _plan_steps(skill_name, skill_context, tool_docs, tool_map, user_query)
    llm_calls += plan_calls

    if plan is None:
        logger.warning(
            "│  ⚠ [%s] DAG planning failed — falling back to ReAct", skill_name
        )
        result = run_skill_react(
            skill_name=skill_name,
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
        result["llm_calls"] = result.get("llm_calls", 0) + llm_calls
        result["_dag_used"] = False
        return result

    logger.info("│  ✔ [%s] Plan contains %d step(s)", skill_name, len(plan))

    # ── Step 2: Deterministic tool execution (0 LLM calls) ────────────────
    step_results: Dict[str, Any] = {}
    execution_error = False

    for step in plan:
        step_id   = step["id"]
        tool_name = step["tool"]
        raw_kwargs = step.get("kwargs", {})

        # Resolve {previous_step} and {__session__.field} tokens in kwargs
        kwargs = _resolve_kwargs(raw_kwargs, step_results, session_vars)

        logger.info(
            "│    [%s] step=%s  tool=%s  kwargs=%s",
            skill_name, step_id, tool_name, str(kwargs)[:120],
        )

        callable_fn = tool_map.get(tool_name)
        if callable_fn is None:
            obs = f"Error: unknown tool '{tool_name}'. Step {step_id} skipped."
            logger.warning("│  ⚠ [%s] %s", skill_name, obs)
            step_results[step_id] = {"status": "error", "message": obs}
            execution_error = True
            continue

        try:
            result_raw = callable_fn(**kwargs) if kwargs else callable_fn()
            step_results[step_id] = result_raw

            # If the tool itself returned status:error, treat this step as failed.
            # This prevents downstream steps from receiving unresolved artifact tokens.
            if isinstance(result_raw, dict) and result_raw.get("status") == "error":
                logger.warning(
                    "│    [%s] ✗ step=%s tool=%s returned error: %s",
                    skill_name, step_id, tool_name,
                    result_raw.get("message", "")[:120],
                )
                execution_error = True
            else:
                # Propagate file paths into artifacts_out
                if isinstance(result_raw, dict):
                    for key in ("file_path", "local_path", "path", "archive"):
                        if result_raw.get(key):
                            artifacts_out["file_path"] = result_raw[key]
                            break
                    if not artifacts_out.get("file_path"):
                        for item in result_raw.get("results", []):
                            fp = (
                                item.get("file_path") or item.get("path")
                                if isinstance(item, dict) else None
                            )
                            if fp:
                                artifacts_out["file_path"] = fp
                                break
                    # Also collect ALL search result paths so the next turn's
                    # session state can populate last_found_paths / last_found_folder.
                    all_result_paths = [
                        item.get("path") or item.get("file_path")
                        for item in result_raw.get("results", [])
                        if isinstance(item, dict)
                        and (item.get("path") or item.get("file_path"))
                    ]
                    if all_result_paths:
                        existing = artifacts_out.get("found_paths", [])
                        artifacts_out["found_paths"] = existing + all_result_paths
                        # ── Auto-save manifest so the next turn can copy ALL found
                        #    files reliably, regardless of session-state size limits.
                        try:
                            from src.files.features.file_ops import save_search_manifest  # noqa: PLC0415
                            save_search_manifest(artifacts_out["found_paths"])
                            logger.info(
                                "│    [%s] manifest saved (%d paths)",
                                skill_name, len(artifacts_out["found_paths"]),
                            )
                        except Exception as _me:
                            logger.warning("│    [%s] manifest save failed: %s", skill_name, _me)

                logger.info("│    [%s] ✔ step=%s succeeded", skill_name, step_id)
        except Exception as exc:
            logger.exception("│    [%s] ✗ step=%s tool=%s raised: %s", skill_name, step_id, tool_name, exc)
            step_results[step_id] = {"status": "error", "message": str(exc)}
            execution_error = True

    # ── Step 3: Synthesis call (1 LLM call) ───────────────────────────────
    final_message, synth_calls = _synthesize(
        skill_name, skill_context, user_query, plan, step_results
    )
    llm_calls += synth_calls

    elapsed = time.time() - t0
    status = "error" if execution_error else "success"

    logger.info(
        "└─ [%s] Skill DAG DONE ✅  steps=%d  llm_calls=%d  elapsed=%.2fs  dag_used=True",
        skill_name, len(plan), llm_calls, elapsed,
    )

    return {
        "status":      status,
        "message":     final_message,
        "action":      "react_response",
        "llm_calls":   llm_calls,
        "_dag_used":   True,
        "file_path":   artifacts_out.get("file_path", ""),
        "found_paths": artifacts_out.get("found_paths", []),
    }


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def _plan_steps(
    skill_name: str,
    skill_context: str,
    tool_docs: str,
    tool_map: Dict[str, Callable],
    user_query: str,
) -> tuple[Optional[List[Dict[str, Any]]], int]:
    """
    Ask the LLM to produce an ordered list of tool-call steps.

    Returns (plan_list, llm_call_count).  plan_list is None on failure.
    """
    from src.agent.llm.llm_parser import get_llm_client

    llm = get_llm_client()

    system_prompt = f"""{skill_context}

You are planning tool calls to fulfill the user's request.

Available tools:
{tool_docs}

Output a JSON array — no markdown fences, no extra text — where each element is:
{{
  "id": "<short unique id, e.g. s1, s2, …>",
  "tool": "<exact tool name from the list above>",
  "kwargs": {{"<param>": "<concrete value>"}},
  "depends_on": ["<id of step whose output this step needs>"],
  "description": "<one sentence: what this step does>"
}}

Rules:
- Use ONLY tools listed above.  Do NOT invent tool names.
- kwargs must contain concrete, real values — never placeholders like "<value>" or "value1".
- ⛔ NEVER produce a plan that asks the user for clarification or a missing value.
  If a destination folder is not specified, use the default path from the skill context (<workspace>/data/).
  Always plan a real tool call with a concrete value.
- If a kwarg value depends on the output of a previous step, write it as {{step_id}} (the
  full result JSON string) or {{step_id.field}} to access a specific field, e.g.
  {{s1.results.0.path}} for the file path of the first search result from step s1.
  IMPORTANT: For file search results use .path (not .id) to get the actual file path.
- If the user query includes a '## Session State' block, you can reference its fields with
  {{__session__.<field>}} tokens.  For example, to pass ALL previously found file paths to
  collect_files_to_folder without enumerating them: "file_paths": "{{__session__.last_found_paths}}"
  The execution engine will replace this token with the actual Python list automatically.
  ONLY use {{__session__.last_found_paths}} when the user refers to previously found files
  using pronouns ("them", "those", "copy them", "send them", etc.).
  If the user is making a FRESH SEARCH request ("Are there any X?", "Find Y", "Search for Z"),
  IGNORE last_found_paths and plan normal search steps instead.
- SEARCH STRATEGY: When the user asks for files by type ("image files", "video files", "pdf files"),
  ALWAYS search by extension — NEVER by name. Plan one search_by_extension step per extension.
  The execution engine automatically saves ALL results to the manifest — no explicit manifest step needed.
  Image extensions: jpg, jpeg, png, gif, bmp, tiff, webp, ico, svg
  Video extensions: mp4, avi, mov, mkv, wmv, flv
  Document extensions: pdf, docx, xlsx, pptx, txt
- Keep the plan minimal: include only the steps actually required.
- Output ONLY the JSON array."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": f"Request: {user_query}"},
    ]

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=messages,
            temperature=0.0,
            max_tokens=2000,
        )
        raw = _strip_fences(response.choices[0].message.content.strip())
    except Exception as exc:
        logger.error("│  ✗ [%s] Planning LLM call failed: %s", skill_name, exc)
        return None, 1

    plan = _parse_plan(raw, tool_map, skill_name)
    return plan, 1


def _parse_plan(
    raw: str,
    tool_map: Dict[str, Callable],
    skill_name: str,
) -> Optional[List[Dict[str, Any]]]:
    """Parse and validate the JSON plan from the LLM response."""
    # Normalise Python-style literals
    normalised = re.sub(r'\bTrue\b', 'true', raw)
    normalised = re.sub(r'\bFalse\b', 'false', normalised)
    normalised = re.sub(r'\bNone\b', 'null', normalised)

    try:
        plan = json.loads(normalised)
    except json.JSONDecodeError:
        m = re.search(r'\[.*\]', normalised, re.DOTALL)
        if m:
            try:
                plan = json.loads(m.group(0))
            except Exception:
                logger.warning("│  ✗ [%s] Could not parse planning response as JSON", skill_name)
                return None
        else:
            logger.warning("│  ✗ [%s] No JSON array found in planning response", skill_name)
            return None

    if not isinstance(plan, list) or len(plan) == 0:
        logger.warning("│  ✗ [%s] Plan is empty or not a list", skill_name)
        return None

    # Validate each step
    valid_ids: set[str] = set()
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            logger.warning("│  ✗ [%s] Step %d is not a dict", skill_name, i)
            return None

        step_id   = step.get("id", "").strip()
        tool_name = step.get("tool", "").strip()

        if not step_id:
            logger.warning("│  ✗ [%s] Step %d has no id", skill_name, i)
            return None

        if tool_name not in tool_map:
            logger.warning(
                "│  ✗ [%s] Step %d references unknown tool '%s'", skill_name, i, tool_name
            )
            return None  # Unknown tool = refuse; fall back to ReAct

        # Ensure depends_on references exist (forward references not allowed)
        for dep in step.get("depends_on", []):
            if dep not in valid_ids:
                logger.warning(
                    "│  ✗ [%s] Step %s depends on unknown/forward step '%s'",
                    skill_name, step_id, dep,
                )
                return None

        valid_ids.add(step_id)

    return plan


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def _synthesize(
    skill_name: str,
    skill_context: str,
    user_query: str,
    plan: List[Dict[str, Any]],
    step_results: Dict[str, Any],
) -> tuple[str, int]:
    """
    One LLM call that turns all tool results into a friendly markdown answer.

    Returns (message_text, llm_call_count).
    """
    from src.agent.llm.llm_parser import get_llm_client

    llm = get_llm_client()

    # Build a concise summary of what each step did
    result_lines = []
    for step in plan:
        sid  = step["id"]
        desc = step.get("description", step["tool"])
        res  = step_results.get(sid, {})
        result_lines.append(f"Step {sid} ({desc}):\n{str(res)[:600]}")

    results_text = "\n\n".join(result_lines)

    messages = [
        {
            "role": "system",
            "content": (
                f"{skill_context}\n\n"
                "Based on the tool results below, write a friendly, "
                "markdown-formatted response (bold, bullets, emojis where appropriate) "
                "that directly answers the user's request.  "
                "Do NOT output JSON.  Output the final answer text only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User request: {user_query}\n\n"
                f"Tool results:\n{results_text}"
            ),
        },
    ]

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=messages,
            temperature=0.3,
            max_tokens=800,
        )
        message = response.choices[0].message.content.strip()
        return message, 1
    except Exception as exc:
        logger.error("│  ✗ [%s] Synthesis LLM call failed: %s", skill_name, exc)
        # Fall back to a clean human-readable summary (no raw dicts)
        clean_lines: list = []
        for _step in plan:
            _sid  = _step["id"]
            _desc = _step.get("description", _step["tool"])
            _res  = step_results.get(_sid, {})
            _msg  = _res.get("message", "") if isinstance(_res, dict) else str(_res)
            if _msg:
                clean_lines.append(f"✅ {_desc} — {_msg[:200]}")
            else:
                clean_lines.append(f"✅ {_desc} — done")
        fallback = "✅ Task completed.\n\n" + "\n".join(clean_lines) if clean_lines else "✅ Task completed."
        return fallback, 1


# ---------------------------------------------------------------------------
# Token resolver
# ---------------------------------------------------------------------------

def _resolve_kwargs(
    kwargs: Dict[str, Any],
    results: Dict[str, Any],
    session_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Substitute ``{step_id}`` / ``{step_id.field.subfield}`` tokens in string
    kwargs values using accumulated step results.

    Also resolves ``{__session__.field}`` tokens using the parsed ## Session State
    block.  When the resolved value is a Python list (e.g. last_found_paths) and
    the *entire* kwarg value is the token, the kwarg is replaced with the real
    list — not a string — so list-typed tool parameters receive proper values.
    """
    _sv = session_vars or {}
    out: Dict[str, Any] = {}

    for key, val in kwargs.items():
        if isinstance(val, str) and '{' in val:
            # Check for {__session__.field} — handle list values specially
            sess_m = re.fullmatch(r'\{__session__\.([^}]+)\}', val.strip())
            if sess_m:
                field = sess_m.group(1)
                resolved = _sv.get(field)
                if resolved is not None:
                    # Keep the native type (list, str, etc.) rather than stringifying
                    out[key] = resolved
                    continue
            # Fall through to general {step_id} / {step_id.field} substitution
            val = _TOKEN_PATTERN.sub(lambda m: _deep_get(m.group(1), results, _sv), val)
        out[key] = val

    return out


_TOKEN_PATTERN = re.compile(r'\{([^}]+)\}')


def _deep_get(path: str, results: Dict[str, Any], session_vars: Optional[Dict[str, Any]] = None) -> str:
    """
    Resolve a dot-separated path like ``s1.results.0.id`` against the accumulated
    step results dict.  Returns the original ``{path}`` string if resolution fails.

    Also handles ``__session__.<field>`` paths, resolving against the parsed
    ## Session State dict.  List values are stringified (JSON) for safe embedding
    in a larger string context; use the full-value token path in _resolve_kwargs
    for proper list passthrough.
    """
    parts = path.split(".")
    step_id = parts[0]

    # ── Session state reference ────────────────────────────────────────────
    if step_id == "__session__":
        sv = session_vars or {}
        if len(parts) < 2:
            return f"{{{path}}}"
        field = parts[1]
        data: Any = sv.get(field)
        for part in parts[2:]:
            if isinstance(data, dict):
                data = data.get(part)
            elif isinstance(data, list) and part.isdigit():
                idx = int(part)
                data = data[idx] if idx < len(data) else None
            else:
                data = None
            if data is None:
                return f"{{{path}}}"
        if data is None:
            return f"{{{path}}}"
        return json.dumps(data) if isinstance(data, (list, dict)) else str(data)

    if step_id not in results:
        return f"{{{path}}}"   # leave token unchanged if step hasn't run yet

    data = results[step_id]

    for part in parts[1:]:
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit():
            idx = int(part)
            data = data[idx] if idx < len(data) else None
        else:
            data = None
        if data is None:
            return f"{{{path}}}"   # resolution failed — leave token as-is

    return str(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(raw: str) -> str:
    """Remove optional ```json … ``` fences from LLM output."""
    if "```" in raw:
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) >= 2 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()
