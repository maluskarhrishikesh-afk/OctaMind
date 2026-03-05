"""
DAGPlanner — Hybrid Planner + Deterministic Execution Engine.

Architecture
------------
    User Input
       ↓
    LLM Planner (1 call) → Structured DAG Plan (JSON with depends_on)
       ↓
    Topological Sort (algorithmic, 0 LLM calls)
       ↓
    Deterministic Execution Engine (0 orchestration LLM calls)
       ├─ Step A: Sub-Agent  (runs its own focused ReAct loop)
       ├─ Step B: Sub-Agent  (receives A's output via {step_id.field} tokens)
       └─ Step C: Sub-Agent  (receives B's output)

Key benefit
-----------
Replaces the multi-turn master ReAct loop (1–12 orchestration LLM calls)
with a single planning call that returns the full execution graph upfront.
Sub-agents still run their own focused ReAct loops for actual tool execution —
only the orchestration overhead is eliminated.

LLM calls comparison
--------------------
    Old (master ReAct loop): 1 [router classify] + 1–12 [master loop] per workflow
    New (DAG planner):        1 [plan call] per workflow
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("workflows.dag")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DAGStep:
    """A single step in the execution DAG."""

    id: str                             # unique step id, e.g. "download1", "zip1"
    agent: str                          # registry key, e.g. "drive", "email", "files"
    instruction: str                    # natural language task for this agent
    depends_on: List[str] = field(default_factory=list)  # step ids this step requires
    output_key: str = ""                # context key to store the result under (defaults to id)
    description: str = ""              # short human-readable UI label

    def __post_init__(self) -> None:
        if not self.output_key:
            self.output_key = self.id


@dataclass
class DAGPlan:
    """Full execution plan produced by the DAG planner."""

    command: str
    steps: List[DAGStep]               # already topologically sorted
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def agents_needed(self) -> List[str]:
        """Return deduplicated, sorted list of agent names in the plan."""
        return sorted({s.agent for s in self.steps})


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------

def topological_sort(steps: List[DAGStep]) -> List[DAGStep]:
    """
    Sort DAGSteps in dependency order using Kahn's algorithm.

    Returns steps in an order where every dependency of a step
    always appears before the step itself.

    Raises
    ------
    ValueError
        If an unknown dependency or a cycle is detected.
    """
    step_map: Dict[str, DAGStep] = {s.id: s for s in steps}
    in_degree: Dict[str, int] = {s.id: 0 for s in steps}
    dependents: Dict[str, List[str]] = {s.id: [] for s in steps}

    for step in steps:
        for dep in step.depends_on:
            if dep not in step_map:
                raise ValueError(
                    f"Step '{step.id}' depends on unknown step '{dep}'. "
                    f"Known steps: {list(step_map.keys())}"
                )
            in_degree[step.id] += 1
            dependents[dep].append(step.id)

    queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)
    sorted_steps: List[DAGStep] = []

    while queue:
        sid = queue.popleft()
        sorted_steps.append(step_map[sid])
        for dependent in dependents[sid]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(sorted_steps) != len(steps):
        cycle_ids = [sid for sid, deg in in_degree.items() if deg > 0]
        raise ValueError(f"Cycle detected in DAG — cannot sort. Involved steps: {cycle_ids}")

    logger.debug("Topological sort: %s", [s.id for s in sorted_steps])
    return sorted_steps


# ---------------------------------------------------------------------------
# Planning prompt
# ---------------------------------------------------------------------------

def _build_dag_planning_prompt() -> str:
    from pathlib import Path as _Path
    from src.agent.workflows.agent_registry import get_capabilities_text
    caps = get_capabilities_text()
    home = _Path.home()
    path_ctx = (
        f"  Home:      {home}\n"
        f"  Downloads: {home / 'Downloads'}\n"
        f"  Desktop:   {home / 'Desktop'}\n"
        f"  Documents: {home / 'Documents'}\n"
    )
    return f"""You are a workflow planning engine for a multi-agent AI system.

Given a user command, produce a DAG (Directed Acyclic Graph) execution plan as a JSON array.
Each step has a unique id, an agent name, a natural-language instruction, a depends_on list, and a description.

