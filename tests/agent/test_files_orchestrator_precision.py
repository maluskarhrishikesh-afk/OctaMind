import importlib
import json
import zipfile
from pathlib import Path


def test_save_search_manifest_updates_active_manifest_metadata(tmp_path: Path, monkeypatch) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"
    monkeypatch.setattr(file_ops, "_DEFAULT_OCTAMIND_DIR", your_data_root)
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", your_data_root / "octa_manifest.txt")
    monkeypatch.setattr(file_ops, "_MANIFESTS_DIR", your_data_root / "manifests" / "files")
    monkeypatch.setattr(file_ops, "_ACTIVE_MANIFEST_FILE", your_data_root / "active_file_manifest.json")

    source_a = tmp_path / "a.txt"
    source_b = tmp_path / "b.txt"
    source_a.write_text("a", encoding="utf-8")
    source_b.write_text("b", encoding="utf-8")

    result = file_ops.save_search_manifest([str(source_a), str(source_b)], label="Text")

    assert result["status"] == "success"
    assert Path(result["manifest_path"]).exists()
    active_payload = json.loads((your_data_root / "active_file_manifest.json").read_text(encoding="utf-8"))
    assert active_payload["manifest_path"] == result["manifest_path"]
    assert active_payload["manifest_id"] == result["manifest_id"]
    assert (your_data_root / "octa_manifest.txt").exists()


def test_zip_files_from_manifest_uses_active_manifest_when_not_explicit(tmp_path: Path, monkeypatch) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"
    monkeypatch.setattr(file_ops, "_DEFAULT_OCTAMIND_DIR", your_data_root)
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", your_data_root / "octa_manifest.txt")
    monkeypatch.setattr(file_ops, "_MANIFESTS_DIR", your_data_root / "manifests" / "files")
    monkeypatch.setattr(file_ops, "_ACTIVE_MANIFEST_FILE", your_data_root / "active_file_manifest.json")

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    matched_one = source_dir / "one.txt"
    matched_two = source_dir / "two.txt"
    matched_one.write_text("one", encoding="utf-8")
    matched_two.write_text("two", encoding="utf-8")

    manifest_result = file_ops.save_search_manifest([str(matched_one), str(matched_two)], label="Text")
    assert manifest_result["status"] == "success"

    zip_path = tmp_path / "active_subset.zip"
    result = file_ops.zip_files_from_manifest(output_path=str(zip_path))

    assert result["status"] == "success"
    assert result["manifest_path"] == manifest_result["manifest_path"]
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = sorted(Path(name).name for name in archive.namelist() if not name.endswith("/"))
    assert names == ["one.txt", "two.txt"]


def test_list_file_manifests_marks_active_and_returns_newest_first(tmp_path: Path, monkeypatch) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"
    monkeypatch.setattr(file_ops, "_DEFAULT_OCTAMIND_DIR", your_data_root)
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", your_data_root / "octa_manifest.txt")
    monkeypatch.setattr(file_ops, "_MANIFESTS_DIR", your_data_root / "manifests" / "files")
    monkeypatch.setattr(file_ops, "_ACTIVE_MANIFEST_FILE", your_data_root / "active_file_manifest.json")

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    older = file_ops.save_search_manifest([str(first)], label="Older")
    newer = file_ops.save_search_manifest([str(second)], label="Newer")

    result = file_ops.list_file_manifests(limit=10)

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["manifests"][0]["manifest_id"] == newer["manifest_id"]
    assert result["manifests"][0]["is_active"] is True
    assert result["manifests"][1]["manifest_id"] == older["manifest_id"]
    assert result["manifests"][1]["is_active"] is False


def test_delete_file_manifest_promotes_previous_manifest_when_active_deleted(tmp_path: Path, monkeypatch) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"
    monkeypatch.setattr(file_ops, "_DEFAULT_OCTAMIND_DIR", your_data_root)
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", your_data_root / "octa_manifest.txt")
    monkeypatch.setattr(file_ops, "_MANIFESTS_DIR", your_data_root / "manifests" / "files")
    monkeypatch.setattr(file_ops, "_ACTIVE_MANIFEST_FILE", your_data_root / "active_file_manifest.json")

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    older = file_ops.save_search_manifest([str(first)], label="Older")
    active = file_ops.save_search_manifest([str(second)], label="Active")

    result = file_ops.delete_file_manifest(manifest_id=active["manifest_id"])

    assert result["status"] == "success"
    assert result["was_active"] is True
    promoted = file_ops.get_active_file_manifest_metadata()
    assert promoted["manifest_id"] == older["manifest_id"]
    assert Path(promoted["manifest_path"]).exists()
    assert Path(active["manifest_path"]).exists() is False


