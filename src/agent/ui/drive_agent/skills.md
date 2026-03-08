# Drive Agent — Tool Skills

## Category: Browse & Search

### list_files
- **signature**: `list_files(query="", max_results=20, folder_id="root")`
- **description**: Browse and list files in Google Drive, optionally filtered by a search query or restricted to a specific folder. Use when the user says "show me my Drive files", "list files in Drive", "what's in my Google Drive", "browse Drive folder X", "show root Drive contents", "list everything in my Drive", "what files are in Drive folder Y", "browse my Google Drive", "show me what's in Drive". Returns file names, types, sizes, and modification dates.
- **tags**: list, browse, view, folder, contents, drive, show drive, what's in drive, browse drive, google drive files

### search_files
- **signature**: `search_files(name="", file_type="", max_results=10)`
- **description**: Search for specific files in Google Drive by name and/or file type. Use when the user says "find file X in Drive", "search Drive for document Y", "is there a spreadsheet named X in Drive", "look for PDF called Y in Drive", "find my presentation about Z", "search Google Drive for X", "locate Drive file Y", "do I have a file called X in Drive". file_type options: "spreadsheet", "document", "presentation", "pdf", "folder", "image".
- **tags**: search, find, name, type, locate, query, find in drive, search google drive, locate file drive

### get_file_info
- **signature**: `get_file_info(file_id)`
- **description**: Return detailed metadata for a specific Drive file: name, type, size, owner, creation date, modification date, sharing settings, and parent folder. Use when the user says "get details of Drive file X", "show Drive file properties", "who owns file X in Drive", "when was Drive file Y created", "what type is this Drive file", "info on Drive document X".
- **tags**: info, metadata, details, properties, file, drive file info, who owns, creation date

### list_shared_with_me
- **signature**: `list_shared_with_me(max_results=20)`
- **description**: List all files and folders that other people have shared with you in Google Drive. Use when the user says "show files shared with me", "what has been shared with me in Drive", "files others shared to me", "see shared files", "what Drive files can I access from others", "show collaboration files shared with me", "received Drive shares".
- **tags**: shared, others, collaboration, received, access, shared with me, drive shares, other people shared

---

## Category: Upload & Download

### upload_file
- **signature**: `upload_file(local_path, name="", folder_id=None, mime_type=None)`
- **description**: Upload a file from your computer to Google Drive. Use when the user says "upload file X to Drive", "add local file to Google Drive", "send this file to Drive", "upload the PDF to Drive", "push my local file to Drive", "import file X into Google Drive", "save file to Drive". Optionally specify a destination folder_id.
- **tags**: upload, add, push, send, transfer, import, upload to drive, add to drive, save to drive

### download_file
- **signature**: `download_file(file_id, local_path)`
- **description**: Download a file from Google Drive to a local path on your computer. Use when the user says "download Drive file X", "save Drive file Y to my computer", "get file X from Drive", "pull Drive document Y to local folder", "download the spreadsheet from Drive to Z", "export Drive file to my PC".
- **tags**: download, get, pull, save, export, fetch, download from drive, save locally, drive to local

### backup_drive_to_local
- **signature**: `backup_drive_to_local(folder_id, output_dir, max_files=100)`
- **description**: Download all files from a Google Drive folder to a local directory as a bulk backup. Google Docs/Sheets/Slides are automatically exported as PDF/XLSX/PPTX. Use when the user says "backup Drive folder X to my computer", "download everything in Drive folder Y", "bulk download Drive folder", "save all Drive files locally", "export entire Drive folder to PC", "local backup of Drive folder X".
- **tags**: backup, download, bulk, export, local, save all, backup drive, download entire folder, bulk export

### sync_local_folder_to_drive
- **signature**: `sync_local_folder_to_drive(local_path, drive_folder_id, dry_run=True)`
- **description**: Upload new or recently modified files from a local folder to a Google Drive folder (one-way sync). Use when the user says "sync my local Projects folder to Drive", "push local changes to Drive", "upload modified files to Drive folder", "mirror local folder to Google Drive", "keep Drive folder in sync with local X". ALWAYS call with dry_run=True first to preview what will be uploaded.
- **tags**: sync, upload, update, mirror, push, synchronize, sync to drive, local to drive, keep in sync

---

## Category: File Operations

### create_folder
- **signature**: `create_folder(name, parent_id=None)`
- **description**: Create a new folder in Google Drive, optionally inside a parent folder. Use when the user says "create a Drive folder called X", "make a new folder in Drive named Y", "add folder Z to my Google Drive", "create directory X in Drive", "I need a new Drive folder called X", "set up a folder in Drive for project Y".
- **tags**: create, new, folder, directory, mkdir, create drive folder, new drive folder, add folder

### move_file
- **signature**: `move_file(file_id, folder_id)`
- **description**: Move a file from its current location to a different folder in Google Drive. Use when the user says "move Drive file X to folder Y", "transfer Drive document to folder Z", "put Drive file X in folder Y", "relocate Drive file X to Y", "move the spreadsheet to the Project folder in Drive".
- **tags**: move, relocate, transfer, organize, move in drive, move to folder drive