Available agents:
{caps}

SPECIAL CONTEXT TOKENS always available in instructions:
- {{__user_email__}} — the authenticated user's own email address.
  Use it when the user says "email me", "send it to me", "notify me", etc.
- {{<step_id>.file_path}} — the local file path produced by a previous step.
  Use it to pass files between agents.
  Example: step 2 instruction → "Zip the file at {{download1.file_path}}"

RESOLVING CONTEXT REFERENCES ("them", "those", "the files", "it", "that folder"):
The user command may arrive with a "## Session State" JSON block.

⚠️  CRITICAL DISTINCTION — fresh search vs. follow-up action:
- A FRESH SEARCH request looks like: "Are there any X files?", "Find all Y", "Search for Z",
  "How many X files are there?", "Do I have any X?" — even if session state has last_found_paths.
  For fresh searches: ALWAYS create normal search steps. IGNORE last_found_paths / last_found_folder.
- A FOLLOW-UP ACTION uses pronouns that refer back to previously found files:
  "them", "those", "those files", "copy them", "send them", "mail them", "zip those", "the images you found".
  For follow-up actions: use last_found_paths / last_found_folder from Session State.

- If `last_found_folder` is present AND the command is a follow-up action on that folder:
  Use it directly — do NOT search again.
  Preferred flow for zip/email: zip_folder(last_found_folder, output_path="C:\\Users\\malus\\Downloads\\<FolderName>.zip") → email zip
- If `last_found_paths` is present (list of file paths) AND the command is a follow-up action:
  CRITICAL — always distinguish the follow-up intent:
  A) "copy them to a folder" / "put them in a folder" / "collect them" (NO email, NO zip):
     → SINGLE files step: instruct the files agent to call
       PREFERRED: collect_files_from_manifest(destination="C:\\Users\\malus\\Downloads\\OctaMind")
         — reads the manifest file saved after the search; contains ALL found paths.
       FALLBACK (if manifest not available): collect_files_to_folder(file_paths=[<all last_found_paths>], destination="C:\\Users\\malus\\Downloads\\OctaMind")
       DEFAULT destination is ALWAYS C:\\Users\\malus\\Downloads\\OctaMind unless the user specifies another.
       ⛔ NEVER create a step that asks the user for a destination — just use OctaMind silently.
       NEVER use copy_file(source=last_found_folder) — that copies the ENTIRE folder including files the user did NOT ask for.
  B) "mail them to me" / "send them to me" / "email those" (involves email):
     - SINGLE FILE (list has exactly 1 item): email it directly — no zip.
     - MULTIPLE FILES from the same parent folder: zip_folder(last_found_folder, output_path=...) → email zip.
     - MULTIPLE FILES spanning different folders: collect_files_from_manifest → zip_folder → email zip.
  C) SINGLE FILE (list has exactly 1 item with a file extension like .pdf/.docx): email it directly — no zip.
- NEVER create a new search step for a follow-up action when last_found_folder or last_found_paths are in Session State.
- DO create search steps when the user's command is a fresh search, even if Session State has prior results.
- Embed the EXACT paths from Session State as literal values in the step instruction.
- ZIP OUTPUT PATH: When zipping for email or delivery, ALWAYS set output_path to
  C:\\Users\\malus\\Downloads\\<ArchiveName>.zip — NEVER omit it. Leaving it empty creates
  the zip next to the source folder which may be read-only (C:\\Windows\\, C:\\Program Files\\, etc.).

SYSTEM PATHS on this machine (use these exact absolute paths in instructions):
{path_ctx}
When the user mentions a folder like "Downloads", "Desktop", or "Documents",
always expand it to the absolute path shown above in the agent instruction.

Each step schema:
{{
  "id": "<unique_snake_case_id>",
  "agent": "<agent_name>",
  "instruction": "<natural language task for this agent — be specific>",
  "depends_on": ["<step_id>", ...],
  "description": "<short UI label>"
}}

