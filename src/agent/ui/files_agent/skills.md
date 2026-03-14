# Files Agent — Tool Skills

## Category: Browse & Inspect

### list_directory
- **signature**: `list_directory(path, show_hidden=False, limit=200)`
- **description**: Browse and list everything inside a specific folder: all files and subfolders with their names, sizes, types, and modification dates. Use when the user wants to see what is inside a directory, browse folder contents, view all items in Downloads/Desktop/Documents, see all files in a location, "show me what's in the folder", "what files are in my Downloads", "list everything in C:/Projects", "what's inside the folder", "show contents of directory X". Returns folders first then files alphabetically.
- **tags**: list, browse, folder, contents, directory, view, show, what is in, inside, items, what's in folder, show contents

### get_file_info
- **signature**: `get_file_info(path)`
- **description**: Get detailed metadata for a specific file or folder: size, creation date, modification date, type, permissions, and full resolved path. Use when the user asks about a specific file's properties: "what is the size of file X", "when was X created", "when was X last modified", "is X a file or folder", "details about file X", "get info on document Y", "how big is X", "file properties of X".
- **tags**: info, metadata, size, date, type, details, properties, created, modified, when, how big, file properties

### open_file
- **signature**: `open_file(path)`
- **description**: Open a file with its default application (same as double-clicking it). Use when the user says "open the file", "launch X", "open document X", "view the file in its app", "open the PDF", "open this spreadsheet", "start the application for X".
- **tags**: open, launch, run, start, view, display, open file, open document

---

## Category: Search

### search_by_name
- **signature**: `search_by_name(query, directory="~", recursive=True, limit=50)`
- **description**: Check if a specific file or folder named X exists inside a directory and locate it. Use when the user asks "is there a folder named X in Downloads?", "do I have a file called X?", "find a folder named X", "is there a file named X on my computer?", "check if X exists in Y", "does folder X exist in Downloads?", "locate file X in Documents", "find file named report.pdf", "is there a Text folder in Downloads". The query is the exact file/folder name, directory is where to search.
- **tags**: search, find, exists, check, name, locate, is there, folder named, file named, does it exist, present, find named, locate file

### search_by_extension
- **signature**: `search_by_extension(ext, directory="~", recursive=True, limit=100)`
- **description**: Find all files of a specific type by their file extension. Use when the user asks "find all PDF files in Downloads", "show me all my Word documents", "list all images on my computer", "find all .docx files", "where are my Excel spreadsheets", "how many PDFs do I have", "find all Python files", "show me all mp3 files", "list all CSV files in Documents".
- **tags**: extension, type, pdf, docx, jpg, png, filter, format, file type, find all, how many, word docs, excel, images, mp3, csv

### search_by_date
- **signature**: `search_by_date(directory, date_from=None, date_to=None, recursive=True, limit=50)`
- **description**: Find files modified or created within a specific date range. Use when the user asks "show files I worked on this week", "find recently modified files", "files changed in the last month", "files modified yesterday", "documents created before March 2025", "what did I edit recently", "files from last Tuesday", "anything new in Downloads today", "files modified in the past 7 days".
- **tags**: date, modified, recent, old, when, time, before, after, last week, yesterday, this month, recently, files from, worked on

### search_by_size
- **signature**: `search_by_size(directory, min_bytes=None, max_bytes=None, recursive=True, limit=50)`
- **description**: Find files within a specific size range. Use when the user asks "find large files over 100MB", "show files bigger than 1GB", "find small files under 1KB", "what are the biggest files in Downloads", "find heavy files taking space", "files larger than 500MB in Documents".
- **tags**: size, large, small, big, bytes, megabytes, gigabytes, heavy, over 100MB, bigger than, smaller than

### search_file_all_drives
- **signature**: `search_file_all_drives(query, extensions=None, limit=20, include_folders=True)`
- **description**: Search ALL drives (C:, D:, external drives) for a file or folder anywhere on the entire computer. ALWAYS use this when the user says "find X on my computer", "search my whole laptop for X", "is X anywhere on my PC", "look everywhere for file X", "search my entire system for Y", "find the file on any drive". query is a name or glob pattern; extensions optionally filters by type (e.g. ["pdf","docx"]). Use limit=500 for "how many" counting queries.
- **tags**: search, all drives, computer, laptop, global, find, locate, everywhere, entire system, whole computer, any drive, all of PC

