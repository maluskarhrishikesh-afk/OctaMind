"""
Local Files skill orchestrator.

Key corrections vs. older version:
- search_by_name first argument is ``query`` (not ``pattern``).
- _build_skill_context() is dynamic so the LLM receives the real
  system paths (home / Downloads / Desktop / Documents) rather than
  guessing platform-specific placeholders.
- Tool documentation is loaded from skills.md with cosine-similarity
  selection for the ReAct engine (fewer tokens, more relevant tools).
  The DAG planner still sees the full tool list.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agent.runtime_paths import get_your_data_dir
from src.agent.telemetry import log_fallback_to_react, log_fast_path_hit
from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag

_FILES_ORCHESTRATOR_ERRORS = (
    AttributeError,
    ImportError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp", "svg", "ico"]
_VIDEO_EXTENSIONS = ["mp4", "avi", "mov", "mkv", "wmv", "flv", "webm"]
_DOCUMENT_EXTENSIONS = ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt"]
_ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
_SKIP_RESULT_PARTS = {"__pycache__", ".pytest_cache"}
_COMPUTER_SCOPE_RE = re.compile(
    r"\b((?:on|in)\s+my\s+(computer|laptop|pc|machine)|(?:on|in)\s+this\s+(computer|laptop|pc|machine)|across\s+all\s+drives|all\s+drives|whole\s+(computer|system)|entire\s+(computer|laptop|system))\b",
    re.IGNORECASE,
)
_SCOPED_SYSTEM_FOLDER_RE = re.compile(
    r"\b(?:is\s+there|do\s+i\s+have|find|search\s+for|look\s+for|locate|check\s+if|how\s+many\s+files\s+are\s+there\s+in)\b.*?\b(?:(file|folder)\s+)?(?:named|called)\s+[\"']?([^\"'?.\n]+?)[\"']?\s+in\s+(downloads?|desktop|documents?|pictures?|videos?|music)\b",
    re.IGNORECASE | re.DOTALL,
)
_SCOPED_SYSTEM_FOLDER_CONTAINS_RE = re.compile(
    r"\b(?:is\s+there|do\s+i\s+have|find|search\s+for|look\s+for|locate|check\s+if)\b.*?\b(?:(file|folder)\s+)?(?:containing|contains|with)\s+(?:the\s+)?name\s+[\"']?([^\"'?.\n]+?)[\"']?\s+in\s+(downloads?|desktop|documents?|pictures?|videos?|music)\b",
    re.IGNORECASE | re.DOTALL,
)
_FILENAME_CONTAINS_RE = re.compile(
    r"\b(?:containing|contains|with)\s+[\"']?([^\"'?.\n]+?)[\"']?\s+in\s+(?:its|the)\s+file\s*name\b",
    re.IGNORECASE,
)
_RECYCLE_BIN_COUNT_RE = re.compile(
    r"\b(?:how\s+many|count|number\s+of|what\s+is\s+in|how\s+full\s+is)\b.*\b(?:recycle\s+bin|trash\s+bin|bin)\b",
    re.IGNORECASE,
)
_LAST_N_MONTHS_PAYSLIP_RE = re.compile(
    r"\b(?:zip|send|share|give)\b.*\blast\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+months?\b.*\b(payslip|payslips)\b",
    re.IGNORECASE | re.DOTALL,
)
_COUNTED_SUBSET_ZIP_RE = re.compile(
    r"\b(?:zip|compress|archive)\b.*\b(?:last|first|\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"|\b(?:zip|compress|archive)\b.*\b(images?|photos?|pictures?|files?|items?|results?|documents?|pdfs?|videos?)\b",
    re.IGNORECASE | re.DOTALL,
)
_SPECIFIC_FOLDER_COUNT_RE = re.compile(
    r"\bhow\s+many\s+files?\s+and\s+folders?\s+are\s+there\s+in\s+(.+?)\s+folder(?:\s+in\s+([a-z]))?\s+drive\b",
    re.IGNORECASE | re.DOTALL,
)
_SPECIFIC_DRIVE_ITEM_LOOKUP_RE = re.compile(
    r"\b(?:is\s+there|do\s+i\s+have|find|search\s+for|look\s+for|locate|check\s+if)\b.*?\b(?:(file|folder)\s+)?(?:named|called)\s+[\"']?([^\"'?.\n]+?)[\"']?\s+(?:on|in)\s+(?:my\s+)?([a-z])\s+drive\b",
    re.IGNORECASE | re.DOTALL,
)
_SPECIFIC_COMPUTER_ITEM_LOOKUP_RE = re.compile(
    r"\b(?:is\s+there|do\s+i\s+have|find|search\s+for|look\s+for|locate|check\s+if)\b.*?\b(?:(file|folder)\s+)?(?:named|called)\s+[\"']?([^\"'?.\n]+?)[\"']?\s+(?:on|in)\s+(?:my|this)\s+(?:computer|laptop|pc|machine)\b",
    re.IGNORECASE | re.DOTALL,
)
_CONTEXTUAL_FOLDER_COUNT_RE = re.compile(
    r"\bhow\s+many\s+(?:files?\s+and\s+folders?|folders?\s+and\s+files?)\b.*?\b(?:inside|in)\s+(?:it|that|this|the\s+folder|the\s+directory)\b",
    re.IGNORECASE | re.DOTALL,
)
_DIRECT_FOLDER_COUNT_RE = re.compile(
    r"\bhow\s+many\s+(?:files?\s+and\s+folders?|folders?\s+and\s+files?)\b.*?\bin\s+(.+?)\s+folder(?:\s+(?:on|in)\s+(?:my|this)\s+(?:computer|laptop|pc|machine))?\b",
    re.IGNORECASE | re.DOTALL,
)
_MONTH_NAME_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_COUNT_WORD_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _return_fast_path_result(result: Dict[str, Any]) -> Dict[str, Any]:
    fast_path = str(result.get("_fast_path", "") or result.get("action", "unknown"))
    log_fast_path_hit("files", fast_path)
    return result


def _infer_extension_filter(user_query: str) -> Optional[List[str]]:
    lowered = str(user_query or "").lower()
    if any(token in lowered for token in ("image file", "image files", "photo", "photos", "picture", "pictures")):
        return list(_IMAGE_EXTENSIONS)
    if any(token in lowered for token in ("video file", "video files", "videos")):
        return list(_VIDEO_EXTENSIONS)
    if "pdf" in lowered:
        return ["pdf"]
    if any(token in lowered for token in ("document file", "document files", "documents")):
        return list(_DOCUMENT_EXTENSIONS)
    return None


def _singularize_term(value: str) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered.endswith("ies") and len(text) > 3:
        return text[:-3] + "y"
    if lowered.endswith("s") and not lowered.endswith(("ss", "us")) and len(text) > 3:
        return text[:-1]
    return text


def _matches_requested_name(item: Dict[str, Any], term: str, match_mode: str = "exact") -> bool:
    requested = str(term or "").strip().casefold()
    if not requested:
        return False

    name = str(item.get("name", "") or "").strip()
    if not name:
        name = Path(str(item.get("path", "") or "").strip()).name
    candidate = name.casefold()
    if not candidate:
        return False

    if match_mode == "contains":
        return requested in candidate

    if candidate == requested:
        return True

    item_type = str(item.get("type", "") or "").strip().lower()
    if item_type == "file" and "." not in requested:
        return Path(name).stem.casefold() == requested

    return False


def _filter_named_matches(matches: List[Dict[str, Any]], term: str, match_mode: str = "exact") -> List[Dict[str, Any]]:
    return [item for item in matches if _matches_requested_name(item, term, match_mode=match_mode)]


def _parse_precise_full_computer_search(user_query: str) -> Optional[Dict[str, Any]]:
    raw_query = str(user_query or "")
    lowered = raw_query.lower()
    if not _COMPUTER_SCOPE_RE.search(raw_query):
        return None

    named_match = re.search(
        r"\b(?:an?\s+)?(?:image|video|pdf|document)?\s*(?:file|folder)?\s*named\s+[\"']?([^\"'?.\n]+?)[\"']?(?:\s+on\s+my\s+(?:computer|laptop|pc|machine)|\?|$)",
        raw_query,
        re.IGNORECASE,
    )
    if named_match:
        term = named_match.group(1).strip().rstrip("?.!,")
        return {
            "mode": "named_search",
            "term": term,
            "match_mode": "exact",
            "extensions": _infer_extension_filter(raw_query),
            "include_folders": "folder named" in lowered and "file named" not in lowered,
            "limit": 50,
        }

    filename_name_match = re.search(
        r"\b(?:an?\s+)?(?:image|video|pdf|document)?\s*(?:file|folder)?\s*name\s+[\"']?([^\"'?.\n]+?)[\"']?(?:\s+(?:on|in)\s+(?:my|this)\s+(?:computer|laptop|pc|machine)|\?|$)",
        raw_query,
        re.IGNORECASE,
    )
    if filename_name_match:
        term = filename_name_match.group(1).strip().rstrip("?.!,")
        return {
            "mode": "named_search",
            "term": term,
            "match_mode": "exact",
            "extensions": _infer_extension_filter(raw_query),
            "include_folders": False,
            "limit": 50,
        }

    contains_name_match = re.search(
        r"\b(?:containing|contains|with)\s+(?:the\s+)?name\s+[\"']?([^\"'?.\n]+?)[\"']?(?:\s+(?:on|in)\s+(?:my|this)\s+(?:computer|laptop|pc|machine)|\?|$)",
        raw_query,
        re.IGNORECASE,
    )
    if contains_name_match:
        term = contains_name_match.group(1).strip().rstrip("?.!,")
        return {
            "mode": "named_search",
            "term": term,
            "match_mode": "contains",
            "extensions": _infer_extension_filter(raw_query),
            "include_folders": False,
            "limit": 50,
        }

    count_match = re.search(
        r"\bhow\s+many\s+(.+?)\s+(?:are\s+there|do\s+i\s+have|exist)\b",
        raw_query,
        re.IGNORECASE,
    )
    if count_match:
        phrase = count_match.group(1).strip().lower()
        phrase = re.sub(r"\b(any|all|the|my)\b", " ", phrase)
        phrase = re.sub(r"\b(files?|folders?|documents?|images?|videos?)\b", " ", phrase)
        phrase = re.sub(r"\s+", " ", phrase).strip(" .?!,")
        if phrase:
            return {
                "mode": "count_search",
                "term": _singularize_term(phrase),
                "extensions": _infer_extension_filter(raw_query),
                "include_folders": False,
                "limit": 0,
            }
    return None


def _system_folder_path(keyword: str) -> Optional[Path]:
    home = Path.home()
    mapping = {
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "document": home / "Documents",
        "pictures": home / "Pictures",
        "picture": home / "Pictures",
        "videos": home / "Videos",
        "video": home / "Videos",
        "music": home / "Music",
    }
    lowered = str(keyword or "").strip().lower()
    return mapping.get(lowered, mapping.get(lowered.rstrip("s")))


def _load_personal_folder_map() -> Dict[str, str]:
    try:
        settings_path = Path(__file__).resolve().parents[4] / "config" / "settings.json"
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        personal_folders = payload.get("personal_folders", {}) if isinstance(payload, dict) else {}
        return {
            str(name).strip().lower(): str(path).strip()
            for name, path in personal_folders.items()
            if not str(name).startswith("_") and str(path).strip()
        }
    except (OSError, TypeError, ValueError):
        return {}


def _resolve_named_folder_path(folder_name: str, drive_letter: str = "") -> Optional[Path]:
    normalized_name = str(folder_name or "").strip().strip('"\'').strip()
    if not normalized_name:
        return None

    personal_map = _load_personal_folder_map()
    mapped = personal_map.get(normalized_name.lower())
    if mapped:
        candidate = Path(mapped)
        if candidate.exists() and candidate.is_dir():
            return candidate

    if drive_letter:
        candidate = Path(f"{drive_letter.upper()}:\\") / normalized_name
        if candidate.exists() and candidate.is_dir():
            return candidate

    fallback = Path.home() / normalized_name
    if fallback.exists() and fallback.is_dir():
        return fallback

    return None


def _parse_specific_folder_count_query(user_query: str) -> Optional[Dict[str, str]]:
    match = _SPECIFIC_FOLDER_COUNT_RE.search(str(user_query or ""))
    if not match:
        return None
    folder_name = str(match.group(1) or "").strip().rstrip("?.!,")
    drive_letter = str(match.group(2) or "").strip()
    if not folder_name:
        return None
    return {
        "folder_name": folder_name,
        "drive_letter": drive_letter,
    }


def _parse_specific_drive_item_query(user_query: str) -> Optional[Dict[str, str]]:
    match = _SPECIFIC_DRIVE_ITEM_LOOKUP_RE.search(str(user_query or ""))
    if not match:
        return None
    item_type = str(match.group(1) or "folder").strip().lower() or "folder"
    item_name = str(match.group(2) or "").strip().rstrip("?.!,")
    drive_letter = str(match.group(3) or "").strip().lower()
    if not item_name or item_type == "file":
        return None
    return {
        "item_type": item_type,
        "item_name": item_name,
        "drive_letter": drive_letter,
    }


def _parse_specific_computer_item_query(user_query: str) -> Optional[Dict[str, str]]:
    match = _SPECIFIC_COMPUTER_ITEM_LOOKUP_RE.search(str(user_query or ""))
    if not match:
        return None
    item_type = str(match.group(1) or "folder").strip().lower() or "folder"
    item_name = str(match.group(2) or "").strip().rstrip("?.!,")
    if not item_name or item_type == "file":
        return None
    return {
        "item_type": item_type,
        "item_name": item_name,
    }


def _parse_direct_folder_count_query(user_query: str) -> Optional[str]:
    match = _DIRECT_FOLDER_COUNT_RE.search(str(user_query or ""))
    if not match:
        return None
    folder_name = str(match.group(1) or "").strip().rstrip("?.!,")
    return folder_name or None


def _parse_scoped_named_search(user_query: str) -> Optional[Dict[str, Any]]:
    raw_query = str(user_query or "")
    match = _SCOPED_SYSTEM_FOLDER_RE.search(raw_query)
    match_mode = "exact"
    if not match:
        match = _SCOPED_SYSTEM_FOLDER_CONTAINS_RE.search(raw_query)
        match_mode = "contains"
    if not match:
        return None

    item_type = (match.group(1) or "").strip().lower()
    term = str(match.group(2) or "").strip().rstrip("?.!,")
    folder_keyword = str(match.group(3) or "").strip().lower()
    scope_path = _system_folder_path(folder_keyword)
    if not term or scope_path is None:
        return None

    return {
        "term": term,
        "match_mode": match_mode,
        "item_type": item_type,
        "scope_label": scope_path.name,
        "directory": str(scope_path),
    }


def _parse_filename_contains_search(user_query: str) -> Optional[Dict[str, Any]]:
    raw_query = str(user_query or "")
    contains_match = _FILENAME_CONTAINS_RE.search(raw_query)
    if not contains_match:
        return None

    term = str(contains_match.group(1) or "").strip().rstrip("?.!,")
    if not term:
        return None

    return {
        "term": term,
        "extensions": _infer_extension_filter(raw_query),
        "include_folders": False,
        "limit": 50,
    }


def _save_precise_search_context(result: Dict[str, Any], query: str) -> None:
    try:
        from src.agent.manifest.context_manifest import auto_save_files_context  # noqa: PLC0415
        from src.files.features.file_ops import save_search_manifest  # noqa: PLC0415

        paths = [str(item.get("path", "")).strip() for item in result.get("results", []) if str(item.get("path", "")).strip()]
        if paths:
            manifest_result = save_search_manifest(paths, label=query or "search_results")
            if manifest_result.get("status") == "success":
                result["manifest_path"] = manifest_result.get("manifest_path", "")
                result["manifest_id"] = manifest_result.get("manifest_id", "")
                result["manifest_label"] = manifest_result.get("label", "")
        auto_save_files_context(result, query)
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def _query_prefers_archives(user_query: str) -> bool:
    lowered = str(user_query or "").lower()
    return any(token in lowered for token in ("zip", "archive", "compressed", "rar", "7z"))


def _is_generated_runtime_artifact(path: Path) -> bool:
    manifests_root = get_your_data_dir("manifests", create=True)
    your_data_root = get_your_data_dir(create=True)
    if _is_within(path, manifests_root):
        return True
    if _is_within(path, your_data_root) and path.name in {"active_file_manifest.json", "octa_manifest.txt"}:
        return True
    return False


def _is_temp_or_test_artifact(path: Path) -> bool:
    lowered_parts = [part.lower() for part in path.parts]
    if any(part in _SKIP_RESULT_PARTS for part in lowered_parts):
        return True
    try:
        temp_root = Path(tempfile.gettempdir()).resolve()
        resolved_path = path.resolve()
        resolved_path.relative_to(temp_root)
        if any(part.startswith("pytest-") or part.startswith("pytest-of-") for part in lowered_parts):
            return True
        return True
    except ValueError:
        return False
    except (OSError, RuntimeError):
        return False


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _stage_precise_search_results(term: str, result: Dict[str, Any]) -> Dict[str, Any]:
    paths = [str(item.get("path", "") or "").strip() for item in result.get("results", []) if str(item.get("path", "") or "").strip()]
    if not paths:
        return result
    try:
        from src.files.features.file_ops import stage_search_results  # noqa: PLC0415

        stage_result = stage_search_results(paths, label=term, category="search_results")
        if stage_result.get("status") == "success":
            enriched = dict(result)
            enriched["search_bundle_dir"] = stage_result.get("bundle_dir", "")
            enriched["search_bundle_files"] = stage_result.get("staged_files", [])
            return enriched
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return result


def _filter_precise_search_results(user_query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    matches = result.get("results", []) or []
    if not matches or _query_prefers_archives(user_query):
        return result

    archive_root = get_your_data_dir("archives", create=True)
    filtered_matches: List[Dict[str, Any]] = []

    for item in matches:
        path_str = str(item.get("path", "") or "").strip()
        if not path_str:
            filtered_matches.append(item)
            continue
        path_obj = Path(path_str)
        if _is_temp_or_test_artifact(path_obj):
            continue
        if _is_generated_runtime_artifact(path_obj):
            continue
        is_archive = path_obj.suffix.lower() in _ARCHIVE_EXTENSIONS
        is_generated_archive = _is_within(path_obj, archive_root)
        if is_archive or is_generated_archive:
            continue
        filtered_matches.append(item)

    if not filtered_matches:
        return result

    filtered_result = dict(result)
    filtered_result["results"] = filtered_matches
    filtered_result["count"] = len(filtered_matches)
    first_path = str(filtered_matches[0].get("path", "") or "").strip() if filtered_matches else ""
    filtered_result["file_path"] = first_path
    filtered_result["filtered_archive_count"] = len(matches) - len(filtered_matches)
    return filtered_result


_FOLLOW_UP_ZIP_RE = re.compile(
    r'\bzip\b.{0,80}\b(them|those|it|files?|results?|found|searched|previous search)\b'
    r'|\b(previous search|searched|found)\b.{0,80}\bzip\b'
    r'|\bzip searched\b',
    re.IGNORECASE | re.DOTALL,
)
_LIST_NAMES_RE = re.compile(
    r'\b(type|list|show|display|write)\b.{0,40}\b(file|folder|item)?\s*names?\b'
    r'|\bwhat are the file names\b'
    r'|\btype the file names here\b',
    re.IGNORECASE | re.DOTALL,
)
_DIRECTORY_FILE_COUNT_RE = re.compile(
    r'\bhow many\s+files\b'
    r'|\bfile\s+count\b'
    r'|\bnumber\s+of\s+files\b',
    re.IGNORECASE,
)
_FOLLOW_UP_RENAME_RE = re.compile(
    r'\brename\b.*?\bto\b\s+["\']?([^"\'\n]+?)["\']?\s*[?!.]?$',
    re.IGNORECASE | re.DOTALL,
)


def _strip_injected_blocks(user_query: str) -> str:
    raw_query = user_query.split("## Context from Previous Turn")[0]
    raw_query = raw_query.split("## Conversation Diary")[0]
    return raw_query.split("## Session State")[0].strip()


def _extract_last_n_months(raw_query: str) -> Optional[int]:
    match = _LAST_N_MONTHS_PAYSLIP_RE.search(str(raw_query or ""))
    if not match:
        return None
    value = str(match.group(1) or "").strip().lower()
    word_map = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    if value.isdigit():
        return max(int(value), 1)
    return word_map.get(value)


def _extract_requested_count(raw_query: str) -> Optional[int]:
    digit_match = re.search(r"\b(\d{1,2})\b", str(raw_query or ""))
    if digit_match:
        return max(int(digit_match.group(1)), 1)
    lowered = str(raw_query or "").lower()
    for token, value in _COUNT_WORD_MAP.items():
        if re.search(rf"\b{token}\b", lowered):
            return value
    return None


def _looks_like_current_channel_delivery(raw_query: str) -> bool:
    lowered = str(raw_query or "").lower()
    if any(token in lowered for token in ("email", "mail", "forward")):
        return False
    return bool(re.search(r"\b(send|share|give|deliver)\b.{0,30}\b(me|here|this chat)\b", lowered, re.DOTALL))


def _read_active_context_entries() -> List[Dict[str, Any]]:
    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
    listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []
    entries: List[Dict[str, Any]] = []
    if isinstance(listed_files, list) and listed_files:
        for index, item in enumerate(listed_files):
            if not isinstance(item, dict):
                continue
            path_str = str(item.get("path", "") or "").strip()
            if not path_str:
                continue
            entries.append(
                {
                    "index": int(item.get("index", index) or index),
                    "path": path_str,
                    "name": str(item.get("name", "") or Path(path_str).name).strip(),
                    "type": str(item.get("type", "") or "").strip().lower(),
                }
            )
        if entries:
            return entries

    selected_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
    if not isinstance(selected_paths, list):
        return []
    for index, raw_path in enumerate(selected_paths):
        path_str = str(raw_path or "").strip()
        if not path_str:
            continue
        path_obj = Path(path_str)
        entries.append(
            {
                "index": index,
                "path": path_str,
                "name": path_obj.name,
                "type": "folder" if path_obj.is_dir() else "file",
            }
        )
    return entries


def _subset_filter_extensions(raw_query: str) -> Optional[List[str]]:
    lowered = str(raw_query or "").lower()
    if any(token in lowered for token in ("images", "image", "photos", "photo", "pictures", "picture")):
        return list(_IMAGE_EXTENSIONS)
    if re.search(r"\bpdfs?\b", lowered):
        return ["pdf"]
    if any(token in lowered for token in ("documents", "document")):
        return list(_DOCUMENT_EXTENSIONS)
    if any(token in lowered for token in ("videos", "video")):
        return list(_VIDEO_EXTENSIONS)
    return None


def _subset_label(raw_query: str) -> str:
    lowered = str(raw_query or "").lower()
    for label, tokens in (
        ("images", ("images", "image", "photos", "photo", "pictures", "picture")),
        ("pdfs", ("pdf", "pdfs")),
        ("documents", ("documents", "document")),
        ("videos", ("videos", "video")),
        ("files", ("files", "file", "results", "result", "items", "item")),
    ):
        if any(token in lowered for token in tokens):
            return label
    return "files"


def _select_context_subset_paths(raw_query: str) -> List[str]:
    entries = _read_active_context_entries()
    if not entries:
        return []

    extensions = _subset_filter_extensions(raw_query)
    filtered_paths: List[str] = []
    for item in entries:
        path_obj = Path(str(item.get("path", "") or "").strip())
        if not path_obj.exists() or not path_obj.is_file():
            continue
        if _is_temp_or_test_artifact(path_obj):
            continue
        if path_obj.suffix.lower() in _ARCHIVE_EXTENSIONS:
            continue
        if extensions is not None and path_obj.suffix.lower().lstrip(".") not in extensions:
            continue
        filtered_paths.append(str(path_obj))

    if not filtered_paths:
        return []

    count = _extract_requested_count(raw_query)
    if count is None:
        return []

    lowered = str(raw_query or "").lower()
    if re.search(r"\blast\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", lowered):
        return filtered_paths[-count:]
    return filtered_paths[:count]


def _try_context_subset_zip(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    if _FRESH_SEARCH_RE.search(raw_query):
        return None
    if not _COUNTED_SUBSET_ZIP_RE.search(raw_query):
        return None

    selected_paths = _select_context_subset_paths(raw_query)
    if not selected_paths:
        return None

    try:
        from src.files.features.file_ops import save_search_manifest, zip_files_from_manifest  # noqa: PLC0415

        count = len(selected_paths)
        subset_name = _subset_label(raw_query)
        direction = "last" if re.search(r"\blast\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", raw_query, re.IGNORECASE) else "first"
        manifest_result = save_search_manifest(selected_paths, label=f"subset_{subset_name}_{direction}_{count}")
        if manifest_result.get("status") != "success":
            return manifest_result

        archive_path = _build_archive_output_path(f"subset_{subset_name}_{direction}_{count}")
        zip_result = zip_files_from_manifest(
            manifest_path=str(manifest_result.get("manifest_path", "") or ""),
            output_path=str(archive_path),
        )
        if zip_result.get("status") != "success":
            return zip_result

        if artifacts_out is not None:
            artifacts_out["file_path"] = zip_result.get("file_path", "")
            artifacts_out["found_paths"] = selected_paths

        try:
            _save_single_file_context(str(zip_result.get("file_path", "") or ""), raw_query)
        except _FILES_ORCHESTRATOR_ERRORS:
            pass

        return {
            "status": "success",
            "message": f"Created a zip with {count} selected {subset_name.rstrip('s') if count == 1 else subset_name} from the current search results.",
            "action": "react_response",
            "file_path": zip_result.get("file_path", ""),
            "selected_paths": selected_paths,
            "raw": zip_result,
        }
    except _FILES_ORCHESTRATOR_ERRORS:
        return None


def _read_active_context_paths() -> List[str]:
    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415
    from src.files.features.file_ops import resolve_file_manifest_path  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
    listed_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
    cleaned = [str(path).strip() for path in listed_paths if str(path).strip()]
    if cleaned:
        return cleaned

    manifest_path = str(entities.get("file_manifest", "") or "").strip()
    resolved_manifest = resolve_file_manifest_path(manifest_path)
    if not resolved_manifest.exists():
        return []
    return [
        line.strip()
        for line in resolved_manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _path_month_key(path: Path) -> Optional[tuple[int, int]]:
    stem = path.stem.lower()
    year_match = re.search(r"(?:^|[^0-9])(20\d{2})(?:[^0-9]|$)", stem)
    month_match = re.search(
        r"(?<![a-z])(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])",
        stem,
        re.IGNORECASE,
    )
    if year_match and month_match:
        return (int(year_match.group(1)), _MONTH_NAME_MAP[month_match.group(1).lower()])
    return None


def _pick_recent_monthly_files(paths: List[str], count: int) -> List[str]:
    candidates: List[tuple[tuple[int, int], float, str]] = []
    fallback: List[tuple[float, str]] = []
    for raw_path in paths:
        path = Path(str(raw_path).strip())
        if not path.exists() or not path.is_file():
            continue
        if _is_temp_or_test_artifact(path):
            continue
        if path.suffix.lower() in _ARCHIVE_EXTENSIONS:
            continue
        lower_name = path.name.lower()
        if "payslip" not in lower_name:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        month_key = _path_month_key(path)
        if month_key is not None:
            candidates.append((month_key, mtime, str(path)))
        else:
            fallback.append((mtime, str(path)))

    if candidates:
        chosen_by_month: Dict[tuple[int, int], tuple[float, str]] = {}
        for month_key, mtime, raw_path in candidates:
            previous = chosen_by_month.get(month_key)
            if previous is None or mtime > previous[0]:
                chosen_by_month[month_key] = (mtime, raw_path)
        ordered_months = sorted(chosen_by_month.keys(), reverse=True)[:count]
        return [chosen_by_month[key][1] for key in ordered_months]

    fallback.sort(reverse=True)
    return [raw_path for _, raw_path in fallback[:count]]


def _try_last_n_months_payslip_zip(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    months = _extract_last_n_months(raw_query)
    if months is None:
        return None

    try:
        from src.files.features.file_ops import save_search_manifest, zip_files_from_manifest  # noqa: PLC0415

        selected_paths = _pick_recent_monthly_files(_read_active_context_paths(), months)
        if not selected_paths:
            return None

        if len(selected_paths) == 1 and _looks_like_current_channel_delivery(raw_query):
            if artifacts_out is not None:
                artifacts_out["file_path"] = selected_paths[0]
                artifacts_out["found_paths"] = selected_paths
            try:
                _save_single_file_context(selected_paths[0], raw_query)
            except _FILES_ORCHESTRATOR_ERRORS:
                pass
            return {
                "status": "success",
                "message": f"I prepared the payslip for delivery: {selected_paths[0]}",
                "action": "react_response",
                "file_path": selected_paths[0],
                "selected_paths": selected_paths,
            }

        manifest_result = save_search_manifest(selected_paths, label=f"payslips_last_{months}_months")
        if manifest_result.get("status") != "success":
            return manifest_result

        archive_path = _build_archive_output_path(f"payslips_last_{months}_months")
        zip_result = zip_files_from_manifest(
            manifest_path=str(manifest_result.get("manifest_path", "") or ""),
            output_path=str(archive_path),
        )
        if zip_result.get("status") != "success":
            return zip_result

        if artifacts_out is not None:
            artifacts_out["file_path"] = zip_result.get("file_path", "")
            artifacts_out["found_paths"] = selected_paths

        try:
            _save_single_file_context(str(zip_result.get("file_path", "") or ""), raw_query)
        except _FILES_ORCHESTRATOR_ERRORS:
            pass

        return {
            "status": "success",
            "message": f"Created a zip with the last {len(selected_paths)} monthly payslip(s).",
            "action": "react_response",
            "file_path": zip_result.get("file_path", ""),
            "selected_paths": selected_paths,
            "raw": zip_result,
        }
    except _FILES_ORCHESTRATOR_ERRORS:
        return None


def _try_specific_folder_count_query(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parsed = _parse_specific_folder_count_query(user_query)
    if not parsed:
        return None

    target_path = _resolve_named_folder_path(parsed["folder_name"], parsed["drive_letter"])
    if target_path is None:
        return None

    return _build_recursive_folder_count_response(target_path, parsed["folder_name"], artifacts_out)


def _try_specific_computer_folder_count_query(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    folder_name = _parse_direct_folder_count_query(user_query)
    if not folder_name:
        return None

    matches = _scan_named_path_all_drives(folder_name, item_type="folder", limit=10)
    if not matches:
        return None

    return _build_recursive_folder_count_response(matches[0], folder_name, artifacts_out)


def _resolve_folder_path_from_files_context() -> Optional[Path]:
    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}

    directory_value = str(entities.get("directory_path", "") or "").strip()
    if directory_value:
        directory_path = Path(directory_value)
        if directory_path.exists() and directory_path.is_dir():
            return directory_path

    selected_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
    if isinstance(selected_paths, list) and len(selected_paths) == 1:
        selected_path = Path(str(selected_paths[0] or "").strip())
        if selected_path.exists() and selected_path.is_dir():
            return selected_path

    listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []
    if isinstance(listed_files, list) and len(listed_files) == 1 and isinstance(listed_files[0], dict):
        listed_path = Path(str(listed_files[0].get("path", "") or "").strip())
        if listed_path.exists() and listed_path.is_dir():
            return listed_path

    return None


def _try_contextual_folder_count_query(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    if not _CONTEXTUAL_FOLDER_COUNT_RE.search(raw_query):
        return None

    target_path = _resolve_folder_path_from_files_context()
    if target_path is None:
        return None

    return _build_recursive_folder_count_response(target_path, target_path.name, artifacts_out)


def _try_specific_drive_item_query(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parsed = _parse_specific_drive_item_query(user_query)
    if not parsed:
        return None

    target_path = _resolve_named_folder_path(parsed["item_name"], parsed["drive_letter"])
    if target_path is None:
        return {
            "status": "success",
            "message": (
                f"I couldn't find a {parsed['item_type']} named {parsed['item_name']} "
                f"on your {parsed['drive_letter'].upper()} drive."
            ),
            "action": "react_response",
        }

    _save_single_file_context(str(target_path), user_query)
    if artifacts_out is not None:
        artifacts_out["file_path"] = str(target_path)

    modified_label = ""
    try:
        modified_label = datetime.fromtimestamp(target_path.stat().st_mtime).strftime("%B %d, %Y")
    except (OSError, RuntimeError, ValueError):
        modified_label = ""

    message = (
        f"Yes, there is a {parsed['item_type']} named {target_path.name} on your {parsed['drive_letter'].upper()} drive.\n"
        f"Path: {target_path}"
    )
    if modified_label:
        message += f"\nLast Modified: {modified_label}"

    return {
        "status": "success",
        "message": message,
        "action": "react_response",
        "raw": {
            "path": str(target_path),
            "type": parsed["item_type"],
        },
    }


def _scan_named_path_all_drives(item_name: str, *, item_type: str = "folder", limit: int = 20) -> List[Path]:
    import string as _string

    normalized = str(item_name or "").strip().lower()
    if not normalized:
        return []

    matches: List[Path] = []
    stack: List[Path] = []
    seen: set[str] = set()

    for letter in _string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        try:
            if drive.exists():
                stack.append(drive)
        except OSError:
            continue

    while stack and len(matches) < limit:
        current = stack.pop()
        current_key = str(current).lower()
        if current_key in seen:
            continue
        seen.add(current_key)
        try:
            with os.scandir(current) as entries:
                child_dirs: List[Path] = []
                for entry in entries:
                    try:
                        entry_name = str(entry.name or "").strip()
                        if not entry_name:
                            continue
                        entry_is_dir = entry.is_dir(follow_symlinks=False)
                        entry_is_file = entry.is_file(follow_symlinks=False)
                        if entry_name.lower() == normalized:
                            if item_type == "folder" and entry_is_dir:
                                matches.append(Path(entry.path))
                            elif item_type == "file" and entry_is_file:
                                matches.append(Path(entry.path))
                            elif item_type == "any":
                                matches.append(Path(entry.path))
                            if len(matches) >= limit:
                                break
                        if entry_is_dir and entry_name not in _SKIP_RESULT_PARTS:
                            child_dirs.append(Path(entry.path))
                    except (OSError, PermissionError):
                        continue
                stack.extend(reversed(child_dirs))
        except (OSError, PermissionError):
            continue

    return matches


def _try_specific_computer_item_query(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parsed = _parse_specific_computer_item_query(user_query)
    if not parsed:
        return None

    matches = _scan_named_path_all_drives(parsed["item_name"], item_type=parsed["item_type"], limit=20)
    if not matches:
        return {
            "status": "success",
            "message": (
                f"I couldn't find a {parsed['item_type']} named {parsed['item_name']} "
                "on your computer."
            ),
            "action": "react_response",
        }

    target_path = matches[0]
    _save_single_file_context(str(target_path), user_query)
    if artifacts_out is not None:
        artifacts_out["file_path"] = str(target_path)

    if len(matches) == 1:
        return {
            "status": "success",
            "message": (
                f"Yes, there is a {parsed['item_type']} named {target_path.name} on your computer.\n"
                f"Path: {target_path}"
            ),
            "action": "react_response",
            "raw": {"path": str(target_path), "type": parsed["item_type"]},
        }

    preview = "\n".join(f"- {path}" for path in matches[:10])
    return {
        "status": "success",
        "message": (
            f"I found {len(matches)} matching {parsed['item_type']}(s) named {parsed['item_name']} on your computer.\n\n"
            f"Top matches:\n{preview}"
        ),
        "action": "react_response",
        "raw": {"matches": [str(path) for path in matches], "type": parsed["item_type"]},
    }


def _count_folder_tree(path: Path) -> Dict[str, Any]:
    files = 0
    folders = 0
    children: List[Dict[str, Any]] = []
    try:
        with os.scandir(path) as entries:
            for entry in sorted(entries, key=lambda item: item.name.lower()):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        nested = _count_folder_tree(Path(entry.path))
                        folders += 1 + int(nested.get("folders", 0) or 0)
                        files += int(nested.get("files", 0) or 0)
                        children.append(
                            {
                                "name": entry.name,
                                "path": entry.path,
                                "files": int(nested.get("files", 0) or 0),
                                "folders": int(nested.get("folders", 0) or 0),
                            }
                        )
                    elif entry.is_file(follow_symlinks=False):
                        files += 1
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return {"files": files, "folders": folders, "children": children}


def _write_recursive_folder_report(target_path: Path, summary: Dict[str, Any]) -> Path:
    report_dir = get_your_data_dir("reports", "files", create=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"{target_path.name}_recursive_report_{timestamp}.txt"
    lines = [
        f"Folder Report: {target_path.name}",
        f"Path: {target_path}",
        "",
        f"Total Files: {int(summary.get('files', 0) or 0)}",
        f"Total Folders: {int(summary.get('folders', 0) or 0)}",
        f"Total Items (Files + Folders): {int(summary.get('files', 0) or 0) + int(summary.get('folders', 0) or 0)}",
    ]
    children = summary.get("children", []) if isinstance(summary, dict) else []
    if isinstance(children, list) and children:
        lines.append("")
        lines.append("Immediate Subfolder Breakdown:")
        for child in children[:50]:
            if not isinstance(child, dict):
                continue
            lines.append(
                f"- {child.get('name', '')}: {int(child.get('files', 0) or 0)} file(s), {int(child.get('folders', 0) or 0)} nested folder(s)"
            )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _build_recursive_folder_count_response(
    target_path: Path,
    folder_label: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = _count_folder_tree(target_path)
    report_path = _write_recursive_folder_report(target_path, summary)
    _save_single_file_context(str(target_path), folder_label)
    if artifacts_out is not None:
        artifacts_out["file_path"] = str(report_path)

    file_count = int(summary.get("files", 0) or 0)
    folder_count = int(summary.get("folders", 0) or 0)
    return {
        "status": "success",
        "message": (
            f"Here's the recursive breakdown of the contents in the {target_path.name} folder:\n\n"
            f"Total Files: {file_count}\n"
            f"Total Folders: {folder_count}\n"
            f"Total Items (Files + Folders): {file_count + folder_count}\n\n"
            f"I also created a detailed report at: {report_path}"
        ),
        "action": "react_response",
        "file_path": str(report_path),
        "raw": {"path": str(target_path), **summary},
    }


def _resolve_existing_archive_from_files_context() -> Optional[Path]:
    source_path = _resolve_single_copy_source_from_files_context()
    if source_path is None or not source_path.exists() or not source_path.is_file():
        return None
    if source_path.suffix.lower() not in _ARCHIVE_EXTENSIONS:
        return None
    return source_path


def _try_reuse_existing_archive_from_context(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    lowered = raw_query.lower()
    if "zip" not in lowered and "archive" not in lowered:
        return None
    if not any(token in lowered for token in ("created", "made", "that zip", "the zip", "previous zip")):
        return None

    archive_path = _resolve_existing_archive_from_files_context()
    if archive_path is None:
        return None

    if artifacts_out is not None:
        artifacts_out["file_path"] = str(archive_path)

    return {
        "status": "success",
        "message": f"Using the existing zip archive: {archive_path}",
        "action": "react_response",
        "file_path": str(archive_path),
    }


def _build_archive_output_path(folder_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", folder_name).strip("._") or "search_results"
    return get_your_data_dir("archives", f"{safe_name}.zip")


def _save_single_file_context(path_str: str, query: str) -> None:
    from src.agent.manifest.context_manifest import auto_save_files_context  # noqa: PLC0415

    file_path = Path(str(path_str or "").strip())
    if not file_path.exists():
        return

    auto_save_files_context(
        {
            "status": "success",
            "path": str(file_path),
            "results": [
                {
                    "path": str(file_path),
                    "name": file_path.name,
                    "type": "folder" if file_path.is_dir() else "file",
                }
            ],
            "count": 1,
            "file_path": str(file_path),
        },
        query,
    )


def _try_list_names_from_files_context(user_query: str) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    if _FRESH_SEARCH_RE.search(raw_query):
        return None
    if not _LIST_NAMES_RE.search(raw_query):
        return None

    from src.agent.manifest.context_manifest import auto_save_files_context, read_context  # noqa: PLC0415
    from src.files.features.file_ops import list_directory  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
    directory_path = str(entities.get("directory_path", "") or "").strip()
    listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []

    if (not isinstance(listed_files, list) or not listed_files) and directory_path:
        refreshed = list_directory(directory_path, limit=200)
        if refreshed.get("status") == "success":
            auto_save_files_context(refreshed, raw_query)
            ctx = read_context(agent="files") or {}
            entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
            listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []

    if not isinstance(listed_files, list) or not listed_files:
        return None

    file_items = [item for item in listed_files if isinstance(item, dict) and str(item.get("type", "") or "").lower() == "file"]
    display_items = file_items or [item for item in listed_files if isinstance(item, dict)]
    if not display_items:
        return None

    folder_label = Path(directory_path).name if directory_path else "the current folder"
    lines = [f"Here are the file names from the **{folder_label}** folder:"]
    for idx, item in enumerate(display_items[:50], start=1):
        name = str(item.get("name", "") or Path(str(item.get("path", "") or "")).name).strip()
        if name:
            lines.append(f"{idx}. **{name}**")
    if len(display_items) > 50:
        lines.append("")
        lines.append(f"Showing 50 of {len(display_items)} names.")

    return {
        "status": "success",
        "message": "\n\n".join(lines),
        "action": "react_response",
    }


def _try_direct_rename_from_files_context(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    if _FRESH_SEARCH_RE.search(raw_query):
        return None

    rename_match = _FOLLOW_UP_RENAME_RE.search(raw_query)
    if not rename_match:
        return None

    candidate_name = str(rename_match.group(1) or "").strip().rstrip("?.!,")
    if not candidate_name:
        return None

    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415
    from src.files.features.file_ops import rename_file  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}

    target_path: Optional[Path] = None
    directory_path = Path(str(entities.get("directory_path", "") or "").strip())
    if directory_path.exists():
        target_path = directory_path
    else:
        selected_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
        if isinstance(selected_paths, list) and len(selected_paths) == 1:
            selected_path = Path(str(selected_paths[0] or "").strip())
            if selected_path.exists():
                target_path = selected_path
        elif isinstance(entities.get("listed_files", []), list) and len(entities.get("listed_files", [])) == 1:
            listed_entry = entities["listed_files"][0]
            if isinstance(listed_entry, dict):
                listed_path = Path(str(listed_entry.get("path", "") or "").strip())
                if listed_path.exists():
                    target_path = listed_path

    if target_path is None:
        return None

    new_name = Path(candidate_name).name.strip()
    if not new_name:
        return None

    result = rename_file(str(target_path), new_name)
    if result.get("status") != "success":
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Rename failed."),
            "action": "react_response",
        }

    if artifacts_out is not None:
        artifacts_out["file_path"] = result.get("new_path", "")

    return {
        "status": "success",
        "message": result.get("message", "Rename successful."),
        "action": "react_response",
        "file_path": result.get("new_path", ""),
    }


def _resolve_single_copy_source_from_files_context() -> Optional[Path]:
    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}

    directory_value = str(entities.get("directory_path", "") or "").strip()
    if directory_value:
        directory_path = Path(directory_value)
        if directory_path.exists():
            return directory_path

    selected_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
    if isinstance(selected_paths, list) and len(selected_paths) == 1:
        selected_path = Path(str(selected_paths[0] or "").strip())
        if selected_path.exists():
            return selected_path

    listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []
    if isinstance(listed_files, list) and len(listed_files) == 1 and isinstance(listed_files[0], dict):
        listed_path = Path(str(listed_files[0].get("path", "") or "").strip())
        if listed_path.exists():
            return listed_path

    return None


_MAKE_COPY_RE = re.compile(
    r"\b(make|create)\b.{0,20}\ba\s+copy\b|\bduplicate\b|\bcopy\s+(it|this|that)\b",
    re.IGNORECASE | re.DOTALL,
)


def _build_adjacent_copy_destination(source_path: Path) -> Path:
    if source_path.is_dir():
        candidate = source_path.with_name(f"{source_path.name} - Copy")
    else:
        candidate = source_path.with_name(f"{source_path.stem} - Copy{source_path.suffix}")

    counter = 2
    while candidate.exists():
        if source_path.is_dir():
            candidate = source_path.with_name(f"{source_path.name} - Copy ({counter})")
        else:
            candidate = source_path.with_name(
                f"{source_path.stem} - Copy ({counter}){source_path.suffix}"
            )
        counter += 1
    return candidate


def _try_direct_zip_from_files_context(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)
    if _FRESH_SEARCH_RE.search(raw_query):
        return None
    if not _FOLLOW_UP_ZIP_RE.search(raw_query) and "zip that" not in raw_query.lower():
        return None

    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415
    from src.files.features.archives import zip_folder  # noqa: PLC0415
    from src.files.features.file_ops import zip_files_from_manifest  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}

    bundle_dir_raw = str(entities.get("search_bundle_dir", "") or "").strip()
    bundle_dir = Path(bundle_dir_raw) if bundle_dir_raw else None
    if bundle_dir is not None and bundle_dir.exists() and bundle_dir.is_dir():
        archive_path = _build_archive_output_path(bundle_dir.name)
        result = zip_folder(str(bundle_dir), str(archive_path))
    else:
        directory_path = Path(str(entities.get("directory_path", "") or "").strip())
        selected_paths = entities.get("selected_paths", []) if isinstance(entities, dict) else []
        listed_files = entities.get("listed_files", []) if isinstance(entities, dict) else []
        folder_target: Optional[Path] = None

        if directory_path.exists() and directory_path.is_dir():
            folder_target = directory_path
        elif isinstance(selected_paths, list) and len(selected_paths) == 1:
            selected_path = Path(str(selected_paths[0] or "").strip())
            if selected_path.exists() and selected_path.is_dir():
                folder_target = selected_path
        elif isinstance(listed_files, list) and len(listed_files) == 1 and isinstance(listed_files[0], dict):
            single_path = Path(str(listed_files[0].get("path", "") or "").strip())
            if single_path.exists() and single_path.is_dir():
                folder_target = single_path

        if folder_target is not None:
            archive_path = _build_archive_output_path(folder_target.name)
            result = zip_folder(str(folder_target), str(archive_path))
        else:
            manifest_path = str(entities.get("file_manifest", "") or "").strip()
            if not manifest_path:
                return None
            archive_stem = directory_path.name if directory_path else "search_results"
            archive_path = _build_archive_output_path(archive_stem)
            result = zip_files_from_manifest(manifest_path=manifest_path, output_path=str(archive_path))

    if result.get("status") != "success":
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Zip failed."),
            "action": "react_response",
        }

    if artifacts_out is not None:
        artifacts_out["file_path"] = result.get("file_path", "")

    try:
        _save_single_file_context(str(result.get("file_path", "") or ""), raw_query)
    except _FILES_ORCHESTRATOR_ERRORS:
        pass

    return {
        "status": "success",
        "message": f"Created zip archive: {result.get('file_path', '')}",
        "action": "react_response",
        "file_path": result.get("file_path", ""),
    }


def _try_direct_zip_from_search_bundle(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    raw_query = _strip_injected_blocks(user_query)

    if _FRESH_SEARCH_RE.search(raw_query):
        return None
    if not _FOLLOW_UP_ZIP_RE.search(raw_query):
        return None

    from src.agent.manifest.context_manifest import read_context  # noqa: PLC0415
    from src.files.features.archives import zip_folder  # noqa: PLC0415

    ctx = read_context(agent="files") or {}
    entities = ctx.get("resolved_entities", {}) if isinstance(ctx, dict) else {}
    bundle_dir = Path(str(entities.get("search_bundle_dir", "") or "").strip())
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return None

    archive_path = get_your_data_dir("archives", f"{bundle_dir.name}.zip")
    result = zip_folder(str(bundle_dir), str(archive_path))

    if result.get("status") != "success":
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Zip failed."),
            "action": "react_response",
        }

    if artifacts_out is not None:
        artifacts_out["file_path"] = result.get("file_path", "")

    try:
        _save_single_file_context(str(result.get("file_path", "") or ""), raw_query)
    except _FILES_ORCHESTRATOR_ERRORS:
        pass

    return {
        "status": "success",
        "message": f"Created zip archive for the previous search results: {result.get('file_path', '')}",
        "action": "react_response",
        "file_path": result.get("file_path", ""),
    }


def _format_precise_search_response(mode: str, term: str, result: Dict[str, Any]) -> str:
    matches = result.get("results", []) or []
    count = int(result.get("count", 0) or 0)
    match_mode = str(result.get("match_mode", "exact") or "exact")
    lines: List[str] = []

    if mode == "named_search":
        descriptor = f"with '{term}' in the name" if match_mode == "contains" else f"named '{term}'"
        if count == 0:
            return f"I couldn't find any matching file {descriptor} on the detected drives."
        if count == 1:
            return f"Yes — I found 1 matching item {descriptor}:\n{matches[0].get('path', '')}"
        lines.append(f"Yes — I found {count} matching items {descriptor}.")
    else:
        if count == 0:
            return f"I couldn't find any files with '{term}' in the filename on the detected drives."
        lines.append(f"I found {count} file(s) with '{term}' in the filename on the detected drives.")

    preview = matches[:10]
    if preview:
        lines.append("")
        lines.append("Top matches:")
        lines.extend(f"- {item.get('path', '')}" for item in preview)
    if count > len(preview):
        lines.append("")
        lines.append(f"Showing {len(preview)} of {count} matches.")
    return "\n".join(lines)


def _try_precise_full_computer_search(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parsed = _parse_precise_full_computer_search(user_query)
    if not parsed:
        return None

    from src.files.features.search import search_file_all_drives  # noqa: PLC0415

    result = search_file_all_drives(
        query=parsed["term"],
        extensions=parsed.get("extensions"),
        limit=parsed.get("limit", 50),
        include_folders=parsed.get("include_folders", True),
    )
    if result.get("status") != "success":
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Search failed."),
            "action": "react_response",
        }

    result = _filter_precise_search_results(user_query, result)
    if parsed["mode"] == "named_search":
        result["results"] = _filter_named_matches(
            result.get("results", []) or [],
            parsed["term"],
            match_mode=str(parsed.get("match_mode", "exact") or "exact"),
        )
        result["count"] = len(result["results"])
        result["file_path"] = str(result["results"][0].get("path", "") or "") if result["results"] else ""
        result["match_mode"] = str(parsed.get("match_mode", "exact") or "exact")
    result = _stage_precise_search_results(parsed["term"], result)

    paths = [str(item.get("path", "") or "").strip() for item in result.get("results", []) if str(item.get("path", "") or "").strip()]

    _save_precise_search_context(result, parsed["term"])
    first_path = str(result.get("file_path", "") or "").strip()
    if artifacts_out is not None and first_path:
        artifacts_out["file_path"] = first_path
    if artifacts_out is not None and paths:
        artifacts_out["found_paths"] = paths
    bundle_dir = str(result.get("search_bundle_dir", "") or "").strip()
    if artifacts_out is not None and bundle_dir:
        artifacts_out["search_bundle_dir"] = bundle_dir

    return {
        "status": "success",
        "message": _format_precise_search_response(parsed["mode"], parsed["term"], result),
        "action": "react_response",
        "raw": result,
    }


def _try_scoped_named_search(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parsed = _parse_scoped_named_search(user_query)
    if not parsed:
        return None

    from src.agent.manifest.context_manifest import auto_save_files_context  # noqa: PLC0415
    from src.files.features.file_ops import list_directory  # noqa: PLC0415
    from src.files.features.search import search_by_name  # noqa: PLC0415

    result = search_by_name(parsed["term"], directory=parsed["directory"], recursive=True, limit=50)
    if result.get("status") != "success":
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Search failed."),
            "action": "react_response",
        }

    matches = result.get("results", []) or []
    item_type = parsed.get("item_type")
    if item_type in {"file", "folder"}:
        matches = [item for item in matches if str(item.get("type", "")).lower() == item_type]
    matches = _filter_named_matches(
        matches,
        parsed["term"],
        match_mode=str(parsed.get("match_mode", "exact") or "exact"),
    )
    result["results"] = matches
    result["count"] = len(matches)

    paths = [str(item.get("path", "") or "").strip() for item in matches if str(item.get("path", "") or "").strip()]
    first_path = paths[0] if paths else ""
    if artifacts_out is not None and first_path:
        artifacts_out["file_path"] = first_path
    if artifacts_out is not None and paths:
        artifacts_out["found_paths"] = paths

    noun = item_type or "item"
    descriptor = (
        f"with '{parsed['term']}' in the name"
        if parsed.get("match_mode") == "contains"
        else f"named '{parsed['term']}'"
    )
    if matches:
        _save_precise_search_context(result, parsed["term"])
        if item_type == "folder" and len(matches) == 1 and _DIRECTORY_FILE_COUNT_RE.search(user_query):
            directory_result = list_directory(first_path, limit=200)
            if directory_result.get("status") == "success":
                auto_save_files_context(directory_result, parsed["term"])
                file_count = int(directory_result.get("files", 0) or 0)
                folder_count = int(directory_result.get("folders", 0) or 0)
                message = (
                    f"I found {file_count} file(s) and {folder_count} folder(s) in "
                    f"'{parsed['term']}' in {parsed['scope_label']}."
                )
                return {
                    "status": "success",
                    "message": message,
                    "action": "react_response",
                    "raw": directory_result,
                }
        if len(matches) == 1:
            message = f"Yes — I found 1 matching {noun} {descriptor} in {parsed['scope_label']}:\n{first_path}"
        else:
            preview = "\n".join(f"- {path}" for path in paths[:10])
            message = (
                f"Yes — I found {len(matches)} matching {noun}s {descriptor} in {parsed['scope_label']}."
                f"\n\nTop matches:\n{preview}"
            )
    else:
        message = f"I couldn't find any matching {noun} {descriptor} in {parsed['scope_label']}."

    return {
        "status": "success",
        "message": message,
        "action": "react_response",
        "raw": result,
    }


def _try_filename_contains_search(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    parsed = _parse_filename_contains_search(user_query)
    if not parsed:
        return None

    from src.files.features.search import search_file_all_drives  # noqa: PLC0415

    result = search_file_all_drives(
        query=parsed["term"],
        extensions=parsed.get("extensions"),
        limit=parsed.get("limit", 50),
        include_folders=parsed.get("include_folders", False),
    )
    if result.get("status") != "success":
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Search failed."),
            "action": "react_response",
        }

    result = _filter_precise_search_results(user_query, result)
    result = _stage_precise_search_results(parsed["term"], result)
    _save_precise_search_context(result, parsed["term"])

    paths = [str(item.get("path", "") or "").strip() for item in result.get("results", []) if str(item.get("path", "") or "").strip()]
    first_path = str(result.get("file_path", "") or "").strip()
    if artifacts_out is not None and first_path:
        artifacts_out["file_path"] = first_path
    if artifacts_out is not None and paths:
        artifacts_out["found_paths"] = paths
    bundle_dir = str(result.get("search_bundle_dir", "") or "").strip()
    if artifacts_out is not None and bundle_dir:
        artifacts_out["search_bundle_dir"] = bundle_dir

    return {
        "status": "success",
        "message": _format_precise_search_response("named_search", parsed["term"], result),
        "action": "react_response",
        "raw": result,
    }


def _try_recycle_bin_query(user_query: str) -> Optional[Dict[str, Any]]:
    if not _RECYCLE_BIN_COUNT_RE.search(str(user_query or "")):
        return None

    from src.files.features.file_ops import get_recycle_bin_info  # noqa: PLC0415

    result = get_recycle_bin_info()
    return {
        "status": result.get("status", "error"),
        "message": result.get("message", "Recycle Bin query failed."),
        "action": "react_response",
        "raw": result,
    }

def _build_skill_context() -> str:
    """Build the files-agent system prompt with real OS paths injected from skill_context.md."""
    import sys as _sys
    home = Path.home()
    downloads = home / "Downloads"
    desktop   = home / "Desktop"
    documents = home / "Documents"
    data_dir  = get_your_data_dir()

    # Detect Windows drive roots so the LLM knows about C:\-level folders
    drive_root_note = ""
    if _sys.platform == "win32":
        try:
            import string as _string
            drive_roots = [
                f"{d}:\\" for d in _string.ascii_uppercase
                if Path(f"{d}:\\").exists()
            ]
            if drive_roots:
                drive_root_note = (
                    "\nAvailable drive roots: " + ", ".join(drive_roots) + "\n"
                    "  Folders at C:\\ root may include user project folders "
                    "(e.g. C:\\Hrishikesh, C:\\Projects, etc.) — these are NOT under Home.\n"
                )
        except (OSError, RuntimeError, ValueError):
            pass

    # Load user-defined personal folders from settings.json
    personal_folders_note = ""
    try:
        _sf = Path(__file__).resolve().parents[4] / "config" / "settings.json"
        _cfg = json.loads(_sf.read_text(encoding="utf-8"))
        _pf = {k: v for k, v in _cfg.get("personal_folders", {}).items() if not k.startswith("_")}
        if _pf:
            _lines = "\n".join(f"  {k}: {v}" for k, v in _pf.items())
            personal_folders_note = (
                "\nUser-defined personal folders (use these EXACT paths \u2014 do NOT search):\n"
                + _lines + "\n"
                "  Rule: when the user mentions one of these exact names (e.g. 'payslips', 'neo'),"
                " call list_directory(<exact path>) DIRECTLY \u2014 never use search_file_all_drives for a known folder.  \n"
            )
    except (OSError, TypeError, ValueError):
        pass

    # Load template and substitute placeholders.
    # Longer/more-specific keys are replaced before any shorter key that is a prefix,
    # so "${downloads_example_subfolder}" is handled before "${downloads}".
    template = (Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8")
    replacements = {
        "${downloads_example_subfolder}": str(downloads / "MyFolder"),
        "${desktop_example_file}": str(desktop / "report.pdf"),
        "${home}": str(home),
        "${downloads}": str(downloads),
        "${desktop}": str(desktop),
        "${documents}": str(documents),
        "${data_dir}": str(data_dir),
        "${drive_root_note}": drive_root_note,
        "${personal_folders_note}": personal_folders_note,
    }
    for k, v in replacements.items():
        template = template.replace(k, v)
    return template.strip()

def _build_all_tools() -> Dict[str, Any]:
    from src.files.features.file_ops import (  # noqa: PLC0415
        list_directory as _list_directory, get_file_info, copy_file, move_file,
        delete_file, create_folder, rename_file, open_file,
        list_laptop_structure, deliver_file,
        write_pdf_report, write_excel_report, organize_folder,
        analyze_disk_usage, get_drive_info, find_duplicate_files,
        count_files_and_folders_all_drives,
        get_recycle_bin_info,
        search_files_by_content, batch_rename, secure_delete,
        cleanup_temp_files, monitor_folder,
        cleanup_app_caches, archive_old_files, resolve_shortcut,
        get_file_hash, list_running_apps,
        collect_files_to_folder,
        save_search_manifest, collect_files_from_manifest, zip_files_from_manifest,
        undo_last_file_operation,
        list_file_operations,
    )
    from src.files.features.search import (  # noqa: PLC0415
        search_by_name as _sbn, search_by_extension as _sbe,
        search_by_date,
        search_by_size, find_duplicates, find_empty_folders,
        search_file_all_drives,
    )
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_files_context, make_save_context_tool,
    )

    def search_by_name(query: str, directory: str = "~", recursive: bool = True, limit: int = 50):
        result = _sbn(query, directory, recursive, limit)
        return auto_save_files_context(result, query)

    def search_by_extension(ext: str, directory: str = "~", recursive: bool = True, limit: int = 100):
        result = _sbe(ext, directory, recursive, limit)
        return auto_save_files_context(result, ext)

    def list_directory(path: str, show_hidden: bool = False, limit: int = 200):
        result = _list_directory(path, show_hidden=show_hidden, limit=limit)
        if result.get("status") == "success":
            directory_path = str(result.get("path", "") or "").strip()
            entry_paths = [
                str(Path(directory_path) / str(entry.get("name", "") or "").strip())
                for entry in result.get("entries", [])
                if isinstance(entry, dict) and str(entry.get("name", "") or "").strip()
            ]
            if entry_paths:
                manifest_result = save_search_manifest(entry_paths, label=Path(directory_path).name or path)
                if manifest_result.get("status") == "success":
                    result["manifest_path"] = manifest_result.get("manifest_path", "")
                    result["manifest_id"] = manifest_result.get("manifest_id", "")
                    result["manifest_label"] = manifest_result.get("label", "")
        return auto_save_files_context(result, path)

    from src.files.features.archives import (  # noqa: PLC0415
        zip_folder, zip_files, unzip_file, list_archive_contents,
    )

    def write_text_file(path: str, content: str) -> dict:
        """Write *content* as plain text to *path*, creating or overwriting the file."""
        try:
            _p = Path(path).expanduser()
            _p.parent.mkdir(parents=True, exist_ok=True)
            _p.write_text(content, encoding="utf-8")
            return {
                "status": "success",
                "path": str(_p),
                "bytes_written": len(content.encode("utf-8")),
                "message": f"Written {len(content)} character(s) to '{_p}'.",
            }
        except (OSError, TypeError, ValueError) as exc:
            return {"status": "error", "message": f"Error writing file: {exc}"}

    return {
        # Browse & Inspect
        "list_directory":          list_directory,
        "get_file_info":           get_file_info,
        "open_file":               open_file,
        # Search
        "search_by_name":          search_by_name,
        "search_by_extension":     search_by_extension,
        "search_by_date":          search_by_date,
        "search_by_size":          search_by_size,
        "search_file_all_drives":  search_file_all_drives,
        "search_files_by_content": search_files_by_content,
        "find_duplicates":         find_duplicates,
        "find_empty_folders":      find_empty_folders,
        "find_duplicate_files":    find_duplicate_files,
        "get_recycle_bin_info":    get_recycle_bin_info,
        # File Operations
        "copy_file":               copy_file,
        "move_file":               move_file,
        "delete_file":             delete_file,
        "create_folder":           create_folder,
        "rename_file":             rename_file,
        "batch_rename":            batch_rename,
        "secure_delete":           secure_delete,
        "collect_files_to_folder": collect_files_to_folder,
        # Archives & Compression
        "zip_folder":              zip_folder,
        "zip_files":               zip_files,
        "zip_files_from_manifest": zip_files_from_manifest,
        "unzip_file":              unzip_file,
        "list_archive_contents":   list_archive_contents,
        # Write & Report
        "write_text_file":         write_text_file,
        "write_pdf_report":        write_pdf_report,
        "write_excel_report":      write_excel_report,
        "deliver_file":            deliver_file,
        # Organisation & Cleanup
        "organize_folder":         organize_folder,
        "cleanup_temp_files":      cleanup_temp_files,
        "cleanup_app_caches":      cleanup_app_caches,
        "archive_old_files":       archive_old_files,
        "monitor_folder":          monitor_folder,
        # Disk & System
        "analyze_disk_usage":      analyze_disk_usage,
        "get_drive_info":          get_drive_info,
        "count_files_and_folders_all_drives": count_files_and_folders_all_drives,
        "list_laptop_structure":   list_laptop_structure,
        "list_running_apps":       list_running_apps,
        "resolve_shortcut":        resolve_shortcut,
        "get_file_hash":           get_file_hash,
        # Context & Manifest
        "save_search_manifest":        save_search_manifest,
        "collect_files_from_manifest": collect_files_from_manifest,
        "undo_last_file_operation":    undo_last_file_operation,
        "list_file_operations":        list_file_operations,
        "save_context":                make_save_context_tool("files"),
    }

def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a FAISS-filtered tool map for the ReAct engine.

    Falls back to the full tool map if FAISS selection fails.
    """
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415
        selected = select_tool_names(
            "files", user_query,
            always_include=["save_context", "deliver_file", "save_search_manifest"],
        )
        filtered = {n: all_tools[n] for n in selected if n in all_tools}
        if filtered:
            return filtered
    except _FILES_ORCHESTRATOR_ERRORS as exc:
        import logging as _lg
        _lg.getLogger("files.orchestrator").warning(
            "[tool-map] FAISS filtering failed (%s) — using full tool map", exc
        )
    return all_tools


