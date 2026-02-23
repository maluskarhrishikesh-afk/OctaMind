"""
AI-powered smart features for the Files Agent.

Uses the system LLM to analyse file contents and folder structures,
suggest organisation strategies, describe files, and more.
Same _call_llm() pattern as WhatsApp's smart_features.py.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from ..files_service import resolve_path, _fmt_size

logger = logging.getLogger("files_agent")


def _llm():
    from src.agent.llm.llm_parser import get_llm_client
    return get_llm_client()


def _call_llm(prompt: str, max_tokens: int = 1500, system: str = "") -> str:
    """Run a single LLM completion and return the response text."""
    client = _llm()
    system_msg = system or (
        "You are a helpful AI assistant specialised in analysing files and folders. "
        "Be concise, practical, and structured."
    )
    resp = client.client.chat.completions.create(
        model=client.model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
        timeout=45,
    )
    return resp.choices[0].message.content.strip()


def summarize_file(path: str) -> Dict[str, Any]:
    """
    Generate an LLM summary of a readable text file.

    Args:
        path: Path to the file (must be text-based: .txt, .md, .py, .json, .csv, etc.).
    """
    try:
        from .reader import read_text_file
        read_result = read_text_file(path, max_lines=400)
        if read_result["status"] == "error":
            return read_result

        content = read_result["content"]
        p = resolve_path(path)
        prompt = (
            f"Summarise the following file named '{p.name}'.\n"
            f"File type: {p.suffix}\n"
            f"Total lines: {read_result['total_lines']}\n\n"
            f"Content:\n{content[:6000]}"
        )
        summary = _call_llm(prompt, max_tokens=600)
        return {
            "status": "success",
            "path": str(p),
            "file": p.name,
            "total_lines": read_result["total_lines"],
            "summary": summary,
        }
    except Exception as exc:
        logger.error("summarize_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def analyze_folder(directory: str) -> Dict[str, Any]:
    """
    Generate an LLM analysis of a folder — contents, size distribution, patterns.

    Args:
        directory: Directory to analyse.
    """
    try:
        from .file_ops import list_directory
        from .disk import get_directory_size
        lst = list_directory(directory, limit=300)
        if lst["status"] == "error":
            return lst

        sz = get_directory_size(directory)
        p = resolve_path(directory)

        # Build a compact text description for the LLM
        ext_count: Dict[str, int] = {}
        for e in lst["entries"]:
            ext = e.get("extension", "") or "(folder)"
            ext_count[ext] = ext_count.get(ext, 0) + 1

        ext_summary = "\n".join(f"  {ext or 'no ext'}: {cnt} file(s)" for ext, cnt in
                                sorted(ext_count.items(), key=lambda x: x[1], reverse=True)[:15])

        prompt = (
            f"Analyse the following directory and provide a concise report.\n\n"
            f"Directory: {p}\n"
            f"Total items: {lst['total_entries']} ({lst['files']} files, {lst['folders']} folders)\n"
            f"Total size: {sz.get('total_size', 'unknown')}\n"
            f"File type breakdown:\n{ext_summary}\n\n"
            f"Provide:\n"
            f"1. A one-sentence description of what this folder seems to contain.\n"
            f"2. Notable observations (largest categories, potential clutter, etc.).\n"
            f"3. 2-3 suggested actions to keep it organised."
        )
        analysis = _call_llm(prompt, max_tokens=700)
        return {
            "status": "success",
            "path": str(p),
            "total_entries": lst["total_entries"],
            "total_size": sz.get("total_size", "unknown"),
            "analysis": analysis,
        }
    except Exception as exc:
        logger.error("analyze_folder failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def suggest_organization(directory: str) -> Dict[str, Any]:
    """
    Ask the LLM to suggest a folder structure for the given directory.

    Args:
        directory: Directory to reorganise.
    """
    try:
        from .file_ops import list_directory
        lst = list_directory(directory, limit=200)
        if lst["status"] == "error":
            return lst

        p = resolve_path(directory)
        file_names = [e["name"] for e in lst["entries"] if e["type"] == "file"][:100]
        folder_names = [e["name"] for e in lst["entries"] if e["type"] == "folder"][:30]

        prompt = (
            f"I have a folder at '{p}' with {lst['files']} files and {lst['folders']} subfolders.\n\n"
            f"Files (sample): {', '.join(file_names[:50])}\n"
            f"Subfolders: {', '.join(folder_names)}\n\n"
            f"Suggest a practical folder structure to organise these files. "
            f"List the suggested subfolders, what goes in each, and any rename suggestions. "
            f"Be specific and actionable."
        )
        suggestion = _call_llm(prompt, max_tokens=800)
        return {
            "status": "success",
            "path": str(p),
            "file_count": lst["files"],
            "suggestion": suggestion,
        }
    except Exception as exc:
        logger.error("suggest_organization failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def generate_rename_suggestions(directory: str) -> Dict[str, Any]:
    """
    Suggest cleaner, more descriptive names for cryptically-named files.

    Args:
        directory: Directory containing files to rename.
    """
    try:
        from .file_ops import list_directory
        lst = list_directory(directory, limit=100)
        if lst["status"] == "error":
            return lst

        p = resolve_path(directory)
        files = [e["name"] for e in lst["entries"] if e["type"] == "file"][:60]

        prompt = (
            f"Here is a list of filenames from the folder '{p.name}':\n\n"
            + "\n".join(f"  {name}" for name in files)
            + "\n\nFor each filename that looks cryptic, abbreviated, or unclear, "
            "suggest a cleaner descriptive name. Format your response as:\n"
            "  OLD_NAME → SUGGESTED_NAME (reason)\n\n"
            "Only suggest renames where it genuinely improves clarity. "
            "Skip names that are already clear."
        )
        suggestions = _call_llm(prompt, max_tokens=1000)
        return {
            "status": "success",
            "path": str(p),
            "file_count": len(files),
            "suggestions": suggestions,
        }
    except Exception as exc:
        logger.error("generate_rename_suggestions failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def find_related_files(path: str) -> Dict[str, Any]:
    """
    Find files related to *path* by name similarity in the same directory.

    Args:
        path: Reference file path.
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"File not found: {p}"}

        stem_lower = p.stem.lower()
        siblings = []
        for child in p.parent.iterdir():
            if child == p:
                continue
            name_lower = child.stem.lower()
            # Check for common tokens
            tokens_ref = set(stem_lower.replace("_", " ").replace("-", " ").split())
            tokens_cmp = set(name_lower.replace("_", " ").replace("-", " ").split())
            common = tokens_ref & tokens_cmp
            if common:
                siblings.append({
                    "name": child.name,
                    "path": str(child),
                    "common_tokens": list(common),
                })

        prompt = (
            f"I have a file named '{p.name}'. These files in the same folder share some name tokens with it:\n"
            + "\n".join(f"  {s['name']} (shared: {', '.join(s['common_tokens'])})" for s in siblings[:20])
            + "\n\nBriefly describe what these files likely have in common and why they are related."
        ) if siblings else ""

        related_description = _call_llm(prompt) if prompt else "No related files found by name similarity."

        return {
            "status": "success",
            "file": p.name,
            "related_count": len(siblings),
            "related_files": siblings[:20],
            "description": related_description,
        }
    except Exception as exc:
        logger.error("find_related_files failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def describe_file(path: str) -> Dict[str, Any]:
    """
    Generate a natural language description of a file (what it likely is and contains).

    Works for text files by reading content; for binary files uses name/extension heuristics.

    Args:
        path: Path to the file.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        from .reader import read_text_file
        read_result = read_text_file(path, max_lines=80)
        content_snippet = ""
        if read_result["status"] == "success":
            content_snippet = read_result["content"][:3000]

        sz = p.stat().st_size
        prompt = (
            f"Describe this file in 2-3 sentences.\n\n"
            f"Name: {p.name}\n"
            f"Extension: {p.suffix}\n"
            f"Size: {_fmt_size(sz)}\n"
            + (f"Content preview:\n{content_snippet}" if content_snippet else "(Binary or unreadable file)")
        )
        description = _call_llm(prompt, max_tokens=300)
        return {
            "status": "success",
            "path": str(p),
            "name": p.name,
            "size": _fmt_size(sz),
            "description": description,
        }
    except Exception as exc:
        logger.error("describe_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}
