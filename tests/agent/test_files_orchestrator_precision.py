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


def test_filter_precise_search_results_excludes_generated_manifest_artifacts(
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
    monkeypatch.setattr(orchestrator, "_is_temp_or_test_artifact", lambda _path: False)

    manifests_dir = your_data_root / "manifests" / "files"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    real_dir = tmp_path / "docs"
    real_dir.mkdir()

    real_payslip = real_dir / "Payslip_Jan.pdf"
    manifest_json = manifests_dir / "payslip_20260317_231742_377626.json"
    manifest_txt = manifests_dir / "payslip_20260317_231742_377626.txt"
    real_payslip.write_text("jan", encoding="utf-8")
    manifest_json.write_text("{}", encoding="utf-8")
    manifest_txt.write_text("manifest", encoding="utf-8")

    filtered = orchestrator._filter_precise_search_results(
        "How many payslips are there in my computer?",
        {
            "results": [
                {"path": str(real_payslip), "name": real_payslip.name, "type": "file"},
                {"path": str(manifest_json), "name": manifest_json.name, "type": "file"},
                {"path": str(manifest_txt), "name": manifest_txt.name, "type": "file"},
            ],
            "count": 3,
            "file_path": str(real_payslip),
        },
    )

    assert filtered["count"] == 1
    assert [item["path"] for item in filtered["results"]] == [str(real_payslip)]


def test_direct_copy_from_files_context_uses_single_folder_context(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    source_folder = tmp_path / "Neo"
    source_folder.mkdir()
    (source_folder / "note.txt").write_text("neo", encoding="utf-8")

    destination_root = tmp_path / "dest"
    destination_root.mkdir()

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "directory_path": str(source_folder),
                "selected_paths": [str(source_folder)],
            },
        },
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    artifacts_out: dict[str, str] = {}
    result = orchestrator._try_direct_copy_from_manifest(
        f"Can you copy Neo folder to {destination_root}?",
        artifacts_out,
    )

    copied_folder = destination_root / "Neo"
    assert result is not None
    assert result["status"] == "success"
    assert copied_folder.exists()
    assert artifacts_out["file_path"] == str(copied_folder)


def test_direct_copy_from_files_context_can_make_adjacent_copy(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    source_folder = tmp_path / "Neo"
    source_folder.mkdir()
    (source_folder / "note.txt").write_text("neo", encoding="utf-8")

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "directory_path": str(source_folder),
                "selected_paths": [str(source_folder)],
            },
        },
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    result = orchestrator._try_direct_copy_from_manifest(
        "Can you make a copy of it?",
        {},
    )

    copied_folder = tmp_path / "Neo - Copy"
    assert result is not None
    assert result["status"] == "success"
    assert copied_folder.exists()


