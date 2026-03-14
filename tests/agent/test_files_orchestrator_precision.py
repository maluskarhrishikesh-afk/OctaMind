import importlib
import zipfile
from pathlib import Path


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


def test_merge_manifest_into_session_keeps_compact_file_context(tmp_path: Path, monkeypatch) -> None:
    skill_dag_engine = importlib.import_module("src.agent.workflows.skill_dag_engine")
    runtime_paths = importlib.import_module("src.agent.runtime_paths")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    manifest = tmp_path / "octa_manifest.txt"
    manifest.write_text("C:\\A\\one.pdf\nC:\\B\\two.pdf\n", encoding="utf-8")

    monkeypatch.setattr(runtime_paths, "get_existing_runtime_state_path", lambda *parts: manifest)
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