Rules:
- depends_on must only reference ids defined earlier in the same array.
- Steps with no shared dependencies can be listed in any order.
- For file handoff: first agent downloads and reports the local path,
  then use {{first_step_id.file_path}} in the receiving agent's instruction.
- When a step uses a local folder the user named (e.g. "Text folder in Downloads"),
  write the full absolute path directly in the instruction — never use a placeholder.
- IMPORTANT — ambiguous folder/file name (no absolute path given, and NOT a known
  standard location like Downloads/Desktop/Documents/Home): NEVER guess the path.
  Instead write the files agent instruction as: "Find the folder/file named '<name>'
  using search_file_all_drives, then <operation> the found path".
  Example: user says "zip xpanse folder" → instruction: "Find the folder named 'xpanse'
  using search_file_all_drives, then zip the found folder and report the archive path".
- Keep the plan minimal — only generate steps directly needed.
- If the user says "this", "the above", "the list", or refers to output from a
  previous assistant message, embed that information as literal text directly
  in the instruction — do NOT create a new fetch/list step for it.
- CRITICAL — "send here" / "send it here for downloading" / "show me the file": use a SINGLE
  `files` step with instruction telling the agent to find the file AND set file_path for delivery.
  The system automatically sends the file to the user's current chat. Do NOT use `whatsapp`.
  Example: "Search for any payslip PDF file (not .lnk shortcuts) and deliver it for download"
- Return ONLY the JSON array. No surrounding text, no markdown code fences.

Example for "Download report.pdf from Drive, zip it, and email it to me":
[
  {{"id": "download1", "agent": "drive", "instruction": "Download report.pdf from Google Drive and save it locally", "depends_on": [], "description": "Download report.pdf"}},
  {{"id": "zip1", "agent": "files", "instruction": "Zip the file at {{download1.file_path}} into an archive", "depends_on": ["download1"], "description": "Zip the file"}},
  {{"id": "email1", "agent": "email", "instruction": "Send the zip archive at {{zip1.file_path}} as an attachment to {{__user_email__}} with subject \\"Report\\"", "depends_on": ["zip1"], "description": "Email the zip"}}
]

Example for "find my payslip and send it here for downloading":
[
  {{"id": "deliver1", "agent": "files", "instruction": "Search for any payslip PDF file on the laptop (skip .lnk shortcuts, look for actual .pdf files). Use search_file_all_drives if available. Deliver the found file for download by the user.", "depends_on": [], "description": "Find and deliver payslip"}}
]

Example for "zip them and mail it to me" WHEN Session State contains last_found_folder="C:\\Hrishikesh\\Neo\\Payslips":
[
  {{"id": "zip1", "agent": "files", "instruction": "Zip the folder C:\\\\Hrishikesh\\\\Neo\\\\Payslips into an archive. Save the zip at C:\\\\Users\\\\malus\\\\Downloads\\\\Payslips.zip", "depends_on": [], "description": "Zip payslips folder"}},
  {{"id": "email1", "agent": "email", "instruction": "Send {{zip1.file_path}} as an attachment to {{__user_email__}} with subject \\"Payslips\\"", "depends_on": ["zip1"], "description": "Email zip"}}
]

Example for "mail it to me" WHEN Session State contains last_found_paths=["C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf"] (SINGLE file — no zip needed):
[
  {{"id": "email1", "agent": "email", "instruction": "Send C:\\\\Hrishikesh\\\\Neo\\\\Payslips\\\\Payslip_2025_Dec.pdf as an attachment to {{__user_email__}} with subject \\"Payslip\\"", "depends_on": [], "description": "Email payslip directly"}}
]

Example for "collect those files and send by email" WHEN Session State contains last_found_paths=["C:\\A\\f1.pdf","C:\\B\\f2.pdf"] (files from different folders):
[
  {{"id": "collect1", "agent": "files", "instruction": "Copy the files from the previous search into C:\\\\Users\\\\malus\\\\Downloads\\\\OctaMind folder. Use collect_files_from_manifest() — it reads the saved manifest of ALL found paths. Fallback: collect_files_to_folder(file_paths=['C:\\\\A\\\\f1.pdf','C:\\\\B\\\\f2.pdf'], destination='C:\\\\Users\\\\malus\\\\Downloads\\\\OctaMind').", "depends_on": [], "description": "Gather files"}},
  {{"id": "zip1", "agent": "files", "instruction": "Zip the folder at {{collect1.file_path}}", "depends_on": ["collect1"], "description": "Zip collected files"}},
  {{"id": "email1", "agent": "email", "instruction": "Send {{zip1.file_path}} as attachment to {{__user_email__}}", "depends_on": ["zip1"], "description": "Email zip"}}
]