def test_prune_stale_file_manifests_keeps_active_and_recent_entries(tmp_path: Path, monkeypatch) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"
    monkeypatch.setattr(file_ops, "_DEFAULT_OCTAMIND_DIR", your_data_root)
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", your_data_root / "octa_manifest.txt")
    monkeypatch.setattr(file_ops, "_MANIFESTS_DIR", your_data_root / "manifests" / "files")
    monkeypatch.setattr(file_ops, "_ACTIVE_MANIFEST_FILE", your_data_root / "active_file_manifest.json")

    stale_file = tmp_path / "stale.txt"
    recent_file = tmp_path / "recent.txt"
    active_file = tmp_path / "active.txt"
    stale_file.write_text("stale", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")
    active_file.write_text("active", encoding="utf-8")

    stale = file_ops.save_search_manifest([str(stale_file)], label="Stale")
    recent = file_ops.save_search_manifest([str(recent_file)], label="Recent")
    active = file_ops.save_search_manifest([str(active_file)], label="Active")

    stale_metadata = json.loads(Path(stale["manifest_path"]).with_suffix(".json").read_text(encoding="utf-8"))
    stale_metadata["written_at"] = "2000-01-01T00:00:00"
    Path(stale["manifest_path"]).with_suffix(".json").write_text(json.dumps(stale_metadata, indent=2), encoding="utf-8")

    result = file_ops.prune_stale_file_manifests(max_age_days=7)

    assert result["status"] == "success"
    assert result["deleted_count"] == 1
    assert stale["manifest_path"] in result["deleted"]
    assert Path(stale["manifest_path"]).exists() is False
    assert Path(recent["manifest_path"]).exists()
    assert Path(active["manifest_path"]).exists()
    assert file_ops.get_active_file_manifest_metadata()["manifest_id"] == active["manifest_id"]


def test_zip_files_from_manifest_only_zips_matched_subset(tmp_path: Path, monkeypatch) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"

    def _fake_get_your_data_dir(*parts: str, create: bool = False):
        target = your_data_root.joinpath(*parts)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(file_ops, "get_your_data_dir", _fake_get_your_data_dir)

    source_a = tmp_path / "folder_a"
    source_b = tmp_path / "folder_b"
    source_a.mkdir()
    source_b.mkdir()

    matched_one = source_a / "octa_bot.jpg"
    matched_two = source_b / "octa_bot_2.jpg"
    extra_file = source_a / "unrelated.jpg"

    matched_one.write_text("one", encoding="utf-8")
    matched_two.write_text("two", encoding="utf-8")
    extra_file.write_text("extra", encoding="utf-8")

    manifest = tmp_path / "octa_manifest.txt"
    manifest.write_text(f"{matched_one}\n{matched_two}\n", encoding="utf-8")

    zip_path = tmp_path / "subset.zip"
    result = file_ops.zip_files_from_manifest(
        manifest_path=str(manifest),
        output_path=str(zip_path),
    )

    assert result["status"] == "success"
    assert result["file_path"] == str(zip_path)
    assert Path(result["bundle_dir"]).is_dir()

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = sorted(Path(name).name for name in archive.namelist() if not name.endswith("/"))

    assert names == ["octa_bot.jpg", "octa_bot_2.jpg"]


def test_zip_files_from_manifest_ignores_archive_inputs_when_files_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    file_ops = importlib.import_module("src.files.features.file_ops")

    your_data_root = tmp_path / "your_data"

    def _fake_get_your_data_dir(*parts: str, create: bool = False):
        target = your_data_root.joinpath(*parts)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(file_ops, "get_your_data_dir", _fake_get_your_data_dir)

    docs = tmp_path / "docs"
    downloads = tmp_path / "Downloads"
    docs.mkdir()
    downloads.mkdir()

    payslip_a = docs / "Payslip_Jan.pdf"
    payslip_b = docs / "Payslip_Feb.pdf"
    stale_archive = downloads / "Payslips.zip"

    payslip_a.write_text("jan", encoding="utf-8")
    payslip_b.write_text("feb", encoding="utf-8")
    stale_archive.write_text("old-zip", encoding="utf-8")

    manifest = tmp_path / "octa_manifest.txt"
    manifest.write_text(
        f"{payslip_a}\n{payslip_b}\n{stale_archive}\n",
        encoding="utf-8",
    )

    zip_path = tmp_path / "payslips.zip"
    result = file_ops.zip_files_from_manifest(
        manifest_path=str(manifest),
        output_path=str(zip_path),
    )

    assert result["status"] == "success"
    assert result["filtered_archives"] == [str(stale_archive)]

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = sorted(Path(name).name for name in archive.namelist() if not name.endswith("/"))

    assert names == ["Payslip_Feb.pdf", "Payslip_Jan.pdf"]
    assert sorted(path.name for path in Path(result["bundle_dir"]).iterdir()) == [
        "Payslip_Feb.pdf",
        "Payslip_Jan.pdf",
    ]


def test_parse_precise_named_image_search() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "is there an image file named octa_bot on my computer?"
    )

    assert parsed is not None
    assert parsed["mode"] == "named_search"
    assert parsed["term"] == "octa_bot"
    assert "png" in parsed["extensions"]
    assert parsed["include_folders"] is False