### copy_file
- **signature**: `copy_file(file_id, name="", folder_id=None)`
- **description**: Create a copy of a Google Drive file, optionally with a new name and in a different folder. Use when the user says "copy Drive file X", "duplicate Drive document Y", "make a copy of spreadsheet X in Drive", "clone Drive file X to folder Y", "I want a duplicate of Drive file Z".
- **tags**: copy, duplicate, clone, make copy, copy drive file

### trash_file
- **signature**: `trash_file(file_id)`
- **description**: Move a Google Drive file or folder to the Drive Trash. Use when the user says "delete Drive file X", "trash Drive document Y", "remove Drive file Z", "send Drive file X to trash", "discard Drive file Y". Files remain in Trash for 30 days before permanent deletion.
- **tags**: trash, delete, remove, discard, trash drive file, delete from drive, remove from drive

### restore_file
- **signature**: `restore_file(file_id)`
- **description**: Restore a trashed Google Drive file back to its original location. Use when the user says "restore deleted Drive file X", "recover Drive file from trash", "undelete Drive file Y", "bring back Drive file X", "recover accidentally deleted Drive document", "restore from Drive trash".
- **tags**: restore, recover, undelete, untrash, recover drive file, restore from trash

### star_file
- **signature**: `star_file(file_id, starred=True)`
- **description**: Star (or un-star) a Google Drive file to mark it as important or a favourite. Use when the user says "star Drive file X", "mark file Y as important in Drive", "favourite Drive document X", "remove star from Drive file Y", "un-star Drive file Z", "mark as important in Drive".
- **tags**: star, favorite, bookmark, mark, important, star drive file, mark important, favourite

### rename_file
- **signature**: `rename_file(file_id, new_name)`
- **description**: Rename a file or folder in Google Drive. Use when the user says "rename Drive file X to Y", "change the name of Drive document X to Y", "rename the Drive spreadsheet to Z", "call Drive file X something else", "update Drive file name to Y".
- **tags**: rename, name, change, rename drive file, change drive file name

---

## Category: Batch Operations

### batch_move_files
- **signature**: `batch_move_files(file_ids, folder_id)`
- **description**: Move multiple files at once to a single destination folder in Google Drive. Use when the user says "move all these Drive files to folder Y", "bulk move Files A, B, C to folder Z", "organize multiple Drive files into one folder", "mass move Drive files to X", "move these files to the Project folder in Drive".
- **tags**: batch, move, bulk, multiple, mass, organize, bulk move drive, move many files drive

### batch_delete_files
- **signature**: `batch_delete_files(file_ids, permanent=False)`
- **description**: Trash or permanently delete multiple Google Drive files at once. Use when the user says "delete these Drive files", "bulk delete files from Drive", "trash multiple Drive files at once", "remove files A B C from Drive", "mass delete Drive files", "clean up multiple Drive files". Set permanent=True only when user explicitly wants permanent deletion.
- **tags**: batch, delete, bulk, multiple, mass, trash, cleanup, bulk delete drive, remove many files

### batch_copy_files
- **signature**: `batch_copy_files(file_ids, folder_id="", name_suffix=" (copy)")`
- **description**: Copy multiple Google Drive files at once, optionally to a destination folder with a name suffix. Use when the user says "copy all these Drive files", "bulk duplicate Drive files to folder Y", "mass copy files in Drive", "copy multiple Drive documents to folder Z".
- **tags**: batch, copy, bulk, multiple, duplicate, mass, bulk copy drive, copy multiple

---

## Category: Sharing & Permissions

### share_file
- **signature**: `share_file(file_id, email="", role="reader", make_public=False)`
- **description**: Share a Google Drive file with a specific person by email or make it publicly accessible via link. Roles: "reader" (view only), "commenter" (can comment), "writer" (can edit). Use when the user says "share Drive file X with Y@email.com", "give X edit access to Drive file Y", "make Drive document Z public", "share the spreadsheet with my colleague", "give view access to Drive file X", "share Drive file with the team", "make this Drive file accessible to anyone".
- **tags**: share, permission, access, collaborate, public, link, invite, share with, give access, edit access, view access, public link