def test_direct_copy_from_manifest_accepts_explicit_absolute_source_path(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    source_folder = tmp_path / "Neo"
    source_folder.mkdir()
    (source_folder / "note.txt").write_text("neo", encoding="utf-8")
    destination_root = tmp_path / "Downloads"
    destination_root.mkdir()

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {"agent": "files", "resolved_entities": {}},
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    artifacts_out: dict[str, str] = {}
    result = orchestrator._try_direct_copy_from_manifest(
        f"Can you copy {source_folder} folder to {destination_root}?",
        artifacts_out,
    )

    copied_folder = destination_root / "Neo"
    assert result is not None
    assert result["status"] == "success"
    assert copied_folder.exists()
    assert artifacts_out["file_path"] == str(copied_folder)


def test_direct_copy_from_manifest_copies_multiple_selected_items_to_new_folder(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    first_zip = tmp_path / "Neo.zip"
    second_zip = tmp_path / "Text.zip"
    first_zip.write_text("zip", encoding="utf-8")
    second_zip.write_text("zip", encoding="utf-8")
    manifest_path = tmp_path / "active_manifest.txt"
    manifest_path.write_text(f"{first_zip}\n{second_zip}\n", encoding="utf-8")
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "selected_paths": [str(first_zip), str(second_zip)],
                "listed_files": [
                    {"path": str(first_zip), "name": first_zip.name, "type": "file"},
                    {"path": str(second_zip), "name": second_zip.name, "type": "file"},
                ],
            },
        },
    )
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", manifest_path)
    def _fake_collect_files_to_folder(file_paths, destination):
        captured["paths"] = list(file_paths)
        captured["destination"] = destination
        return {
            "status": "success",
            "copied_count": len(file_paths),
            "destination": destination,
            "skipped": [],
        }

    monkeypatch.setattr(
        file_ops,
        "collect_files_to_folder",
        _fake_collect_files_to_folder,
    )

    result = orchestrator._try_direct_copy_from_manifest(
        "Can copy both of them to a new folder?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert captured["destination"]
    assert captured["paths"] == [str(first_zip), str(second_zip)]
    assert Path(captured["destination"]).name.startswith("Collected Files")


def test_direct_copy_from_manifest_uses_selected_paths_when_manifest_is_missing(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    first_zip = tmp_path / "Neo.zip"
    second_zip = tmp_path / "Text.zip"
    first_zip.write_text("zip", encoding="utf-8")
    second_zip.write_text("zip", encoding="utf-8")
    missing_manifest = tmp_path / "missing_manifest.txt"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "selected_paths": [str(first_zip), str(second_zip)],
                "listed_files": [
                    {"path": str(first_zip), "name": first_zip.name, "type": "file"},
                    {"path": str(second_zip), "name": second_zip.name, "type": "file"},
                ],
            },
        },
    )
    monkeypatch.setattr(file_ops, "_DEFAULT_MANIFEST", missing_manifest)

    def _fake_collect_files_to_folder(file_paths, destination):
        captured["paths"] = list(file_paths)
        captured["destination"] = destination
        return {
            "status": "success",
            "copied_count": len(file_paths),
            "destination": destination,
            "skipped": [],
        }

    monkeypatch.setattr(file_ops, "collect_files_to_folder", _fake_collect_files_to_folder)

    result = orchestrator._try_direct_copy_from_manifest(
        "Can copy both of them to a new folder?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert captured["paths"] == [str(first_zip), str(second_zip)]
    assert Path(str(captured["destination"])).name.startswith("Collected Files")


def test_direct_copy_from_manifest_resolves_the_one_in_parent_hint(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    hrishikesh_folder = tmp_path / "Hrishikesh" / "Neo"
    hrishikesh_folder.mkdir(parents=True)
    (hrishikesh_folder / "one.txt").write_text("1", encoding="utf-8")

    other_folder = tmp_path / "Program Files" / "McAfee" / "neo"
    other_folder.mkdir(parents=True)

    destination_root = tmp_path / "Downloads"
    destination_root.mkdir()

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "listed_files": [
                    {"path": str(hrishikesh_folder), "name": hrishikesh_folder.name, "type": "folder"},
                    {"path": str(other_folder), "name": other_folder.name, "type": "folder"},
                ],
                "selected_paths": [str(hrishikesh_folder), str(other_folder)],
            },
        },
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    result = orchestrator._try_direct_copy_from_manifest(
        f"Can you copy the one in Hrishikesh to {destination_root}?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert (destination_root / "Neo").exists()


def test_direct_move_from_context_resolves_the_one_in_parent_hint(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    hrishikesh_folder = tmp_path / "Hrishikesh" / "Neo"
    hrishikesh_folder.mkdir(parents=True)
    (hrishikesh_folder / "one.txt").write_text("1", encoding="utf-8")

    other_folder = tmp_path / "Program Files" / "McAfee" / "neo"
    other_folder.mkdir(parents=True)

    destination_root = tmp_path / "Downloads"
    destination_root.mkdir()

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "listed_files": [
                    {"path": str(hrishikesh_folder), "name": hrishikesh_folder.name, "type": "folder"},
                    {"path": str(other_folder), "name": other_folder.name, "type": "folder"},
                ],
                "selected_paths": [str(hrishikesh_folder), str(other_folder)],
            },
        },
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    result = orchestrator._try_direct_move_from_context(
        f"Can you move the one in Hrishikesh to {destination_root}?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert not hrishikesh_folder.exists()
    assert (destination_root / "Neo").exists()


def test_direct_delete_from_context_resolves_the_one_in_parent_hint(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    hrishikesh_folder = tmp_path / "Hrishikesh" / "Neo"
    hrishikesh_folder.mkdir(parents=True)
    (hrishikesh_folder / "one.txt").write_text("1", encoding="utf-8")

    other_folder = tmp_path / "Program Files" / "McAfee" / "neo"
    other_folder.mkdir(parents=True)

    deleted: dict[str, object] = {}

    def _fake_delete_file(path: str, permanent: bool = False):
        deleted["path"] = path
        deleted["permanent"] = permanent
        return {
            "status": "success",
            "message": f"Moved to Recycle Bin: {path}",
        }

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "listed_files": [
                    {"path": str(hrishikesh_folder), "name": hrishikesh_folder.name, "type": "folder"},
                    {"path": str(other_folder), "name": other_folder.name, "type": "folder"},
                ],
                "selected_paths": [str(hrishikesh_folder), str(other_folder)],
            },
        },
    )
    monkeypatch.setattr(
        "src.files.features.file_ops.delete_file",
        _fake_delete_file,
    )

    result = orchestrator._try_direct_delete_from_context(
        "Can you delete the one in Hrishikesh?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert deleted["path"] == str(hrishikesh_folder)


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
        "How many payslips are there in my computer?"
    )

    assert parsed is not None
    assert parsed["mode"] == "count_search"
    assert parsed["term"] == "payslip"
    assert parsed["limit"] == 0


def test_parse_precise_named_image_search_with_name_phrase() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "Is there any image file name octa on my computer?"
    )

    assert parsed is not None
    assert parsed["mode"] == "named_search"
    assert parsed["term"] == "octa"
    assert parsed["include_folders"] is False
    assert "png" in parsed["extensions"]


