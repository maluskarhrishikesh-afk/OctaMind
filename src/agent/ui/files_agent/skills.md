# Files Agent — Tool Skills

## Category: Browse & Inspect

### list_directory
- **signature**: `list_directory(path, show_hidden=False, limit=200)`
- **description**: List files in a local directory.
- **tags**: list, browse, folder, contents, directory, view, show

### get_file_info
- **signature**: `get_file_info(path)`
- **description**: Get metadata for a local file or folder.
- **tags**: info, metadata, size, date, type, details, properties

### open_file
- **signature**: `open_file(path)`
- **description**: Open a file with its default application.
- **tags**: open, launch, run, start, view, display

## Category: Search

### search_by_name
- **signature**: `search_by_name(query, directory="~", recursive=True, limit=50)`
- **description**: Search files/folders whose name matches query (glob or substring). First arg is the search term, second is the directory to search.
- **tags**: search, find, name, match, locate, query, lookup

### search_by_extension
- **signature**: `search_by_extension(ext, directory="~", recursive=True, limit=100)`
- **description**: Find all files with a given extension (e.g. 'pdf' or '.pdf').
- **tags**: extension, type, pdf, docx, jpg, png, filter, format

### search_by_date
- **signature**: `search_by_date(directory, date_from=None, date_to=None, recursive=True, limit=50)`
- **description**: Search by modification date.
- **tags**: date, modified, recent, old, when, time, before, after

### search_by_size
- **signature**: `search_by_size(directory, min_bytes=None, max_bytes=None, recursive=True, limit=50)`
- **description**: Search by file size.
- **tags**: size, large, small, big, bytes, megabytes, gigabytes, heavy

### search_file_all_drives
- **signature**: `search_file_all_drives(query, extensions=None, limit=20, include_folders=True)`
- **description**: Search ALL drives (C:, D:, …) for a file OR folder. query is a name/glob substring; use query="*" to match ALL files when filtering only by extension. extensions is an optional list e.g. ["pdf","docx"] to restrict file types. Set limit=500 for comprehensive counting queries. Returns file_path set to the first match. ALWAYS use this (not search_by_name/search_by_extension) when the user says "on my computer", "on my laptop" or gives no specific folder. ALWAYS use this before zip_folder when the folder path is unknown.
- **tags**: search, all drives, computer, laptop, global, find, locate, everywhere

### search_files_by_content
- **signature**: `search_files_by_content(query, directory="~", extensions=None, max_results=50, case_sensitive=False)`
- **description**: Grep-like search: find files whose content contains query text. extensions e.g. ['py','txt','md'].
- **tags**: content, grep, text, inside, contains, body, search within

### find_duplicates
- **signature**: `find_duplicates(directory, recursive=True)`
- **description**: Find duplicate files.
- **tags**: duplicate, same, identical, copy, redundant

### find_empty_folders
- **signature**: `find_empty_folders(directory, recursive=True)`
- **description**: Find empty folders.
- **tags**: empty, unused, clean, blank, no files

### find_duplicate_files
- **signature**: `find_duplicate_files(directory, recursive=True, min_size_bytes=1024)`
- **description**: Find duplicate files by MD5 hash. Returns groups and wasted space.
- **tags**: duplicate, hash, md5, wasted, space, identical

## Category: File Operations

### copy_file
- **signature**: `copy_file(source, destination)`
- **description**: Copy a file or folder.
- **tags**: copy, duplicate, clone, backup

### collect_files_to_folder
- **signature**: `collect_files_to_folder(file_paths, destination)`
- **description**: Copy a LIST of files/folders (from any locations) into a single destination folder, creating it if needed. Returns the destination folder path as file_path. Use BEFORE zip_folder when you have files scattered across multiple locations that need to be gathered first.
- **tags**: collect, gather, consolidate, combine, group, aggregate, multiple

### move_file
- **signature**: `move_file(source, destination)`
- **description**: Move / rename a file or folder.
- **tags**: move, relocate, transfer, cut, paste

