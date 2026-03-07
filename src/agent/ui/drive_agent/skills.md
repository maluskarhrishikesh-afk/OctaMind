# Drive Agent — Tool Skills

## Category: Browse & Search

### list_files
- **signature**: `list_files(query="", max_results=20, folder_id="root")`
- **description**: List files in Drive (optional folder filter).
- **tags**: list, browse, view, folder, contents, drive

### search_files
- **signature**: `search_files(name="", file_type="", max_results=10)`
- **description**: Search files by name and/or type (e.g. "spreadsheet").
- **tags**: search, find, name, type, locate, query

### get_file_info
- **signature**: `get_file_info(file_id)`
- **description**: Return metadata for a specific file.
- **tags**: info, metadata, details, properties, file

### list_shared_with_me
- **signature**: `list_shared_with_me(max_results=20)`
- **description**: List all files shared with me by others.
- **tags**: shared, others, collaboration, received, access

## Category: Upload & Download

### upload_file
- **signature**: `upload_file(local_path, name="", folder_id=None, mime_type=None)`
- **description**: Upload a local file to Drive.
- **tags**: upload, add, push, send, transfer, import

### download_file
- **signature**: `download_file(file_id, local_path)`
- **description**: Download a Drive file to a local path.
- **tags**: download, get, pull, save, export, fetch

### backup_drive_to_local
- **signature**: `backup_drive_to_local(folder_id, output_dir, max_files=100)`
- **description**: Download all files from a Drive folder to a local directory. Google Docs/Sheets exported as PDF/XLSX.
- **tags**: backup, download, bulk, export, local, save all

### sync_local_folder_to_drive
- **signature**: `sync_local_folder_to_drive(local_path, drive_folder_id, dry_run=True)`
- **description**: Upload new or modified files from a local folder to Drive. Always dry_run=True first.
- **tags**: sync, upload, update, mirror, push, synchronize

## Category: File Operations

### create_folder
- **signature**: `create_folder(name, parent_id=None)`
- **description**: Create a new folder.
- **tags**: create, new, folder, directory, mkdir

### move_file
- **signature**: `move_file(file_id, folder_id)`
- **description**: Move a single file to a different folder.
- **tags**: move, relocate, transfer, organize

### copy_file
- **signature**: `copy_file(file_id, name="", folder_id=None)`
- **description**: Copy a single file.
- **tags**: copy, duplicate, clone

### trash_file
- **signature**: `trash_file(file_id)`
- **description**: Move a single file to Trash.
- **tags**: trash, delete, remove, discard

### restore_file
- **signature**: `restore_file(file_id)`
- **description**: Restore a trashed file.
- **tags**: restore, recover, undelete, untrash

### star_file
- **signature**: `star_file(file_id, starred=True)`
- **description**: Star or un-star a file.
- **tags**: star, favorite, bookmark, mark, important

### rename_file
- **signature**: `rename_file(file_id, new_name)`
- **description**: Rename a file in Drive.
- **tags**: rename, name, change

## Category: Batch Operations

### batch_move_files
- **signature**: `batch_move_files(file_ids, folder_id)`
- **description**: Move multiple files to a folder in one call. file_ids is a list of Drive file IDs.
- **tags**: batch, move, bulk, multiple, mass, organize

### batch_delete_files
- **signature**: `batch_delete_files(file_ids, permanent=False)`
- **description**: Trash (or permanently delete) multiple files at once.
- **tags**: batch, delete, bulk, multiple, mass, trash, cleanup

### batch_copy_files
- **signature**: `batch_copy_files(file_ids, folder_id="", name_suffix=" (copy)")`
- **description**: Copy multiple files, optionally to a destination folder.
- **tags**: batch, copy, bulk, multiple, duplicate, mass

## Category: Sharing & Permissions

### share_file
- **signature**: `share_file(file_id, email="", role="reader", make_public=False)`
- **description**: Share a file with a person (role: reader/commenter/writer) or make it publicly accessible.
- **tags**: share, permission, access, collaborate, public, link, invite

### manage_file_permissions
- **signature**: `manage_file_permissions(file_id, action, permission_id="", new_role="reader")`
- **description**: action: 'list' (show all), 'remove' (delete), 'update' (change role).
- **tags**: permissions, access, role, manage, control, security

### revoke_access_all
- **signature**: `revoke_access_all(file_id)`
- **description**: Remove ALL non-owner permissions from a file (make it completely private).
- **tags**: revoke, private, remove access, security, lock

### get_sharing_stats
- **signature**: `get_sharing_stats(file_id)`
- **description**: Show all permissions for a file: who has access, at what role, whether it is public.
- **tags**: sharing, stats, who, access, permissions, audit

## Category: Storage & Cleanup

### get_storage_quota
- **signature**: `get_storage_quota()`
- **description**: Return used/total/free Drive storage quota.
- **tags**: storage, quota, space, used, free, capacity

### find_large_files
- **signature**: `find_large_files(folder_id="root", min_size_mb=10.0, max_results=25)`
- **description**: Find the largest files in Drive. Use to diagnose storage issues.
- **tags**: large, big, size, storage, space, heavy, biggest

### find_drive_duplicates
- **signature**: `find_drive_duplicates(folder_id="root", max_results=200)`
- **description**: Find duplicate files in Drive by name+size fingerprint.
- **tags**: duplicate, same, identical, redundant, cleanup

### trash_drive_duplicates
- **signature**: `trash_drive_duplicates(folder_id="root", keep="newest")`
- **description**: Trash duplicates, keeping one copy per group. keep: 'newest' or 'oldest'.
- **tags**: duplicate, cleanup, trash, deduplicate, remove

### suggest_archival
- **signature**: `suggest_archival(folder_id="root", months_old=6, max_results=25)`
- **description**: Find files not modified in N months. Use for 'what can I archive?' or 'show stale files'.
- **tags**: archive, old, stale, inactive, unused, cleanup

## Category: Conversion & Versioning

### convert_document
- **signature**: `convert_document(file_id, output_format="pdf", save_path="")`
- **description**: Export a Google Docs/Sheets/Slides file to pdf/docx/xlsx/pptx/csv/txt/html.
- **tags**: convert, export, pdf, docx, xlsx, format, transform

### list_file_versions
- **signature**: `list_file_versions(file_id)`
- **description**: List all revision history for a Drive file.
- **tags**: version, history, revision, changes, track

### cleanup_old_versions
- **signature**: `cleanup_old_versions(file_id, keep_latest=3)`
- **description**: Delete old file revisions, keeping only the N most recent.
- **tags**: cleanup, version, old, revisions, prune

## Category: Context

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist the current Drive file listing for the next turn so the user can say "share the second one" without searching again. topic="drive_listing", resolved_entities={"listed_files":[...]}, awaiting="drive_file_action".
- **tags**: context, save, cross-turn, persist, session, follow-up
