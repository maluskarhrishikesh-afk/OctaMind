"""
Google Drive skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag

_TOOL_DOCS = """
list_files(query="", max_results=20, folder_id="root") – List files in Drive (optional folder filter).
search_files(name="", file_type="", max_results=10) – Search files by name and/or type (e.g. "spreadsheet").
get_file_info(file_id) – Return metadata for a specific file.
upload_file(local_path, name="", folder_id=None, mime_type=None) – Upload a local file to Drive.
download_file(file_id, local_path) – Download a Drive file to a local path.
create_folder(name, parent_id=None) – Create a new folder.
move_file(file_id, folder_id) – Move a single file to a different folder.
copy_file(file_id, name="", folder_id=None) – Copy a single file.
trash_file(file_id) – Move a single file to Trash.
restore_file(file_id) – Restore a trashed file.
star_file(file_id, starred=True) – Star or un-star a file.
get_storage_quota() – Return used/total/free Drive storage quota.
batch_move_files(file_ids, folder_id) – Move multiple files to a folder in one call. file_ids is a list of Drive file IDs.
batch_delete_files(file_ids, permanent=False) – Trash (or permanently delete) multiple files at once.
batch_copy_files(file_ids, folder_id="", name_suffix=" (copy)") – Copy multiple files, optionally to a destination folder.
share_file(file_id, email="", role="reader", make_public=False) – Share a file with a person (role: reader/commenter/writer) or make it publicly accessible.
manage_file_permissions(file_id, action, permission_id="", new_role="reader") – action: 'list' (show all), 'remove' (delete), 'update' (change role).
list_shared_with_me(max_results=20) – List all files shared with me by others.
find_large_files(folder_id="root", min_size_mb=10.0, max_results=25) – Find the largest files in Drive. Use to diagnose storage issues.
find_drive_duplicates(folder_id="root", max_results=200) – Find duplicate files in Drive by name+size fingerprint.
trash_drive_duplicates(folder_id="root", keep="newest") – Trash duplicates, keeping one copy per group. keep: 'newest' or 'oldest'.
convert_document(file_id, output_format="pdf", save_path="") – Export a Google Docs/Sheets/Slides file to pdf/docx/xlsx/pptx/csv/txt/html.
list_file_versions(file_id) – List all revision history for a Drive file.
cleanup_old_versions(file_id, keep_latest=3) – Delete old file revisions, keeping only the N most recent.
revoke_access_all(file_id) – Remove ALL non-owner permissions from a file (make it completely private).
get_sharing_stats(file_id) – Show all permissions for a file: who has access, at what role, whether it is public.
suggest_archival(folder_id="root", months_old=6, max_results=25) – Find files not modified in N months. Use for 'what can I archive?' or 'show stale files'.
backup_drive_to_local(folder_id, output_dir, max_files=100) – Download all files from a Drive folder to a local directory. Google Docs/Sheets exported as PDF/XLSX.
sync_local_folder_to_drive(local_path, drive_folder_id, dry_run=True) – Upload new or modified files from a local folder to Drive. Always dry_run=True first.
""".strip()

_SKILL_CONTEXT = """
You are the Google Drive Skill Agent.
Help the user manage their Google Drive: list, search, upload, download, move, copy, delete, share and organise files.
When the user says "upload", ask for the local file path if not provided.
When the user says "download", ask for the file name or ID if not provided.
Always prefer search_files over list_files when looking for a specific file by name.
For sharing: use share_file(file_id, email, role) to share with a specific person, or share_file(file_id, make_public=True) for a public link.
For bulk operations (move/delete/copy multiple files): use batch_move_files / batch_delete_files / batch_copy_files — pass a list of file IDs, NOT individual calls per file.
For storage questions ("how much space do I have?", "what's eating my storage?"): call get_storage_quota() then find_large_files().
For duplicate cleanup: call find_drive_duplicates() to show groups, then trash_drive_duplicates() to clean.
For format conversion: use convert_document(file_id, output_format) — supports pdf, docx, xlsx, pptx, csv, txt.
For permission management: use manage_file_permissions(file_id, 'list') to see who has access, then 'remove'/'update' to modify.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.drive import drive_service as ds  # noqa: PLC0415

    return {
        "list_files": lambda query="", max_results=20, folder_id=None: ds.list_files(
            max_results=int(max_results) if max_results else 20,
            query=query or "",
            folder_id=folder_id or "root",
        ),
        "search_files": lambda name="", file_type="", max_results=10: ds.search_files(
            query=" and ".join(filter(None, [
                (f"name contains '{name}'" if name else ""),
                (f"mimeType='{file_type}'" if file_type else ""),
            ])) or "",
            max_results=int(max_results) if str(max_results).isdigit() else 10,
        ),
        "get_file_info": lambda file_id: ds.get_file_info(file_id),
        "upload_file": lambda local_path, name="", folder_id=None, mime_type=None: ds.upload_file(local_path, name, folder_id, mime_type),
        "download_file": lambda file_id, local_path: ds.download_file(file_id, local_path),
        "create_folder": lambda name, parent_id=None: ds.create_folder(name, parent_id),
        "move_file": lambda file_id, folder_id: ds.move_file(file_id, folder_id),
        "copy_file": lambda file_id, name="", folder_id=None: ds.copy_file(file_id, name, folder_id),
        "trash_file": lambda file_id: ds.trash_file(file_id),
        "restore_file": lambda file_id: ds.restore_file(file_id),
        "star_file": lambda file_id, starred=True: ds.star_file(file_id, starred),
        "get_storage_quota": lambda: ds.get_storage_quota(),
        # ── NEW ────────────────────────────────────────────────────────────
        "batch_move_files":    lambda file_ids, folder_id: ds.batch_move_files(file_ids, folder_id),
        "batch_delete_files":  lambda file_ids, permanent=False: ds.batch_delete_files(file_ids, permanent),
        "batch_copy_files":    lambda file_ids, folder_id="", name_suffix=" (copy)": ds.batch_copy_files(file_ids, folder_id, name_suffix),
        "share_file":          lambda file_id, email="", role="reader", make_public=False: ds.share_file(file_id, email, role, make_public),
        "manage_file_permissions": lambda file_id, action, permission_id="", new_role="reader": ds.manage_file_permissions(file_id, action, permission_id, new_role=new_role),
        "list_shared_with_me": lambda max_results=20: ds.list_shared_with_me(max_results),
        "find_large_files":    lambda folder_id="root", min_size_mb=10.0, max_results=25: ds.find_large_files(folder_id, min_size_mb, max_results),
        "find_drive_duplicates":  lambda folder_id="root", max_results=200: ds.find_drive_duplicates(folder_id, max_results),
        "trash_drive_duplicates": lambda folder_id="root", keep="newest": ds.trash_drive_duplicates(folder_id, keep),
        "convert_document":    lambda file_id, output_format="pdf", save_path="": ds.convert_document(file_id, output_format, save_path),
        "list_file_versions":  lambda file_id: ds.list_file_versions(file_id),
        "cleanup_old_versions": lambda file_id, keep_latest=3: ds.cleanup_old_versions(file_id, keep_latest),
        # ── NEW ─────────────────────────────────────────────────
        "revoke_access_all":  lambda file_id: ds.revoke_access_all(file_id),
        "get_sharing_stats":  lambda file_id: ds.get_sharing_stats(file_id),
        "suggest_archival":   lambda folder_id="root", months_old=6, max_results=25: ds.suggest_archival(folder_id, months_old, max_results),
        "backup_drive_to_local": lambda folder_id, output_dir, max_files=100: ds.backup_drive_to_local(folder_id, output_dir, max_files),
        "sync_local_folder_to_drive": lambda local_path, drive_folder_id, dry_run=True: ds.sync_local_folder_to_drive(local_path, drive_folder_id, dry_run),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat.

    Primary path: DAG planner (2 LLM calls regardless of task length).
    Fallback:      ReAct loop (1 LLM call per step, up to 6 iterations).
    """
    tool_map = _get_tools()
    try:
        return run_skill_dag(
            skill_name="drive",
            skill_context=_SKILL_CONTEXT,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("drive.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        return run_skill_react(
            skill_name="drive",
            skill_context=_SKILL_CONTEXT,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Drive skill error: {exc}",
            "action": "react_response",
        }
