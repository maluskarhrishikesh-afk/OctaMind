"""
File content reading tools for the Files Agent.

All tools use Python stdlib only — no external dependencies.
Supports: plain text, CSV, JSON, log tail, and file hashing.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..files_service import resolve_path, _fmt_size

logger = logging.getLogger("files_agent")

_READABLE_EXTENSIONS = {
    ".txt", ".md", ".log", ".py", ".js", ".ts", ".html", ".css", ".java",
    ".cpp", ".c", ".h", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".sh", ".bat", ".ps1", ".sql", ".r", ".rb", ".go", ".rs", ".php",
    ".json", ".csv", ".toml",
}

_MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB hard cap for text reads


def read_text_file(path: str, max_lines: int = 200) -> Dict[str, Any]:
    """
    Read a text-based file and return its contents.

    Supports .txt, .md, .log, .py, .json, .csv, .xml, .yaml, .html, and more.

    Args:
        path:      Path to the file.
        max_lines: Maximum number of lines to return. Default 200.
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"File does not exist: {p}"}
        if not p.is_file():
            return {"status": "error", "message": f"Not a file: {p}"}
        if p.stat().st_size > _MAX_READ_BYTES:
            return {
                "status": "error",
                "message": f"File is too large to read ({_fmt_size(p.stat().st_size)}). Use tail_log for log files.",
            }

        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                text = p.read_text(encoding=encoding)
                lines = text.splitlines()
                truncated = len(lines) > max_lines
                return {
                    "status": "success",
                    "path": str(p),
                    "encoding": encoding,
                    "total_lines": len(lines),
                    "returned_lines": min(len(lines), max_lines),
                    "truncated": truncated,
                    "content": "\n".join(lines[:max_lines]),
                }
            except (UnicodeDecodeError, UnicodeError):
                continue

        return {"status": "error", "message": "File encoding could not be detected. It may be a binary file."}
    except Exception as exc:
        logger.error("read_text_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_file_stats(path: str) -> Dict[str, Any]:
    """
    Return word count, line count, and character count for a text file.

    Args:
        path: Path to the file.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        result = read_text_file(path, max_lines=999999)
        if result["status"] == "error":
            return result

        content = result["content"]
        lines = content.splitlines()
        words = content.split()
        return {
            "status": "success",
            "path": str(p),
            "size": _fmt_size(p.stat().st_size),
            "lines": len(lines),
            "words": len(words),
            "characters": len(content),
            "non_empty_lines": sum(1 for l in lines if l.strip()),
        }
    except Exception as exc:
        logger.error("get_file_stats failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def preview_csv(path: str, rows: int = 10) -> Dict[str, Any]:
    """
    Preview a CSV file: show column headers and the first N rows.

    Args:
        path: Path to the CSV file.
        rows: Number of data rows to preview. Default 10.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                with open(p, newline="", encoding=encoding) as fh:
                    reader = csv.DictReader(fh)
                    headers = reader.fieldnames or []
                    data = [row for _, row in zip(range(rows), reader)]
                return {
                    "status": "success",
                    "path": str(p),
                    "columns": list(headers),
                    "column_count": len(headers),
                    "preview_rows": len(data),
                    "rows": data,
                }
            except (UnicodeDecodeError, UnicodeError):
                continue
        return {"status": "error", "message": "Could not decode CSV — encoding issue."}
    except Exception as exc:
        logger.error("preview_csv failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def read_json_file(path: str) -> Dict[str, Any]:
    """
    Parse and return the contents of a JSON file.

    Args:
        path: Path to the JSON file.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}
        if p.stat().st_size > _MAX_READ_BYTES:
            return {"status": "error", "message": "JSON file is too large (> 5 MB)."}

        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                data = json.loads(p.read_text(encoding=encoding))
                return {
                    "status": "success",
                    "path": str(p),
                    "type": type(data).__name__,
                    "length": len(data) if isinstance(data, (list, dict)) else None,
                    "data": data,
                }
            except (UnicodeDecodeError, UnicodeError):
                continue
            except json.JSONDecodeError as exc:
                return {"status": "error", "message": f"Invalid JSON: {exc}"}
        return {"status": "error", "message": "Could not decode file."}
    except Exception as exc:
        logger.error("read_json_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def tail_log(path: str, lines: int = 50) -> Dict[str, Any]:
    """
    Return the last N lines of a text or log file.

    Args:
        path:  Path to the file.
        lines: Number of lines from the end. Default 50.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                all_lines = p.read_text(encoding=encoding).splitlines()
                tail = all_lines[-lines:]
                return {
                    "status": "success",
                    "path": str(p),
                    "total_lines": len(all_lines),
                    "showing_last": len(tail),
                    "content": "\n".join(tail),
                }
            except (UnicodeDecodeError, UnicodeError):
                continue
        return {"status": "error", "message": "Could not decode file."}
    except Exception as exc:
        logger.error("tail_log failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def calculate_file_hash(path: str, algorithm: str = "md5") -> Dict[str, Any]:
    """
    Calculate the cryptographic hash of a file for integrity verification.

    Args:
        path:      Path to the file.
        algorithm: Hash algorithm: 'md5' (default) or 'sha256'.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        algo = algorithm.lower().replace("-", "")
        if algo not in ("md5", "sha256"):
            return {"status": "error", "message": "Algorithm must be 'md5' or 'sha256'."}

        h = hashlib.new(algo)
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)

        return {
            "status": "success",
            "path": str(p),
            "algorithm": algo,
            "hash": h.hexdigest(),
            "file_size": _fmt_size(p.stat().st_size),
        }
    except Exception as exc:
        logger.error("calculate_file_hash failed: %s", exc)
        return {"status": "error", "message": str(exc)}