### search_files_by_content
- **signature**: `search_files_by_content(query, directory="~", extensions=None, max_results=50, case_sensitive=False)`
- **description**: Search inside file contents to find files that contain specific text (like grep). Use when the user says "find files that contain the word X", "which file mentions Y", "search inside files for text Z", "grep for term X in my documents", "find documents containing phrase Y", "which Python file has function X", "files that mention the project name". Extensions like ['py','txt','md'] narrow the search.
- **tags**: content, grep, text, inside, contains, body, search within, find files containing, which file mentions

### find_duplicates
- **signature**: `find_duplicates(directory, recursive=True)`
- **description**: Find duplicate files in a folder. Use when the user asks "are there any duplicate files", "find copies of files", "which files are duplicated", "clean up duplicates in Downloads".
- **tags**: duplicate, same, identical, copy, redundant, find copies

### find_empty_folders
- **signature**: `find_empty_folders(directory, recursive=True)`
- **description**: Find all empty folders with no files in them. Use when the user says "find empty folders", "show me empty directories", "which folders have nothing in them", "clean up empty folders", "any empty directories to delete".
- **tags**: empty, unused, clean, blank, no files, empty folders, empty directories

### find_duplicate_files
- **signature**: `find_duplicate_files(directory, recursive=True, min_size_bytes=1024)`
- **description**: Find duplicate files using MD5 hash comparison — guarantees truly identical content. Returns duplicate groups with wasted space totals. Use when the user says "find exact duplicate files", "find truly identical files", "how much space is wasted on duplicates", "deduplicate Downloads folder", "find files with same content".
- **tags**: duplicate, hash, md5, wasted, space, identical, true duplicate, same content, deduplicate

---

## Category: File Operations

### copy_file
- **signature**: `copy_file(source, destination)`
- **description**: Copy a file or folder to a new location while keeping the original. Use when the user says "copy file X to folder Y", "duplicate X to Z", "make a copy of X in Y", "backup file X to Z", "copy the folder to another location". Both source and destination are full paths.
- **tags**: copy, duplicate, clone, backup, make a copy, copy to

### collect_files_to_folder
- **signature**: `collect_files_to_folder(file_paths, destination)`
- **description**: Copy a list of files from any multiple locations into a single destination folder, creating the destination if needed. Use when the user says "gather all these files into one folder", "collect files from different places to X", "consolidate files into a single folder", "combine results into one directory", "group these files together in Y". Use BEFORE zip_folder when files are scattered.
- **tags**: collect, gather, consolidate, combine, group, aggregate, multiple, gather files, consolidate into folder

### move_file
- **signature**: `move_file(source, destination)`
- **description**: Move or rename a file or folder to a new location. Use when the user says "move file X to folder Y", "relocate X to Z", "transfer the file to Y", "rename file X to Y", "move the folder to Z", "cut and paste X to Y". Can rename by moving to same directory with different name.
- **tags**: move, relocate, transfer, cut, paste, rename, rename by moving

### delete_file
- **signature**: `delete_file(path, permanent=False)`
- **description**: Delete a file or folder (sends to Recycle Bin by default; set permanent=True to skip Recycle Bin). Use when the user says "delete file X", "remove folder Y", "trash file X", "put X in recycle bin", "permanently delete X", "erase file X", "get rid of folder Y". Always use permanent=False unless user explicitly says permanent delete.
- **tags**: delete, remove, trash, recycle, discard, erase, put in bin, permanently delete

### create_folder
- **signature**: `create_folder(path)`
- **description**: Create a new directory (folder) at the specified path. Use when the user says "create a new folder named X", "make a directory at Y", "create folder X in Downloads", "set up a new directory", "mkdir X in Z", "I need a folder called X at Y".
- **tags**: create, new, folder, directory, mkdir, make folder, new directory

### rename_file
- **signature**: `rename_file(path, new_name)`
- **description**: Rename a file or folder in place. Use when the user says "rename file X to Y", "change the name of folder X to Y", "rename document X", "call this file Y instead", "give this folder a new name". The new_name is just the name without the path.
- **tags**: rename, name, change name, give new name, rename file