def _maybe_save_manifest(artifacts_out: Optional[Dict[str, Any]]) -> None:
    """Save found_paths to the active file manifest if the current execution produced any."""
    if not artifacts_out:
        return
    found = artifacts_out.get("found_paths", [])
    if not found:
        return
    try:
        from src.files.features.file_ops import save_search_manifest  # noqa: PLC0415
        save_search_manifest(found)
        import logging as _lg
        _lg.getLogger("files.orchestrator").info(
            "[manifest] saved %d paths to the active file manifest", len(found)
        )
    except _FILES_ORCHESTRATOR_ERRORS as exc:
        import logging as _lg
        _lg.getLogger("files.orchestrator").warning("[manifest] save failed: %s", exc)

# ---------------------------------------------------------------------------
# Pre-flight: direct copy-from-manifest (no LLM needed)
# ---------------------------------------------------------------------------

_FOLLOW_UP_COPY_RE = re.compile(
    # action word followed by file/image/pronoun reference within ~100 chars
    r'\b(copy|move|put|collect|gather|transfer)\b'
    r'.{0,100}'
    r'\b(them|those|it|files?|images?|photos?|videos?|documents?|results?|found)\b'
    # pronoun first, action word second
    r'|\b(them|those)\b.{0,50}\b(copy|move|put|collect|gather|transfer)\b'
    # direct: "copy them", "collect those", "put it"
    r'|\b(copy|move|put|collect)\s+(them|those|it)\b'
    # common user phrases
    r'|\bcan you copy\b'
    # action + previously/found/searched — catches DAG-rewritten instructions
    r'|\b(copy|move|collect|gather)\b.{0,40}\b(previously|found|searched|earlier)\b',
    re.IGNORECASE | re.DOTALL,
)

