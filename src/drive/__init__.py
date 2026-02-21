"""
Google Drive Module

Core Drive service and all feature modules.

Usage:
    from src.drive import list_files, search_files, upload_file
    from src.drive import share_file, find_duplicates, storage_breakdown
"""

# ── Phase 1 — Core file operations ───────────────────────────────────────────
from .drive_service import (
    list_files,
    search_files,
    get_file_info,
    upload_file,
    download_file,
    create_folder,
    move_file,
    copy_file,
    trash_file,
    restore_file,
    star_file,
    get_storage_quota,
)

# ── Phase 2 — Sharing & Permissions ──────────────────────────────────────────
from .features.sharing import (
    share_file,
    list_permissions,
    remove_permission,
    update_permission,
    make_public,
    remove_public,
)

# ── Phase 3 — Smart / AI features ────────────────────────────────────────────
from .features.summarizer import (
    summarize_file,
    summarize_folder,
)
from .features.duplicates import (
    find_duplicates,
    trash_duplicates,
)
from .features.organizer import (
    suggest_organization,
    auto_organize,
    bulk_rename,
)
from .features.versions import (
    list_versions,
    get_version_info,
    restore_version,
    delete_old_versions,
)

# ── Phase 4 — Analytics & Insights ───────────────────────────────────────────
from .features.analytics import (
    storage_breakdown,
    list_large_files,
    list_old_files,
    list_recently_modified,
    find_orphaned_files,
    sharing_report,
)
from .features.insights import (
    generate_drive_report,
    get_usage_insights,
)

__all__ = [
    # Phase 1
    "list_files", "search_files", "get_file_info", "upload_file", "download_file",
    "create_folder", "move_file", "copy_file", "trash_file", "restore_file",
    "star_file", "get_storage_quota",
    # Phase 2
    "share_file", "list_permissions", "remove_permission", "update_permission",
    "make_public", "remove_public",
    # Phase 3
    "summarize_file", "summarize_folder",
    "find_duplicates", "trash_duplicates",
    "suggest_organization", "auto_organize", "bulk_rename",
    "list_versions", "get_version_info", "restore_version", "delete_old_versions",
    # Phase 4
    "storage_breakdown", "list_large_files", "list_old_files", "list_recently_modified",
    "find_orphaned_files", "sharing_report",
    "generate_drive_report", "get_usage_insights",
]
