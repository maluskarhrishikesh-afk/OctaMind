"""
File Organizer Agent

An APPROVAL-DRIVEN intelligent file organization agent that:
  1. Scans folders and proposes an organization plan (never modifies without approval)
  2. Presents a detailed preview of what will change
  3. Applies the plan only after the user confirms
  4. Manages archival policies (store rules, auto-archive old files)
  5. Maintains OctaMind's own data/ and memory/ directories

Differentiator from the Files Agent:
  Files Agent      = General-purpose file manager (immediate actions)
  File Organizer   = Conversational "scan → propose → preview → approve → apply" workflow
                     + archival policies + OctaMind's own data maintenance
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("file_organizer_agent")

_ROOT         = Path(__file__).parent.parent.parent.parent.parent  # project root
_DATA_DIR     = _ROOT / "data"
_MEMORY_DIR   = _ROOT / "memory"
_PLANS_FILE   = _DATA_DIR / "organizer_pending_plans.json"
_POLICIES_FILE = _DATA_DIR / "organizer_archival_policies.json"

# Extension → category map (mirrors files_agent organizer but standalone)
_EXT_MAP: Dict[str, str] = {
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
    ".bmp": "Images", ".svg": "Images", ".webp": "Images", ".heic": "Images",
    ".mp4": "Videos", ".mov": "Videos", ".avi": "Videos", ".mkv": "Videos",
    ".mp3": "Audio",  ".wav": "Audio",  ".flac": "Audio", ".aac": "Audio",
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".xls": "Documents", ".xlsx": "Documents", ".ppt": "Documents", ".pptx": "Documents",
    ".txt": "Text",  ".md": "Text",   ".csv": "Text",  ".json": "Text",
    ".py":  "Code",  ".js":  "Code",  ".ts":  "Code",  ".html": "Code",
    ".css": "Code",  ".java":"Code",  ".cpp": "Code",  ".c":    "Code",
    ".zip": "Archives", ".rar": "Archives", ".7z": "Archives", ".tar": "Archives",
    ".exe": "Executables", ".msi": "Executables", ".bat": "Executables",
}


# ── Persistent plan store ──────────────────────────────────────────────────────

def _load_plans() -> Dict[str, Any]:
    try:
        if _PLANS_FILE.exists():
            return json.loads(_PLANS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_plans(plans: Dict[str, Any]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _PLANS_FILE.write_text(json.dumps(plans, indent=2, default=str), encoding="utf-8")


def _load_policies() -> List[Dict[str, Any]]:
    try:
        if _POLICIES_FILE.exists():
            data = json.loads(_POLICIES_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("policies", [])
    except Exception:
        pass
    return []


def _save_policies(policies: List[Dict[str, Any]]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _POLICIES_FILE.write_text(json.dumps(policies, indent=2, default=str), encoding="utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_resolve(raw_path: str) -> Optional[Path]:
    """Resolve a path; allow absolute paths or paths relative to project root."""
    p = Path(raw_path)
    if not p.is_absolute():
        p = _ROOT / p
    return p if p.exists() else None


def _fmt_size(sz: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if sz < 1024:
            return f"{sz:.1f} {unit}"
        sz //= 1024
    return f"{sz:.1f} TB"


# ── Tool: scan_and_propose ─────────────────────────────────────────────────────

def _scan_and_propose(
    directory: str,
    strategy: str = "by_type",
    max_files: int = 200,
) -> Dict[str, Any]:
    """
    Scan a directory and build an organization plan WITHOUT modifying anything.

    strategy: "by_type" | "by_date" | "by_name_prefix"
    Returns a plan_id that can be passed to apply_plan.
    """
    p = _safe_resolve(directory)
    if p is None:
        return {"status": "error", "message": f"Directory not found: '{directory}'"}

    if not p.is_dir():
        return {"status": "error", "message": f"'{directory}' is not a directory."}

    files = [f for f in p.iterdir() if f.is_file()][:max_files]
    if not files:
        return {"status": "success", "message": f"No files to organize in '{directory}'.", "plan_id": None}

    moves: List[Dict[str, str]] = []
    unmatched: List[str] = []

    for f in files:
        if strategy == "by_type":
            category = _EXT_MAP.get(f.suffix.lower(), "Other")
            dest = p / category / f.name
        elif strategy == "by_date":
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            folder = mtime.strftime("%Y-%m")
            dest   = p / folder / f.name
        elif strategy == "by_name_prefix":
            prefix = f.name[0].upper() if f.name else "Other"
            dest   = p / prefix / f.name
        else:
            unmatched.append(f.name)
            continue

        if dest != f:
            moves.append({"from": str(f), "to": str(dest), "file": f.name, "category": dest.parent.name})

    plan_id = str(uuid.uuid4())[:8]
    plan = {
        "plan_id": plan_id,
        "directory": str(p),
        "strategy": strategy,
        "created_at": datetime.now().isoformat(),
        "moves": moves,
        "status": "pending",
    }

    plans = _load_plans()
    plans[plan_id] = plan
    _save_plans(plans)

    # Build summary grouped by category
    from collections import Counter
    categories = Counter(m["category"] for m in moves)

    return {
        "status": "success",
        "plan_id": plan_id,
        "directory": str(p),
        "strategy": strategy,
        "total_files": len(files),
        "files_to_move": len(moves),
        "files_already_organised": len(files) - len(moves),
        "proposed_categories": dict(categories),
        "message": (
            f"Proposed organization plan '{plan_id}' for {len(files)} files in '{p.name}' "
            f"using strategy '{strategy}'.\n"
            f"{len(moves)} files will be moved into {len(categories)} categories: "
            f"{', '.join(f'{k} ({v})' for k, v in categories.most_common(5))}.\n\n"
            f"✅ Say **'apply plan {plan_id}'** to execute, or **'discard plan {plan_id}'** to cancel."
        ),
    }


# ── Tool: preview_plan ─────────────────────────────────────────────────────────

def _preview_plan(plan_id: str, max_show: int = 20) -> Dict[str, Any]:
    """Show the first N moves in a plan before applying."""
    plans = _load_plans()
    plan  = plans.get(plan_id)
    if not plan:
        return {"status": "error", "message": f"No plan found with id '{plan_id}'."}

    moves   = plan["moves"]
    preview = moves[:max_show]
    return {
        "status": "success",
        "plan_id": plan_id,
        "strategy": plan["strategy"],
        "total_moves": len(moves),
        "showing": len(preview),
        "preview": preview,
        "message": (
            f"Plan '{plan_id}': {len(moves)} file moves using '{plan['strategy']}' strategy.\n"
            + "\n".join(
                f"  {m['file']} → {Path(m['to']).parent.name}/"
                for m in preview
            )
            + (f"\n  … and {len(moves) - max_show} more." if len(moves) > max_show else "")
        ),
    }


# ── Tool: apply_plan ──────────────────────────────────────────────────────────

def _apply_plan(plan_id: str) -> Dict[str, Any]:
    """Execute a previously proposed organization plan."""
    plans = _load_plans()
    plan  = plans.get(plan_id)
    if not plan:
        return {"status": "error", "message": f"No pending plan with id '{plan_id}'."}
    if plan.get("status") == "applied":
        return {"status": "error", "message": f"Plan '{plan_id}' has already been applied."}

    moves   = plan["moves"]
    success = 0
    errors  = []

    for move in moves:
        src  = Path(move["from"])
        dest = Path(move["to"])
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            success += 1
        except Exception as e:
            errors.append(f"{move['file']}: {e}")

    plan["status"]     = "applied"
    plan["applied_at"] = datetime.now().isoformat()
    plan["success"]    = success
    plan["errors"]     = errors
    plans[plan_id]     = plan
    _save_plans(plans)

    return {
        "status":  "success" if not errors else "partial",
        "plan_id": plan_id,
        "moved":   success,
        "errors":  errors,
        "message": (
            f"✅ Plan '{plan_id}' applied: {success}/{len(moves)} files moved.\n"
            + (f"⚠️ {len(errors)} errors:\n" + "\n".join(errors[:5]) if errors else "")
        ),
    }


# ── Tool: discard_plan ────────────────────────────────────────────────────────

def _discard_plan(plan_id: str) -> Dict[str, Any]:
    """Discard a pending plan without applying it."""
    plans = _load_plans()
    if plan_id not in plans:
        return {"status": "error", "message": f"No plan with id '{plan_id}'."}
    del plans[plan_id]
    _save_plans(plans)
    return {"status": "success", "message": f"Plan '{plan_id}' discarded."}


# ── Tool: list_plans ──────────────────────────────────────────────────────────

def _list_plans() -> Dict[str, Any]:
    """List all pending and recently applied plans."""
    plans  = _load_plans()
    result = []
    for pid, plan in plans.items():
        result.append({
            "plan_id":    pid,
            "directory":  Path(plan["directory"]).name,
            "strategy":   plan["strategy"],
            "moves":      len(plan["moves"]),
            "status":     plan.get("status", "pending"),
            "created_at": plan.get("created_at", ""),
        })
    return {
        "status": "success",
        "count":  len(result),
        "plans":  result,
        "message": (
            f"{len(result)} plan(s) on file.\n"
            + "\n".join(f"  [{p['status']}] {p['plan_id']} — {p['directory']} ({p['moves']} moves, {p['strategy']})" for p in result)
            if result else "No pending plans."
        ),
    }


# ── Tool: archive_old_files ───────────────────────────────────────────────────

def _archive_old_files(
    directory: str,
    days_old: int = 90,
    destination: str = "",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Find files older than N days and propose/execute archival.

    dry_run=True (default): show what would be archived
    dry_run=False: actually move files to destination
    """
    p = _safe_resolve(directory)
    if p is None:
        return {"status": "error", "message": f"Directory not found: '{directory}'"}

    cutoff = datetime.now() - timedelta(days=days_old)
    old_files = []
    for f in p.rglob("*"):
        if f.is_file():
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                old_files.append({"file": f.name, "path": str(f), "modified": mtime.isoformat(), "size": f.stat().st_size})

    if not old_files:
        return {"status": "success", "message": f"No files older than {days_old} days found in '{directory}'."}

    dest_path = Path(destination) if destination else p / f"Archive_{date.today().isoformat()}"
    total_size = sum(f["size"] for f in old_files)

    if dry_run:
        return {
            "status": "dry_run",
            "files_found": len(old_files),
            "total_size": _fmt_size(total_size),
            "destination": str(dest_path),
            "sample": old_files[:10],
            "message": (
                f"🔍 DRY RUN: Found {len(old_files)} files older than {days_old} days "
                f"({_fmt_size(total_size)}).\n"
                f"Would be moved to: '{dest_path.name}/'\n\n"
                f"Run again with dry_run=False to apply."
            ),
        }

    dest_path.mkdir(parents=True, exist_ok=True)
    moved = 0
    errors = []
    for f in old_files:
        try:
            shutil.move(f["path"], str(dest_path / f["file"]))
            moved += 1
        except Exception as e:
            errors.append(f"{f['file']}: {e}")

    return {
        "status":      "success" if not errors else "partial",
        "moved":       moved,
        "errors":      errors,
        "destination": str(dest_path),
        "message":     f"✅ Archived {moved}/{len(old_files)} files to '{dest_path.name}'.",
    }