def _is_follow_up_copy(query: str) -> bool:
    """Return True when the query looks like 'copy them / put those / collect the files'."""
    return bool(_FOLLOW_UP_COPY_RE.search(query))

def _resolve_destination_from_query(user_query: str) -> str:
    """
    Extract and resolve a destination folder name from a natural-language query.

    Handles (in priority order):
      1. Absolute Windows/Unix path: "copy to C:\\Users\\..."
      2. Named folder: "a folder named/called X" or "folder named/called X"
      3. Sub-path under a known keyword: "to Downloads/X", "to Desktop\\X"
      4. Known keyword standalone: "to downloads", "to desktop", "to documents"
      5. Sub-path under Downloads "<keyword>/X" within a 'to' clause
      6. Simple single-word name at end of query: "copy to qwerty", "put in test"

    Returns the resolved absolute path string, or "" if nothing parseable is found.
    """
    home = Path.home()
    downloads = home / "Downloads"
    _KW: Dict[str, Path] = {
        "downloads": home / "Downloads",
        "download":  home / "Downloads",
        "desktop":   home / "Desktop",
        "documents": home / "Documents",
        "document":  home / "Documents",
        "home":      home,
    }
    # Stopwords that are never folder names
    _STOP = frozenset({
        "them", "those", "it", "the", "a", "an", "my", "our", "your",
        "all", "folder", "folders", "directory", "file", "files",
        "here", "there", "this", "that",
    })

    # 1. Absolute path after "to" (Windows drive letter or Unix root)
    abs_m = re.search(
        r'\bto\s+([A-Za-z]:[/\\][^\s,]+|/[^\s,]+)',
        user_query, re.IGNORECASE,
    )
    if abs_m:
        return abs_m.group(1).strip().rstrip("/\\?!. ,")

    # 2. "a folder named/called X" / "folder named/called X" / "named/called X folder"
    named_m = re.search(
        r'\b(?:a\s+)?(?:new\s+)?folder\s+(?:named|called)\s+["\']?(\w[\w\-\.]*)["\']?'
        r'|(?:named|called)\s+["\']?(\w[\w\-\.]*)["\']?\s*(?:folder|directory)?',
        user_query, re.IGNORECASE,
    )
    if named_m:
        name = (named_m.group(1) or named_m.group(2) or "").strip()
        if name and name.lower() not in _STOP:
            return str(downloads / name)

    # 3. Known keyword + sub-folder: "to Downloads/qwerty", "to Desktop\test"
    sub_m = re.search(
        r'\bto\s+(downloads?|desktop|documents?|home)[/\\](\w[\w\-\.]*)',
        user_query, re.IGNORECASE,
    )
    if sub_m:
        base = _KW.get(sub_m.group(1).lower().rstrip("s"), _KW.get(sub_m.group(1).lower(), downloads))
        return str(base / sub_m.group(2))

    # 4. Standalone known keyword: "to downloads", "to desktop"
    kw_m = re.search(
        r'\bto\s+(downloads?|desktop|documents?|home)\b',
        user_query, re.IGNORECASE,
    )
    if kw_m:
        kw = kw_m.group(1).lower().rstrip("s")
        return str(_KW.get(kw, _KW.get(kw_m.group(1).lower(), downloads)))

    # 5. "in Downloads/X" or "in Desktop/X"
    in_sub_m = re.search(
        r'\bin\s+(downloads?|desktop|documents?|home)[/\\](\w[\w\-\.]*)',
        user_query, re.IGNORECASE,
    )
    if in_sub_m:
        base = _KW.get(in_sub_m.group(1).lower().rstrip("s"), _KW.get(in_sub_m.group(1).lower(), downloads))
        return str(base / in_sub_m.group(2))

    # 6. "to X" or "into X" where X is a simple identifier at/near end of query
    simple_m = re.search(
        r'\b(?:to|into)\s+(?:a\s+)?(?:new\s+)?(?:folder\s+)?(?:named\s+|called\s+)?([A-Za-z]\w*)\s*[?!.]?\s*$',
        user_query.strip(), re.IGNORECASE,
    )
    if simple_m:
        name = simple_m.group(1).strip()
        if name.lower() not in _STOP:
            return str(downloads / name)

    # 7. "put/place them in X" where X is a simple name at end
    in_m = re.search(
        r'\b(?:put|place|store|save)\b.{0,40}\bin\s+(?:a\s+)?(?:new\s+)?(?:folder\s+)?(?:named\s+|called\s+)?([A-Za-z]\w*)\s*[?!.]?\s*$',
        user_query.strip(), re.IGNORECASE,
    )
    if in_m:
        name = in_m.group(1).strip()
        if name.lower() not in _STOP:
            return str(downloads / name)

    # 8. "to this folder - X" / "folder - X" — dash used as a name separator
    #    e.g. "copy them to this folder - payslips_01"
    folder_dash_m = re.search(
        r'\bfolder\s*[-–]\s*([A-Za-z]\w*)',
        user_query, re.IGNORECASE,
    )
    if folder_dash_m:
        name = folder_dash_m.group(1).strip()
        if name and name.lower() not in _STOP:
            return str(downloads / name)

    return ""