def test_parse_precise_payslip_count_search() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "How many payslips are there on my computer?"
    )

    assert parsed is not None
    assert parsed["mode"] == "count_search"
    assert parsed["term"] == "payslip"
    assert parsed["limit"] == 0


def test_parse_scoped_named_search_for_downloads_folder() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = getattr(orchestrator, "_parse_scoped_named_search")(
        "Is there a folder named Text in Downloads?"
    )

    assert parsed is not None
    assert parsed["term"] == "Text"
    assert parsed["item_type"] == "folder"
    assert parsed["scope_label"] == "Downloads"
    assert parsed["directory"].endswith("Downloads")


def test_scoped_folder_count_query_lists_directory_and_saves_context(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    folder = tmp_path / "Downloads" / "Text"
    folder.mkdir(parents=True)

    monkeypatch.setattr(
        orchestrator,
        "_system_folder_path",
        lambda keyword: tmp_path / "Downloads",
    )

    search_module = importlib.import_module("src.files.features.search")
    file_ops = importlib.import_module("src.files.features.file_ops")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    monkeypatch.setattr(
        search_module,
        "search_by_name",
        lambda term, directory="", recursive=True, limit=50: {
            "status": "success",
            "results": [{"path": str(folder), "type": "folder", "name": "Text"}],
            "count": 1,
        },
    )
    monkeypatch.setattr(
        file_ops,
        "list_directory",
        lambda path, limit=200: {
            "status": "success",
            "path": str(folder),
            "entries": [
                {"name": "one.txt", "type": "file", "size_human": "1 B"},
                {"name": "two.txt", "type": "file", "size_human": "1 B"},
                {"name": "subdir", "type": "folder", "size_human": "-"},
            ],
            "files": 2,
            "folders": 1,
        },
    )

    saved = {}

    def _fake_auto_save(result, query=""):
        saved["result"] = result
        saved["query"] = query
        return result

    monkeypatch.setattr(context_manifest, "auto_save_files_context", _fake_auto_save)

    result = getattr(orchestrator, "_try_scoped_named_search")(
        "How many files are there in the folder named Text in Downloads?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "2 file(s) and 1 folder(s)" in result["message"]
    assert saved["result"]["path"] == str(folder)


def test_parse_filename_contains_search_for_images() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = getattr(orchestrator, "_parse_filename_contains_search")(
        "Find an image file containing octa in its filename"
    )

    assert parsed is not None
    assert parsed["term"] == "octa"
    assert parsed["include_folders"] is False
    assert "png" in parsed["extensions"]


def test_try_recycle_bin_query_uses_dedicated_tool(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    monkeypatch.setattr(
        file_ops,
        "get_recycle_bin_info",
        lambda: {
            "status": "success",
            "item_count": 7,
            "size": "10.0 MB",
            "message": "Recycle Bin currently contains 7 item(s) using 10.0 MB.",
        },
    )

    result = getattr(orchestrator, "_try_recycle_bin_query")(
        "How many files are there in the recycle bin of my computer?"
    )

    assert result is not None
    assert result["status"] == "success"
    assert "7 item(s)" in result["message"]


def test_filter_precise_search_results_drops_archives_for_non_archive_queries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    your_data_root = tmp_path / "your_data"

    def _fake_get_your_data_dir(*parts: str, create: bool = False):
        target = your_data_root.joinpath(*parts)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(orchestrator, "get_your_data_dir", _fake_get_your_data_dir)
    monkeypatch.setattr(orchestrator.tempfile, "gettempdir", lambda: str(tmp_path / "separate_temp_root"))

    payslip_pdf = tmp_path / "Payslip_March.pdf"
    archive_copy = tmp_path / "Downloads" / "Payslips.zip"
    archive_copy.parent.mkdir()
    payslip_pdf.write_text("pdf", encoding="utf-8")
    archive_copy.write_text("zip", encoding="utf-8")

    result = orchestrator.filter_precise_search_results(
        "How many payslips are there on my computer?",
        {
            "status": "success",
            "results": [
                {"path": str(payslip_pdf)},
                {"path": str(archive_copy)},
            ],
            "count": 2,
            "file_path": str(payslip_pdf),
        },
    )

    assert result["count"] == 1
    assert result["results"] == [{"path": str(payslip_pdf)}]
    assert result["filtered_archive_count"] == 1


def test_filter_precise_search_results_drops_temp_test_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    your_data_root = tmp_path / "your_data"
    temp_root = tmp_path / "temp_root"

    def _fake_get_your_data_dir(*parts: str, create: bool = False):
        target = your_data_root.joinpath(*parts)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(orchestrator, "get_your_data_dir", _fake_get_your_data_dir)
    monkeypatch.setattr(orchestrator.tempfile, "gettempdir", lambda: str(temp_root))

    real_payslip = tmp_path / "docs" / "Payslip_April.pdf"
    temp_payslip = temp_root / "pytest-of-user" / "pytest-1" / "Payslip_Test.pdf"
    real_payslip.parent.mkdir(parents=True)
    temp_payslip.parent.mkdir(parents=True)
    real_payslip.write_text("real", encoding="utf-8")
    temp_payslip.write_text("temp", encoding="utf-8")

    result = orchestrator.filter_precise_search_results(
        "How many payslips are there on my computer?",
        {
            "status": "success",
            "results": [
                {"path": str(real_payslip)},
                {"path": str(temp_payslip)},
            ],
            "count": 2,
            "file_path": str(real_payslip),
        },
    )

    assert result["count"] == 1
    assert result["results"] == [{"path": str(real_payslip)}]


def test_try_direct_zip_from_search_bundle_uses_saved_folder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")
    archives = importlib.import_module("src.files.features.archives")

    your_data_root = tmp_path / "your_data"
    bundle_dir = your_data_root / "archives" / "search_results" / "payslips_20260311_180000"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "Payslip_Jan.pdf").write_text("jan", encoding="utf-8")

    def _fake_get_your_data_dir(*parts: str, create: bool = False):
        target = your_data_root.joinpath(*parts)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def _fake_read_context(agent: str = ""):
        assert agent == "files"
        return {"resolved_entities": {"search_bundle_dir": str(bundle_dir)}}

    def _fake_zip_folder(folder_path: str, output_path: str):
        assert Path(folder_path) == bundle_dir
        assert Path(output_path) == your_data_root / "archives" / f"{bundle_dir.name}.zip"
        Path(output_path).write_text("zip", encoding="utf-8")
        return {"status": "success", "file_path": output_path}

    monkeypatch.setattr(orchestrator, "get_your_data_dir", _fake_get_your_data_dir)
    monkeypatch.setattr(context_manifest, "read_context", _fake_read_context)
    monkeypatch.setattr(archives, "zip_folder", _fake_zip_folder)

    artifacts_out = {}
    direct_zip = getattr(orchestrator, "_try_direct_zip_from_search_bundle")
    result = direct_zip("Zip searched payslips", artifacts_out)

    assert result is not None
    assert result["status"] == "success"
    assert artifacts_out["file_path"].endswith(f"{bundle_dir.name}.zip")


def test_conversation_state_uses_compact_files_context_not_last_found_paths(monkeypatch) -> None:
    conversation_state = importlib.import_module("src.agent.context.conversation_state")

    monkeypatch.setattr(
        conversation_state,
        "read_context",
        lambda agent="": {
            "resolved_entities": {
                "search_bundle_dir": r"C:\bundle_dir",
                "file_manifest": r"C:\octa_manifest.txt",
                "found_count": 12,
            }
        },
    )

    history = [
        {
            "role": "assistant",
            "content": "I found some files.",
            "search_paths": [r"C:\A\one.pdf", r"C:\B\two.pdf"],
        }
    ]

    enriched = conversation_state.build_structured_query("zip them", history)

    assert '"last_found_paths"' not in enriched
    assert '"last_found_bundle_dir"' in enriched
    assert 'bundle_dir' in enriched
    assert '"file_manifest"' in enriched
    assert 'octa_manifest.txt' in enriched
    assert '"found_count": 12' in enriched


def test_try_list_names_from_files_context_returns_all_saved_names(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {
            "resolved_entities": {
                "directory_path": r"C:\Users\malus\Downloads\Text",
                "listed_files": [
                    {"index": 0, "path": r"C:\Users\malus\Downloads\Text\one.json", "name": "one.json", "type": "file"},
                    {"index": 1, "path": r"C:\Users\malus\Downloads\Text\two.json", "name": "two.json", "type": "file"},
                    {"index": 2, "path": r"C:\Users\malus\Downloads\Text\three.json", "name": "three.json", "type": "file"},
                ],
            }
        },
    )

    result = getattr(orchestrator, "_try_list_names_from_files_context")(
        "Can you type the file names here?"
    )

    assert result is not None
    assert result["status"] == "success"
    assert "1. **one.json**" in result["message"]
    assert "2. **two.json**" in result["message"]
    assert "3. **three.json**" in result["message"]


def test_try_direct_zip_from_files_context_uses_directory_path(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")
    archives = importlib.import_module("src.files.features.archives")

    your_data_root = tmp_path / "your_data"
    folder = tmp_path / "Downloads" / "Text-123"
    folder.mkdir(parents=True)
    (folder / "one.txt").write_text("one", encoding="utf-8")

    def _fake_get_your_data_dir(*parts: str, create: bool = False):
        target = your_data_root.joinpath(*parts)
        if create:
            target.parent.mkdir(parents=True, exist_ok=True) if target.suffix else target.mkdir(parents=True, exist_ok=True)
        return target

    def _fake_read_context(agent: str = ""):
        assert agent == "files"
        return {
            "resolved_entities": {
                "directory_path": str(folder),
                "selected_paths": [str(folder)],
                "selection_kind": "directory_listing",
            }
        }

    def _fake_zip_folder(folder_path: str, output_path: str):
        assert Path(folder_path) == folder
        assert Path(output_path) == your_data_root / "archives" / "Text-123.zip"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("zip", encoding="utf-8")
        return {"status": "success", "file_path": output_path}

    monkeypatch.setattr(orchestrator, "get_your_data_dir", _fake_get_your_data_dir)
    monkeypatch.setattr(context_manifest, "read_context", _fake_read_context)
    monkeypatch.setattr(archives, "zip_folder", _fake_zip_folder)

    artifacts_out = {}
    result = getattr(orchestrator, "_try_direct_zip_from_files_context")(
        "Can you zip that and send it to me?",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert artifacts_out["file_path"].endswith("Text-123.zip")


def test_try_direct_rename_from_files_context_uses_current_directory_path(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")
    file_ops = importlib.import_module("src.files.features.file_ops")

    folder = tmp_path / "Text"
    folder.mkdir()

    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {
            "resolved_entities": {
                "directory_path": str(folder),
                "selected_paths": [str(folder)],
            }
        },
    )

    captured = {}

    def _fake_rename_file(path: str, new_name: str):
        captured["path"] = path
        captured["new_name"] = new_name
        return {"status": "success", "message": "Renamed to Text-123", "new_path": str(folder.parent / new_name)}

    monkeypatch.setattr(file_ops, "rename_file", _fake_rename_file)

    artifacts_out = {}
    result = getattr(orchestrator, "_try_direct_rename_from_files_context")(
        "Rename it to Text-123",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert captured["path"] == str(folder)
    assert captured["new_name"] == "Text-123"
    assert artifacts_out["file_path"].endswith("Text-123")


def test_strip_injected_blocks_removes_diary_before_followup_parsing() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    stripped = getattr(orchestrator, "_strip_injected_blocks")(
        "Rename it to Text-123\n\n## Conversation Diary\n- [2026-01-01] files/zip: Zip that and send it to me"
    )

    assert stripped == "Rename it to Text-123"


def test_merge_manifest_into_session_keeps_compact_file_context(tmp_path: Path, monkeypatch) -> None:
    skill_dag_engine = importlib.import_module("src.agent.workflows.skill_dag_engine")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")
    file_ops = importlib.import_module("src.files.features.file_ops")

    manifest = tmp_path / "octa_manifest.txt"
    manifest.write_text("C:\\A\\one.pdf\nC:\\B\\two.pdf\n", encoding="utf-8")

    monkeypatch.setattr(file_ops, "get_active_file_manifest_metadata", lambda: {})
    monkeypatch.setattr(file_ops, "resolve_file_manifest_path", lambda manifest_path="": manifest)
    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {"resolved_entities": {"search_bundle_dir": r"C:\bundle_dir"}},
    )

    merge_manifest = getattr(skill_dag_engine, "_merge_manifest_into_session")
    merged = merge_manifest({})

    assert "last_found_paths" not in merged
    assert merged["last_found_bundle_dir"] == r"C:\bundle_dir"
    assert merged["file_manifest"] == str(manifest)
    assert merged["found_count"] == 2
    assert "last_found_file_path" not in merged
