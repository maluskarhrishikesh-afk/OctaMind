"""
LiteParse-backed document parsing tools.

These tools shell out to the local LiteParse CLI when available and return
actionable setup guidance when it is not installed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
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
_GENERIC_ID_HINTS = ("id", "number", "no", "reference", "ref", "uan", "pan", "account")
_MONETARY_LABEL_HINTS = (
    "amount",
    "pay",
    "earnings",
    "deduction",
    "bonus",
    "allowance",
    "tax",
    "contribution",
    "arrears",
    "salary",
    "gross",
    "net",
)
_DOC_TYPE_PATTERNS = {
    "payslip": ("payslip", "salary slip", "employee pay summary", "gross earnings", "net pay"),
    "invoice": ("invoice", "bill to", "invoice number", "amount due", "tax invoice"),
    "receipt": ("receipt", "payment received", "receipt number", "payment method"),
    "bank_statement": ("bank statement", "opening balance", "closing balance", "statement period"),
    "offer_letter": ("offer letter", "position", "joining date", "compensation"),
    "resume": ("experience", "education", "skills", "projects"),
}
_PAYSLIP_FIELD_MAP = {
    "employee_id": ("employee_id",),
    "employee_name": ("employee_name",),
    "designation": ("designation",),
    "date_of_joining": ("date_of_joining",),
    "pay_date": ("pay_date",),
    "paid_days": ("paid_days",),
    "lop_days": ("lop_days",),
    "uan": ("uan",),
    "basic": ("basic",),
    "house_rent_allowance": ("house_rent_allowance",),
    "fixed_bonus": ("fixed_bonus",),
    "other_allowances": ("other_allowances",),
    "advance_or_arrears": ("advance_or_arrears_or_notice_pay", "advance_or_arrears"),
    "gross_earnings": ("gross_earnings",),
    "net_pay": ("net_pay",),
    "total_deductions": ("total_deductions",),
    "epf_contribution": ("epf_contribution",),
    "income_tax": ("income_tax",),
    "professional_tax": ("professional_tax",),
    "other_deductions": ("other_deductions",),
}
_NUMBER_WORDS = {
    "zero": 0,
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
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_NUMBER_SCALES = {
    "hundred": 100,
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
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


def _default_structured_output_path(parse_output: Path) -> Path:
    stem = parse_output.stem
    if stem.endswith("_liteparse"):
        stem = stem[: -len("_liteparse")]
    return parse_output.with_name(f"{stem}_structured.json")


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


def _normalize_label(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(label or "").strip().lower())
    return normalized.strip("_")


def _first_non_empty_line(text: str) -> str:
    for line in str(text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def _parse_numeric_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    digits = re.sub(r"[^0-9-]", "", str(value))
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _parse_number_words(text: str) -> Optional[int]:
    tokens = [tok for tok in re.split(r"[^a-z]+", str(text or "").lower()) if tok and tok != "and"]
    if not tokens:
        return None

    total = 0
    current = 0
    matched = False
    for token in tokens:
        if token in _NUMBER_WORDS:
            current += _NUMBER_WORDS[token]
            matched = True
            continue
        if token == "hundred":
            if current == 0:
                current = 1
            current *= _NUMBER_SCALES[token]
            matched = True
            continue
        scale = _NUMBER_SCALES.get(token)
        if scale and scale >= 1000:
            if current == 0:
                current = 1
            total += current * scale
            current = 0
            matched = True
            continue
        return None

    if not matched:
        return None
    return total + current


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_lines_from_parsed_json(parsed_data: Any) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    pages = parsed_data.get("pages") if isinstance(parsed_data, dict) else None
    if not isinstance(pages, list):
        return lines

    for page_entry in pages:
        if not isinstance(page_entry, dict):
            continue
        page_number = page_entry.get("page")
        page_text = str(page_entry.get("text", "") or "")
        for raw_line in page_text.splitlines():
            line = raw_line.rstrip()
            if line.strip():
                lines.append({"page": page_number, "line": line})
    return lines


def _extract_label_value_pairs(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    for entry in lines:
        segments = [segment.strip() for segment in re.split(r"\s{2,}", entry["line"].strip()) if segment.strip()]
        if len(segments) < 2:
            continue
        for index in range(0, len(segments) - 1, 2):
            label = segments[index]
            value = segments[index + 1]
            if not label or not value:
                continue
            pairs.append(
                {
                    "page": entry.get("page"),
                    "label": label,
                    "normalized_label": _normalize_label(label),
                    "value": value,
                }
            )
    return pairs


def _build_label_index(pairs: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for pair in pairs:
        key = pair["normalized_label"]
        index.setdefault(key, [])
        if pair["value"] not in index[key]:
            index[key].append(pair["value"])
    return index


def _first_index_value(label_index: Dict[str, List[str]], *keys: str) -> Optional[str]:
    for key in keys:
        values = label_index.get(key)
        if values:
            return values[0]
    return None


def _detect_document_type(text: str, source_name: str) -> Dict[str, Any]:
    haystack = f"{source_name}\n{text}".lower()
    best_type = "generic"
    best_score = 0
    for doc_type, patterns in _DOC_TYPE_PATTERNS.items():
        score = sum(1 for pattern in patterns if pattern in haystack)
        if doc_type in source_name.lower():
            score += 2
        if score > best_score:
            best_score = score
            best_type = doc_type
    confidence = 0.2 if best_type == "generic" else min(0.98, 0.45 + (0.12 * best_score))
    return {"type": best_type, "confidence": round(confidence, 2), "score": best_score}


def _extract_generic_candidates(
    lines: List[Dict[str, Any]],
    pairs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    dates: List[str] = []
    for entry in lines:
        for match in re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", entry["line"]):
            if match not in dates:
                dates.append(match)

    identifiers: List[Dict[str, Any]] = []
    monetary_fields: List[Dict[str, Any]] = []
    named_fields: Dict[str, Any] = {}
    for pair in pairs:
        label = pair["label"]
        normalized = pair["normalized_label"]
        values = named_fields.get(normalized)
        if values is None:
            named_fields[normalized] = pair["value"]
        elif isinstance(values, list):
            if pair["value"] not in values:
                values.append(pair["value"])
        elif values != pair["value"]:
            named_fields[normalized] = [values, pair["value"]]

        if any(hint in normalized for hint in _GENERIC_ID_HINTS):
            identifiers.append({"label": label, "value": pair["value"], "page": pair.get("page")})
        amount = _parse_numeric_value(pair["value"])
        if amount is not None and any(hint in normalized for hint in _MONETARY_LABEL_HINTS):
            monetary_fields.append(
                {"label": label, "value": pair["value"], "numeric_value": amount, "page": pair.get("page")}
            )

    return {
        "dates": dates[:20],
        "identifiers": identifiers[:20],
        "monetary_fields": monetary_fields[:30],
        "named_fields": named_fields,
    }


def _extract_payslip_fields(text: str, label_index: Dict[str, List[str]]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for field_name, aliases in _PAYSLIP_FIELD_MAP.items():
        value = _first_index_value(label_index, *aliases)
        if value is not None:
            fields[field_name] = value

    pay_period_match = re.search(r"Payslip for the month of\s+([A-Za-z]+\s+\d{4})", text, re.IGNORECASE)
    if pay_period_match:
        fields["pay_period"] = pay_period_match.group(1).strip()

    words_match = re.search(r"Rupees\s+(.+?)\s+Only", text, re.IGNORECASE | re.DOTALL)
    if words_match:
        fields["net_pay_in_words"] = re.sub(r"\s+", " ", words_match.group(1)).strip()

    earnings_breakdown = {
        key: fields[key]
        for key in ("basic", "house_rent_allowance", "fixed_bonus", "other_allowances", "advance_or_arrears")
        if key in fields
    }
    if earnings_breakdown:
        fields["earnings_breakdown"] = earnings_breakdown

    deductions_breakdown = {
        key: fields[key]
        for key in ("epf_contribution", "income_tax", "professional_tax", "other_deductions", "total_deductions")
        if key in fields
    }
    if deductions_breakdown:
        fields["deductions_breakdown"] = deductions_breakdown

    return fields


def _extract_document_title(lines: List[Dict[str, Any]], doc_type: str) -> str:
    for entry in lines:
        line = entry["line"].strip()
        if doc_type == "payslip" and "payslip for the month of" in line.lower():
            return line
        if len(line) >= 12 and not re.fullmatch(r"[*\-_= ]+", line):
            return line
    return ""


def _build_tamper_assessment(
    document_type: str,
    fields: Dict[str, Any],
    generic_candidates: Dict[str, Any],
) -> Dict[str, Any]:
    score = 0
    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []

    if document_type == "payslip":
        gross = _parse_numeric_value(fields.get("gross_earnings"))
        deductions = _parse_numeric_value(fields.get("total_deductions"))
        net_pay = _parse_numeric_value(fields.get("net_pay"))
        if gross is not None and deductions is not None and net_pay is not None:
            expected = gross - deductions
            passed = expected == net_pay
            checks.append(
                {
                    "name": "gross_minus_deductions_equals_net_pay",
                    "passed": passed,
                    "expected": expected,
                    "actual": net_pay,
                }
            )
            if not passed:
                score += 65
                warnings.append("Net pay does not equal gross earnings minus total deductions.")
        else:
            checks.append(
                {
                    "name": "gross_minus_deductions_equals_net_pay",
                    "passed": False,
                    "skipped": True,
                    "reason": "Missing gross, deductions, or net pay fields.",
                }
            )
            score += 10

        amount_in_words = fields.get("net_pay_in_words")
        if amount_in_words and net_pay is not None:
            parsed_words = _parse_number_words(amount_in_words)
            passed = parsed_words == net_pay if parsed_words is not None else False
            checks.append(
                {
                    "name": "amount_in_words_matches_net_pay",
                    "passed": passed,
                    "expected": net_pay,
                    "actual": parsed_words,
                }
            )
            if parsed_words is None:
                score += 5
                warnings.append("Net pay in words could not be normalized to a numeric amount.")
            elif not passed:
                score += 40
                warnings.append("Net pay in words does not match the numeric net pay.")

        required_fields = [
            "employee_id",
            "employee_name",
            "designation",
            "gross_earnings",
            "total_deductions",
            "net_pay",
        ]
        missing = [field_name for field_name in required_fields if not fields.get(field_name)]
        checks.append(
            {
                "name": "required_payslip_fields_present",
                "passed": not missing,
                "missing_fields": missing,
            }
        )
        if missing:
            score += min(30, 5 * len(missing))
            warnings.append(f"Missing expected payslip fields: {', '.join(missing)}.")

    conflicting_labels = [
        key
        for key, value in generic_candidates.get("named_fields", {}).items()
        if isinstance(value, list) and len({str(item) for item in value}) > 1
    ]
    checks.append(
        {
            "name": "conflicting_named_fields",
            "passed": not conflicting_labels,
            "conflicting_fields": conflicting_labels,
        }
    )
    if conflicting_labels:
        score += min(30, 8 * len(conflicting_labels))
        warnings.append("Some labeled fields were extracted with conflicting values.")

    if score >= 60:
        risk_level = "high"
        verdict = "suspicious_inconsistency"
    elif score >= 20:
        risk_level = "medium"
        verdict = "review_recommended"
    else:
        risk_level = "low"
        verdict = "no_obvious_tampering"

    return {
        "risk_level": risk_level,
        "risk_score": score,
        "verdict": verdict,
        "checks": checks,
        "warnings": warnings,
        "limitations": [
            "This is a heuristic consistency check, not a forensic authenticity guarantee.",
            "Reliable tamper detection may require original PDF metadata, digital signatures, or issuer-side verification.",
        ],
    }


def _build_structured_document_payload(
    *,
    source_path: Optional[Path],
    parse_output_path: Path,
    parsed_data: Dict[str, Any],
) -> Dict[str, Any]:
    lines = _extract_lines_from_parsed_json(parsed_data)
    pairs = _extract_label_value_pairs(lines)
    label_index = _build_label_index(pairs)
    page_text = "\n".join(entry["line"] for entry in lines)
    document_info = _detect_document_type(page_text, source_path.name if source_path else parse_output_path.name)
    generic_candidates = _extract_generic_candidates(lines, pairs)
    key_fields: Dict[str, Any]
    if document_info["type"] == "payslip":
        key_fields = _extract_payslip_fields(page_text, label_index)
    else:
        key_fields = {
            "title": _extract_document_title(lines, document_info["type"]),
            "primary_date": generic_candidates["dates"][0] if generic_candidates["dates"] else None,
            "named_fields": generic_candidates["named_fields"],
            "identifier_fields": generic_candidates["identifiers"],
            "monetary_fields": generic_candidates["monetary_fields"],
        }

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(source_path) if source_path else "",
            "name": source_path.name if source_path else parse_output_path.name,
            "extension": source_path.suffix.lower() if source_path else "",
            "sha256": _sha256_file(source_path) if source_path and source_path.exists() else "",
        },
        "parser": {
            "parse_output_path": str(parse_output_path),
            "page_count": len(parsed_data.get("pages", [])) if isinstance(parsed_data.get("pages"), list) else 0,
            "top_level_keys": list(parsed_data.keys())[:20],
        },
        "document": {
            "type": document_info["type"],
            "type_confidence": document_info["confidence"],
            "issuer": _first_non_empty_line(page_text),
            "title": _extract_document_title(lines, document_info["type"]),
        },
        "key_fields": key_fields,
        "generic_candidates": {
            "dates": generic_candidates["dates"],
            "identifiers": generic_candidates["identifiers"],
            "monetary_fields": generic_candidates["monetary_fields"],
        },
        "label_value_pairs": pairs,
    }
    payload["tamper_assessment"] = _build_tamper_assessment(document_info["type"], key_fields, generic_candidates)
    return payload


def extract_document_key_fields(
    parse_output_path: str,
    source_path: str = "",
    output_path: str = "",
) -> Dict[str, Any]:
    try:
        parse_output = resolve_path(parse_output_path)
        if not parse_output.exists():
            return {"status": "error", "message": f"Parse output does not exist: {parse_output}"}
        if not parse_output.is_file():
            return {"status": "error", "message": f"Not a file: {parse_output}"}
        if parse_output.suffix.lower() != ".json":
            return {"status": "error", "message": "extract_document_key_fields requires a LiteParse JSON output file."}

        source: Optional[Path] = None
        if source_path:
            source = resolve_path(source_path)
        parsed_data = json.loads(parse_output.read_text(encoding="utf-8"))
        if not isinstance(parsed_data, dict):
            return {"status": "error", "message": "LiteParse JSON must be a top-level object."}

        structured_output = _coerce_output_path(output_path, is_dir=False) if output_path else _default_structured_output_path(parse_output)
        payload = _build_structured_document_payload(
            source_path=source,
            parse_output_path=parse_output,
            parsed_data=parsed_data,
        )
        structured_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "status": "success",
            "parse_output_path": str(parse_output),
            "output_path": str(structured_output),
            "document_type": payload["document"]["type"],
            "key_fields": payload["key_fields"],
            "tamper_assessment": payload["tamper_assessment"],
            "message": f"Created structured document summary at {structured_output.name}.",
        }
    except (OSError, ValueError, TypeError) as exc:
        logger.error("extract_document_key_fields failed: %s", exc)
        return {"status": "error", "message": str(exc)}


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
    generate_structured_output: bool = True,
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
        if chosen_format == "json" and generate_structured_output:
            structured_result = extract_document_key_fields(str(output), source_path=str(source))
            if structured_result.get("status") == "success":
                payload["structured_output_path"] = structured_result.get("output_path")
                payload["document_type"] = structured_result.get("document_type")
                payload["key_fields"] = structured_result.get("key_fields")
                payload["tamper_assessment"] = structured_result.get("tamper_assessment")
            else:
                payload["structured_output_error"] = structured_result.get("message", "Structured output generation failed.")
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
    generate_structured_output: bool = True,
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
        raw_outputs = [path for path in outputs if not path.name.endswith("_structured.json")]
        structured_outputs: List[str] = []
        if chosen_format == "json" and generate_structured_output:
            for raw_output in raw_outputs:
                structured_result = extract_document_key_fields(str(raw_output))
                if structured_result.get("status") == "success":
                    structured_outputs.append(str(structured_result["output_path"]))

        return {
            "status": "success",
            "input_dir": str(source_dir),
            "output_dir": str(destination),
            "output_format": chosen_format,
            "file_count": len(raw_outputs),
            "files": [str(path) for path in raw_outputs[:100]],
            "truncated": len(raw_outputs) > 100,
            "structured_file_count": len(structured_outputs),
            "structured_files": structured_outputs[:100],
            "structured_truncated": len(structured_outputs) > 100,
            "message": f"Batch parsed {len(raw_outputs)} file(s) into {destination}.",
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