# Fresh-search patterns — these ALWAYS bypass the direct-copy shortcut,
# regardless of injected context or session state.
_FRESH_SEARCH_RE = re.compile(
    r'\b(how many|are there|do i have|find all|search for|count|list all|'
    r'how much|any \w+ files?|search.*computer|look for|show me all)\b',
    re.IGNORECASE,
)

def _try_direct_copy_from_manifest(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Bypass the LLM entirely when:
      1. The query is a follow-up copy/move/collect request, AND
            2. An active file manifest exists and is non-empty.

    Returns a result dict on success/failure, or None if conditions are not met
    (so the caller falls through to the normal LLM path).
    """
    # Extract the raw user intent — strip injected ## Context and ## Session State
    # blocks so we never accidentally trigger a copy on fresh search queries whose
    # injected 'file_action' instruction contains "collect" / "copy" + "files".
    _raw = user_query.split("## Context from Previous Turn")[0]
    _raw = _raw.split("## Session State")[0].strip()

    # Explicit guard: fresh search queries must NEVER be treated as copy follow-ups.
    if _FRESH_SEARCH_RE.search(_raw):
        return None

    if not _is_follow_up_copy(_raw):
        return None

    from src.files.features.file_ops import (
        collect_files_from_manifest,  # noqa: PLC0415
        copy_file,
        _DEFAULT_MANIFEST,
        _DEFAULT_OCTAMIND_DIR,
    )

    source_path = _resolve_single_copy_source_from_files_context()
    destination = _resolve_destination_from_query(_raw)

    if source_path is not None:
        if not destination and _MAKE_COPY_RE.search(_raw):
            destination = str(_build_adjacent_copy_destination(source_path))
        if destination:
            result = copy_file(str(source_path), destination)
            copied_path = str(result.get("destination", "") or "").strip()
            if artifacts_out is not None and copied_path:
                artifacts_out["file_path"] = copied_path
            if result.get("status") == "success" and copied_path:
                try:
                    _save_single_file_context(copied_path, _raw)
                except _FILES_ORCHESTRATOR_ERRORS:
                    pass
                return {
                    "status": "success",
                    "message": f"✅ Copied **{source_path.name}** to:\n`{copied_path}`",
                    "action": "react_response",
                }
            return {
                "status": result.get("status", "error"),
                "message": f"❌ Copy failed: {result.get('message', 'unknown error')}",
                "action": "react_response",
            }

    if not _DEFAULT_MANIFEST.exists():
        import logging as _lg
        _lg.getLogger("files.orchestrator").info(
            "[direct-copy] manifest not found — falling through to LLM"
        )
        return None

    import logging as _lg
    _lg.getLogger("files.orchestrator").info(
        "[direct-copy] follow-up copy detected + manifest exists — executing directly"
    )

    # Resolve destination using the cleaned raw intent (no injected ## blocks)
    _lg.getLogger("files.orchestrator").info(
        "[direct-copy] resolved destination=%r from query=%r", destination, _raw
    )

    # If we can't determine where the user wants the files, fall through to the LLM
    # rather than silently dumping everything into the default data directory.
    if not destination:
        _lg.getLogger("files.orchestrator").info(
            "[direct-copy] destination unresolvable — falling through to LLM"
        )
        return None

    result = collect_files_from_manifest(destination=destination)

    if artifacts_out is not None:
        artifacts_out["file_path"] = result.get("destination", "")

    count = result.get("copied_count", 0)
    dest  = result.get("destination", str(_DEFAULT_OCTAMIND_DIR))
    skipped = result.get("skipped", [])
    skipped_note = f"  ({len(skipped)} file(s) skipped — not found on disk)" if skipped else ""

    if result.get("status") == "success":
        message = (
            f"✅ Copied **{count}** file(s) from the previous search into:\n"
            f"`{dest}`{skipped_note}"
        )
        # Clear the file_action context — the action is complete; the next
        # turn should not re-trigger the same copy.
        try:
            from src.agent.manifest.context_manifest import clear_context as _cc  # noqa: PLC0415
            _cc()
        except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            pass
    else:
        message = f"❌ Copy failed: {result.get('message', 'unknown error')}"

    return {
        "status":  result.get("status", "error"),
        "message": message,
        "action":  "react_response",
    }

# ---------------------------------------------------------------------------
# Background job dispatch — heavy full-disk scans
# ---------------------------------------------------------------------------

# Queries that imply scanning the entire computer / all drives
_HEAVY_SCAN_RE = re.compile(
    r'\b('
    r'on\s+my\s+(computer|laptop|machine|pc)\b'          # "on my computer"
    r'|across\s+(all|my|the)\s+drives?\b'                # "across all drives"
    r'|search\s+all\s+drives?\b'                         # "search all drives"
    r'|on\s+all\s+drives?\b'                             # "on all drives"
    r'|entire\s+(computer|laptop|machine|disk|system)\b' # "entire computer"
    r'|full\s+(disk|system|computer|laptop)\s+scan\b'    # "full disk scan"
    r'|all\s+drives?\s+and\b'                            # "all drives and..."
    r')',
    re.IGNORECASE,
)

# Queries that narrow the scope to a specific folder (exempt from background)
_SCOPED_DIR_RE = re.compile(
    r'\b(in\s+(downloads?|desktop|documents?|pictures?|videos?|music)\b'
    r'|in\s+["\'][\w\s]+["\']'        # in "folder name"
    r'|under\s+[A-Za-z]:\\'           # under C:\
    r'|inside\s+\w+'                  # inside SomeFolder
    r')',
    re.IGNORECASE,
)

def _is_heavy_scan(query: str) -> bool:
    """
    Return True when the query requires an unscoped full-disk scan that
    would block the chat for potentially minutes.
    """
    if not _HEAVY_SCAN_RE.search(query):
        return False
    # Scoped queries ("on my computer in Downloads") are still fast enough
    if _SCOPED_DIR_RE.search(query):
        return False
    return True

def _try_background_job(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    If the query is a heavy full-disk scan, dispatch it to a background job
    and return an immediate acknowledgement message.

    Returns a result dict (immediate response) on dispatch, or None to fall
    through to normal synchronous LLM execution.
    """
    if not _is_heavy_scan(user_query):
        return None

    session_id = (artifacts_out or {}).get("_session_id", "")
    pa_id      = (artifacts_out or {}).get("_pa_id", "")

    # Fallback: read PA_ID from the process environment (set by Telegram poller)
    if not pa_id:
        pa_id = os.environ.get("PA_ID", "")

    try:
        from src.agent.manifest.job_manifest import create_job, update_job  # noqa: PLC0415
        from src.agent.manifest.job_runner import submit_job                 # noqa: PLC0415
    except _FILES_ORCHESTRATOR_ERRORS as exc:
        import logging as _lg
        _lg.getLogger("files.orchestrator").warning(
            "[bg-scan] job manifest/runner unavailable (%s) — running synchronously", exc
        )
        return None  # fall through to synchronous execution

    job_id = create_job(
        agent="files",
        description=user_query[:120],
        session_id=session_id,
        pa_id=pa_id,
        params={"query": user_query},
    )

    # Strip any injected '## Session State' block from the query so the plain
    # natural-language question is stored cleanly in the closure.
    _clean_marker = "## Session State"
    _raw_query = user_query.split(_clean_marker)[0].strip()

    # Capture references for the closure
    _job_id = job_id

    # ------------------------------------------------------------------
    # Classify query type so _do_scan can search directly without LLM.
    # ------------------------------------------------------------------
    _lower = _raw_query.lower()
    _EXT_MAP = {
        "image":    ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp", "svg", "ico"],
        "video":    ["mp4", "avi", "mov", "mkv", "wmv", "flv", "webm"],
        "audio":    ["mp3", "wav", "flac", "aac", "m4a", "ogg", "wma"],
        "document": ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt"],
        "pdf":      ["pdf"],
    }
    _type_label: Optional[str] = None
    _scan_exts: Optional[list] = None
    if any(w in _lower for w in ("image", "photo", "picture", "screenshot", "jpg", "png")):
        _type_label, _scan_exts = "image", _EXT_MAP["image"]
    elif any(w in _lower for w in ("video", "film", "movie", "recording", "mp4", "mkv")):
        _type_label, _scan_exts = "video", _EXT_MAP["video"]
    elif any(w in _lower for w in ("audio", "music", "song", "mp3", "wav")):
        _type_label, _scan_exts = "audio", _EXT_MAP["audio"]
    elif "pdf" in _lower and not any(w in _lower for w in ("document", "word", "excel")):
        _type_label, _scan_exts = "PDF", _EXT_MAP["pdf"]
    elif any(w in _lower for w in ("document", "doc", "word", "excel", "spreadsheet", "office")):
        _type_label, _scan_exts = "document", _EXT_MAP["document"]

    def _do_scan() -> str:
        """
        Direct Python search — no LLM, no iteration limits.

        For extension-based queries (images, videos, PDFs…) we call
        search_by_extension() directly for each relevant extension.
        For unrecognised queries we fall back to the DAG/ReAct engine
        with the clean (Session-State-free) query.
        """
        import sys as _sys
        import string as _string
        from src.files.features.search import search_by_extension as _sbe  # noqa: PLC0415
        from src.files.features.file_ops import save_search_manifest as _ssm  # noqa: PLC0415

        if _scan_exts:
            # ── Direct extension search (no LLM) ─────────────────────────────
            all_paths: list = []
            home = Path.home()
            total = len(_scan_exts)

            # Build list of directories to search:
            # 1. Home directory (C:\Users\malus — covers most user files)
            # 2. C:\ root but ONLY non-system top-level folders
            #    (catches C:\Hrishikesh\, C:\Projects\, etc.)
            # 3. Any additional drive roots (D:\, E:\, …)
            search_roots: list = [str(home)]

            # Add non-home, non-system top-level C:\ folders
            try:
                c_root = Path("C:\\")
                if c_root.exists():
                    _skip = {"windows", "program files", "program files (x86)",
                              "programdata", "users", "recovery", "system volume information",
                              "$recycle.bin", "perflogs", "msocache"}
                    for child in c_root.iterdir():
                        if child.is_dir() and child.name.lower() not in _skip:
                            search_roots.append(str(child))
            except (OSError, RuntimeError, ValueError):
                pass

            # Add other drive roots (D:\, E:\, …)
            if _sys.platform == "win32":
                try:
                    for d in _string.ascii_uppercase:
                        if d == "C":
                            continue
                        drive = Path(f"{d}:\\")
                        if drive.exists():
                            search_roots.append(str(drive))
                except (OSError, RuntimeError, ValueError):
                    pass

            for i, ext in enumerate(_scan_exts):
                update_job(
                    _job_id, status="running",
                    progress_pct=int(5 + 85 * i / total),
                    progress_detail=f"Searching *.{ext} files ({i + 1}/{total})…",
                )
                for root_dir in search_roots:
                    try:
                        result = _sbe(ext, root_dir, True, 0)
                        for entry in result.get("results", []):
                            p = entry.get("path", "")
                            if p:
                                all_paths.append(p)
                    except _FILES_ORCHESTRATOR_ERRORS:
                        pass

            # Deduplicate preserving order
            seen: set = set()
            unique: list = []
            for p in all_paths:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)

            update_job(_job_id, status="running", progress_pct=95,
                       progress_detail="Saving results…")
            if unique:
                _ssm(unique)

            count = len(unique)
            # Build extension breakdown (top 5)
            ext_counts: dict = {}
            for p in unique:
                e = Path(p).suffix.lower().lstrip(".") or "other"
                ext_counts[e] = ext_counts.get(e, 0) + 1
            top = sorted(ext_counts.items(), key=lambda x: -x[1])[:5]
            breakdown = "  |  ".join(f".{e}: **{c}**" for e, c in top)

            if count == 0:
                return (f"✅ Scan complete — No {_type_label} files found on your computer.\n\n"
                        f"_(Searched: {', '.join('.' + x for x in _scan_exts)})_")
            s = "s" if count != 1 else ""
            lines = [
                f"✅ Scan complete — Found **{count} {_type_label} file{s}** on your computer.",
                "",
                f"📊 Breakdown: {breakdown}",
                "",
                "💡 Say *'copy them to Downloads'* to collect all found files.",
            ]
            return "\n".join(lines)

        else:
            # ── Fallback: LLM orchestration for non-extension queries ─────────
            # Use the clean query (no injected Session State) to avoid DAG
            # planning failures caused by non-JSON LLM responses.
            update_job(_job_id, status="running", progress_pct=5,
                       progress_detail="Starting analysis…")
            _skill_context = _build_skill_context()
            _all_tools     = _build_all_tools()
            _dag_docs = _get_tool_docs_for_dag()
            _react_docs = _get_tool_docs_for_react(_raw_query)
            try:
                res = run_skill_dag(
                    skill_name="files",
                    skill_context=_skill_context,
                    tool_map=_all_tools,
                    tool_docs=_dag_docs,
                    user_query=_raw_query,
                    artifacts_out={},
                )
            except _FILES_ORCHESTRATOR_ERRORS:
                res = run_skill_react(
                    skill_name="files",
                    skill_context=_skill_context,
                    tool_map=_get_tool_map_for_react(_raw_query, _all_tools),
                    tool_docs=_react_docs,
                    user_query=_raw_query,
                    artifacts_out={},
                )
            return res.get("message", "Scan complete.")

    submit_job(job_id, _do_scan, session_id=session_id, pa_id=pa_id)

    return {
        "status":  "success",
        "message": (
            f"⏳ I've started the search in the background *(Job `{job_id}`)*.\n\n"
            "This may take a few minutes for a full scan across all drives. "
            "I'll send you a message here as soon as the results are ready! 🔔"
        ),
        "action":  "react_response",
        "job_id":  job_id,
    }