Example for "copy them to a folder" / "put them in a folder" WHEN Session State contains last_found_paths (copy ONLY those files found in the previous search, NOT the whole folder):
[
  {{"id": "copy1", "agent": "files", "instruction": "Copy ALL files from the previous search into C:\\\\Users\\\\malus\\\\Downloads\\\\OctaMind. Use collect_files_from_manifest() which reads the manifest file saved during the search and copies EVERY found file. Do NOT use copy_file on the parent folder.", "depends_on": [], "description": "Collect searched files into OctaMind folder"}}
]
"""


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences that some models add around JSON."""
    if "```" in raw:
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) >= 2 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# ---------------------------------------------------------------------------
# Planning — single LLM call
# ---------------------------------------------------------------------------

def plan_dag_workflow(command: str) -> Optional[DAGPlan]:
    """
    Ask the LLM to produce a DAGPlan for *command*.

    This is a **single LLM call** that replaces the entire multi-turn master
    ReAct orchestration loop.  The returned plan contains topologically sorted
    steps ready for deterministic execution.

    Returns
    -------
    DAGPlan
        A valid, topologically sorted execution plan.
    None
        On any failure — caller should fall back to ``react_workflow()``.
    """
    from src.agent.llm.llm_parser import get_llm_client

    llm = get_llm_client()
    t0 = time.time()
    logger.info("DAG planner: planning command=%.140s", command)

    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": _build_dag_planning_prompt()},
                {"role": "user",   "content": f"User command: {command}"},
            ],
            temperature=0.1,
            max_tokens=2000,
            timeout=40,
        )
        raw = _strip_code_fences(response.choices[0].message.content.strip())

        steps_data: List[Dict[str, Any]] = json.loads(raw)
        if not isinstance(steps_data, list) or not steps_data:
            logger.warning("DAG planner: LLM returned empty or non-list — falling back")
            return None

        # Validate agent names against registry
        from src.agent.workflows.agent_registry import registered_agents
        valid_agents = set(registered_agents())
        unknown = [s.get("agent", "") for s in steps_data if s.get("agent", "") not in valid_agents]
        if unknown:
            logger.warning("DAG planner: unknown agents in plan %s — falling back", unknown)
            return None

        steps = [
            DAGStep(
                id=s["id"],
                agent=s["agent"],
                instruction=s["instruction"],
                depends_on=s.get("depends_on", []),
                description=s.get("description", ""),
            )
            for s in steps_data
        ]

        sorted_steps = topological_sort(steps)
        plan = DAGPlan(command=command, steps=sorted_steps)

        usage = getattr(response, "usage", None)
        tokens = (usage.prompt_tokens + usage.completion_tokens) if usage else "?"
        logger.info(
            "DAG planner: plan ready  steps=%d  agents=%s  tokens=%s  elapsed=%.2fs",
            len(sorted_steps), plan.agents_needed, tokens, time.time() - t0,
        )
        return plan

    except (ValueError, KeyError) as exc:
        logger.warning("DAG planner: invalid plan structure: %s — falling back", exc)
        return None
    except Exception as exc:
        logger.exception("DAG planner: unexpected error: %s — falling back", exc)
        return None


# ---------------------------------------------------------------------------
# Instruction resolver
# ---------------------------------------------------------------------------

