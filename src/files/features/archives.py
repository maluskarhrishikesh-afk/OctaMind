"""
Archive (zip) tools for the Files Agent.

Handles creating, extracting, listing, and inspecting zip archives.
Uses Python stdlib zipfile — no external dependencies required.
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from ..files_service import resolve_path, _fmt_size

logger = logging.getLogger("files_agent")


def zip_files(
    sources: List[str],
    output_path: str,
    compression_level: int = 6,
) -> Dict[str, Any]:
    """
    Zip one or more files and/or folders into a single archive.

    Args:
        sources:           List of paths (files or folders) to include.
        output_path:       Full path for the output .zip file.
        compression_level: 0 (store) to 9 (max). Default 6.
    """
    try:
        out = resolve_path(output_path)
        if not out.suffix:
            out = out.with_suffix(".zip")
        out.parent.mkdir(parents=True, exist_ok=True)

        total_original = 0
        file_count = 0

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zf:
            for src_str in sources:
                src = resolve_path(src_str)
                if not src.exists():
                    return {"status": "error", "message": f"Source does not exist: {src}"}
                if src.is_dir():
                    for child in src.rglob("*"):
                        if child.is_file():
                            arcname = child.relative_to(src.parent)
                            zf.write(child, arcname)
                            total_original += child.stat().st_size
                            file_count += 1
                else:
                    zf.write(src, src.name)
                    total_original += src.stat().st_size
                    file_count += 1

        compressed_size = out.stat().st_size
        ratio = (1 - compressed_size / max(total_original, 1)) * 100

        return {
            "status": "success",
            "archive": str(out),
            "file_path": str(out),   # alias used by cross-agent {step_id.file_path} tokens
            "file_count": file_count,
            "original_size": _fmt_size(total_original),
            "compressed_size": _fmt_size(compressed_size),
            "compression_ratio": f"{ratio:.1f}%",
            "message": f"Created {out.name} with {file_count} file(s) ({_fmt_size(compressed_size)})",
        }
    except Exception as exc:
        logger.error("zip_files failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def zip_folder(folder_path: str, output_path: str = "") -> Dict[str, Any]:
    """
    Zip an entire folder into a zip archive.

    Args:
        folder_path: Path to the folder to zip.
        output_path: Destination .zip path. Defaults to same location as folder with .zip extension.
    """
    try:
        folder = resolve_path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return {"status": "error", "message": f"Folder does not exist: {folder}"}

        if output_path:
            out_str = output_path
        else:
            out_str = str(folder.parent / (folder.name + ".zip"))

        return zip_files([folder_path], out_str)
    except Exception as exc:
        logger.error("zip_folder failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def unzip_file(archive_path: str, destination: str = "") -> Dict[str, Any]:
    """
    Extract a zip archive.

    Args:
        archive_path: Path to the .zip file.
        destination:  Where to extract. Defaults to a folder named after the archive
                      in the same directory.
    """
    try:
        arc = resolve_path(archive_path)
        if not arc.exists():
            return {"status": "error", "message": f"Archive does not exist: {arc}"}

        if destination:
            dest = resolve_path(destination)
        else:
            dest = arc.parent / arc.stem

        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(arc, "r") as zf:
            zf.extractall(dest)
            names = zf.namelist()

        return {
            "status": "success",
            "archive": str(arc),
            "destination": str(dest),
            "extracted_files": len(names),
            "message": f"Extracted {len(names)} file(s) to {dest}",
        }
    except zipfile.BadZipFile:
        return {"status": "error", "message": f"Not a valid zip file: {archive_path}"}
    except Exception as exc:
        logger.error("unzip_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def list_archive_contents(archive_path: str) -> Dict[str, Any]:
    """
    List the contents of a zip archive without extracting.

    Args:
        archive_path: Path to the .zip file.
    """
    try:
        arc = resolve_path(archive_path)
        if not arc.exists():
            return {"status": "error", "message": f"Archive does not exist: {arc}"}

        with zipfile.ZipFile(arc, "r") as zf:
            infos = zf.infolist()
            contents = [
                {
                    "name": info.filename,
                    "compressed_size": _fmt_size(info.compress_size),
                    "original_size": _fmt_size(info.file_size),
                    "is_dir": info.filename.endswith("/"),
                }
                for info in infos
            ]

        return {
            "status": "success",
            "archive": str(arc),
            "archive_size": _fmt_size(arc.stat().st_size),
            "entry_count": len(contents),
            "contents": contents[:200],
        }
    except zipfile.BadZipFile:
        return {"status": "error", "message": f"Not a valid zip file: {archive_path}"}
    except Exception as exc:
        logger.error("list_archive_contents failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_archive_info(archive_path: str) -> Dict[str, Any]:
    """
    Get summary statistics about a zip archive.

    Args:
        archive_path: Path to the .zip file.
    """
    try:
        arc = resolve_path(archive_path)
        if not arc.exists():
            return {"status": "error", "message": f"Archive does not exist: {arc}"}

        with zipfile.ZipFile(arc, "r") as zf:
            infos = zf.infolist()
            total_compressed = sum(i.compress_size for i in infos)
            total_original   = sum(i.file_size for i in infos)
            file_count = sum(1 for i in infos if not i.filename.endswith("/"))
            folder_count = sum(1 for i in infos if i.filename.endswith("/"))

        ratio = (1 - total_compressed / max(total_original, 1)) * 100

        return {
            "status": "success",
            "archive": str(arc),
            "archive_size_on_disk": _fmt_size(arc.stat().st_size),
            "files": file_count,
            "folders": folder_count,
            "total_compressed": _fmt_size(total_compressed),
            "total_original": _fmt_size(total_original),
            "compression_ratio": f"{ratio:.1f}%",
        }
    except zipfile.BadZipFile:
        return {"status": "error", "message": f"Not a valid zip file: {archive_path}"}
    except Exception as exc:
        logger.error("get_archive_info failed: %s", exc)
        return {"status": "error", "message": str(exc)}
