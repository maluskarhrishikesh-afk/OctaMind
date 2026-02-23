"""
Unit tests for:
  - src/files/files_service.py
    - resolve_path()  ← validates the new user-folder alias fix
    - _fmt_size()
    - _is_safe_path()
    - _file_dict()
    - _hash_file()
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_IS_WINDOWS = sys.platform == "win32"

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.files.files_service import (
    _fmt_size,
    _hash_file,
    _is_safe_path,
    resolve_path,
)


# ══════════════════════════════════════════════════════════════════════════════
# resolve_path — user-folder alias expansion
# ══════════════════════════════════════════════════════════════════════════════

class TestResolvePath:
    # ── Alias expansion ────────────────────────────────────────────────────
    def test_downloads_lowercased_expands_to_home(self):
        p = resolve_path("downloads/myfile.txt")
        assert p == Path.home() / "Downloads" / "myfile.txt"

    def test_downloads_capitalized_expands_to_home(self):
        p = resolve_path("Downloads/myfile.txt")
        assert p == Path.home() / "Downloads" / "myfile.txt"

    def test_desktop_alias(self):
        p = resolve_path("Desktop/shortcut.lnk")
        assert p == Path.home() / "Desktop" / "shortcut.lnk"

    def test_documents_alias(self):
        p = resolve_path("Documents/report.pdf")
        assert p == Path.home() / "Documents" / "report.pdf"

    def test_pictures_alias(self):
        p = resolve_path("Pictures/vacation.jpg")
        assert p == Path.home() / "Pictures" / "vacation.jpg"

    def test_videos_alias(self):
        p = resolve_path("videos/clip.mp4")
        assert p == Path.home() / "Videos" / "clip.mp4"

    def test_music_alias(self):
        p = resolve_path("music/track.mp3")
        assert p == Path.home() / "Music" / "track.mp3"

    # ── Tilde expansion ───────────────────────────────────────────────────
    def test_tilde_documents_expands(self):
        p = resolve_path("~/Documents/report.pdf")
        assert p == Path.home() / "Documents" / "report.pdf"

    def test_tilde_home_root(self):
        p = resolve_path("~/somefile.txt")
        assert p == Path.home() / "somefile.txt"

    # ── Absolute paths kept as-is ─────────────────────────────────────────
    def test_absolute_path_not_redirected(self):
        p = resolve_path("C:/Users/test/file.txt")
        assert p == Path("C:/Users/test/file.txt")

    # ── Relative paths resolve to CWD when not an alias ─────────────────-
    def test_relative_non_alias_resolves_from_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = resolve_path("projects/app.py")
        assert p == tmp_path / "projects" / "app.py"

    # ── Edge: bare alias name alone ───────────────────────────────────────
    def test_alias_bare_name(self):
        p = resolve_path("Downloads")
        assert p == Path.home() / "Downloads"


# ══════════════════════════════════════════════════════════════════════════════
# _fmt_size
# ══════════════════════════════════════════════════════════════════════════════

class TestFmtSize:
    def test_zero_bytes(self):
        assert _fmt_size(0) == "0.0 B"

    def test_bytes(self):
        assert _fmt_size(512) == "512.0 B"

    def test_kilobytes(self):
        assert _fmt_size(1024) == "1.0 KB"

    def test_megabytes(self):
        assert _fmt_size(1024 ** 2) == "1.0 MB"

    def test_gigabytes(self):
        assert _fmt_size(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert _fmt_size(1024 ** 4) == "1.0 TB"

    def test_fractional_mb(self):
        size = int(2.5 * 1024 ** 2)
        assert _fmt_size(size) == "2.5 MB"


# ══════════════════════════════════════════════════════════════════════════════
# _is_safe_path
# ══════════════════════════════════════════════════════════════════════════════

class TestIsSafePath:
    def test_user_home_is_safe(self):
        assert _is_safe_path(Path.home()) is True

    def test_user_documents_is_safe(self):
        assert _is_safe_path(Path.home() / "Documents" / "file.txt") is True

    def test_user_downloads_is_safe(self):
        assert _is_safe_path(Path.home() / "Downloads" / "archive.zip") is True

    def test_windows_system_dir_blocked(self):
        assert _is_safe_path(Path("C:/Windows")) is False

    def test_windows_system32_blocked(self):
        assert _is_safe_path(Path("C:/Windows/System32")) is False

    def test_program_files_blocked(self):
        assert _is_safe_path(Path("C:/Program Files/App")) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only paths")
    def test_etc_blocked_on_unix(self):
        assert _is_safe_path(Path("/etc/passwd")) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only paths")
    def test_usr_bin_blocked_on_unix(self):
        assert _is_safe_path(Path("/usr/bin/python")) is False

    def test_tmp_path_is_safe(self, tmp_path):
        assert _is_safe_path(tmp_path) is True


# ══════════════════════════════════════════════════════════════════════════════
# _hash_file
# ══════════════════════════════════════════════════════════════════════════════

class TestHashFile:
    def test_correct_md5(self, tmp_path):
        content = b"hello world"
        f = tmp_path / "test.txt"
        f.write_bytes(content)

        expected = hashlib.md5(content).hexdigest()
        assert _hash_file(f) == expected

    def test_different_contents_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        assert _hash_file(f1) != _hash_file(f2)

    def test_identical_contents_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"same content")
        f2.write_bytes(b"same content")

        assert _hash_file(f1) == _hash_file(f2)


# ══════════════════════════════════════════════════════════════════════════════
# _file_dict
# ══════════════════════════════════════════════════════════════════════════════

class TestFileDict:
    def test_file_dict_has_required_fields(self, tmp_path):
        from src.files.files_service import _file_dict

        f = tmp_path / "sample.txt"
        f.write_text("hello")

        d = _file_dict(f)
        for key in ("name", "path", "type", "extension", "size_bytes", "size", "modified"):
            assert key in d, f"Missing key: {key}"

    def test_file_type_is_file(self, tmp_path):
        from src.files.files_service import _file_dict

        f = tmp_path / "note.txt"
        f.write_text("data")
        assert _file_dict(f)["type"] == "file"

    def test_folder_type_is_folder(self, tmp_path):
        from src.files.files_service import _file_dict

        d = tmp_path / "myfolder"
        d.mkdir()
        result = _file_dict(d)
        assert result["type"] == "folder"

    def test_extension_extracted(self, tmp_path):
        from src.files.files_service import _file_dict

        f = tmp_path / "report.pdf"
        f.write_bytes(b"pdf content")
        assert _file_dict(f)["extension"] == ".pdf"

    def test_size_bytes_correct(self, tmp_path):
        from src.files.files_service import _file_dict

        content = b"A" * 256
        f = tmp_path / "data.bin"
        f.write_bytes(content)
        assert _file_dict(f)["size_bytes"] == 256

    def test_include_hash(self, tmp_path):
        from src.files.files_service import _file_dict

        f = tmp_path / "hashed.txt"
        f.write_text("checksum test")
        d = _file_dict(f, include_hash=True)
        # hash is stored as 'md5' key
        assert "md5" in d
        assert len(d["md5"]) == 32  # MD5 hex length

    def test_no_hash_by_default(self, tmp_path):
        from src.files.files_service import _file_dict

        f = tmp_path / "nohash.txt"
        f.write_text("data")
        d = _file_dict(f)
        assert "hash" not in d
