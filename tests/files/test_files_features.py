"""
Unit tests for Files feature modules:
  - src/files/features/file_ops.py
  - src/files/features/search.py
  - src/files/features/archives.py
  - src/files/features/organizer.py
  - src/files/features/disk.py

All tests operate on tmp_path — no writes outside the test sandbox.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _write(path: Path, content: str = "content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — list_directory
# ══════════════════════════════════════════════════════════════════════════════

class TestListDirectory:
    def test_lists_files_and_folders(self, tmp_path):
        from src.files.features.file_ops import list_directory

        _write(tmp_path / "a.txt", "aaaa")
        _write(tmp_path / "b.txt", "bbbb")
        (tmp_path / "subdir").mkdir()

        result = list_directory(str(tmp_path))
        assert result["status"] == "success"
        assert result["total_entries"] == 3

    def test_nonexistent_path_returns_error(self, tmp_path):
        from src.files.features.file_ops import list_directory

        result = list_directory(str(tmp_path / "doesnt_exist"))
        assert result["status"] == "error"

    def test_limit_respected(self, tmp_path):
        from src.files.features.file_ops import list_directory

        for i in range(10):
            _write(tmp_path / f"file{i}.txt")

        result = list_directory(str(tmp_path), limit=3)
        assert result["status"] == "success"
        assert len(result["entries"]) == 3

    def test_hidden_files_excluded_by_default(self, tmp_path):
        from src.files.features.file_ops import list_directory

        _write(tmp_path / ".hidden_file.txt")
        _write(tmp_path / "visible.txt")

        result = list_directory(str(tmp_path), show_hidden=False)
        names = [e["name"] for e in result["entries"]]
        assert ".hidden_file.txt" not in names
        assert "visible.txt" in names

    def test_hidden_files_shown_when_requested(self, tmp_path):
        from src.files.features.file_ops import list_directory

        _write(tmp_path / ".hidden_file.txt")
        result = list_directory(str(tmp_path), show_hidden=True)
        names = [e["name"] for e in result["entries"]]
        assert ".hidden_file.txt" in names


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — get_file_info
# ══════════════════════════════════════════════════════════════════════════════

class TestGetFileInfo:
    def test_returns_metadata_for_file(self, tmp_path):
        from src.files.features.file_ops import get_file_info

        f = _write(tmp_path / "sample.txt", "hello world")
        result = get_file_info(str(f))

        assert result["status"] == "success"
        assert result["name"] == "sample.txt"
        assert result["type"] == "file"
        assert result["extension"] == ".txt"

    def test_returns_metadata_for_folder(self, tmp_path):
        from src.files.features.file_ops import get_file_info

        d = tmp_path / "mydir"
        d.mkdir()
        result = get_file_info(str(d))
        assert result["status"] == "success"
        assert result["type"] == "folder"

    def test_nonexistent_path_returns_error(self, tmp_path):
        from src.files.features.file_ops import get_file_info

        result = get_file_info(str(tmp_path / "ghost.txt"))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — copy_file
# ══════════════════════════════════════════════════════════════════════════════

class TestCopyFile:
    def test_copies_file_to_destination(self, tmp_path):
        from src.files.features.file_ops import copy_file

        src = _write(tmp_path / "src.txt", "copy me")
        dst = tmp_path / "dst.txt"

        result = copy_file(str(src), str(dst))
        assert result["status"] == "success"
        assert dst.exists()
        assert dst.read_text() == "copy me"
        assert src.exists()  # source must still exist

    def test_copies_folder(self, tmp_path):
        from src.files.features.file_ops import copy_file

        src_dir = tmp_path / "src_dir"
        src_dir.mkdir()
        _write(src_dir / "nested.txt", "nested")

        dst_dir = tmp_path / "dst_dir"
        result = copy_file(str(src_dir), str(dst_dir))
        assert result["status"] == "success"
        assert (dst_dir / "nested.txt").exists()

    def test_nonexistent_source_returns_error(self, tmp_path):
        from src.files.features.file_ops import copy_file

        result = copy_file(str(tmp_path / "ghost.txt"), str(tmp_path / "out.txt"))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — move_file
# ══════════════════════════════════════════════════════════════════════════════

class TestMoveFile:
    def test_moves_file_to_destination(self, tmp_path):
        from src.files.features.file_ops import move_file

        src = _write(tmp_path / "move_me.txt", "moving")
        dst = tmp_path / "moved.txt"

        result = move_file(str(src), str(dst))
        assert result["status"] == "success"
        assert dst.exists()
        assert not src.exists()  # source must be gone

    def test_nonexistent_source_returns_error(self, tmp_path):
        from src.files.features.file_ops import move_file

        result = move_file(str(tmp_path / "ghost.txt"), str(tmp_path / "out.txt"))
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — create_folder
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateFolder:
    def test_creates_single_directory(self, tmp_path):
        from src.files.features.file_ops import create_folder

        new_dir = tmp_path / "new_folder"
        result = create_folder(str(new_dir))
        assert result["status"] == "success"
        assert new_dir.is_dir()

    def test_creates_nested_directories(self, tmp_path):
        from src.files.features.file_ops import create_folder

        nested = tmp_path / "level1" / "level2" / "level3"
        result = create_folder(str(nested))
        assert result["status"] == "success"
        assert nested.is_dir()

    def test_already_existing_returns_error_or_no_op(self, tmp_path):
        from src.files.features.file_ops import create_folder

        existing = tmp_path / "existing"
        existing.mkdir()
        result = create_folder(str(existing))
        # Must not crash; error or success both acceptable
        assert result["status"] in ("success", "error")


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — rename_file
# ══════════════════════════════════════════════════════════════════════════════

class TestRenameFile:
    def test_renames_file(self, tmp_path):
        from src.files.features.file_ops import rename_file

        f = _write(tmp_path / "old_name.txt", "data")
        result = rename_file(str(f), "new_name.txt")
        assert result["status"] == "success"
        assert not f.exists()
        assert (tmp_path / "new_name.txt").exists()

    def test_nonexistent_source_returns_error(self, tmp_path):
        from src.files.features.file_ops import rename_file

        result = rename_file(str(tmp_path / "ghost.txt"), "new.txt")
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# file_ops — delete_file (permanent, skips recycle bin for tmp_path items)
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteFile:
    def test_delete_file_permanently(self, tmp_path):
        from src.files.features.file_ops import delete_file

        f = _write(tmp_path / "delete_me.txt", "bye")
        result = delete_file(str(f), permanent=True)
        assert result["status"] == "success"
        assert not f.exists()

    def test_delete_folder_permanently(self, tmp_path):
        from src.files.features.file_ops import delete_file

        d = tmp_path / "del_folder"
        d.mkdir()
        _write(d / "child.txt")
        result = delete_file(str(d), permanent=True)
        assert result["status"] == "success"
        assert not d.exists()

    def test_delete_protected_path_returns_error(self, tmp_path):
        from src.files.features.file_ops import delete_file

        # C:/Windows should be blocked by _is_safe_path
        result = delete_file("C:/Windows", permanent=True)
        assert result["status"] == "error"

    def test_delete_nonexistent_returns_error(self, tmp_path):
        from src.files.features.file_ops import delete_file

        result = delete_file(str(tmp_path / "nope.txt"), permanent=True)
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════════════════════════
# search — search_by_name
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchByName:
    def test_finds_matching_files(self, tmp_path):
        from src.files.features.search import search_by_name

        _write(tmp_path / "report_2024.pdf")
        _write(tmp_path / "notes.txt")

        result = search_by_name("report", directory=str(tmp_path))
        assert result["status"] == "success"
        assert result["count"] == 1
        assert "report_2024.pdf" in result["results"][0]["name"]

    def test_no_match_returns_zero(self, tmp_path):
        from src.files.features.search import search_by_name

        _write(tmp_path / "file.txt")
        result = search_by_name("xyznosuchmatch", directory=str(tmp_path))
        assert result["count"] == 0

    def test_nonexistent_directory_returns_error(self, tmp_path):
        from src.files.features.search import search_by_name

        result = search_by_name("anything", directory=str(tmp_path / "missing"))
        assert result["status"] == "error"

    def test_limit_respected(self, tmp_path):
        from src.files.features.search import search_by_name

        for i in range(10):
            _write(tmp_path / f"report_{i}.txt")

        result = search_by_name("report", directory=str(tmp_path), limit=3)
        assert result["count"] == 3


# ══════════════════════════════════════════════════════════════════════════════
# search — search_by_extension
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchByExtension:
    def test_finds_correct_extension(self, tmp_path):
        from src.files.features.search import search_by_extension

        _write(tmp_path / "doc.pdf")
        _write(tmp_path / "notes.txt")
        _write(tmp_path / "report.pdf")

        result = search_by_extension("pdf", directory=str(tmp_path))
        assert result["status"] == "success"
        assert result["count"] == 2

    def test_leading_dot_stripped(self, tmp_path):
        from src.files.features.search import search_by_extension

        _write(tmp_path / "code.py")
        result = search_by_extension(".py", directory=str(tmp_path))
        assert result["count"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# search — search_by_size
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchBySize:
    def test_finds_small_files(self, tmp_path):
        from src.files.features.search import search_by_size

        _write(tmp_path / "tiny.txt", "hi")
        result = search_by_size(
            directory=str(tmp_path), min_mb=0, max_mb=1
        )
        assert result["status"] == "success"
        assert result["count"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# search — find_duplicates
# ══════════════════════════════════════════════════════════════════════════════

class TestFindDuplicates:
    def test_identifies_identical_files(self, tmp_path):
        from src.files.features.search import find_duplicates

        _write(tmp_path / "original.txt", "same content here")
        _write(tmp_path / "copy.txt", "same content here")
        _write(tmp_path / "unique.txt", "completely different content")

        result = find_duplicates(str(tmp_path))
        assert result["status"] == "success"
        assert result["duplicate_groups"] >= 1

    def test_no_duplicates_in_unique_files(self, tmp_path):
        from src.files.features.search import find_duplicates

        for i in range(5):
            _write(tmp_path / f"unique{i}.txt", f"unique content {i}")

        result = find_duplicates(str(tmp_path))
        assert result["duplicate_groups"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# search — find_empty_folders
# ══════════════════════════════════════════════════════════════════════════════

class TestFindEmptyFolders:
    def test_finds_empty_directory(self, tmp_path):
        from src.files.features.search import find_empty_folders

        (tmp_path / "empty_dir").mkdir()
        non_empty = tmp_path / "has_file"
        non_empty.mkdir()
        _write(non_empty / "file.txt")

        result = find_empty_folders(str(tmp_path))
        assert result["status"] == "success"
        # empty_folders is a list of path strings
        names = [Path(e).name for e in result["empty_folders"]]
        assert "empty_dir" in names
        assert "has_file" not in names

    def test_no_empty_folders_returns_zero(self, tmp_path):
        from src.files.features.search import find_empty_folders

        d = tmp_path / "nonempty"
        d.mkdir()
        _write(d / "content.txt")

        result = find_empty_folders(str(tmp_path))
        assert result["count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# archives — zip_files / zip_folder / unzip_file
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def src_folder(tmp_path):
    """Create a small source folder with two files."""
    folder = tmp_path / "src_folder"
    folder.mkdir()
    _write(folder / "alpha.txt", "alpha content")
    _write(folder / "beta.txt", "beta content")
    return folder


class TestZipFiles:
    def test_zip_single_file(self, tmp_path, src_folder):
        from src.files.features.archives import zip_files

        out = str(tmp_path / "out.zip")
        src = str(src_folder / "alpha.txt")

        result = zip_files([src], out)
        assert result["status"] == "success"
        assert Path(out).exists()
        assert result["file_count"] == 1

    def test_zip_multiple_files(self, tmp_path, src_folder):
        from src.files.features.archives import zip_files

        out = str(tmp_path / "multi.zip")
        sources = [str(src_folder / "alpha.txt"), str(src_folder / "beta.txt")]

        result = zip_files(sources, out)
        assert result["status"] == "success"
        assert result["file_count"] == 2

    def test_nonexistent_source_returns_error(self, tmp_path):
        from src.files.features.archives import zip_files

        result = zip_files([str(tmp_path / "ghost.txt")], str(tmp_path / "out.zip"))
        assert result["status"] == "error"

    def test_zip_adds_extension_if_missing(self, tmp_path, src_folder):
        from src.files.features.archives import zip_files

        out_no_ext = str(tmp_path / "archive")
        src = str(src_folder / "alpha.txt")

        result = zip_files([src], out_no_ext)
        assert result["status"] == "success"


class TestZipFolder:
    def test_zip_folder_creates_archive(self, tmp_path, src_folder):
        from src.files.features.archives import zip_folder

        out = str(tmp_path / "folder.zip")
        result = zip_folder(str(src_folder), out)
        assert result["status"] == "success"
        assert Path(out).exists()

    def test_zip_folder_contains_contents(self, tmp_path, src_folder):
        from src.files.features.archives import zip_folder

        out = tmp_path / "folder.zip"
        zip_folder(str(src_folder), str(out))

        with zipfile.ZipFile(out, "r") as zf:
            names = zf.namelist()
        assert any("alpha.txt" in n for n in names)
        assert any("beta.txt" in n for n in names)

    def test_nonexistent_folder_returns_error(self, tmp_path):
        from src.files.features.archives import zip_folder

        result = zip_folder(str(tmp_path / "no_such_folder"), str(tmp_path / "out.zip"))
        assert result["status"] == "error"


class TestUnzipFile:
    def test_extracts_contents(self, tmp_path, src_folder):
        from src.files.features.archives import zip_folder, unzip_file

        zip_path = str(tmp_path / "test.zip")
        zip_folder(str(src_folder), zip_path)

        extraction_dir = tmp_path / "extracted"
        result = unzip_file(zip_path, str(extraction_dir))
        assert result["status"] == "success"
        # Extracted files should be present somewhere under extraction_dir
        all_files = list(extraction_dir.rglob("*.txt"))
        assert len(all_files) == 2

    def test_nonexistent_archive_returns_error(self, tmp_path):
        from src.files.features.archives import unzip_file

        result = unzip_file(str(tmp_path / "ghost.zip"), str(tmp_path / "out"))
        assert result["status"] == "error"


class TestListArchiveContents:
    def test_lists_file_names(self, tmp_path, src_folder):
        from src.files.features.archives import zip_folder, list_archive_contents

        zip_path = tmp_path / "contents.zip"
        zip_folder(str(src_folder), str(zip_path))

        result = list_archive_contents(str(zip_path))
        assert result["status"] == "success"
        names = [e["name"] for e in result["contents"]]
        assert any("alpha.txt" in n for n in names)

    def test_nonexistent_archive_returns_error(self, tmp_path):
        from src.files.features.archives import list_archive_contents

        result = list_archive_contents(str(tmp_path / "none.zip"))
        assert result["status"] == "error"


class TestGetArchiveInfo:
    def test_returns_info_dict(self, tmp_path, src_folder):
        from src.files.features.archives import zip_folder, get_archive_info

        zip_path = tmp_path / "info.zip"
        zip_folder(str(src_folder), str(zip_path))

        result = get_archive_info(str(zip_path))
        assert result["status"] == "success"
        assert result["files"] == 2  # key is 'files' not 'file_count'
        assert "total_compressed" in result
        assert "compression_ratio" in result


# ══════════════════════════════════════════════════════════════════════════════
# organizer — organize_by_type (dry_run vs real)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mixed_folder(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    _write(folder / "photo.jpg", "JPEG")
    _write(folder / "report.pdf", "PDF")
    _write(folder / "song.mp3", "MP3")
    _write(folder / "script.py", "PY")
    return folder


class TestOrganizeByType:
    def test_dry_run_does_not_move_files(self, mixed_folder):
        from src.files.features.organizer import organize_by_type

        result = organize_by_type(str(mixed_folder), dry_run=True)
        assert result["status"] == "success"
        assert result.get("dry_run") is True
        # Original files must still be in place
        assert (mixed_folder / "photo.jpg").exists()
        assert (mixed_folder / "report.pdf").exists()

    def test_actual_run_moves_files(self, mixed_folder):
        from src.files.features.organizer import organize_by_type

        result = organize_by_type(str(mixed_folder), dry_run=False)
        assert result["status"] == "success"
        # Original flat location should be gone for at least one file
        at_least_one_moved = not (mixed_folder / "photo.jpg").exists() or \
                             not (mixed_folder / "report.pdf").exists()
        assert at_least_one_moved

    def test_dry_run_reports_what_would_be_moved(self, mixed_folder):
        from src.files.features.organizer import organize_by_type

        result = organize_by_type(str(mixed_folder), dry_run=True)
        assert result["status"] == "success"
        assert isinstance(result.get("preview"), list)  # key is 'preview'
        assert len(result["preview"]) >= 1


class TestBulkRename:
    def test_dry_run_returns_preview(self, mixed_folder):
        from src.files.features.organizer import bulk_rename

        result = bulk_rename(str(mixed_folder), "photo", "img", dry_run=True)
        assert result["status"] == "success"
        assert result.get("dry_run") is True
        assert (mixed_folder / "photo.jpg").exists()  # not actually renamed

    def test_actual_rename(self, mixed_folder):
        from src.files.features.organizer import bulk_rename

        result = bulk_rename(str(mixed_folder), "photo", "img", dry_run=False)
        assert result["status"] == "success"
        assert (mixed_folder / "img.jpg").exists()
        assert not (mixed_folder / "photo.jpg").exists()


class TestCleanEmptyFolders:
    def test_dry_run_does_not_delete(self, tmp_path):
        from src.files.features.organizer import clean_empty_folders

        empty = tmp_path / "empty"
        empty.mkdir()

        result = clean_empty_folders(str(tmp_path), dry_run=True)
        assert result["status"] == "success"
        assert empty.exists()

    def test_actual_removes_empty_dirs(self, tmp_path):
        from src.files.features.organizer import clean_empty_folders

        empty = tmp_path / "empty_to_remove"
        empty.mkdir()

        result = clean_empty_folders(str(tmp_path), dry_run=False)
        assert result["status"] == "success"
        assert not empty.exists()


class TestDeduplicateFiles:
    def test_dry_run_identifies_duplicates(self, tmp_path):
        from src.files.features.organizer import deduplicate_files

        _write(tmp_path / "dup1.txt", "same")
        _write(tmp_path / "dup2.txt", "same")
        _write(tmp_path / "unique.txt", "different xyz")

        result = deduplicate_files(str(tmp_path), dry_run=True)
        assert result["status"] == "success"
        assert result.get("dry_run") is True
        # Both dup files must still exist
        assert (tmp_path / "dup1.txt").exists()
        assert (tmp_path / "dup2.txt").exists()
        assert result["duplicate_groups"] >= 1  # key is 'duplicate_groups'


# ══════════════════════════════════════════════════════════════════════════════
# disk — get_disk_usage / get_directory_size / find_large_files / get_recently_modified
# ══════════════════════════════════════════════════════════════════════════════

class TestGetDiskUsage:
    def test_returns_usage_dict(self, tmp_path):
        from src.files.features.disk import get_disk_usage

        result = get_disk_usage(str(tmp_path))
        assert result["status"] == "success"
        for key in ("total", "used", "free", "used_pct"):
            assert key in result

    def test_used_pct_has_percent_sign(self, tmp_path):
        from src.files.features.disk import get_disk_usage

        result = get_disk_usage(str(tmp_path))
        assert "%" in result["used_pct"]

    def test_nonexistent_path_returns_error(self):
        from src.files.features.disk import get_disk_usage

        result = get_disk_usage("/does/not/exist/xyz123")
        assert result["status"] == "error"


class TestGetDirectorySize:
    def test_size_matches_file_contents(self, tmp_path):
        from src.files.features.disk import get_directory_size

        content = b"A" * 1024  # exactly 1 KiB
        (tmp_path / "testfile.bin").write_bytes(content)

        result = get_directory_size(str(tmp_path))
        assert result["status"] == "success"
        assert result["total_bytes"] >= 1024  # key is 'total_bytes'

    def test_empty_folder_is_zero_or_minimal(self, tmp_path):
        from src.files.features.disk import get_directory_size

        empty = tmp_path / "empty"
        empty.mkdir()

        result = get_directory_size(str(empty))
        assert result["status"] == "success"
        assert result["total_bytes"] == 0


class TestFindLargeFiles:
    def test_returns_files_sorted_by_size(self, tmp_path):
        from src.files.features.disk import find_large_files

        (tmp_path / "big.bin").write_bytes(b"B" * 2048)
        (tmp_path / "small.bin").write_bytes(b"S" * 256)

        # min_mb=0 means include everything (parameter is megabytes)
        result = find_large_files(str(tmp_path), min_mb=0, limit=10)
        assert result["status"] == "success"
        assert result["count"] >= 2
        sizes = [f["size_bytes"] for f in result["results"]]  # key is 'results'
        assert sizes == sorted(sizes, reverse=True)  # descending order

    def test_min_bytes_filters_small_files(self, tmp_path):
        from src.files.features.disk import find_large_files

        (tmp_path / "tiny.txt").write_bytes(b"T" * 10)
        (tmp_path / "large.bin").write_bytes(b"L" * 5000)

        # min_mb is in megabytes; 0.004 MB ≈ 4096 bytes — tiny.txt (10 bytes) excluded
        result = find_large_files(str(tmp_path), min_mb=0.004, limit=10)
        assert result["status"] == "success"
        assert all(f["size_bytes"] >= 4096 for f in result["results"])


class TestGetRecentlyModified:
    def test_recently_created_file_returned(self, tmp_path):
        from src.files.features.disk import get_recently_modified

        _write(tmp_path / "fresh.txt", "just created")
        # parameter is 'days', not 'hours'
        result = get_recently_modified(str(tmp_path), days=1)
        assert result["status"] == "success"
        assert any("fresh.txt" in f["name"] for f in result["results"])  # key is 'results'

    def test_limit_respected(self, tmp_path):
        from src.files.features.disk import get_recently_modified

        for i in range(10):
            _write(tmp_path / f"file{i}.txt", "new")

        result = get_recently_modified(str(tmp_path), days=1, limit=3)
        # 'count' is total found; 'results' is the page-limited slice
        assert len(result["results"]) == 3


class TestListDrives:
    def test_drives_list_non_empty(self):
        from src.files.features.disk import list_drives

        result = list_drives()
        assert result["status"] == "success"
        assert len(result["drives"]) >= 1