# ── Tool: cleanup_app_data ────────────────────────────────────────────────────

def _cleanup_app_data(dry_run: bool = True) -> Dict[str, Any]:
    """
    Analyse and optionally clean OctaMind's own data/ directory:
    - data/exports/ files older than 30 days
    - organizer_pending_plans.json entries with status=applied
    - Completed/stale scheduled messages
    """
    findings = []
    actions  = []

    # 1. Old export files
    exports_dir = _DATA_DIR / "exports"
    if exports_dir.exists():
        cutoff = datetime.now() - timedelta(days=30)
        for f in exports_dir.iterdir():
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    findings.append({"type": "old_export", "file": f.name, "modified": mtime.isoformat()})
                    if not dry_run:
                        try:
                            f.unlink()
                            actions.append(f"Deleted old export: {f.name}")
                        except Exception as e:
                            actions.append(f"Error deleting {f.name}: {e}")

    # 2. Applied plan entries in plans file
    plans = _load_plans()
    stale_plans = [pid for pid, p in plans.items() if p.get("status") == "applied"]
    if stale_plans:
        findings.append({"type": "applied_plans", "count": len(stale_plans), "plan_ids": stale_plans})
        if not dry_run:
            for pid in stale_plans:
                del plans[pid]
            _save_plans(plans)
            actions.append(f"Removed {len(stale_plans)} applied plan records.")

    # 3. data/ JSON file sizes
    large_jsons = []
    for f in _DATA_DIR.glob("*.json"):
        sz = f.stat().st_size
        if sz > 500_000:  # > 500KB
            large_jsons.append({"file": f.name, "size": _fmt_size(sz)})
    if large_jsons:
        findings.append({"type": "large_json", "files": large_jsons})

    if not findings:
        return {"status": "success", "message": "✅ OctaMind data directory looks clean — nothing to do."}

    summary_lines = []
    for f in findings:
        if f["type"] == "old_export":
            summary_lines.append(f"  - Old export file: {f['file']}")
        elif f["type"] == "applied_plans":
            summary_lines.append(f"  - {f['count']} applied plan record(s) (safe to remove)")
        elif f["type"] == "large_json":
            for lj in f["files"]:
                summary_lines.append(f"  - Large data file: {lj['file']} ({lj['size']})")

    prefix = "🔍 DRY RUN — " if dry_run else "✅ Applied — "
    return {
        "status":   "dry_run" if dry_run else "success",
        "findings": findings,
        "actions":  actions,
        "message": (
            f"{prefix}OctaMind data cleanup:\n"
            + "\n".join(summary_lines)
            + ("\n\nRun with dry_run=False to apply." if dry_run else "")
        ),
    }