def _resolve_instruction(
    instruction: str,
    ctx_results: Dict[str, Any],
    user_email: Optional[str],
) -> str:
    """
    Substitute ``{step_id.field}`` and ``{__user_email__}`` tokens in an
    instruction string with values from the execution context.

    Examples
    --------
    ``{download1.file_path}`` → ``C:\\Users\\user\\Downloads\\report.pdf``
    ``{__user_email__}``      → ``alice@gmail.com``
    """
    from pathlib import Path as _Path
    if user_email:
        instruction = instruction.replace("{__user_email__}", user_email)

    # Expand tilde shortcuts to the real home directory so the LLM's ~/path
    # outputs become valid absolute paths on every OS.
    _home = str(_Path.home())
    instruction = instruction.replace("~\\", _home + "\\")
    instruction = instruction.replace("~/", _home + "/")
    # Handle bare ~ at word boundary (e.g. "at ~") but not inside tokens like {~foo}
    # Use a lambda to avoid re interpreting backslashes in _home as escape sequences
    instruction = re.sub(r'(?<![{/\\])~(?=[/\\]|\s|$)', lambda _: _home, instruction)

    def _replace(match: re.Match) -> str:
        ref = match.group(1)
        if ref == "__user_email__":
            return user_email or match.group(0)
        if "." in ref:
            key, field_name = ref.split(".", 1)
            val = ctx_results.get(key)
            if isinstance(val, dict):
                result = (
                    val.get("artifacts", {}).get(field_name)
                    or val.get(field_name)
                )
                if result is not None:
                    return str(result)
        else:
            val = ctx_results.get(ref)
            if val is not None:
                if isinstance(val, dict):
                    return val.get("text", str(val))
                return str(val)
        return match.group(0)   # leave unresolved placeholder intact

    return re.sub(r"\{([\w.]+)\}", _replace, instruction)


# ---------------------------------------------------------------------------
# Deterministic execution
# ---------------------------------------------------------------------------

