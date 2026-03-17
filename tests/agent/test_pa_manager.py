import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.hub import pa_manager


def test_cleanup_pa_resources_removes_named_and_legacy_logs_and_memory(tmp_path, monkeypatch):
    your_data = tmp_path / "your_data"
    your_data.mkdir()
    monkeypatch.setattr(pa_manager, "_PA_PATH", your_data / "assistants.json")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    memory_dir = tmp_path / "memory" / "pa_123"
    memory_dir.mkdir(parents=True)

    (logs_dir / "octa-001.log").write_text("structured", encoding="utf-8")
    (logs_dir / "octa-001_stderr.txt").write_text("stderr", encoding="utf-8")
    (logs_dir / "pa_123.log").write_text("legacy structured", encoding="utf-8")
    (logs_dir / "pa_pa_123_stderr.txt").write_text("legacy stderr", encoding="utf-8")

    monkeypatch.setitem(sys.modules, "src.telegram.pa_poller_manager", type("PollerModule", (), {"stop_pa_poller": staticmethod(lambda pa_id: True)}))

    pa_manager._cleanup_pa_resources({"id": "pa_123", "name": "octa-001"})

    assert not (logs_dir / "octa-001.log").exists()
    assert not (logs_dir / "octa-001_stderr.txt").exists()
    assert not (logs_dir / "pa_123.log").exists()
    assert not (logs_dir / "pa_pa_123_stderr.txt").exists()
    assert not memory_dir.exists()


def test_cleanup_orphaned_pa_resources_removes_deleted_pa_artifacts(tmp_path, monkeypatch):
    your_data = tmp_path / "your_data"
    your_data.mkdir()
    monkeypatch.setattr(pa_manager, "_PA_PATH", your_data / "assistants.json")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    memory_root = tmp_path / "memory"
    memory_root.mkdir()

    active_log = logs_dir / "octa-001.log"
    orphan_log = logs_dir / "octa-999.log"
    orphan_stderr = logs_dir / "octa-999_stderr.txt"
    legacy_orphan = logs_dir / "pa_pa_999_stderr.txt"
    active_log.write_text("active", encoding="utf-8")
    orphan_log.write_text("orphan", encoding="utf-8")
    orphan_stderr.write_text("orphan stderr", encoding="utf-8")
    legacy_orphan.write_text("legacy orphan", encoding="utf-8")

    (memory_root / "pa_active").mkdir()
    (memory_root / "pa_deleted").mkdir()
    (memory_root / "_collective_memory_").mkdir()

    assistants = [{"id": "pa_active", "name": "octa-001"}]

    pa_manager.cleanup_orphaned_pa_resources(assistants)

    assert active_log.exists()
    assert not orphan_log.exists()
    assert not orphan_stderr.exists()
    assert not legacy_orphan.exists()
    assert (memory_root / "pa_active").exists()
    assert not (memory_root / "pa_deleted").exists()
    assert (memory_root / "_collective_memory_").exists()


def test_load_assistants_triggers_orphan_cleanup(tmp_path, monkeypatch):
    your_data = tmp_path / "your_data"
    your_data.mkdir()
    monkeypatch.setattr(pa_manager, "_PA_PATH", your_data / "assistants.json")

    assistants_payload = [{"id": "pa_active", "name": "octa-001", "skills": [], "channels": [], "config": {}, "memory_id": "pa_active", "created_at": "2026-03-15T00:00:00+00:00"}]
    (your_data / "assistants.json").write_text(json.dumps(assistants_payload), encoding="utf-8")

    called = {"value": False}

    def _cleanup(assistants):
        called["value"] = assistants == assistants_payload

    monkeypatch.setattr(pa_manager, "cleanup_orphaned_pa_resources", _cleanup)

    loaded = pa_manager.load_assistants()

    assert loaded == assistants_payload
    assert called["value"] is True