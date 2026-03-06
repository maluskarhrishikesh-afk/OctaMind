"""
Unit tests for src/agent/manifest/context_manifest.py

Tests cover the keyed-store refactor (schema_version=2):
  - write/read round-trip for a single agent
  - two agents coexist in the store without overwriting each other
  - read_context(agent=X) returns the right slot
  - read_context() with no agent returns the most-recently-written entry
  - clear_context(agent=X) removes only that agent's slot
  - clear_context() removes the entire file
  - scope field is persisted and returned in the context dict
  - legacy flat format (schema_version=1) is migrated on next write
  - TTL expiry returns None
  - missing file returns None

All tests operate in a temporary directory (tmp_path) — the real
data/octa_context.json is never touched.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_files(tmp_path: Path):
    """Return a context-manager that redirects all manifest file paths into tmp_path."""
    ctx_file     = tmp_path / "octa_context.json"
    history_file = tmp_path / "octa_context_history.jsonl"
    stamp_file   = tmp_path / ".last_context_prune"
    import src.agent.manifest.context_manifest as cm
    return patch.multiple(
        cm,
        _CONTEXT_FILE=ctx_file,
        _CONTEXT_HISTORY_FILE=history_file,
        _PRUNE_STAMP_FILE=stamp_file,
        _MANIFEST_DIR=tmp_path,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContextManifestWrite:

    def test_write_returns_success(self, tmp_path):
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            result = write_context(
                agent="files",
                topic="file_search",
                resolved_entities={"query": "payslip", "count": 3},
            )
        assert result["status"] == "success"

    def test_write_creates_keyed_store_file(self, tmp_path):
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            write_context(
                agent="files",
                topic="file_search",
                resolved_entities={"query": "payslip", "count": 3},
            )
            ctx_file = tmp_path / "octa_context.json"
            assert ctx_file.exists()
            data = json.loads(ctx_file.read_text())
            assert "files" in data
            assert data["files"]["agent"] == "files"
            assert data["files"]["schema_version"] == 2

    def test_write_two_agents_coexist(self, tmp_path):
        """Writing two different agents keeps both slots in the store."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            write_context(
                agent="files",
                topic="file_search",
                resolved_entities={"query": "payslip"},
            )
            write_context(
                agent="email",
                topic="email_list",
                resolved_entities={"count": 5},
            )
            ctx_file = tmp_path / "octa_context.json"
            data = json.loads(ctx_file.read_text())
            assert "files" in data
            assert "email" in data

    def test_write_second_call_overwrites_same_agent_slot(self, tmp_path):
        """A second write for the same agent overwrites just that agent's slot."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            write_context(agent="files", topic="first", resolved_entities={"v": 1})
            write_context(agent="files", topic="second", resolved_entities={"v": 2})
            ctx_file = tmp_path / "octa_context.json"
            data = json.loads(ctx_file.read_text())
            assert data["files"]["topic"] == "second"
            assert data["files"]["resolved_entities"]["v"] == 2

    def test_write_scope_field_stored(self, tmp_path):
        """scope= keyword arg is persisted inside the agent's slot."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            write_context(
                agent="files",
                topic="file_search",
                resolved_entities={"paths": ["/a/b"]},
                scope="single_folder",
            )
            ctx_file = tmp_path / "octa_context.json"
            data = json.loads(ctx_file.read_text())
            assert data["files"]["scope"] == "single_folder"

    def test_write_scope_omitted_not_present(self, tmp_path):
        """When scope is not passed the key should not appear in the stored entry."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            write_context(
                agent="files",
                topic="file_search",
                resolved_entities={"paths": []},
            )
            ctx_file = tmp_path / "octa_context.json"
            data = json.loads(ctx_file.read_text())
            assert "scope" not in data["files"]

    def test_write_audit_history_appended(self, tmp_path):
        """Each write appends a compact line to the JSONL audit history file."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context
            write_context(agent="email", topic="email_list", resolved_entities={"n": 1})
            write_context(agent="files", topic="file_search", resolved_entities={"n": 2})
            history_file = tmp_path / "octa_context_history.jsonl"
            lines = [l for l in history_file.read_text().splitlines() if l.strip()]
            assert len(lines) == 2
            entry = json.loads(lines[0])
            assert "written_at" in entry
            assert "agent" in entry