### batch_rename
- **signature**: `batch_rename(directory, find, replace, dry_run=True, use_regex=False, extensions=None)`
- **description**: Bulk rename multiple files at once by replacing a pattern in their filenames. Use when the user says "rename all files replacing X with Y", "bulk rename files in folder Z", "replace old name with new name in all files", "mass rename files matching pattern X", "rename all PDFs removing prefix X". ALWAYS call with dry_run=True first to preview changes, then dry_run=False to apply.
- **tags**: batch, rename, bulk, mass, replace, pattern, regex, multiple rename, all files rename

### secure_delete
- **signature**: `secure_delete(path, passes=3)`
- **description**: Securely erase a file by overwriting with random bytes N times before deleting, making recovery impossible. Use when the user says "securely delete X", "shred file X", "wipe the file permanently", "delete sensitive file X so it can't be recovered", "destroy file X", "securely erase private document". For sensitive financial or personal files.
- **tags**: secure, shred, wipe, permanent, sensitive, privacy, destroy, can't recover, private document

---

## Category: Archives & Compression

### zip_folder
- **signature**: `zip_folder(folder_path, output_path="")`
- **description**: Compress an entire folder into a single .zip archive file. Use when the user says "zip the folder X", "compress folder Y into a zip", "archive folder X", "create a zip of folder Y", "bundle folder X into zip", "make a zip archive of directory X". output_path defaults to same location as folder.
- **tags**: zip, compress, archive, folder, bundle, create zip, compress folder

### zip_files
- **signature**: `zip_files(sources, output_path)`
- **description**: Create a .zip archive from one or more individual files or folders. Use when the user says "zip these files together", "create a zip with files X Y Z", "compress multiple files into one archive", "bundle these files as a zip", "pack these documents into a zip file". sources is a list of file paths.
- **tags**: zip, compress, archive, multiple, bundle, pack, zip files, create archive

### zip_files_from_manifest
- **signature**: `zip_files_from_manifest(manifest_path="", output_path="")`
- **description**: Read the saved search manifest and zip EXACTLY the file paths from the previous search. Use for follow-up requests like "zip them", "archive those results", or "send the files you found as a zip". This is preferred over `zip_folder` when the previous search matched only a subset of files inside a folder.
- **tags**: zip manifest, zip previous search, zip exact results, archive found files, zip them, zip those

### unzip_file
- **signature**: `unzip_file(archive_path, destination="")`
- **description**: Extract / decompress a .zip archive to a folder. Use when the user says "unzip file X", "extract the archive", "decompress X to folder Y", "unzip and extract to Z", "extract contents of zip X", "open the zip file". Destination defaults to a folder named after the archive.
- **tags**: unzip, extract, decompress, unarchive, unpack, open zip, extract archive

### list_archive_contents
- **signature**: `list_archive_contents(archive_path)`
- **description**: Preview what is inside a .zip archive without extracting it. Use when the user says "what's inside the zip file", "list contents of archive X", "show files in zip without extracting", "preview archive X", "what does the zip contain", "inspect the archive".
- **tags**: archive, contents, list, preview, inspect, zip, what's in zip, show archive contents

---

## Category: Write & Report

### write_text_file
- **signature**: `write_text_file(path, content)`
- **description**: Write plain text or Markdown content to a local file, creating or overwriting it. Use when the user says "write this note to a file", "save this text as a file", "create a text file with this content", "write to notepad", "save to a .txt file", "create a markdown file", "write this to a file called X".
- **tags**: write, text, save, notepad, create, output, txt, plain text, save to file, text file

### write_pdf_report
- **signature**: `write_pdf_report(path, title, content)`
- **description**: Generate a formatted PDF report file with title and structured content sections. Use when the user asks for a polished multi-page report as a PDF: "generate a PDF report", "create a PDF of this", "write a formatted PDF", "save this as a PDF report", "make a PDF document called X". Falls back to .txt if fpdf2 is not installed.
- **tags**: pdf, report, document, generate, formatted, polished, write, create pdf, pdf report

### write_excel_report
- **signature**: `write_excel_report(path, sheet_data, title="")`
- **description**: Generate an Excel .xlsx workbook with one or more sheets. Use when the user says "create an Excel spreadsheet", "save this as Excel", "write this data to a spreadsheet", "generate an xlsx file", "export data to Excel", "make an Excel workbook with sheets". sheet_data maps sheet names to lists of row-dicts.
- **tags**: excel, spreadsheet, xlsx, table, data, workbook, write, create excel, export to excel