def test_parse_precise_image_search_containing_name_phrase() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "Are there any images on my computer containing the name octa?"
    )

    assert parsed is not None
    assert parsed["mode"] == "named_search"
    assert parsed["term"] == "octa"
    assert parsed["include_folders"] is False


def test_parse_scoped_named_search_for_downloads_folder() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = getattr(orchestrator, "_parse_scoped_named_search")(
        "Is there a folder named Text in Downloads?"
    )

    assert parsed is not None
    assert parsed["term"] == "Text"
    assert parsed["match_mode"] == "exact"
    assert parsed["item_type"] == "folder"
    assert parsed["scope_label"] == "Downloads"
    assert parsed["directory"].endswith("Downloads")


def test_parse_scoped_named_search_for_contains_name_query() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = getattr(orchestrator, "_parse_scoped_named_search")(
        "Is there a folder containing the name Text in Downloads?"
    )

    assert parsed is not None
    assert parsed["term"] == "Text"
    assert parsed["match_mode"] == "contains"
    assert parsed["item_type"] == "folder"


def test_parse_scoped_multi_named_search_for_downloads_zip_files() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = getattr(orchestrator, "_parse_scoped_multi_named_search")(
        "Are there zip files named Neo and Text in Downloads?"
    )

    assert parsed is not None
    assert parsed["terms"] == ["Neo", "Text"]
    assert parsed["item_type"] == "file"
    assert parsed["extensions"] == ["zip"]
    assert parsed["scope_label"] == "Downloads"