def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner (needs all tools to plan)."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    docs = get_all_tool_docs("files")
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("files.orchestrator").error(
            "[files-agent] skills.md returned no tools — check ui/files_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs

def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine (cosine-similarity top-K)."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    docs = load_tool_docs(
        "files", user_query,
        always_include=["save_context", "deliver_file", "save_search_manifest"],
    )
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("files.orchestrator").error(
            "[files-agent] FAISS returned no tool docs for query=%r — "
            "check ui/files_agent/skills.md", user_query[:60]
        )
    return docs

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat.

    Primary path: DAG planner (2 LLM calls regardless of task length).
    Fallback:      ReAct loop (1 LLM call per step, up to 6 iterations).
    """
    del agent_id
    # ── Pre-flight: copy-from-manifest bypass (no LLM needed) ────────────
    direct = _try_direct_copy_from_manifest(user_query, artifacts_out)
    if direct is not None:
        return _return_fast_path_result(direct)

    list_names = _try_list_names_from_files_context(user_query)
    if list_names is not None:
        return _return_fast_path_result(list_names)

    direct_rename = _try_direct_rename_from_files_context(user_query, artifacts_out)
    if direct_rename is not None:
        return _return_fast_path_result(direct_rename)

    existing_archive = _try_reuse_existing_archive_from_context(user_query, artifacts_out)
    if existing_archive is not None:
        return _return_fast_path_result(existing_archive)

    subset_zip = _try_context_subset_zip(user_query, artifacts_out)
    if subset_zip is not None:
        return _return_fast_path_result(subset_zip)

    direct_zip_from_context = _try_direct_zip_from_files_context(user_query, artifacts_out)
    if direct_zip_from_context is not None:
        return _return_fast_path_result(direct_zip_from_context)

    recent_payslip_zip = _try_last_n_months_payslip_zip(user_query, artifacts_out)
    if recent_payslip_zip is not None:
        return _return_fast_path_result(recent_payslip_zip)

    direct_zip = _try_direct_zip_from_search_bundle(user_query, artifacts_out)
    if direct_zip is not None:
        return _return_fast_path_result(direct_zip)

    recycle_bin = _try_recycle_bin_query(user_query)
    if recycle_bin is not None:
        return _return_fast_path_result(recycle_bin)

    specific_drive_item = _try_specific_drive_item_query(user_query, artifacts_out)
    if specific_drive_item is not None:
        return _return_fast_path_result(specific_drive_item)

    specific_computer_item = _try_specific_computer_item_query(user_query, artifacts_out)
    if specific_computer_item is not None:
        return _return_fast_path_result(specific_computer_item)

    contextual_folder_count = _try_contextual_folder_count_query(user_query, artifacts_out)
    if contextual_folder_count is not None:
        return _return_fast_path_result(contextual_folder_count)

    specific_computer_folder_count = _try_specific_computer_folder_count_query(user_query, artifacts_out)
    if specific_computer_folder_count is not None:
        return _return_fast_path_result(specific_computer_folder_count)

    specific_folder_count = _try_specific_folder_count_query(user_query, artifacts_out)
    if specific_folder_count is not None:
        return _return_fast_path_result(specific_folder_count)

    scoped = _try_scoped_named_search(user_query, artifacts_out)
    if scoped is not None:
        return _return_fast_path_result(scoped)

    filename_contains = _try_filename_contains_search(user_query, artifacts_out)
    if filename_contains is not None:
        return _return_fast_path_result(filename_contains)

    # ── Pre-flight: deterministic targeted full-computer search ───────────
    precise = _try_precise_full_computer_search(user_query, artifacts_out)
    if precise is not None:
        return _return_fast_path_result(precise)

    # ── Background dispatch: heavy full-disk scans run async ──────────────
    try:
        bg = _try_background_job(user_query, artifacts_out)
        if bg is not None:
            return _return_fast_path_result(bg)
    except _FILES_ORCHESTRATOR_ERRORS as _bg_exc:
        import logging as _bg_log
        _bg_log.getLogger("files.orchestrator").warning(
            "[bg-scan] background dispatch raised %s — running synchronously", _bg_exc
        )

    skill_context = _build_skill_context()  # dynamic — includes real OS paths
    all_tools = _build_all_tools()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        result = run_skill_dag(
            skill_name="files",
            skill_context=skill_context,
            tool_map=all_tools,           # DAG planner needs the full tool set
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
        _maybe_save_manifest(artifacts_out)  # safety net — DAG engine already tries this
        return result
    except _FILES_ORCHESTRATOR_ERRORS as dag_exc:
        import logging as _logging
        _logging.getLogger("files.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
        log_fallback_to_react("files", "files_orchestrator_exception")
    try:
        result = run_skill_react(
            skill_name="files",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),  # FAISS-filtered
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
        _maybe_save_manifest(artifacts_out)  # ReAct engine does NOT auto-save manifest
        return result
    except _FILES_ORCHESTRATOR_ERRORS as exc:
        return {
            "status": "error",
            "message": f"❌ Files skill error: {exc}",
            "action": "react_response",
        }


parse_precise_full_computer_search = _parse_precise_full_computer_search
filter_precise_search_results = _filter_precise_search_results