def execute_dag_workflow(
    plan: DAGPlan,
    agent_ids: Optional[Dict[str, str]] = None,
    user_email: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Execute a DAGPlan deterministically.

    The steps were topologically sorted during planning, so each step's
    dependencies are always satisfied before it runs.

    ``{step_id.field}`` tokens in instructions are resolved from the
    previous steps' outputs before each agent is called.

    This is the *zero-orchestration-LLM* execution layer.  Sub-agents
    still run their own focused ReAct loops for actual tool execution.

    Parameters
    ----------
    plan:       DAGPlan with topologically sorted steps.
    agent_ids:  Optional mapping of agent type → agent_id for memory lookup.
    user_email: Authenticated user's email, substituted for {__user_email__}.

    Returns
    -------
    List of step result dicts compatible with the existing UI renderer.
    """
    from src.agent.workflows.agent_registry import get_executor

    agent_ids = agent_ids or {}
    ctx_results: Dict[str, Any] = {}
    steps_results: List[Dict[str, Any]] = []

    logger.info(
        "┌─ DAG execution START  steps=%d  agents=%s",
        len(plan.steps), plan.agents_needed,
    )

    # Track which step ids have failed so downstream dependents can be skipped
    failed_step_ids: set[str] = set()

    for step in plan.steps:
        t0 = time.time()

        # ── Skip if any upstream dependency failed ──────────────────────
        blocking = [dep for dep in step.depends_on if dep in failed_step_ids]
        if blocking:
            skip_msg = (
                f"Skipped because upstream step(s) failed: {blocking}. "
                "Fix the earlier step and retry."
            )
            logger.warning(
                "│  ⏭ DAG step [%-12s]  SKIPPED (upstream failed: %s)",
                step.id, blocking,
            )
            failed_step_ids.add(step.id)
            ctx_results[step.id] = {"text": skip_msg, "artifacts": {}}
            steps_results.append({
                "step":        step.id,
                "agent":       step.agent,
                "tool":        step.description or step.instruction[:60],
                "instruction": step.instruction,
                "status":      "skipped",
                "error":       skip_msg,
                "result":      None,
                "elapsed":     time.time() - t0,
            })
            continue

        resolved = _resolve_instruction(step.instruction, ctx_results, user_email)

        # If any {step_id.field} tokens remain unresolved, the upstream step
        # failed silently (returned "success" but produced no artifact).
        # Skip this step so the user gets a clear error instead of the agent
        # receiving a literal "{zip1.file_path}" string.
        unresolved = re.findall(r"\{([\w]+\.[\w]+)\}", resolved)
        if unresolved:
            skip_msg = (
                f"Skipped because required output(s) from a previous step were "
                f"not produced: {unresolved}. "
                "The upstream step likely failed to create the expected file/resource."
            )
            logger.warning(
                "│  ⏭ DAG step [%-12s]  SKIPPED (unresolved tokens: %s)",
                step.id, unresolved,
            )
            failed_step_ids.add(step.id)
            ctx_results[step.id] = {"text": skip_msg, "artifacts": {}}
            steps_results.append({
                "step":        step.id,
                "agent":       step.agent,
                "tool":        step.description or step.instruction[:60],
                "instruction": step.instruction,
                "status":      "skipped",
                "error":       skip_msg,
                "result":      None,
                "elapsed":     time.time() - t0,
            })
            continue

        logger.info(
            "│  ▶ DAG step [%-12s]  agent=%-10s  resolved_instruction=%.120s",
            step.id, step.agent, resolved,
        )

        executor = get_executor(step.agent)
        if executor is None:
            error_msg = f"No executor registered for agent '{step.agent}'"
            logger.error("│  ✗ DAG step [%s]: %s", step.id, error_msg)
            failed_step_ids.add(step.id)
            steps_results.append({
                "step": step.id,
                "agent": step.agent,
                "tool": step.description or step.instruction[:60],
                "instruction": step.instruction,
                "status": "error",
                "error": error_msg,
                "result": None,
                "elapsed": time.time() - t0,
            })
            # Store empty context so downstream {step_id.x} tokens degrade gracefully
            ctx_results[step.id] = {"text": error_msg, "artifacts": {}}
            continue

        artifacts_out: Dict[str, Any] = {}
        try:
            raw_result = executor(
                user_query=resolved,
                agent_id=agent_ids.get(step.agent),
                artifacts_out=artifacts_out,
            )

            if isinstance(raw_result, dict):
                text        = raw_result.get("message", str(raw_result))
                exec_status = raw_result.get("status", "success")
            else:
                text        = str(raw_result)
                exec_status = "success"

            # Accumulate per-sub-agent LLM call counts for the summary log
            _step_llm_calls = raw_result.get("llm_calls", 0) if isinstance(raw_result, dict) else 0

            # Store result so subsequent steps can reference {step.id.field}
            ctx_results[step.id] = {"text": text, "artifacts": artifacts_out}

            # Mark failed so dependents are skipped
            if exec_status == "error":
                failed_step_ids.add(step.id)

            steps_results.append({
                "step":        step.id,
                "agent":       step.agent,
                "tool":        step.description or step.instruction[:60],
                "instruction": step.instruction,
                "status":      exec_status,
                "result":      {"message": text[:500], "artifacts": artifacts_out},
                "error":       text[:300] if exec_status == "error" else None,
                "elapsed":     time.time() - t0,
                "llm_calls":   _step_llm_calls,
            })

            logger.info(
                "│  ✔ DAG step [%-12s]  agent=%-10s  status=%-8s  elapsed=%.2fs",
                step.id, step.agent, exec_status, time.time() - t0,
            )

        except Exception as exc:
            logger.exception(
                "│  ✗ DAG step [%-12s]  agent=%-10s  error: %s",
                step.id, step.agent, exc,
            )
            failed_step_ids.add(step.id)
            ctx_results[step.id] = {"text": str(exc), "artifacts": {}}
            steps_results.append({
                "step":        step.id,
                "agent":       step.agent,
                "tool":        step.description or step.instruction[:60],
                "instruction": step.instruction,
                "status":      "error",
                "error":       str(exc),
                "result":      None,
                "elapsed":     time.time() - t0,
            })

    success_count = sum(1 for r in steps_results if r["status"] == "success")
    total_sub_llm_calls = sum(r.get("llm_calls", 0) for r in steps_results)
    logger.info(
        "└─ DAG execution DONE  steps=%d/%d-success  sub_agent_llm_calls=%d",
        success_count, len(steps_results), total_sub_llm_calls,
    )
    return steps_results
