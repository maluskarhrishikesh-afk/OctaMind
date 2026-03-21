"""
LiteParse-backed document parsing tools.

These tools shell out to the local LiteParse CLI when available and return
actionable setup guidance when it is not installed.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.agent.runtime_paths import get_your_data_dir

from ..files_service import _fmt_size, resolve_path

logger = logging.getLogger("document_parser")

_DOCUMENT_PARSER_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    subprocess.SubprocessError,
)

_LITEPARSE_COMMAND_ENV = "LITEPARSE_COMMAND"
_PREVIEW_CHAR_LIMIT = 4000
_SUPPORTED_PARSE_FORMATS = {"json", "text"}
_SUPPORTED_SCREENSHOT_FORMATS = {"png", "jpg"}
_LIKELY_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".tsv",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    ".rtf",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".webp",
    ".svg",
}


def _slugify(value: str) -> str:
    cleaned = []
    for ch in str(value or ""):
        if ch.isalnum() or ch in ("-", "_"):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned).strip("._-")
    return slug or "document"


def _liteparse_install_hint() -> str:
    return (
        "LiteParse is not available on this machine. Install Node.js, then run "
        "'npm i -g @llamaindex/liteparse'. For Office documents on Windows, install "
        "LibreOffice and ensure its program directory is on PATH. For images, install "
        "ImageMagick if you need image-to-PDF conversion."
    )


def _resolve_liteparse_command() -> Tuple[Optional[List[str]], Optional[str]]:
    env_command = str(os.environ.get(_LITEPARSE_COMMAND_ENV, "") or "").strip()
    if env_command:
        return shlex.split(env_command, posix=os.name != "nt"), "env"

    lit_path = shutil.which("lit")
    if lit_path:
        return [lit_path], "lit"

    npx_path = shutil.which("npx")
    if npx_path:
        return [npx_path, "--yes", "@llamaindex/liteparse"], "npx"

    return None, None


def _default_parse_output_path(source: Path, output_format: str) -> Path:
    suffix = ".json" if output_format == "json" else ".txt"
    filename = f"{_slugify(source.stem)}_liteparse{suffix}"
    return get_your_data_dir("reports", "document_parser", create=True) / filename


def _default_screenshot_output_dir(source: Path) -> Path:
    return get_your_data_dir(
        "reports",
        "document_parser",
        f"{_slugify(source.stem)}_screenshots",
        create=True,
    )


def _coerce_output_path(path: str, *, is_dir: bool) -> Path:
    target = Path(path).expanduser()
    if is_dir:
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_preview(path: Path) -> tuple[str, bool]:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            return text[:_PREVIEW_CHAR_LIMIT], len(text) > _PREVIEW_CHAR_LIMIT
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            break
    return "", False


def _run_liteparse(args: List[str], timeout_seconds: int) -> Dict[str, Any]:
    command_prefix, source = _resolve_liteparse_command()
    if not command_prefix:
        return {
            "status": "error",
            "message": _liteparse_install_hint(),
            "available": False,
        }

    full_command = [*command_prefix, *args]
    try:
        completed = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=max(int(timeout_seconds), 1),
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": "error",
            "message": _liteparse_install_hint(),
            "available": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "error",
            "message": f"LiteParse timed out after {int(timeout_seconds)} second(s).",
            "available": True,
            "stdout": (exc.stdout or "")[:1000],
            "stderr": (exc.stderr or "")[:1000],
        }

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    result: Dict[str, Any] = {
        "status": "success" if completed.returncode == 0 else "error",
        "available": True,
        "command": full_command,
        "command_source": source,
        "returncode": completed.returncode,
        "stdout": stdout[:2000],
        "stderr": stderr[:2000],
    }
    if completed.returncode != 0:
        result["message"] = stderr.strip() or stdout.strip() or "LiteParse command failed."
    return result


def check_liteparse_installation() -> Dict[str, Any]:
    command, source = _resolve_liteparse_command()
    if not command:
        return {
            "status": "error",
            "available": False,
            "message": _liteparse_install_hint(),
        }
    return {
        "status": "success",
        "available": True,
        "message": "LiteParse command is available.",
        "command": command,
        "command_source": source,
    }


def parse_document_spatially(
    path: str,
    output_format: str = "json",
    output_path: str = "",
    target_pages: str = "",
    max_pages: int = 1000,
    dpi: int = 150,
    ocr_enabled: bool = True,
    ocr_language: str = "en",
    precise_bounding_boxes: bool = True,
    preserve_small_text: bool = False,
    timeout_seconds: int = 600,
) -> Dict[str, Any]:
    try:
        source = resolve_path(path)
        if not source.exists():
            return {"status": "error", "message": f"File does not exist: {source}"}
        if not source.is_file():
            return {"status": "error", "message": f"Not a file: {source}"}

        chosen_format = str(output_format or "json").strip().lower()
        if chosen_format not in _SUPPORTED_PARSE_FORMATS:
            return {"status": "error", "message": "output_format must be 'json' or 'text'."}

        output = _coerce_output_path(output_path, is_dir=False) if output_path else _default_parse_output_path(source, chosen_format)
        args = [
            "parse",
            str(source),
            "--format",
            chosen_format,
            "-o",
            str(output),
            "--max-pages",
            str(max(int(max_pages), 1)),
            "--dpi",
            str(max(int(dpi), 72)),
            "--ocr-language",
            str(ocr_language or "en"),
            "-q",
        ]
        if target_pages:
            args.extend(["--target-pages", str(target_pages)])
        if not ocr_enabled:
            args.append("--no-ocr")
        if not precise_bounding_boxes:
            args.append("--no-precise-bbox")
        if preserve_small_text:
            args.append("--preserve-small-text")

        command_result = _run_liteparse(args, timeout_seconds)
        if command_result["status"] == "error":
            return command_result
        if not output.exists():
            return {
                "status": "error",
                "message": "LiteParse completed but did not produce an output file.",
                "command": command_result.get("command", []),
            }

        preview, preview_truncated = _read_preview(output)
        payload: Dict[str, Any] = {
            "status": "success",
            "source_path": str(source),
            "output_path": str(output),
            "output_format": chosen_format,
            "source_size": _fmt_size(source.stat().st_size),
            "output_size": _fmt_size(output.stat().st_size),
            "preview": preview,
            "preview_truncated": preview_truncated,
            "target_pages": str(target_pages or "all"),
            "message": f"Parsed {source.name} with LiteParse into {output.name}.",
            "command": command_result.get("command", []),
        }
        if source.suffix.lower() in _LIKELY_DOCUMENT_EXTENSIONS:
            payload["detected_extension"] = source.suffix.lower()
        if chosen_format == "json" and output.stat().st_size <= 1_000_000:
            try:
                parsed_data = json.loads(output.read_text(encoding="utf-8"))
                if isinstance(parsed_data, dict):
                    payload["json_top_level_keys"] = list(parsed_data.keys())[:20]
                    pages = parsed_data.get("pages") if isinstance(parsed_data.get("pages"), list) else None
                    if pages is not None:
                        payload["page_count"] = len(pages)
                elif isinstance(parsed_data, list):
                    payload["record_count"] = len(parsed_data)
            except (OSError, ValueError, TypeError):
                logger.debug("LiteParse JSON output could not be summarized for %s", output)
        return payload
    except _DOCUMENT_PARSER_ERRORS as exc:
        logger.error("parse_document_spatially failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def batch_parse_documents(
    input_dir: str,
    output_dir: str = "",
    output_format: str = "json",
    recursive: bool = True,
    extension: str = "",
    max_pages: int = 1000,
    dpi: int = 150,
    ocr_enabled: bool = True,
    ocr_language: str = "en",
    timeout_seconds: int = 1200,
) -> Dict[str, Any]:
    try:
        source_dir = resolve_path(input_dir)
        if not source_dir.exists():
            return {"status": "error", "message": f"Directory does not exist: {source_dir}"}
        if not source_dir.is_dir():
            return {"status": "error", "message": f"Not a directory: {source_dir}"}

        chosen_format = str(output_format or "json").strip().lower()
        if chosen_format not in _SUPPORTED_PARSE_FORMATS:
            return {"status": "error", "message": "output_format must be 'json' or 'text'."}

        default_dir = get_your_data_dir("reports", "document_parser", f"batch_{_slugify(source_dir.name)}", create=True)
        destination = _coerce_output_path(output_dir, is_dir=True) if output_dir else default_dir
        args = [
            "batch-parse",
            str(source_dir),
            str(destination),
            "--format",
            chosen_format,
            "--max-pages",
            str(max(int(max_pages), 1)),
            "--dpi",
            str(max(int(dpi), 72)),
            "--ocr-language",
            str(ocr_language or "en"),
            "-q",
        ]
        if recursive:
            args.append("--recursive")
        if extension:
            ext = str(extension).strip()
            args.extend(["--extension", ext if ext.startswith(".") else f".{ext}"])
        if not ocr_enabled:
            args.append("--no-ocr")

        command_result = _run_liteparse(args, timeout_seconds)
        if command_result["status"] == "error":
            return command_result

        outputs = sorted(path for path in destination.rglob("*") if path.is_file())
        return {
            "status": "success",
            "input_dir": str(source_dir),
            "output_dir": str(destination),
            "output_format": chosen_format,
            "file_count": len(outputs),
            "files": [str(path) for path in outputs[:100]],
            "truncated": len(outputs) > 100,
            "message": f"Batch parsed {len(outputs)} file(s) into {destination}.",
            "command": command_result.get("command", []),
        }
    except _DOCUMENT_PARSER_ERRORS as exc:
        logger.error("batch_parse_documents failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def screenshot_document_pages(
    path: str,
    output_dir: str = "",
    target_pages: str = "",
    dpi: int = 200,
    image_format: str = "png",
    timeout_seconds: int = 900,
) -> Dict[str, Any]:
    try:
        source = resolve_path(path)
        if not source.exists():
            return {"status": "error", "message": f"File does not exist: {source}"}
        if not source.is_file():
            return {"status": "error", "message": f"Not a file: {source}"}

        chosen_format = str(image_format or "png").strip().lower()
        if chosen_format not in _SUPPORTED_SCREENSHOT_FORMATS:
            return {"status": "error", "message": "image_format must be 'png' or 'jpg'."}

        destination = _coerce_output_path(output_dir, is_dir=True) if output_dir else _default_screenshot_output_dir(source)
        args = [
            "screenshot",
            str(source),
            "-o",
            str(destination),
            "--dpi",
            str(max(int(dpi), 72)),
            "--format",
            chosen_format,
            "-q",
        ]
        if target_pages:
            args.extend(["--target-pages", str(target_pages)])

        command_result = _run_liteparse(args, timeout_seconds)
        if command_result["status"] == "error":
            return command_result

        screenshots = sorted(path for path in destination.iterdir() if path.is_file())
        return {
            "status": "success",
            "source_path": str(source),
            "output_dir": str(destination),
            "image_format": chosen_format,
            "count": len(screenshots),
            "files": [str(path) for path in screenshots[:100]],
            "truncated": len(screenshots) > 100,
            "target_pages": str(target_pages or "all"),
            "message": f"Generated {len(screenshots)} screenshot(s) for {source.name}.",
            "command": command_result.get("command", []),
        }
    except _DOCUMENT_PARSER_ERRORS as exc:
        logger.error("screenshot_document_pages failed: %s", exc)
        return {"status": "error", "message": str(exc)}