# ── Tool: set_archival_policy ─────────────────────────────────────────────────

def _set_archival_policy(
    directory: str,
    days_old: int = 90,
    destination: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """Save an archival policy rule for a directory."""
    p = _safe_resolve(directory)
    dir_display = str(p) if p else directory

    policies = _load_policies()
    # Replace existing rule for the same directory
    policies = [pol for pol in policies if pol.get("directory") != dir_display]
    policies.append({
        "id":          str(uuid.uuid4())[:8],
        "directory":   dir_display,
        "days_old":    days_old,
        "destination": destination or str(Path(dir_display) / "Archive"),
        "description": description or f"Auto-archive files older than {days_old} days",
        "created_at":  datetime.now().isoformat(),
        "active":      True,
    })
    _save_policies(policies)

    return {
        "status": "success",
        "message": (
            f"✅ Archival policy set for '{Path(dir_display).name}':\n"
            f"  - Archive files older than {days_old} days\n"
            f"  - Destination: '{Path(destination or dir_display).name}/Archive'\n"
            f"  - Run **'run archival policies'** to apply all active policies."
        ),
    }


# ── Tool: show_archival_policies ──────────────────────────────────────────────

def _show_archival_policies() -> Dict[str, Any]:
    policies = _load_policies()
    if not policies:
        return {"status": "success", "message": "No archival policies defined yet.", "policies": []}

    lines = []
    for pol in policies:
        lines.append(
            f"  [{pol['id']}] {Path(pol['directory']).name}: "
            f"archive files > {pol['days_old']} days old → "
            f"{Path(pol['destination']).name}/"
        )
    return {
        "status":   "success",
        "count":    len(policies),
        "policies": policies,
        "message":  f"{len(policies)} archival policy/policies:\n" + "\n".join(lines),
    }


# ── Tool: run_archival_policies ───────────────────────────────────────────────

def _run_archival_policies(dry_run: bool = True) -> Dict[str, Any]:
    """Execute all active archival policies."""
    policies = [p for p in _load_policies() if p.get("active", True)]
    if not policies:
        return {"status": "success", "message": "No active archival policies to run."}

    results = []
    for pol in policies:
        result = _archive_old_files(
            directory   = pol["directory"],
            days_old    = pol["days_old"],
            destination = pol["destination"],
            dry_run     = dry_run,
        )
        results.append({"policy": pol["id"], "directory": Path(pol["directory"]).name, "result": result})

    prefix = "DRY RUN" if dry_run else "APPLIED"
    return {
        "status":  "success",
        "dry_run": dry_run,
        "results": results,
        "message": (
            f"[{prefix}] Ran {len(policies)} archival policy/policies.\n"
            + "\n".join(f"  {r['directory']}: {r['result'].get('message','')}" for r in results)
        ),
    }


# ── Tool dispatcher ────────────────────────────────────────────────────────────

_TOOLS_DESCRIPTION = """
1. **scan_and_propose**(directory: str, strategy: str = "by_type", max_files: int = 200)
   - Scan a folder and generate an organization plan WITHOUT touching any files.
   - strategy: "by_type" | "by_date" | "by_name_prefix"
   - Returns a plan_id. Always run this BEFORE apply_plan.
   - Use for: "organize my Downloads folder", "categorize my files"

2. **preview_plan**(plan_id: str, max_show: int = 20)
   - Show the first N proposed file moves from a plan.
   - Use for: "show me what plan X will do", "preview the organization"

3. **apply_plan**(plan_id: str)
   - Execute a previously generated plan. MODIFIES FILES.
   - Use for: "apply plan X", "yes, go ahead with the organization"

4. **discard_plan**(plan_id: str)
   - Discard a plan without applying it.
   - Use for: "cancel plan X", "forget the organization plan"

5. **list_plans**()
   - Show all pending and recently applied plans.
   - Use for: "show my pending plans", "what plans do I have?"

6. **archive_old_files**(directory: str, days_old: int = 90, destination: str = "", dry_run: bool = True)
   - Find and optionally archive files older than N days.
   - dry_run=True (default) shows preview; dry_run=False actually moves them.
   - Use for: "archive files older than 3 months", "clean up old files"

7. **cleanup_app_data**(dry_run: bool = True)
   - Analyse and clean OctaMind's own data/ directory (old exports, applied plans, etc.)
   - dry_run=True shows what would be done.
   - Use for: "clean up OctaMind data", "maintenance", "tidy up app data"

8. **set_archival_policy**(directory: str, days_old: int = 90, destination: str = "", description: str = "")
   - Create/update an archival rule for a folder (persisted to disk).
   - Use for: "auto-archive old files in Downloads after 60 days"

9. **show_archival_policies**()
   - List all saved archival policies.
   - Use for: "show archival policies", "what are my archive rules?"

10. **run_archival_policies**(dry_run: bool = True)
    - Execute all active archival policies.
    - Use for: "run archival policies", "apply all archive rules"
"""


def _dispatch_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
    _MAP = {
        "scan_and_propose":       lambda p: _scan_and_propose(**p),
        "preview_plan":           lambda p: _preview_plan(**p),
        "apply_plan":             lambda p: _apply_plan(**p),
        "discard_plan":           lambda p: _discard_plan(**p),
        "list_plans":             lambda p: _list_plans(**p),
        "archive_old_files":      lambda p: _archive_old_files(**p),
        "cleanup_app_data":       lambda p: _cleanup_app_data(**p),
        "set_archival_policy":    lambda p: _set_archival_policy(**p),
        "show_archival_policies": lambda p: _show_archival_policies(**p),
        "run_archival_policies":  lambda p: _run_archival_policies(**p),
    }
    fn = _MAP.get(tool)
    if fn is None:
        return {"status": "error", "message": f"Unknown tool: {tool}"}
    return fn(params)


# ── Main entry point ───────────────────────────────────────────────────────────

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> Dict[str, Any]:
    """
    Execute a natural-language file organization command.

    Approval workflow:
      scan_and_propose → (user reviews) → apply_plan
    """
    from src.agent.llm.llm_parser import get_llm_client

    user_command = user_query
    today_str    = date.today().isoformat()
    llm          = get_llm_client()

    selection_prompt = f"""Today's date is {today_str}.

You are an intelligent file organization assistant. Select ONE tool to handle the user's request.

Available tools:
{_TOOLS_DESCRIPTION}

User request: "{user_command}"

Respond with ONLY valid JSON:
{{
  "tool": "<tool_name>",
  "params": {{<key>: <value>, ...}},
  "reasoning": "<one sentence>"
}}

Rules:
- NEVER apply_plan directly unless the user explicitly says "apply", "yes go ahead", or "execute plan X"
- For organization requests: always scan_and_propose first
- For cleanup requests without explicit confirmation: use dry_run=True
- plan_id is an 8-char string (e.g. "a1b2c3d4")
- Omit optional params you don't need
"""

    try:
        sel_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a precise file organizer tool selector. Return ONLY valid JSON."},
                {"role": "user",   "content": selection_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=30,
        )
        sel_text = sel_response.choices[0].message.content.strip()
        clean    = re.sub(r"^```[a-z]*\n?", "", sel_text)
        clean    = re.sub(r"\n?```$", "", clean).strip()
        selection = json.loads(clean)
        tool   = selection.get("tool", "list_plans")
        params = selection.get("params", {})
        logger.info("[file_organizer_agent] Tool selected: %s params=%s", tool, params)
    except Exception as exc:
        logger.warning("[file_organizer_agent] Tool selection failed: %s — fallback to list_plans", exc)
        tool   = "list_plans"
        params = {}

    raw = _dispatch_tool(tool, params)

    compose_prompt = f"""The user asked: "{user_command}"

The file organizer tool "{tool}" returned:
{json.dumps(raw, indent=2, default=str)[:3000]}

Write a clear, helpful response:
- Use **bold** for file/folder names and plan IDs
- Use bullet points for file lists
- Use 📁 📂 🗄️ ✅ ⚠️ 🔍 emojis naturally
- For scan/propose results: clearly show the plan_id and tell the user how to preview or apply
- For dry-run results: explain what would happen and how to apply
- For apply results: confirm success and list any errors
- Do NOT expose raw JSON keys or internal field names
"""

    try:
        compose_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful file organization assistant."},
                {"role": "user",   "content": compose_prompt},
            ],
            temperature=0.4,
            max_tokens=1500,
            timeout=30,
        )
        final_message = compose_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[file_organizer_agent] Response composition failed: %s", exc)
        final_message = raw.get("message", str(raw))

    return {
        "status":    raw.get("status", "success"),
        "message":   final_message,
        "action":    "react_response",
        "raw":       raw,
        "tool_used": tool,
    }
