"""
Files Agent features package — public re-exports.
"""
from .file_ops import (
    list_directory,
    get_file_info,
    copy_file,
    move_file,
    delete_file,
    create_folder,
    rename_file,
    open_file,
)
from .search import (
    search_by_name,
    search_by_extension,
    search_by_date,
    search_by_size,
    find_duplicates,
    find_empty_folders,
)
from .archives import (
    zip_files,
    zip_folder,
    unzip_file,
    list_archive_contents,
    get_archive_info,
)
from .organizer import (
    bulk_rename,
    organize_by_type,
    organize_by_date,
    move_files_matching,
    delete_files_matching,
    clean_empty_folders,
    deduplicate_files,
)
from .disk import (
    list_drives,
    get_disk_usage,
    get_directory_size,
    find_large_files,
    get_recently_modified,
)
from .reader import (
    read_text_file,
    get_file_stats,
    preview_csv,
    read_json_file,
    tail_log,
    calculate_file_hash,
)
from .smart_features import (
    summarize_file,
    analyze_folder,
    suggest_organization,
    generate_rename_suggestions,
    find_related_files,
    describe_file,
)
from .cross_agent import (
    zip_and_email,
    zip_and_upload_to_drive,
    email_file,
    upload_file_to_drive,
    send_file_via_whatsapp,
)

__all__ = [
    # file_ops
    "list_directory", "get_file_info", "copy_file", "move_file",
    "delete_file", "create_folder", "rename_file", "open_file",
    # search
    "search_by_name", "search_by_extension", "search_by_date",
    "search_by_size", "find_duplicates", "find_empty_folders",
    # archives
    "zip_files", "zip_folder", "unzip_file", "list_archive_contents", "get_archive_info",
    # organizer
    "bulk_rename", "organize_by_type", "organize_by_date",
    "move_files_matching", "delete_files_matching", "clean_empty_folders", "deduplicate_files",
    # disk
    "list_drives", "get_disk_usage", "get_directory_size",
    "find_large_files", "get_recently_modified",
    # reader
    "read_text_file", "get_file_stats", "preview_csv",
    "read_json_file", "tail_log", "calculate_file_hash",
    # smart_features
    "summarize_file", "analyze_folder", "suggest_organization",
    "generate_rename_suggestions", "find_related_files", "describe_file",
    # cross_agent
    "zip_and_email", "zip_and_upload_to_drive", "email_file",
    "upload_file_to_drive", "send_file_via_whatsapp",
]
