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
(for example a tool-produced list value) the **entire kwarg** is replaced with
the real object — not a stringified version.  This lets the LLM plan pass
structured values without embedding them verbatim in the JSON plan:

    "kwargs": {"file_manifest": "{__session__.file_manifest}", "destination": "C:\\..."}

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

from src.agent.runtime_paths import get_your_data_dir
from src.agent.workflows.confirmation_policy import maybe_guard_destructive_tool_call

logger = logging.getLogger("workflows.skill_dag")

def _get_authenticated_user_email() -> str:
    """Return the authenticated Gmail address when available."""
    try:
        from src.email.gmail_auth import get_gmail_service  # noqa: PLC0415

        svc: Any = get_gmail_service()
        profile = svc.users().getProfile(userId="me").execute()
        return str(profile.get("emailAddress", "") or "").strip()
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.debug("│  [skill-dag] could not resolve authenticated email: %s", exc)
        return ""

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _extract_session_state(user_query: str) -> Dict[str, Any]:
    """Parse the optional '## Session State' JSON block appended to the user query.

    Returns a dict (possibly empty) with compact keys like last_found_bundle_dir,
    last_found_folder, last_found_file_path, file_manifest, etc.
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
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    return {}


def _merge_manifest_into_session(session_vars: Dict[str, Any]) -> Dict[str, Any]:
    """Augment session_vars with compact current file context.

    Detailed file lists should live in the files context / manifest, not in the
    prompt-sized session state. This helper only injects compact fields the
    planner can use safely:
    - file_manifest
    - found_count
    - last_found_bundle_dir
    - last_found_file_path for a single resolved item

    The manifest remains the fallback source of truth when no live files context
    is present.
    """
    import os
    from pathlib import Path as _Path
    from src.agent.manifest.context_manifest import read_context
    from src.files.features.file_ops import get_active_file_manifest_metadata, resolve_file_manifest_path

    try:
        updated = dict(session_vars)

        files_ctx = read_context(agent="files") or {}
        entities = files_ctx.get("resolved_entities", {}) if isinstance(files_ctx, dict) else {}
        if isinstance(entities, dict):
            bundle_dir = str(entities.get("search_bundle_dir", "") or "").strip()
            if bundle_dir:
                updated["last_found_bundle_dir"] = bundle_dir
            file_manifest = str(entities.get("file_manifest", "") or "").strip()
            if file_manifest:
                updated["file_manifest"] = file_manifest
            found_count = entities.get("found_count")
            if isinstance(found_count, int) and found_count > 0:
                updated["found_count"] = found_count
            listed_files = entities.get("listed_files", [])
            if isinstance(listed_files, list) and len(listed_files) == 1 and isinstance(listed_files[0], dict):
                single_path = str(listed_files[0].get("path", "") or "").strip()
                if single_path:
                    updated["last_found_file_path"] = single_path
                    if str(listed_files[0].get("type", "") or "").strip().lower() == "folder":
                        updated["last_found_folder"] = single_path

        active_manifest = get_active_file_manifest_metadata()
        manifest_candidate = str(active_manifest.get("manifest_path", "") or "").strip()
        manifest_path = _Path(manifest_candidate) if manifest_candidate else resolve_file_manifest_path()
        if not manifest_path.exists():
            return updated

        raw_paths = [
            p.strip()
            for p in manifest_path.read_text(encoding="utf-8").splitlines()
            if p.strip()
        ]
        if not raw_paths:
            return updated

        manifest_age_s = time.time() - os.path.getmtime(manifest_path)
        if manifest_age_s > 1800:
            return updated

        updated.setdefault("file_manifest", str(manifest_path))
        if active_manifest.get("manifest_id"):
            updated.setdefault("manifest_id", str(active_manifest.get("manifest_id")))
        updated.setdefault("found_count", len(raw_paths))
        if len(raw_paths) == 1:
            updated.setdefault("last_found_file_path", raw_paths[0])
            updated.setdefault("last_found_folder", str(_Path(raw_paths[0]).parent))
        logger.info(
            "│  [session-merge] manifest has %d path(s) (age=%.0fs) → updating compact file context",
            len(raw_paths), manifest_age_s,
        )
        return updated
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.debug("│  [session-merge] manifest read failed: %s", exc)
        return session_vars


def _should_enforce_email_pdf_delivery(skill_name: str, user_query: str, plan: List[Dict[str, Any]]) -> bool:
    """Return True when an email-summary request should produce a PDF attachment."""
    if skill_name != "email":
        return False

    lowered = user_query.lower()
    has_fetch_step = any(step.get("tool") == "fetch_emails_to_markdown" for step in plan)
    wants_summary = any(token in lowered for token in ("summary", "summarize", "digest", "overview", "report"))
    wants_pdf = "pdf" in lowered or "report" in lowered
    wants_email_delivery = any(
        token in lowered
        for token in (
            "send it to me",
            "send me",
            "email it",
            "email me",
            "mail it",
            "mail me",
            "send to me",
            "my inbox",
        )
    )
    return has_fetch_step and wants_summary and wants_pdf and wants_email_delivery


def _clone_plan(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cloned: List[Dict[str, Any]] = []
    for step in plan:
        cloned.append(
            {
                **step,
                "kwargs": dict(step.get("kwargs", {})),
                "depends_on": list(step.get("depends_on", [])),
            }
        )
    return cloned


def _next_step_id(plan: List[Dict[str, Any]]) -> str:
    used = {str(step.get("id", "")).strip() for step in plan}
    idx = 1
    while f"s{idx}" in used:
        idx += 1
    return f"s{idx}"


def _slugify_report_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "emails"


def _derive_email_report_slug(fetch_step: Dict[str, Any], user_query: str) -> str:
    query = str(fetch_step.get("kwargs", {}).get("query", "") or "")
    sender_match = re.search(r"from:([^\s]+)", query, re.IGNORECASE)
    if sender_match:
        return _slugify_report_name(sender_match.group(1))
    if "today" in user_query.lower():
        return "today"
    return "emails"


def _derive_email_report_title(fetch_step: Dict[str, Any], user_query: str) -> str:
    query = str(fetch_step.get("kwargs", {}).get("query", "") or "")
    sender_match = re.search(r"from:([^\s]+)", query, re.IGNORECASE)
    if sender_match:
        return f"Email Summary Report - {sender_match.group(1)}"
    if "today" in user_query.lower():
        return "Email Summary Report - Today"
    return "Email Summary Report"


def _looks_like_email_followup(user_query: str) -> bool:
    lowered = str(user_query or "").lower()
    if not any(token in lowered for token in ("summary", "summarize", "digest", "report", "send it", "email it", "mail it")):
        return False
    return any(token in lowered for token in ("them", "those", "these", "listed", "above", "selected", "first", "second", "third", "last"))


def _apply_email_followup_constraints(user_query: str, fetch_step: Dict[str, Any]) -> None:
    if not _looks_like_email_followup(user_query):
        return
    try:
        from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

        ctx = read_context(agent="email")
        if not ctx:
            return
        entities = ctx.get("resolved_entities", {}) or {}
        listed = entities.get("listed_emails", []) or []
        if listed and not fetch_step.get("kwargs", {}).get("max_results"):
            fetch_step.setdefault("kwargs", {})["max_results"] = len(listed)
        if entities.get("query") and not fetch_step.get("kwargs", {}).get("query"):
            fetch_step.setdefault("kwargs", {})["query"] = entities["query"]
    except (AttributeError, ImportError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return


def _repair_email_pdf_delivery_plan(
    skill_name: str,
    user_query: str,
    plan: List[Dict[str, Any]],
    user_email: str,
) -> List[Dict[str, Any]]:
    """Ensure email-summary-to-PDF requests generate and send a PDF attachment."""
    if not _should_enforce_email_pdf_delivery(skill_name, user_query, plan):
        return plan

    repaired = _clone_plan(plan)
    fetch_index = next(
        (idx for idx, step in enumerate(repaired) if step.get("tool") == "fetch_emails_to_markdown"),
        None,
    )
    if fetch_index is None:
        return plan

    fetch_step = repaired[fetch_index]
    fetch_step_id = str(fetch_step.get("id", "s1"))
    _apply_email_followup_constraints(user_query, fetch_step)
    report_slug = _derive_email_report_slug(fetch_step, user_query)
    report_title = _derive_email_report_title(fetch_step, user_query)
    report_path = str(get_your_data_dir("reports", f"email_summary_{report_slug}.pdf"))

    pdf_index = next(
        (idx for idx, step in enumerate(repaired) if step.get("tool") == "write_pdf_report"),
        None,
    )
    if pdf_index is None:
        pdf_step_id = _next_step_id(repaired)
        pdf_step = {
            "id": pdf_step_id,
            "tool": "write_pdf_report",
            "kwargs": {
                "path": report_path,
                "title": report_title,
                "content": f"{{{fetch_step_id}.report_content}}",
            },
            "depends_on": [fetch_step_id],
            "description": "Write the fetched email summary to a PDF report.",
        }
        repaired.insert(fetch_index + 1, pdf_step)
        pdf_index = fetch_index + 1
    else:
        pdf_step = repaired[pdf_index]
        pdf_step_id = str(pdf_step.get("id", "") or _next_step_id(repaired))
        pdf_step["id"] = pdf_step_id
        pdf_step["tool"] = "write_pdf_report"
        pdf_step["kwargs"].setdefault("path", report_path)
        pdf_step["kwargs"].setdefault("title", report_title)
        pdf_step["kwargs"]["content"] = f"{{{fetch_step_id}.report_content}}"
        pdf_step["depends_on"] = [fetch_step_id]
        pdf_step.setdefault("description", "Write the fetched email summary to a PDF report.")

    delivery_index = next(
        (
            idx for idx, step in enumerate(repaired)
            if step.get("tool") in {"send_email", "send_email_with_attachment", "deliver_file"}
        ),
        None,
    )

    fallback_recipient = user_email or "me"
    fallback_message = "Please find the attached PDF summary report."

    if delivery_index is None:
        repaired.append(
            {
                "id": _next_step_id(repaired),
                "tool": "send_email_with_attachment",
                "kwargs": {
                    "to": fallback_recipient,
                    "subject": report_title,
                    "message": fallback_message,
                    "attachment_path": f"{{{pdf_step_id}.path}}",
                },
                "depends_on": [pdf_step_id],
                "description": "Email the generated PDF summary report to the user.",
            }
        )
        return repaired

    delivery_step = repaired.pop(delivery_index)
    delivery_kwargs = dict(delivery_step.get("kwargs", {}))
    message = str(delivery_kwargs.get("message", "") or "").strip()
    if not message or "report_content" in message or len(message) > 400:
        message = fallback_message

    subject = str(delivery_kwargs.get("subject", "") or "").strip() or report_title
    delivery_step["tool"] = "send_email_with_attachment"
    delivery_step["kwargs"] = {
        "to": delivery_kwargs.get("to") or fallback_recipient,
        "subject": subject,
        "message": message,
        "attachment_path": f"{{{pdf_step_id}.path}}",
    }
    delivery_step["depends_on"] = [pdf_step_id]
    delivery_step["description"] = "Email the generated PDF summary report to the user."

    insert_at = min(len(repaired), pdf_index + 1)
    repaired.insert(insert_at, delivery_step)
    return repaired


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
    react_tool_map: Optional[Dict[str, Callable]] = None,
    react_tool_docs: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a skill task using a two-call DAG approach.

    Parameters
    ----------
    skill_name:    Human-readable skill label used in log lines.
    skill_context: System-level instructions specific to this skill.
    tool_map:      Full mapping of tool_name → callable (DAG planner needs all tools).
    tool_docs:     Full tool documentation string (DAG planner needs all tools).
    user_query:    Natural-language instruction from the master orchestrator.
    artifacts_out: Mutable dict; tool results (file paths etc.) are merged
                   in for cross-agent handoff.
    react_tool_map: Optional FAISS-filtered tool map used when falling back to ReAct.
                    If not provided, the full ``tool_map`` is used (safe but noisy).
    react_tool_docs: Optional FAISS-filtered tool docs for the ReAct fallback prompt.
                    If not provided, the full ``tool_docs`` is used.

    Returns
    -------
    dict with keys: status, message, action (``"react_response"``), llm_calls
    """
    from src.agent.workflows.skill_react_engine import run_skill_react  # local import to avoid circular deps

    if artifacts_out is None:
        artifacts_out = {}

    t0 = time.time()
    llm_calls = 0
    user_email = _get_authenticated_user_email()

    # ── Extract session state from enriched query (## Session State block) ──
    # Used to resolve {__session__.field} tokens in LLM-planned kwargs.
    session_vars = _extract_session_state(user_query)
    # ── Augment compact file context from the active file manifest when available ──
    # Background jobs update the manifest but NOT the session state, which can
    # cause stale session state to point at old file paths (e.g. the email report
    # folder instead of the just-searched payslip files).
    session_vars = _merge_manifest_into_session(session_vars)
    if session_vars:
        logger.debug("│  [%s] Session state extracted: %s", skill_name, str(session_vars)[:200])

    logger.info("┌─ [%s] Skill DAG START  query=%.100s", skill_name, user_query)

    # ── Step 1: Planning call ──────────────────────────────────────────────
    plan, plan_calls = _plan_steps(skill_name, skill_context, tool_docs, tool_map, user_query, user_email)
    llm_calls += plan_calls

    if plan is None:
        logger.warning(
            "│  ⚠ [%s] DAG planning failed — falling back to ReAct", skill_name
        )
        try:
            from src.agent.telemetry import log_fallback_to_react  # noqa: PLC0415

            log_fallback_to_react(skill_name, "skill_dag_planning")
        except Exception:
            pass
        _react_map  = react_tool_map  if react_tool_map  is not None else tool_map
        _react_docs = react_tool_docs if react_tool_docs is not None else tool_docs
        if react_tool_map is not None:
            logger.info(
                "│  [%s] ReAct fallback using FAISS-filtered tool map (%d tools)",
                skill_name, len(_react_map),
            )
        result = run_skill_react(
            skill_name=skill_name,
            skill_context=skill_context,
            tool_map=_react_map,
            tool_docs=_react_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
        result["llm_calls"] = result.get("llm_calls", 0) + llm_calls
        result["_dag_used"] = False
        return result

    repaired_plan = _repair_email_pdf_delivery_plan(skill_name, user_query, plan, user_email)
    if repaired_plan != plan:
        logger.info("│  [%s] repaired plan to enforce PDF summary attachment delivery", skill_name)
        plan = repaired_plan

    logger.info("│  ✔ [%s] Plan contains %d step(s)", skill_name, len(plan))

    # ── Step 2: Deterministic tool execution (0 LLM calls) ────────────────
    step_results: Dict[str, Any] = {}
    execution_error = False

    for step in plan:
        step_id   = step["id"]
        tool_name = step["tool"]
        raw_kwargs = step.get("kwargs", {})

        # Resolve {previous_step} and {__session__.field} tokens in kwargs
        kwargs = _resolve_kwargs(raw_kwargs, step_results, session_vars, user_email)

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
            confirmation = maybe_guard_destructive_tool_call(
                skill_name=skill_name,
                tool_name=tool_name,
                kwargs=kwargs if isinstance(kwargs, dict) else {},
                artifacts_out=artifacts_out,
            )
            if confirmation:
                confirmation.setdefault("action", tool_name)
                confirmation["llm_calls"] = llm_calls
                confirmation["_dag_used"] = True
                confirmation["file_path"] = artifacts_out.get("file_path", "")
                confirmation["found_paths"] = artifacts_out.get("found_paths", [])
                return confirmation
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
                        # Also check inside result lists
                        for _list_key in ("results", "entries", "items", "files"):
                            for item in result_raw.get(_list_key, []):
                                fp = (
                                    item.get("file_path") or item.get("path")
                                    if isinstance(item, dict) else None
                                )
                                if fp:
                                    artifacts_out["file_path"] = fp
                                    break
                            if artifacts_out.get("file_path"):
                                break
                    # Collect ALL search result paths — check every common list key
                    # so tools like list_directory ("entries") work alongside
                    # search_by_name/search_by_extension ("results").
                    all_result_paths: list = []
                    for _list_key in ("results", "entries", "items", "files"):
                        _source_list = result_raw.get(_list_key, [])
                        if not isinstance(_source_list, list):
                            continue
                        _candidates = [
                            item.get("path") or item.get("file_path")
                            for item in _source_list
                            if isinstance(item, dict)
                            and (item.get("path") or item.get("file_path"))
                        ]
                        all_result_paths.extend(_candidates)
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
                        except (AttributeError, ImportError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as _me:
                            logger.warning("│    [%s] manifest save failed: %s", skill_name, _me)

                logger.info("│    [%s] ✔ step=%s succeeded", skill_name, step_id)
        except (AttributeError, ImportError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
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

    # ── Write diary entry so future turns can look up what was done ───────
    try:
        from src.agent.manifest.context_manifest import write_diary_entry  # noqa: PLC0415
        _tools_used = [s.get("tool", "") for s in plan]
        _action = ", ".join(_tools_used) if _tools_used else "unknown"
        write_diary_entry(
            user_request=user_query.split("\n")[0][:200],  # strip session state block
            agent=skill_name,
            action=_action,
            found_paths=artifacts_out.get("found_paths", []),
            file_path=artifacts_out.get("file_path", ""),
            result_summary=final_message[:300],
        )
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as _de:
        logger.debug("Diary write skipped: %s", _de)

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

def _compact_tool_docs_for_planning(tool_docs: str, max_desc_chars: int = 90) -> str:
    """Shorten each tool's description to its first sentence for the planning prompt.

    The full rich descriptions in skills.md are needed for FAISS similarity selection
    but consume too many tokens in the planning prompt (~3,500 tokens for 44 tools).
    This trims each description to its first sentence (≤ ``max_desc_chars`` chars),
    keeping the tool name + signature visible while dramatically reducing token count.
    """
    compact = []
    for line in tool_docs.splitlines():
        if not line:
            compact.append(line)
            continue
        if " – " in line:
            sig, desc = line.split(" – ", 1)
            # Keep only the first sentence
            period_idx = desc.find(". ")
            if 0 < period_idx < max_desc_chars:
                desc = desc[:period_idx + 1]
            elif len(desc) > max_desc_chars:
                desc = desc[:max_desc_chars].rstrip() + "…"
            compact.append(f"{sig} – {desc}")
        else:
            compact.append(line)
    return "\n".join(compact)


def _plan_steps(
    skill_name: str,
    skill_context: str,
    tool_docs: str,
    tool_map: Dict[str, Callable],
    user_query: str,
    user_email: str = "",
) -> tuple[Optional[List[Dict[str, Any]]], int]:
    """
    Ask the LLM to produce an ordered list of tool-call steps.

    Returns (plan_list, llm_call_count).  plan_list is None on failure.
    """
    from src.agent.llm.llm_parser import get_llm_client, request_completion

    llm = get_llm_client()

    # Compact tool docs for planning prompt — full rich descriptions are only
    # needed for FAISS embedding; the planner only needs name + signature + 1 sentence.
    tool_docs_plan = _compact_tool_docs_for_planning(tool_docs)

    # Trim skill_context to keep planning prompt well under the 8k token limit.
    # The first 2000 chars cover the critical defaults (paths, rules, etc.).
    skill_context_plan = skill_context[:2000].rstrip()
    if len(skill_context) > 2000:
        skill_context_plan += "\n[…context truncated for planning…]"

    # ── Planning prompt: planning instruction FIRST, skill_context LAST ──
    # IMPORTANT: skill_context must NOT override the JSON-array output rule.
    # Put it at the end as "domain guidance" only, then restate the output
    # requirement as a final reminder so the model doesn't drift into prose.
    system_prompt = f"""You are a tool-call planner for the {skill_name} skill agent.

⚠️  YOUR ONLY JOB: output a JSON array of tool-call steps.
    The array MUST contain at least one step.
    NEVER produce an empty array or an object — always plan a concrete tool call.

Available tools:
{tool_docs_plan}

Output a JSON array — no markdown fences, no extra text — where each element is:
{{
  "id": "<short unique id, e.g. s1, s2, …>",
  "tool": "<exact tool name from the list above>",
  "kwargs": {{"<param>": "<concrete value>"}},
  "depends_on": ["<id of step whose output this step needs>"],
  "description": "<one sentence: what this step does>"
}}

Planning rules:
- Use ONLY tools listed above.  Do NOT invent tool names.
- kwargs must contain concrete, real values — never placeholders like "<value>" or "value1".
- The authenticated user's email address is available as {{__user_email__}}.
    If the user says "email me", "send it to me", "mail it to myself", or similar,
    use {{__user_email__}} for the recipient. Never use placeholder addresses such as
    user@example.com or recipient@example.com, and never put literal values like "me"
    or "myself" in the `to` field.
- ⛔ NEVER produce a plan that asks the user for clarification or a missing value.
  If a destination folder is not specified, use the default path shown in the domain guide below.
  Always plan a real tool call with a concrete value.
- For email counting requests like "how many emails from X", prefer a dedicated count tool
    when available. Do not use list_emails with max_results=1 to estimate totals.
- For email-summary requests where the user wants a PDF/report emailed to them, ALWAYS plan
    fetch_emails_to_markdown -> write_pdf_report -> send_email_with_attachment. Do not send
    raw markdown/report text via send_email for those requests.
- If a kwarg value depends on the output of a previous step, write it as {{step_id}} (the
  full result JSON string) or {{step_id.field}} to access a specific field, e.g.
  {{s1.results.0.path}} for the file path of the first search result from step s1.
  IMPORTANT: For file search results use .path (not .id) to get the actual file path.
- If the user query includes a '## Session State' block, you can reference its compact fields with
    {{__session__.<field>}} tokens.
    Prefer {{__session__.last_found_bundle_dir}} for previous-search zip/email follow-ups,
    {{__session__.last_found_file_path}} for single-file follow-ups, and
    {{__session__.file_manifest}} only as a manifest fallback when the files agent should call
    collect_files_from_manifest() or zip_files_from_manifest().
    If the user is making a FRESH SEARCH request ("Are there any X?", "Find Y", "Search for Z"),
    IGNORE previous file-follow-up fields and plan normal search steps instead.
- SEARCH STRATEGY: When the user asks for files by type ("image files", "video files", "pdf files"),
  ALWAYS search by extension — NEVER by name. Plan one search_by_extension step per extension.
  The execution engine automatically saves ALL results to the manifest — no explicit manifest step needed.
  Image extensions: jpg, jpeg, png, gif, bmp, tiff, webp, ico, svg
  Video extensions: mp4, avi, mov, mkv, wmv, flv
  Document extensions: pdf, docx, xlsx, pptx, txt
- Keep the plan minimal: include only the steps actually required.

Domain guidance (informational only — use to understand tool purpose and defaults):
{skill_context_plan}

Authenticated user email:
{user_email or "(unavailable)"}

--- END DOMAIN GUIDANCE ---
⚠️  OUTPUT REMINDER: Your response MUST be a JSON array starting with `[` and ending with `]`.
    Even for a 1-step task, output exactly `[{{...}}]`.  No prose, no wrapper object, no empty array."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": f"Request: {user_query}"},
    ]

    try:
        response = request_completion(
            llm=llm,
            messages=messages,
            temperature=0.0,
            max_tokens=800,
            timeout=40,
            purpose="skill_dag_planning",
            allow_local_fallback=True,
        )
        raw = _strip_fences(response.choices[0].message.content.strip())
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.error("│  ✗ [%s] Planning LLM call failed: %s", skill_name, exc)
        return None, 1

    logger.debug("│  [%s] raw planning response: %.500s", skill_name, raw)
    plan = _parse_plan(raw, tool_map, skill_name)
    if plan is None:
        logger.warning("│  [%s] full raw planning response (for diagnosis): %s", skill_name, raw[:1000])
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
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("│  ✗ [%s] Could not parse planning response as JSON", skill_name)
                return None
        else:
            logger.warning("│  ✗ [%s] No JSON array found in planning response", skill_name)
            return None

    # If the LLM wrapped the array in an object like {"steps": [...]} unwrap it
    if isinstance(plan, dict):
        for key in ("steps", "plan", "dag", "tasks"):
            if isinstance(plan.get(key), list):
                plan = plan[key]
                break

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
        if not message:
            logger.warning("│  ⚠ [%s] Synthesis returned empty message — using fallback", skill_name)
            raise ValueError("synthesis returned empty content")
        return message, 1
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
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
    user_email: str = "",
) -> Dict[str, Any]:
    """
    Substitute ``{step_id}`` / ``{step_id.field.subfield}`` tokens in string
    kwargs values using accumulated step results.

    Also resolves ``{__session__.field}`` tokens using the parsed ## Session State
    block. When the resolved value is structured data and the *entire* kwarg
    value is the token, the kwarg is replaced with the real object rather than
    a stringified version.
    """
    _sv = session_vars or {}
    _user_email = user_email or ""

    def _maybe_native_json(value: str) -> Any:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or value[0] not in "[{":
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value

    def _resolve_value(value: Any) -> Any:
        if isinstance(value, str) and '{' in value:
            sess_m = re.fullmatch(r'\{__session__\.([^}]+)\}', value.strip())
            if sess_m:
                field = sess_m.group(1)
                resolved = _sv.get(field)
                if resolved is not None:
                    return resolved
            user_m = re.fullmatch(r'\{__user_email__\}', value.strip())
            if user_m and _user_email:
                return _user_email
            return _TOKEN_PATTERN.sub(lambda m: _deep_get(m.group(1), results, _sv, _user_email), value)
        if isinstance(value, list):
            return [_resolve_value(item) for item in value]
        if isinstance(value, dict):
            if len(value) == 1:
                only_key, only_val = next(iter(value.items()))
                if (
                    isinstance(only_key, str)
                    and re.fullmatch(r'(?:__session__\.)?[A-Za-z0-9_]+(?:\.(?:[A-Za-z0-9_]+|\d+))*', only_key)
                    and only_val in ("", None, [], {})
                ):
                    resolved = _deep_get(only_key, results, _sv, _user_email)
                    if resolved != f"{{{only_key}}}":
                        return _maybe_native_json(resolved)
            return {k: _resolve_value(v) for k, v in value.items()}
        return value

    return {key: _resolve_value(val) for key, val in kwargs.items()}


_TOKEN_PATTERN = re.compile(r'\{([^}]+)\}')


def _deep_get(
    path: str,
    results: Dict[str, Any],
    session_vars: Optional[Dict[str, Any]] = None,
    user_email: str = "",
) -> str:
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
    if step_id == "__user_email__":
        return user_email or f"{{{path}}}"

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
        elif isinstance(data, list) and part in ("results", "emails", "messages", "items"):
            continue
        elif isinstance(data, list) and part.isdigit():
            idx = int(part)
            data = data[idx] if idx < len(data) else None
        else:
            data = None
        if data is None:
            # Graceful fallback: the LLM used a field name that doesn't exist
            # in the tool's return dict (e.g. "{s1.results}" when the tool
            # returns {"status": ..., "message": "..."}).
            # Prefer rich content fields first so report-generation steps can still
            # succeed when the planner references the wrong key (for example
            # {s1.results} for fetch_emails_to_markdown, which actually returns
            # report_content/content/emails).
            # Then fall back to the step's "message" field, then "data"/"results", then
            # the full result serialised as JSON.
            _sr = results.get(step_id, {})
            if isinstance(_sr, dict):
                _fallback = (
                    _sr.get("report_content")
                    or _sr.get("content")
                    or _sr.get("summary")
                    or _sr.get("emails")
                    or _sr.get("message")
                    or _sr.get("data")
                    or _sr.get("results")
                )
                if _fallback is not None:
                    return (
                        json.dumps(_fallback)
                        if isinstance(_fallback, (list, dict))
                        else str(_fallback)
                    )
                return json.dumps(_sr)
            if isinstance(_sr, list):
                return json.dumps(_sr)
            return str(_sr) if _sr is not None else f"{{{path}}}"

    return json.dumps(data) if isinstance(data, (list, dict)) else str(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(raw: str) -> str:
    """Remove optional ```json … ``` fences and any leading prose from LLM output.

    Handles both JSON arrays (``[…]``) and JSON objects (``{…}``).
    A common LLM pattern is to wrap the array in ``{"steps": […], "description": "…"}``;
    ``_parse_plan`` already unwraps that — so we must not corrupt the object by
    stripping the ``{" prefix when looking for the opening ``[``.
    """
    if "```" in raw:
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) >= 2 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    # Strip any leading prose before the actual JSON.  The response may start
    # with an array '[' or an object '{'.  Find whichever valid JSON start
    # comes first, and strip everything before it.
    arr = raw.find("[")
    obj = raw.find("{")
    candidates = [p for p in (arr, obj) if p >= 0]
    if candidates:
        start = min(candidates)
        if start > 0:
            raw = raw[start:]
    return raw.strip()