def test_try_scoped_named_search_handles_multi_named_downloads_lookup(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    neo_zip = downloads / "Neo.zip"
    text_zip = downloads / "Text.zip"
    neo_zip.write_text("neo", encoding="utf-8")
    text_zip.write_text("text", encoding="utf-8")

    monkeypatch.setattr(orchestrator, "_system_folder_path", lambda keyword: downloads)
    monkeypatch.setattr(
        file_ops,
        "list_directory",
        lambda path, limit=500: {
            "status": "success",
            "path": str(downloads),
            "entries": [
                {"name": "Neo.zip", "type": "file"},
                {"name": "Text.zip", "type": "file"},
                {"name": "Other.zip", "type": "file"},
            ],
        },
    )

    saved = {}

    def _fake_auto_save(result, query=""):
        saved["result"] = result
        saved["query"] = query
        return result

    monkeypatch.setattr(context_manifest, "auto_save_files_context", _fake_auto_save)

    result = getattr(orchestrator, "_try_scoped_named_search")(
        "Are there zip files named Neo and Text in Downloads?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Neo.zip" in result["message"]
    assert "Text.zip" in result["message"]
    assert saved["result"]["count"] == 2
    assert len(saved["result"]["results"]) == 2


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


def test_scoped_named_search_filters_to_exact_name(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    exact_folder = tmp_path / "Downloads" / "Text"
    partial_folder = tmp_path / "Downloads" / "Text_Folder"
    exact_folder.mkdir(parents=True)
    partial_folder.mkdir(parents=True)

    monkeypatch.setattr(
        orchestrator,
        "_system_folder_path",
        lambda keyword: tmp_path / "Downloads",
    )

    search_module = importlib.import_module("src.files.features.search")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    monkeypatch.setattr(
        search_module,
        "search_by_name",
        lambda term, directory="", recursive=True, limit=50: {
            "status": "success",
            "results": [
                {"path": str(exact_folder), "type": "folder", "name": "Text"},
                {"path": str(partial_folder), "type": "folder", "name": "Text_Folder"},
            ],
            "count": 2,
        },
    )
    monkeypatch.setattr(context_manifest, "auto_save_files_context", lambda result, query="": result)

    result = getattr(orchestrator, "_try_scoped_named_search")(
        "Is there a folder named Text in Downloads?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert str(exact_folder) in result["message"]
    assert str(partial_folder) not in result["message"]


def test_precise_full_computer_named_search_filters_to_exact_stem(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    search_module = importlib.import_module("src.files.features.search")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    exact_file = tmp_path / "octa.png"
    partial_file = tmp_path / "octa_banner.png"
    exact_file.write_text("exact", encoding="utf-8")
    partial_file.write_text("partial", encoding="utf-8")

    monkeypatch.setattr(
        search_module,
        "search_file_all_drives",
        lambda query, extensions=None, limit=50, include_folders=True: {
            "status": "success",
            "results": [
                {"path": str(exact_file), "type": "file", "name": exact_file.name},
                {"path": str(partial_file), "type": "file", "name": partial_file.name},
            ],
            "count": 2,
            "file_path": str(exact_file),
        },
    )
    monkeypatch.setattr(orchestrator, "_filter_precise_search_results", lambda user_query, result: result)
    monkeypatch.setattr(orchestrator, "_stage_precise_search_results", lambda term, result: result)
    monkeypatch.setattr(context_manifest, "auto_save_files_context", lambda result, query="": result)

    result = getattr(orchestrator, "_try_precise_full_computer_search")(
        "Is there any image file named octa on my computer?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert str(exact_file) in result["message"]
    assert str(partial_file) not in result["message"]


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


def test_try_direct_zip_from_files_context_resolves_the_one_in_parent_hint(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    archives = importlib.import_module("src.files.features.archives")

    hrishikesh_folder = tmp_path / "Hrishikesh" / "Neo"
    hrishikesh_folder.mkdir(parents=True)
    other_folder = tmp_path / "Program Files" / "McAfee" / "neo"
    other_folder.mkdir(parents=True)
    zip_output = tmp_path / "Neo.zip"

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent="": {
            "resolved_entities": {
                "listed_files": [
                    {"path": str(hrishikesh_folder), "name": hrishikesh_folder.name, "type": "folder"},
                    {"path": str(other_folder), "name": other_folder.name, "type": "folder"},
                ],
                "selected_paths": [str(hrishikesh_folder), str(other_folder)],
            }
        },
    )
    monkeypatch.setattr(orchestrator, "_build_archive_output_path", lambda folder_name: zip_output)
    monkeypatch.setattr(archives, "zip_folder", lambda folder_path, output_path: {"status": "success", "file_path": output_path})
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    result = getattr(orchestrator, "_try_direct_zip_from_files_context")(
        "Can you zip the one in Hrishikesh?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["file_path"] == str(zip_output)


def test_try_direct_rename_from_files_context_resolves_the_one_in_parent_hint(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    hrishikesh_folder = tmp_path / "Hrishikesh" / "Neo"
    hrishikesh_folder.mkdir(parents=True)
    other_folder = tmp_path / "Program Files" / "McAfee" / "neo"
    other_folder.mkdir(parents=True)

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent="": {
            "resolved_entities": {
                "listed_files": [
                    {"path": str(hrishikesh_folder), "name": hrishikesh_folder.name, "type": "folder"},
                    {"path": str(other_folder), "name": other_folder.name, "type": "folder"},
                ],
                "selected_paths": [str(hrishikesh_folder), str(other_folder)],
            }
        },
    )
    monkeypatch.setattr(
        file_ops,
        "rename_file",
        lambda path, new_name: {"status": "success", "message": "Rename successful.", "new_path": str(Path(path).with_name(new_name))},
    )

    result = getattr(orchestrator, "_try_direct_rename_from_files_context")(
        "Can you rename the one in Hrishikesh to Neo-123?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["file_path"].endswith("Neo-123")


def test_ambiguous_copy_followup_returns_numbered_clarification(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    first = tmp_path / "Hrishikesh" / "Neo"
    first.mkdir(parents=True)
    second = tmp_path / "Program Files" / "McAfee" / "neo"
    second.mkdir(parents=True)
    captured_write: dict[str, object] = {}

    def _fake_write_context(**kwargs):
        captured_write.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent="": {
            "topic": "file_search",
            "awaiting": "file_action",
            "resolved_entities": {
                "listed_files": [
                    {"path": str(first), "name": first.name, "type": "folder"},
                    {"path": str(second), "name": second.name, "type": "folder"},
                ],
                "selected_paths": [str(first), str(second)],
            }
        },
    )
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", _fake_write_context)

    result = getattr(orchestrator, "_try_direct_copy_from_manifest")(
        "Can you copy that to Downloads?",
        {},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Reply with 1, 2, or 3" in result["message"]
    assert str(first) in result["message"]
    assert captured_write["pending_selection"] == {
        "kind": "contextual_path_choice",
        "action_label": "copy",
        "original_query": "Can you copy that to Downloads?",
        "candidate_paths": [str(first), str(second)],
        "rephrase_index": 3,
    }


def test_numeric_selection_replays_pending_copy_request(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    first = tmp_path / "Hrishikesh" / "Neo.zip"
    first.parent.mkdir(parents=True)
    first.write_text("neo", encoding="utf-8")

    second = tmp_path / "Program Files" / "McAfee" / "neo.zip"
    second.parent.mkdir(parents=True)
    second.write_text("neo-2", encoding="utf-8")

    destination = tmp_path / "Downloads"
    destination.mkdir()

    state = {
        "topic": "file_search",
        "awaiting": "file_action",
        "resolved_entities": {
            "listed_files": [
                {"path": str(first), "name": first.name, "type": "file"},
                {"path": str(second), "name": second.name, "type": "file"},
            ],
            "selected_paths": [str(first), str(second)],
        },
        "pending_selection": {
            "kind": "contextual_path_choice",
            "action_label": "copy",
            "original_query": f"Can you copy that to {destination}?",
            "candidate_paths": [str(first), str(second)],
            "rephrase_index": 3,
        },
    }

    def _fake_read_context(agent=""):
        return state

    def _fake_write_context(**kwargs):
        state.clear()
        state.update({
            "topic": kwargs["topic"],
            "awaiting": kwargs.get("awaiting"),
            "resolved_entities": kwargs["resolved_entities"],
        })
        pending = kwargs.get("pending_selection")
        if pending:
            state["pending_selection"] = pending
        return {"status": "success"}

    def _fake_auto_save_files_context(result, query):
        file_path = Path(str(result.get("file_path", "") or "").strip())
        state.clear()
        state.update({
            "topic": "file_search",
            "awaiting": "file_action",
            "resolved_entities": {
                "listed_files": [
                    {"path": str(file_path), "name": file_path.name, "type": "file"},
                ],
                "selected_paths": [str(file_path)],
                "file_path": str(file_path),
            },
        })
        return result

    monkeypatch.setattr("src.agent.manifest.context_manifest.read_context", _fake_read_context)
    monkeypatch.setattr("src.agent.manifest.context_manifest.write_context", _fake_write_context)
    monkeypatch.setattr("src.agent.manifest.context_manifest.auto_save_files_context", _fake_auto_save_files_context)
    def _fake_copy_file(source, dest):
        copied_path = Path(dest) / Path(source).name
        copied_path.parent.mkdir(parents=True, exist_ok=True)
        copied_path.write_text(Path(source).read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "status": "success",
            "destination": str(copied_path),
        }

    monkeypatch.setattr(file_ops, "copy_file", _fake_copy_file)

    artifacts: dict[str, str] = {}
    result = orchestrator.execute_with_llm_orchestration("1", artifacts_out=artifacts)

    assert result["status"] == "success"
    assert str(destination / first.name) in result["message"]
    assert artifacts["file_path"] == str(destination / first.name)
    assert state["resolved_entities"]["selected_paths"] == [str(destination / first.name)]
    assert "pending_selection" not in state


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
            if target.suffix:
                target.parent.mkdir(parents=True, exist_ok=True)
            else:
                target.mkdir(parents=True, exist_ok=True)
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
        return {
            "status": "success",
            "new_path": str(folder.with_name("Text-123")),
        }

    artifacts_out = {}

    monkeypatch.setattr(file_ops, "rename_file", _fake_rename_file)
    result = getattr(orchestrator, "_try_direct_rename_from_files_context")(
        "Rename it to Text-123",
        artifacts_out,
    )

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


def test_try_last_n_months_payslip_zip_uses_existing_context_subset(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    nov = tmp_path / "Payslip_2025_Nov.pdf"
    dec = tmp_path / "Payslip_2025_Dec.pdf"
    jan = tmp_path / "Payslip_2026_Jan.pdf"
    aug = tmp_path / "Payslip_2025_Aug.pdf"
    for path in (nov, dec, jan, aug):
        path.write_text(path.stem, encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_read_active_context_paths",
        lambda: [str(aug), str(dec), str(nov), str(jan)],
    )
    monkeypatch.setattr(orchestrator, "_is_temp_or_test_artifact", lambda path: False)

    captured = {}

    file_ops = importlib.import_module("src.files.features.file_ops")

    def _fake_save_search_manifest(paths, label="search_results", manifest_path=""):
        del manifest_path
        captured["paths"] = list(paths)
        return {
            "status": "success",
            "manifest_path": str(tmp_path / "subset_manifest.txt"),
            "manifest_id": "subset_manifest",
            "label": label,
        }

    def _fake_zip_files_from_manifest(manifest_path="", output_path=""):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("zip", encoding="utf-8")
        return {
            "status": "success",
            "file_path": output_path,
            "manifest_path": manifest_path,
        }

    monkeypatch.setattr(file_ops, "save_search_manifest", _fake_save_search_manifest)
    monkeypatch.setattr(file_ops, "zip_files_from_manifest", _fake_zip_files_from_manifest)

    artifacts_out = {}
    result = getattr(orchestrator, "_try_last_n_months_payslip_zip")(
        "Can you zip and send me last 3 months payslips?",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert captured["paths"] == [str(jan), str(dec), str(nov)]
    assert artifacts_out["file_path"].endswith("payslips_last_3_months.zip")


def test_try_last_n_months_payslip_send_uses_direct_file_when_only_one_match(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    jan = tmp_path / "Payslip_2026_Jan.pdf"
    jan.write_text("jan", encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_read_active_context_paths",
        lambda: [str(jan)],
    )
    monkeypatch.setattr(orchestrator, "_is_temp_or_test_artifact", lambda path: False)
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    artifacts_out = {}
    result = getattr(orchestrator, "_try_last_n_months_payslip_zip")(
        "Send me last one month payslips",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["file_path"] == str(jan)
    assert artifacts_out["file_path"] == str(jan)


def test_try_context_subset_zip_uses_last_n_files_from_saved_results(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    third = tmp_path / "three.txt"
    fourth = tmp_path / "four.txt"
    for path in (first, second, third, fourth):
        path.write_text(path.stem, encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_read_active_context_entries",
        lambda: [
            {"path": str(first), "type": "file", "name": first.name},
            {"path": str(second), "type": "file", "name": second.name},
            {"path": str(third), "type": "file", "name": third.name},
            {"path": str(fourth), "type": "file", "name": fourth.name},
        ],
    )
    monkeypatch.setattr(orchestrator, "_is_temp_or_test_artifact", lambda path: False)

    captured = {}

    def _fake_save_search_manifest(paths, label="search_results", manifest_path=""):
        del manifest_path
        captured["paths"] = list(paths)
        return {
            "status": "success",
            "manifest_path": str(tmp_path / "subset_manifest.txt"),
            "manifest_id": "subset_manifest",
            "label": label,
        }

    monkeypatch.setattr(file_ops, "save_search_manifest", _fake_save_search_manifest)
    monkeypatch.setattr(
        file_ops,
        "zip_files_from_manifest",
        lambda manifest_path="", output_path="": {
            "status": "success",
            "file_path": output_path,
            "manifest_path": manifest_path,
        },
    )

    artifacts_out = {}
    result = getattr(orchestrator, "_try_context_subset_zip")(
        "Can you zip last 2 files that the assistant searched?",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert captured["paths"] == [str(third), str(fourth)]
    assert artifacts_out["file_path"].endswith("subset_files_last_2.zip")


def test_try_context_subset_zip_filters_images_from_saved_results(tmp_path: Path, monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    file_ops = importlib.import_module("src.files.features.file_ops")

    image_one = tmp_path / "one.jpg"
    image_two = tmp_path / "two.png"
    doc = tmp_path / "notes.txt"
    for path in (image_one, image_two, doc):
        path.write_text(path.stem, encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_read_active_context_entries",
        lambda: [
            {"path": str(image_one), "type": "file", "name": image_one.name},
            {"path": str(doc), "type": "file", "name": doc.name},
            {"path": str(image_two), "type": "file", "name": image_two.name},
        ],
    )
    monkeypatch.setattr(orchestrator, "_is_temp_or_test_artifact", lambda path: False)

    captured = {}

    def _fake_save_search_manifest(paths, label="search_results", manifest_path=""):
        del manifest_path
        captured["paths"] = list(paths)
        return {
            "status": "success",
            "manifest_path": str(tmp_path / "subset_manifest.txt"),
            "manifest_id": "subset_manifest",
            "label": label,
        }

    monkeypatch.setattr(file_ops, "save_search_manifest", _fake_save_search_manifest)
    monkeypatch.setattr(
        file_ops,
        "zip_files_from_manifest",
        lambda manifest_path="", output_path="": {
            "status": "success",
            "file_path": output_path,
            "manifest_path": manifest_path,
        },
    )

    result = getattr(orchestrator, "_try_context_subset_zip")(
        "Zip 2 images",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert captured["paths"] == [str(image_one), str(image_two)]
    assert result["file_path"].endswith("subset_images_first_2.zip")


def test_try_specific_folder_count_query_prefers_exact_personal_folder(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    neo_folder = tmp_path / "Neo"
    neo_folder.mkdir()
    (neo_folder / "one.txt").write_text("1", encoding="utf-8")
    (neo_folder / "two.txt").write_text("2", encoding="utf-8")
    (neo_folder / "docs").mkdir()

    monkeypatch.setattr(
        orchestrator,
        "_resolve_named_folder_path",
        lambda folder_name, drive_letter="": neo_folder,
    )

    saved = {}
    monkeypatch.setattr(
        orchestrator,
        "_save_single_file_context",
        lambda path_str, query: saved.setdefault("call", (path_str, query)),
    )

    result = getattr(orchestrator, "_try_specific_folder_count_query")(
        "How many files and folders are there in Neo folder in C drive?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Total Files: 2" in result["message"]
    assert "Total Folders: 1" in result["message"]
    assert Path(result["file_path"]).exists()


def test_try_specific_drive_item_query_saves_folder_context(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    neo_folder = tmp_path / "Neo"
    neo_folder.mkdir()

    monkeypatch.setattr(
        orchestrator,
        "_resolve_named_folder_path",
        lambda folder_name, drive_letter="": neo_folder,
    )

    artifacts_out = {}

    result = getattr(orchestrator, "_try_specific_drive_item_query")(
        "Is there a folder named Neo on my C drive?",
        artifacts_out=artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert str(neo_folder) in result["message"]
    assert artifacts_out["file_path"] == str(neo_folder)


def test_specific_computer_item_lookup_saves_context_for_inside_that_followup(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    xpanse_folder = tmp_path / "xpanse"
    xpanse_folder.mkdir()
    (xpanse_folder / "only.txt").write_text("1", encoding="utf-8")

    saved_context = {}

    def _fake_auto_save(result, query=""):
        del query
        saved_context["resolved_entities"] = {
            "selected_paths": [str(xpanse_folder)],
            "listed_files": [{"path": str(xpanse_folder), "name": xpanse_folder.name, "type": "folder"}],
        }
        return result

    monkeypatch.setattr(
        orchestrator,
        "_scan_named_path_all_drives",
        lambda item_name, item_type="folder", limit=20: [xpanse_folder],
    )
    monkeypatch.setattr(context_manifest, "auto_save_files_context", _fake_auto_save)
    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {"resolved_entities": dict(saved_context.get("resolved_entities", {}))},
    )

    lookup_result = getattr(orchestrator, "_try_specific_computer_item_query")(
        "Is there a folder named xpanse on my computer?",
        artifacts_out={},
    )
    assert lookup_result is not None
    assert lookup_result["status"] == "success"

    followup_result = getattr(orchestrator, "_try_contextual_folder_count_query")(
        "How many files and folders are there inside that?",
        artifacts_out={},
    )

    assert followup_result is not None
    assert followup_result["status"] == "success"
    assert "Total Files: 1" in followup_result["message"]
    assert "Total Folders: 0" in followup_result["message"]


def test_try_contextual_folder_count_query_uses_saved_folder(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    neo_folder = tmp_path / "Neo"
    neo_folder.mkdir()
    (neo_folder / "one.txt").write_text("1", encoding="utf-8")
    (neo_folder / "nested").mkdir()
    (neo_folder / "nested" / "two.txt").write_text("2", encoding="utf-8")

    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {"resolved_entities": {"directory_path": str(neo_folder)}},
    )
    monkeypatch.setattr(
        context_manifest,
        "auto_save_files_context",
        lambda result, query="": result,
    )

    result = getattr(orchestrator, "_try_contextual_folder_count_query")(
        "How many files and folders are there inside it?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Total Files: 2" in result["message"]
    assert "Total Folders: 1" in result["message"]


def test_try_contextual_folder_count_query_resolves_one_inside_parent_hint(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    hrishikesh_folder = tmp_path / "Hrishikesh" / "Neo"
    hrishikesh_folder.mkdir(parents=True)
    (hrishikesh_folder / "one.txt").write_text("1", encoding="utf-8")
    nested = hrishikesh_folder / "sub"
    nested.mkdir()
    (nested / "two.txt").write_text("2", encoding="utf-8")

    other_folder = tmp_path / "Program Files" / "McAfee" / "neo"
    other_folder.mkdir(parents=True)
    (other_folder / "three.txt").write_text("3", encoding="utf-8")

    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.read_context",
        lambda agent=None: {
            "agent": "files",
            "resolved_entities": {
                "listed_files": [
                    {"path": str(hrishikesh_folder), "name": hrishikesh_folder.name, "type": "folder"},
                    {"path": str(other_folder), "name": other_folder.name, "type": "folder"},
                ],
                "selected_paths": [str(hrishikesh_folder), str(other_folder)],
            },
        },
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    result = getattr(orchestrator, "_try_contextual_folder_count_query")(
        "How many files and folders are there in the one inside Hrishikesh?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Total Files: 2" in result["message"]
    assert "Total Folders: 1" in result["message"]


def test_try_specific_computer_item_query_finds_folder_case_insensitively(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    neo_folder = tmp_path / "neo-123"
    neo_folder.mkdir()

    monkeypatch.setattr(
        orchestrator,
        "_scan_named_path_all_drives",
        lambda item_name, item_type="folder", limit=20: [neo_folder],
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    result = getattr(orchestrator, "_try_specific_computer_item_query")(
        "Is there a folder named Neo-123 on my computer?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert str(neo_folder) in result["message"]


def test_specific_computer_folder_count_query_builds_recursive_report(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    neo_folder = tmp_path / "Neo"
    neo_folder.mkdir()
    nested = neo_folder / "sub"
    nested.mkdir()
    (neo_folder / "one.txt").write_text("1", encoding="utf-8")
    (nested / "two.txt").write_text("2", encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_scan_named_path_all_drives",
        lambda item_name, item_type="folder", limit=10: [neo_folder],
    )
    monkeypatch.setattr(
        "src.agent.manifest.context_manifest.auto_save_files_context",
        lambda result, query="": result,
    )

    artifacts_out = {}
    result = getattr(orchestrator, "_try_specific_computer_folder_count_query")(
        "How many files and folders are there in Neo folder on my computer?",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Total Files: 2" in result["message"]
    assert "Total Folders: 1" in result["message"]
    assert Path(artifacts_out["file_path"]).exists()


def test_specific_computer_folder_count_query_accepts_absolute_path(tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    neo_folder = tmp_path / "neo-123"
    neo_folder.mkdir()
    (neo_folder / "one.txt").write_text("1", encoding="utf-8")
    nested = neo_folder / "Payslips"
    nested.mkdir()

    result = getattr(orchestrator, "_try_specific_computer_folder_count_query")(
        f"How many files and folders are there in {neo_folder}?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Total Files: 1" in result["message"]
    assert "Total Folders: 1" in result["message"]


def test_specific_computer_folder_count_query_prefers_context_after_rename(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    neo_folder = tmp_path / "Neo"
    neo_folder.mkdir()
    (neo_folder / "one.jpg").write_text("1", encoding="utf-8")
    nested = neo_folder / "Photos"
    nested.mkdir()
    (nested / "two.jpg").write_text("2", encoding="utf-8")

    monkeypatch.setattr(orchestrator, "_resolve_folder_path_from_files_context", lambda: neo_folder)
    monkeypatch.setattr(orchestrator, "_scan_named_path_all_drives", lambda item_name, item_type="folder", limit=10: [])

    result = getattr(orchestrator, "_try_specific_computer_folder_count_query")(
        "How many files and folders are there in Neo?",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert "Total Files: 2" in result["message"]
    assert "Total Folders: 1" in result["message"]


def test_try_report_from_files_context_creates_csv_report(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    image_one = tmp_path / "one.png"
    image_two = tmp_path / "two.jpg"
    image_one.write_text("1", encoding="utf-8")
    image_two.write_text("2", encoding="utf-8")
    manifest = tmp_path / "images_manifest.txt"
    manifest.write_text(f"{image_one}\n{image_two}\n", encoding="utf-8")

    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {
            "resolved_entities": {
                "file_manifest": str(manifest),
                "listed_files": [
                    {"path": str(image_one), "name": image_one.name, "type": "file"},
                    {"path": str(image_two), "name": image_two.name, "type": "file"},
                ],
            }
        },
    )

    result = getattr(orchestrator, "_try_report_from_files_context")(
        "Can you create a list of all image files and email it to me? It should contain the image file name, path and type.",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["file_path"].endswith(".csv")
    report_text = Path(result["file_path"]).read_text(encoding="utf-8")
    assert "summary_metric,summary_value" in report_text
    assert "group,label,count" in report_text
    assert "selected_columns,\"name, path, type\"" in report_text
    assert "name,path,type" in report_text
    assert "type,file,2" in report_text
    assert "extension,.jpg,1" in report_text
    assert "extension,.png,1" in report_text
    assert image_one.name in report_text
    assert str(image_two) in report_text


def test_try_full_computer_inventory_report_creates_report_file(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    rows = [
        {"name": "one.png", "path": str(tmp_path / "one.png"), "type": "file", "extension": ".png", "size_bytes": 1024, "size": "1.0 KB", "modified": "2026-03-19T10:00:00", "created": "2026-03-19T10:00:00"},
        {"name": "two.jpg", "path": str(tmp_path / "two.jpg"), "type": "file", "extension": ".jpg", "size_bytes": 2048, "size": "2.0 KB", "modified": "2026-03-19T10:00:00", "created": "2026-03-19T10:00:00"},
    ]

    monkeypatch.setattr(
        "src.files.features.search.search_file_all_drives",
        lambda query="", extensions=None, limit=0, include_folders=False: {
            "status": "success",
            "count": len(rows),
            "results": rows,
            "file_path": rows[0]["path"],
        },
    )
    monkeypatch.setattr(orchestrator, "_save_precise_search_context", lambda result, query: None)

    result = getattr(orchestrator, "_try_full_computer_inventory_report")(
        "Can you create a list of all image files and email it to me? It should contain the image file name, path and type.",
        artifacts_out={},
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["file_path"].endswith(".csv")
    report_text = Path(result["file_path"]).read_text(encoding="utf-8")
    assert "summary_metric,summary_value" in report_text
    assert "total_size_bytes,3072" in report_text
    assert "selected_columns,\"name, path, type\"" in report_text
    assert "name,path,type" in report_text
    assert "one.png" in report_text


def test_infer_report_fields_defaults_to_professional_schema() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    fields = getattr(orchestrator, "_infer_report_fields")("Create a report of all python files")

    assert fields == ["name", "path", "type", "extension", "size", "modified", "created"]


def test_infer_report_fields_keeps_requested_columns_and_adds_extension_when_requested() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    fields = getattr(orchestrator, "_infer_report_fields")(
        "Create a report with the file name, path, type, and size for image files"
    )

    assert fields == ["name", "path", "type", "size"]

    fields_with_extension = getattr(orchestrator, "_infer_report_fields")(
        "Create a report with the file name, path, type, extension, and size for image files"
    )

    assert fields_with_extension == ["name", "path", "type", "extension", "size"]


def test_try_reuse_existing_archive_from_context_returns_current_zip(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    archive_path = tmp_path / "payslips_last_4_months.zip"
    archive_path.write_text("zip", encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_resolve_single_copy_source_from_files_context",
        lambda: archive_path,
    )

    artifacts_out = {}
    result = getattr(orchestrator, "_try_reuse_existing_archive_from_context")(
        "Can you also mail me the zip that you created for payslips?",
        artifacts_out,
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["file_path"] == str(archive_path)
    assert artifacts_out["file_path"] == str(archive_path)