class TestContextManifestRead:

    def test_read_returns_none_when_file_missing(self, tmp_path):
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import read_context
            assert read_context() is None

    def test_read_agent_specific(self, tmp_path):
        """read_context(agent='files') returns files' slot, not email's."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, read_context
            write_context(agent="files", topic="file_search", resolved_entities={"q": "payslip"})
            write_context(agent="email", topic="email_list", resolved_entities={"q": "inbox"})
            ctx = read_context(agent="files")
            assert ctx is not None
            assert ctx["agent"] == "files"
            assert ctx["resolved_entities"]["q"] == "payslip"

    def test_read_no_arg_returns_most_recent(self, tmp_path):
        """read_context() with no agent arg returns the most-recently-written entry."""
        ctx_file = tmp_path / "octa_context.json"
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, read_context
            from datetime import datetime, timedelta
            write_context(agent="files", topic="file_search", resolved_entities={"first": True})
            # Backdate the files entry so it appears older than the upcoming email write
            data = json.loads(ctx_file.read_text())
            old_time = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
            data["files"]["written_at"] = old_time
            ctx_file.write_text(json.dumps(data))
            write_context(agent="email", topic="email_list", resolved_entities={"last": True})
            ctx = read_context()
            assert ctx is not None
            assert ctx["agent"] == "email"

    def test_read_wrong_agent_returns_none(self, tmp_path):
        """Requesting an agent whose slot does not exist returns None."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, read_context
            write_context(agent="files", topic="t", resolved_entities={})
            assert read_context(agent="email") is None

    def test_read_expired_context_returns_none(self, tmp_path):
        """Context past its expires_at timestamp is discarded."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, read_context
            import src.agent.manifest.context_manifest as cm
            # Write normally
            write_context(agent="files", topic="t", resolved_entities={"v": 1})
            # Manually backdate the written_at and expires_at to be in the past
            ctx_file = tmp_path / "octa_context.json"
            data = json.loads(ctx_file.read_text())
            old_time = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
            data["files"]["written_at"] = old_time
            data["files"]["expires_at"] = old_time
            ctx_file.write_text(json.dumps(data))
            # Should be treated as expired
            assert read_context(agent="files") is None

    def test_read_scope_field_returned(self, tmp_path):
        """scope persisted in write is available in the read result."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, read_context
            write_context(
                agent="files",
                topic="t",
                resolved_entities={},
                scope="multi_folder",
            )
            ctx = read_context(agent="files")
            assert ctx is not None
            assert ctx["scope"] == "multi_folder"


class TestContextManifestClear:

    def test_clear_all_deletes_file(self, tmp_path):
        """clear_context() with no args deletes the entire context file."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, clear_context
            write_context(agent="files", topic="t", resolved_entities={})
            ctx_file = tmp_path / "octa_context.json"
            assert ctx_file.exists()
            clear_context()
            assert not ctx_file.exists()

    def test_clear_all_on_missing_file_is_noop(self, tmp_path):
        """clear_context() when the file doesn't exist doesn't raise."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import clear_context
            clear_context()  # must not raise

    def test_clear_partial_removes_only_target_agent(self, tmp_path):
        """clear_context(agent='files') leaves other agents' contexts intact."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, clear_context, read_context
            write_context(agent="files", topic="f", resolved_entities={"x": 1})
            write_context(agent="email", topic="e", resolved_entities={"y": 2})
            clear_context(agent="files")
            # files slot gone
            assert read_context(agent="files") is None
            # email slot still there
            assert read_context(agent="email") is not None

    def test_clear_partial_deletes_file_when_store_empty(self, tmp_path):
        """After removing the only agent's slot the file is deleted (not left as {})."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, clear_context
            write_context(agent="files", topic="t", resolved_entities={})
            ctx_file = tmp_path / "octa_context.json"
            clear_context(agent="files")
            assert not ctx_file.exists()

    def test_clear_partial_nonexistent_agent_is_noop(self, tmp_path):
        """Clearing an agent that doesn't exist in the store doesn't raise and doesn't corrupt the store."""
        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, clear_context, read_context
            write_context(agent="email", topic="e", resolved_entities={"n": 1})
            clear_context(agent="files")  # files not in store — should be fine
            assert read_context(agent="email") is not None


class TestLegacyFlatFormat:

    def test_legacy_flat_format_migrated_on_write(self, tmp_path):
        """
        If the file exists in the legacy flat (schema_version=1) format and a new
        agent writes to it, the legacy entry is migrated to the keyed store first
        so neither the old nor the new entry is lost.
        """
        ctx_file = tmp_path / "octa_context.json"
        # Write a legacy v1 flat payload directly to disk
        legacy_payload = {
            "schema_version": 1,
            "written_at": datetime.now().isoformat(timespec="seconds"),
            "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(timespec="seconds"),
            "agent": "calendar",
            "topic": "slot_booking",
            "resolved_entities": {"resolved_date": "2026-03-06"},
            "awaiting": "time_selection",
        }
        ctx_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import write_context, read_context
            # Now write a new agent — should trigger migration
            write_context(agent="email", topic="email_list", resolved_entities={"n": 5})

            data = json.loads(ctx_file.read_text())
            # Both keys should exist
            assert "calendar" in data, "Legacy calendar entry should be migrated to keyed store"
            assert "email" in data, "New email entry should be present"
            assert data["email"]["topic"] == "email_list"

    def test_legacy_flat_format_readable_via_read_context(self, tmp_path):
        """
        read_context() on a legacy flat file returns the entry even though
        migration hasn't happened yet (no write occurred).
        """
        ctx_file = tmp_path / "octa_context.json"
        legacy_payload = {
            "schema_version": 1,
            "written_at": datetime.now().isoformat(timespec="seconds"),
            "expires_at": (datetime.now() + timedelta(minutes=60)).isoformat(timespec="seconds"),
            "agent": "email",
            "topic": "email_list",
            "resolved_entities": {"count": 3},
        }
        ctx_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

        with _patch_files(tmp_path):
            from src.agent.manifest.context_manifest import read_context
            ctx = read_context(agent="email")
            assert ctx is not None
            assert ctx["topic"] == "email_list"