### manage_file_permissions
- **signature**: `manage_file_permissions(file_id, action, permission_id="", new_role="reader")`
- **description**: View, update, or remove specific permissions on a Google Drive file. action: "list" (show all who have access), "remove" (revoke access for one person), "update" (change someone's role). Use when the user says "show who has access to Drive file X", "remove X's access to Drive file Y", "change X's permission on Drive file Z to reader", "who can see Drive file X", "update permissions on Drive document".
- **tags**: permissions, access, role, manage, control, security, who has access, view permissions, update role

### revoke_access_all
- **signature**: `revoke_access_all(file_id)`
- **description**: Remove ALL non-owner permissions from a Google Drive file, making it completely private and accessible only to the owner. Use when the user says "make Drive file X completely private", "revoke all access to Drive file Y", "remove everyone's access from Drive document Z", "lock down Drive file X", "stop sharing Drive file Y with everyone", "make it private again".
- **tags**: revoke, private, remove access, security, lock, completely private, stop sharing all, restrict access

### get_sharing_stats
- **signature**: `get_sharing_stats(file_id)`
- **description**: Show a full permissions audit for a Google Drive file: who has access, at what role, whether it is public, and the share link if any. Use when the user says "who can access Drive file X", "show sharing details for Drive document Y", "is Drive file X public", "audit sharing on Drive file Y", "sharing status of Drive document Z", "check if Drive file is shared publicly".
- **tags**: sharing, stats, who, access, permissions, audit, who can see, public check, sharing status

---

## Category: Storage & Cleanup

### get_storage_quota
- **signature**: `get_storage_quota()`
- **description**: Return how much Google Drive storage is used, free, and total across the account. Use when the user says "how much Drive storage do I have", "check Google Drive quota", "how full is my Drive", "how much space left in Drive", "Drive storage usage", "am I running out of Drive space", "Drive capacity remaining", "storage breakdown for Google Drive".
- **tags**: storage, quota, space, used, free, capacity, drive storage, how much space drive, google drive quota

### find_large_files
- **signature**: `find_large_files(folder_id="root", min_size_mb=10.0, max_results=25)`
- **description**: Find the largest files in Google Drive sorted by size, useful for diagnosing storage usage. Use when the user says "what large files are in my Drive", "find big files in Drive", "show biggest Drive files", "what is taking space in my Drive", "files over 100MB in Drive", "Drive storage hogs", "largest files in Google Drive", "what's using up my Drive storage".
- **tags**: large, big, size, storage, space, heavy, biggest, drive storage hogs, large drive files, biggest files drive

### find_drive_duplicates
- **signature**: `find_drive_duplicates(folder_id="root", max_results=200)`
- **description**: Find duplicate files in Google Drive by comparing file name and size. Use when the user says "find duplicate files in Drive", "are there duplicates in my Google Drive", "find copies of files in Drive", "clean up duplicate Drive files", "identical files in Google Drive", "wasteful duplicates in Drive".
- **tags**: duplicate, same, identical, redundant, cleanup, find duplicates drive, duplicate files, drive cleanup

### trash_drive_duplicates
- **signature**: `trash_drive_duplicates(folder_id="root", keep="newest")`
- **description**: Automatically trash duplicate files in Google Drive, keeping one copy per group based on newest or oldest. Use when the user says "delete duplicate files in Drive", "clean up Drive duplicates automatically", "trash drive duplicates keep newest", "remove redundant Drive files", "deduplicate my Google Drive", "clean Drive by removing copies". keep: "newest" or "oldest".
- **tags**: duplicate, cleanup, trash, deduplicate, remove, auto clean drive, remove duplicate drive files

### suggest_archival
- **signature**: `suggest_archival(folder_id="root", months_old=6, max_results=25)`
- **description**: Find Google Drive files that haven't been modified in N months — candidates for archiving or deletion. Use when the user says "what Drive files can I archive", "show stale Drive files", "which Drive files haven't been used in 6 months", "old inactive Drive files", "what should I clean up in Drive", "files not touched in a year in Drive", "find unused Drive files".
- **tags**: archive, old, stale, inactive, unused, cleanup, archival candidates, old drive files, not modified

---

## Category: Conversion & Versioning

### convert_document
- **signature**: `convert_document(file_id, output_format="pdf", save_path="")`
- **description**: Export a Google Docs, Sheets, or Slides file to a downloadable format. Output formats: "pdf", "docx", "xlsx", "pptx", "csv", "txt", "html". Use when the user says "export Drive document to PDF", "convert Drive spreadsheet to Excel", "download Drive presentation as PPTX", "save Drive doc as Word file", "convert Google Doc to PDF", "export Sheet as CSV", "turn Drive file into docx".
- **tags**: convert, export, pdf, docx, xlsx, format, transform, export drive, google doc to pdf, sheet to excel

### list_file_versions
- **signature**: `list_file_versions(file_id)`
- **description**: List all revision history entries for a Google Drive file, showing who made changes and when. Use when the user says "show version history of Drive file X", "list revisions of Drive document Y", "who edited Drive file X and when", "show Drive file change history", "view Drive document revisions", "track changes in Drive file".
- **tags**: version, history, revision, changes, track, drive version history, file revisions, edit history

### cleanup_old_versions
- **signature**: `cleanup_old_versions(file_id, keep_latest=3)`
- **description**: Delete old revision history for a Drive file, keeping only the N most recent versions to free up storage. Use when the user says "clean up old versions of Drive file X", "delete old revisions of Drive document Y", "keep only last 3 versions of Drive file X", "prune Drive file history", "remove old file revisions from Drive".
- **tags**: cleanup, version, old, revisions, prune, delete old versions drive, remove revision history

---

## Category: Context

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist the current Drive file listing as cross-turn context so the user can reference files in the next message without repeating the search. Call after listing Drive files so subsequent turns support "share the second one", "download that file", "trash the first one". topic="drive_listing", resolved_entities={"listed_files":[...]}, awaiting="drive_file_action".
- **tags**: context, save, cross-turn, persist, session, follow-up, remember drive files, refer to files next turn
