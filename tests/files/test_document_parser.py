from __future__ import annotations

import importlib
from pathlib import Path


def test_resolve_liteparse_command_prefers_lit(monkeypatch) -> None:
    module = importlib.import_module("src.files.features.document_parser")
    resolve_command = getattr(module, "_resolve_liteparse_command")

    monkeypatch.delenv("LITEPARSE_COMMAND", raising=False)
    monkeypatch.setattr(module.shutil, "which", lambda name: "C:/Tools/lit.cmd" if name == "lit" else None)

    command, source = resolve_command()

    assert command == ["C:/Tools/lit.cmd"]
    assert source == "lit"


def test_resolve_liteparse_command_uses_env_override(monkeypatch) -> None:
    module = importlib.import_module("src.files.features.document_parser")
    resolve_command = getattr(module, "_resolve_liteparse_command")

    monkeypatch.setenv("LITEPARSE_COMMAND", 'python -m liteparse_proxy')

    command, source = resolve_command()

    assert command == ["python", "-m", "liteparse_proxy"]
    assert source == "env"


def test_check_liteparse_installation_returns_helpful_error(monkeypatch) -> None:
    module = importlib.import_module("src.files.features.document_parser")

    monkeypatch.setattr(module, "_resolve_liteparse_command", lambda: (None, None))

    result = module.check_liteparse_installation()

    assert result["status"] == "error"
    assert "npm i -g @llamaindex/liteparse" in result["message"]


def test_parse_document_spatially_returns_preview(monkeypatch, tmp_path: Path) -> None:
    module = importlib.import_module("src.files.features.document_parser")

    source = tmp_path / "invoice.pdf"
    source.write_text("fake-pdf", encoding="utf-8")
    output = tmp_path / "invoice_liteparse.json"

    def _fake_run(args, _timeout_seconds):
        output.write_text('{"pages": [{"text": "hello"}], "metadata": {"title": "Invoice"}}', encoding="utf-8")
        return {"status": "success", "command": ["lit", *args]}

    monkeypatch.setattr(module, "_run_liteparse", _fake_run)

    result = module.parse_document_spatially(str(source), output_path=str(output))

    assert result["status"] == "success"
    assert result["output_path"] == str(output)
    assert result["json_top_level_keys"] == ["pages", "metadata"]
    assert result["page_count"] == 1
    assert "hello" in result["preview"]


def test_screenshot_document_pages_uses_default_output_dir(monkeypatch, tmp_path: Path) -> None:
    module = importlib.import_module("src.files.features.document_parser")

    source = tmp_path / "contract.pdf"
    source.write_text("fake-pdf", encoding="utf-8")
    screenshots_dir = tmp_path / "screenshots"

    monkeypatch.setattr(module, "_default_screenshot_output_dir", lambda _source: screenshots_dir)

    def _fake_run(args, _timeout_seconds):
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        (screenshots_dir / "page-1.png").write_text("img", encoding="utf-8")
        (screenshots_dir / "page-2.png").write_text("img", encoding="utf-8")
        return {"status": "success", "command": ["lit", *args]}

    monkeypatch.setattr(module, "_run_liteparse", _fake_run)

    result = module.screenshot_document_pages(str(source))

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["files"] == [
        str(screenshots_dir / "page-1.png"),
        str(screenshots_dir / "page-2.png"),
    ]


def test_batch_parse_documents_collects_outputs(monkeypatch, tmp_path: Path) -> None:
    module = importlib.import_module("src.files.features.document_parser")

    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    output_dir = tmp_path / "parsed"

    def _fake_run(args, _timeout_seconds):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "one.json").write_text("{}", encoding="utf-8")
        (output_dir / "two.json").write_text("{}", encoding="utf-8")
        return {"status": "success", "command": ["lit", *args]}

    monkeypatch.setattr(module, "_run_liteparse", _fake_run)

    result = module.batch_parse_documents(str(source_dir), output_dir=str(output_dir))

    assert result["status"] == "success"
    assert result["file_count"] == 2
    assert result["files"] == [str(output_dir / "one.json"), str(output_dir / "two.json")]