### deliver_file
- **signature**: `deliver_file(path)`
- **description**: Send a locally generated file to the user as a downloadable file via Telegram document or dashboard download button. ONLY call AFTER write_pdf_report, write_text_file or zip_files has created the file. Use when the user says "send me the file", "download this", "give me the zip", "deliver the report", "I want to download it", "share the file". For MULTIPLE files: collect → zip_files() → deliver_file() the zip once.
- **tags**: deliver, send, download, share, give, transfer, receive, download file, send to me

---

## Category: Organization & Cleanup

### organize_folder
- **signature**: `organize_folder(directory, by="extension", dry_run=True, include_hidden=False)`
- **description**: Automatically organize all files in a folder into sub-folders by a chosen scheme. Options: "extension" (groups into PDF/, Images/, Documents/ etc.), "date" (groups by year-month), "name" (alphabetical A-Z), "size" (Small/Medium/Large). Use when user says "organize my Downloads folder", "sort files by type", "tidy up folder X", "clean up Downloads into categories", "sort files by date", "put files into folders by extension". ALWAYS call dry_run=True first to preview the plan.
- **tags**: organize, sort, arrange, categorize, group, tidy, clean, sort by type, organize downloads, clean up folder

### cleanup_temp_files
- **signature**: `cleanup_temp_files(dry_run=True)`
- **description**: Remove OS temporary files, Windows Update cache leftovers, and Python __pycache__ directories to free up disk space. Use when the user says "clean up temp files", "free up disk space", "remove junk files", "delete temporary files", "clear system cache", "clean up Windows temp", "delete pycache", "free up storage". ALWAYS dry_run=True first.
- **tags**: cleanup, temp, temporary, cache, junk, clear, free space, remove temp, delete temp, system cleanup

### cleanup_app_caches
- **signature**: `cleanup_app_caches(dry_run=True)`
- **description**: Remove Chrome, Edge, and Firefox browser caches plus Windows AppData temp files to reclaim disk space. Use when the user says "clear browser cache", "clean up Chrome cache", "remove browser data", "free up storage from browsers", "delete Edge cache", "clean AppData temp folder", "free space from browser junk". ALWAYS dry_run=True first.
- **tags**: cache, browser, chrome, edge, firefox, cleanup, clear, browser cache, appdata, clear cache

### archive_old_files
- **signature**: `archive_old_files(folder, months_old=6, output_zip="", dry_run=True)`
- **description**: Compress files not modified in the last N months into a zip archive and optionally remove originals. Use when the user says "archive old files in Downloads", "compress files I haven't used in 6 months", "zip up stale files", "archive files older than a year in Documents", "move old files to an archive zip". ALWAYS dry_run=True first.
- **tags**: archive, old, stale, compress, age, months, inactive, archive old, zip old files

---

## Category: Disk & System

### analyze_disk_usage
- **signature**: `analyze_disk_usage(path, depth=2, top_n=20)`
- **description**: Analyze what is consuming disk space under a path, showing folder sizes and the biggest space consumers recursively. Use when the user asks "what is taking up space on my computer", "show disk usage breakdown", "which folders are the biggest", "why is my disk full", "analyze storage usage", "how much space does X use", "what is eating my storage", "show me disk hogs", "what folder is using the most space", "where is my disk space going".
- **tags**: disk, usage, space, size, largest, biggest, storage, analyze, full, taking up, eating, consuming, disk hogs, where is space going

### get_drive_info
- **signature**: `get_drive_info()`
- **description**: Return total, used, and free storage space for all local drives (C:, D:, etc.). Use when the user asks "how much free space do I have", "what is my disk space", "how full is my C drive", "check storage on all drives", "how much space is left on my computer", "disk capacity breakdown".
- **tags**: drive, storage, space, free, total, used, capacity, how much free space, disk full check

### count_files_and_folders_all_drives
- **signature**: `count_files_and_folders_all_drives(include_hidden=True, follow_symlinks=False)`
- **description**: Count the total number of accessible files and folders across all detected local drives. This is the correct tool for count-style questions such as "how many files and folders are there on my system", "count all files on my laptop", "how many folders do I have on this computer", "total files and folders across all drives", "what is the total number of files on my PC", or "give me the file and folder count for my whole system".
- **tags**: count files, count folders, total files, total folders, how many files and folders, system count, laptop count, all drives count, whole system count, file count, folder count, total number of files