### delete_file
- **signature**: `delete_file(path, permanent=False)`
- **description**: Delete a file (recycle bin by default).
- **tags**: delete, remove, trash, recycle, discard, erase

### create_folder
- **signature**: `create_folder(path)`
- **description**: Create a new directory.
- **tags**: create, new, folder, directory, mkdir

### rename_file
- **signature**: `rename_file(path, new_name)`
- **description**: Rename a file or folder.
- **tags**: rename, name, change name

### batch_rename
- **signature**: `batch_rename(directory, find, replace, dry_run=True, use_regex=False, extensions=None)`
- **description**: Rename files by replacing 'find' with 'replace' in filenames. ALWAYS dry_run=True first to show plan.
- **tags**: batch, rename, bulk, mass, replace, pattern, regex

### secure_delete
- **signature**: `secure_delete(path, passes=3)`
- **description**: Overwrite file with random bytes N times before deleting. Use for sensitive files.
- **tags**: secure, shred, wipe, permanent, sensitive, privacy

## Category: Archives & Compression

### zip_folder
- **signature**: `zip_folder(folder_path, output_path="")`
- **description**: Zip an entire folder into a .zip archive. output_path defaults to same location as folder with .zip extension.
- **tags**: zip, compress, archive, folder, bundle

### zip_files
- **signature**: `zip_files(sources, output_path)`
- **description**: Zip one or more files and/or folders into a single archive. sources is a list of paths.
- **tags**: zip, compress, archive, multiple, bundle, pack

### unzip_file
- **signature**: `unzip_file(archive_path, destination="")`
- **description**: Extract a zip archive. destination defaults to a folder named after the archive.
- **tags**: unzip, extract, decompress, unarchive, unpack

### list_archive_contents
- **signature**: `list_archive_contents(archive_path)`
- **description**: List contents of a zip archive without extracting.
- **tags**: archive, contents, list, preview, inspect, zip

## Category: Write & Report

### write_text_file
- **signature**: `write_text_file(path, content)`
- **description**: Write text content to a local file (creates or overwrites it). Use when the user says "write this in a notepad", "save this as text", or similar.
- **tags**: write, text, save, notepad, create, output, txt

### write_pdf_report
- **signature**: `write_pdf_report(path, title, content)`
- **description**: Generate a formatted PDF report. Falls back to .txt if fpdf2 is not installed. Use for polished multi-page reports.
- **tags**: pdf, report, document, generate, formatted, polished, write

### write_excel_report
- **signature**: `write_excel_report(path, sheet_data, title="")`
- **description**: Generate an Excel .xlsx workbook. sheet_data is a dict mapping sheet_name → list-of-dicts. Use when the user asks for data in a spreadsheet or Excel format.
- **tags**: excel, spreadsheet, xlsx, table, data, workbook, write

### deliver_file
- **signature**: `deliver_file(path)`
- **description**: Send a single file to the user as a download (Telegram document / Dashboard button). ONLY call when the user EXPLICITLY requests to receive a file ('send it', 'download this', 'give me the file', 'deliver it', 'show me the file'). For MULTIPLE files: collect → zip_files() → deliver_file() the zip ONCE.
- **tags**: deliver, send, download, share, give, transfer, receive

## Category: Organization & Cleanup

### organize_folder
- **signature**: `organize_folder(directory, by="extension", dry_run=True, include_hidden=False)`
- **description**: Organise files in a folder into sub-folders. by options: "extension" (PDF/, Images/, etc.), "date" (year-month), "name" (A-Z), "size" (Small/Medium/Large). ALWAYS call with dry_run=True first to show the user the plan, then call again with dry_run=False to apply.
- **tags**: organize, sort, arrange, categorize, group, tidy, clean

### cleanup_temp_files
- **signature**: `cleanup_temp_files(dry_run=True)`
- **description**: Remove OS temp files, Windows Update cache, Python __pycache__. ALWAYS dry_run=True first to show what will be removed.
- **tags**: cleanup, temp, temporary, cache, junk, clear, free space