### list_laptop_structure
- **signature**: `list_laptop_structure(include_hidden=False, output_file="", depth=2)`
- **description**: Get a complete high-level overview of this laptop: all drives (C:, D:, etc.) with their top folder structure including Downloads, Desktop, Documents, Pictures, Videos, and other major directories. Use when the user asks "show me all folders on my laptop", "what drives do I have", "give me an overview of my computer's file structure", "scan my entire laptop", "list all drives and folders", "show the folder tree of my PC", or wants a browsable structure report. Do not use this for total file/folder counts.
- **tags**: laptop, structure, scan, all, drives, overview, tree, full, computer, all folders, complete, folder tree, pc structure, structure report, directory tree

### list_running_apps
- **signature**: `list_running_apps()`
- **description**: List all currently running processes with PID, application name, memory usage, and CPU percentage. Use when the user asks "what apps are running", "show running processes", "what is using memory", "which programs are open", "task manager view", "what is consuming CPU", "show all open applications", "check running programs".
- **tags**: processes, running, apps, memory, cpu, task manager, open apps, what's running, running programs

### resolve_shortcut
- **signature**: `resolve_shortcut(lnk_path)`
- **description**: Resolve a Windows .lnk shortcut file to its actual target executable or folder path. Use when the user asks "where does this shortcut point to", "resolve the .lnk file", "find the real path of this shortcut", "what does the shortcut X link to".
- **tags**: shortcut, lnk, resolve, target, link, where does shortcut point

### get_file_hash
- **signature**: `get_file_hash(file_path, algorithm="md5")`
- **description**: Compute a cryptographic hash (MD5, SHA256, or SHA1) of a file for integrity verification or duplicate detection. Use when the user says "get the MD5 hash of file X", "verify file integrity of X", "compute checksum of X", "get SHA256 of this file", "compare hash of two files", "is this file corrupted".
- **tags**: hash, md5, sha256, checksum, integrity, verify, file hash, compute hash, is file corrupted

### monitor_folder
- **signature**: `monitor_folder(path, timeout_seconds=30, poll_interval=1.0)`
- **description**: Watch a specific folder for file changes (created, modified, deleted) for up to N seconds in real-time. Use when the user says "watch this folder for changes", "monitor Downloads for new files", "alert me when something appears in folder X", "track file changes in Y", "notify me of new files in Z".
- **tags**: monitor, watch, changes, new files, real-time, track, watch folder, alert new files

---

## Category: Context & Manifest

### save_search_manifest
- **signature**: `save_search_manifest(found_paths, manifest_path="")`
- **description**: Persist a list of found file paths to the manifest file (`your_data/octa_manifest.txt` by default) for use in subsequent turns. CALL IMMEDIATELY after any search step so the paths are available in the next turn when the user asks to copy, zip, or process them. Without this, file paths are lost between turns.
- **tags**: save, manifest, persist, paths, results, cross-turn, save paths, remember files

### collect_files_from_manifest
- **signature**: `collect_files_from_manifest(manifest_path="", destination="")`
- **description**: Read the saved manifest file and copy EVERY listed file path to a destination folder. Use when the user says "copy those files now" or "collect the files you found" after a previous search turn saved a manifest. Avoids having to re-run the search.
- **tags**: collect, manifest, copy, previous, gather, restore, copy from last search

### undo_last_file_operation
- **signature**: `undo_last_file_operation()`
- **description**: Undo the most recent copy or collect file operation by deleting the destination folder that was created. Use when the user says "undo that", "revert the copy", "undo the last file operation", "take that back", "cancel what you just did", "undo the collect".
- **tags**: undo, revert, rollback, cancel, take back, undo copy, undo last

### list_file_operations
- **signature**: `list_file_operations(days=30)`
- **description**: Return the file operation audit history for the last N days, newest first. Each entry shows operation type, destination, file count, timestamp, and whether it was undone. Use when the user asks "show file operation history", "what file operations did you do", "show recent file changes", "what did you do to my files", "file audit log".
- **tags**: history, audit, log, operations, recent, track, file history, what was done, operation log

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist the current file search results as cross-turn context so the user can follow-up with actions without repeating the search. Call after every search listing so the next turn supports "copy them", "zip those", "delete them". topic="file_search", resolved_entities={"listed_files":[...], "query":"..."}, awaiting="file_action".
- **tags**: context, save, cross-turn, persist, session, follow-up, remember files, file action next turn