### cleanup_app_caches
- **signature**: `cleanup_app_caches(dry_run=True)`
- **description**: Remove Chrome/Edge/Firefox browser caches and Windows AppData temp files. ALWAYS dry_run=True first to show sizes, then dry_run=False to delete.
- **tags**: cache, browser, chrome, edge, firefox, cleanup, clear

### archive_old_files
- **signature**: `archive_old_files(folder, months_old=6, output_zip="", dry_run=True)`
- **description**: Compress files not modified in N months into a zip. dry_run=True first to preview.
- **tags**: archive, old, stale, compress, age, months, inactive

## Category: Disk & System

### analyze_disk_usage
- **signature**: `analyze_disk_usage(path, depth=2, top_n=20)`
- **description**: Recursively compute folder sizes and show biggest space consumers. Use when user asks 'what's taking up space' or 'show disk usage'.
- **tags**: disk, usage, space, size, largest, biggest, storage, analyze

### get_drive_info
- **signature**: `get_drive_info()`
- **description**: Return total/used/free space for all local drives (C:, D:, etc.).
- **tags**: drive, storage, space, free, total, used, capacity

### list_laptop_structure
- **signature**: `list_laptop_structure(include_hidden=False, output_file="", depth=2)`
- **description**: DETERMINISTIC full-laptop scan: discovers all available drives (C:, D:, …) and lists every drive root plus the major user directories (Home, Downloads, Desktop, Documents, Pictures, Music, Videos). Always writes a report .txt file automatically. Use this whenever the user asks about ALL folders/files on their laptop.
- **tags**: laptop, structure, scan, all, drives, overview, tree, full

### list_running_apps
- **signature**: `list_running_apps()`
- **description**: List all running processes with PID, name, memory usage, and CPU percentage.
- **tags**: processes, running, apps, memory, cpu, task manager

### resolve_shortcut
- **signature**: `resolve_shortcut(lnk_path)`
- **description**: Resolve a Windows .lnk shortcut file to its target executable or folder path.
- **tags**: shortcut, lnk, resolve, target, link

### get_file_hash
- **signature**: `get_file_hash(file_path, algorithm="md5")`
- **description**: Compute MD5/SHA256/SHA1 hash of a file for integrity checking or duplicate detection.
- **tags**: hash, md5, sha256, checksum, integrity, verify

### monitor_folder
- **signature**: `monitor_folder(path, timeout_seconds=30, poll_interval=1.0)`
- **description**: Watch a folder for file changes (created/modified/deleted) for up to N seconds.
- **tags**: monitor, watch, changes, new files, real-time, track

## Category: Context & Manifest

### save_search_manifest
- **signature**: `save_search_manifest(found_paths, manifest_path="")`
- **description**: Persist a list of found file paths to data/octa_manifest.txt (one path per line). Call this IMMEDIATELY after any search step so the paths survive across turns.
- **tags**: save, manifest, persist, paths, results, cross-turn

### collect_files_from_manifest
- **signature**: `collect_files_from_manifest(manifest_path="", destination="")`
- **description**: Read the manifest file written by save_search_manifest and copy EVERY listed file to destination. Use this instead of collect_files_to_folder when copying files from a previous search turn.
- **tags**: collect, manifest, copy, previous, gather, restore

### undo_last_file_operation
- **signature**: `undo_last_file_operation()`
- **description**: Undo the most-recent copy/collect operation by deleting the destination folder that was created. Call this when the user says 'undo', 'revert that', 'undo the copy'.
- **tags**: undo, revert, rollback, cancel, take back

### list_file_operations
- **signature**: `list_file_operations(days=30)`
- **description**: Return the file-operation audit history for the last N days (newest-first). Each entry has: type, destination, count, timestamp, undone.
- **tags**: history, audit, log, operations, recent, track

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist the current file listing as cross-turn context. topic="file_search", resolved_entities={"listed_files":[...], "query":"..."}, awaiting="file_action". Call AFTER every search so the user can say 'copy them' next turn.
- **tags**: context, save, cross-turn, persist, session, follow-up
