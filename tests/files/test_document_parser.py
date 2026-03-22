from __future__ import annotations

import importlib
import json
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
    assert result["structured_output_path"].endswith("invoice_structured.json")


def test_extract_document_key_fields_builds_structured_json(tmp_path: Path) -> None:
    module = importlib.import_module("src.files.features.document_parser")

    source = tmp_path / "Payslip_2026_Jan.pdf"
    source.write_text("fake-pdf", encoding="utf-8")
    parse_output = tmp_path / "Payslip_2026_Jan_liteparse.json"
    parse_output.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page": 1,
                        "text": (
                            "NeoZoom Technologies Pvt Ltd\n"
                            "Payslip for the month of January 2026\n"
                            "Employee ID   NZ66                   Employee Name     Hrishikesh Maluskar\n"
                            "Designation   Sr. Java Developer     Date of Joining   9/25/2023\n"
                            "Pay Date      2/3/2026               Paid Days         31\n"
                            "LOP Days      0                      UAN               100165351971\n"
                            "Basic                                             53500   EPF Contribution     6420\n"
                            "House Rent Allowance                              26750   Income Tax          70010\n"
                            "Fixed Bonus                                       32100   Professional Tax      200\n"
                            "Other Allowances                                 237362   Other Deductions        0\n"
                            "Advance or Arrears or Notice Pay                      0\n"
                            "Gross Earnings                                   349712\n"
                            "Net Pay                                          273082   Total Deductions    76630\n"
                            "Rupees Two Hundred Seventy Three Thousand Eighty Two Only\n"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = module.extract_document_key_fields(str(parse_output), source_path=str(source))

    assert result["status"] == "success"
    assert result["document_type"] == "payslip"
    assert result["key_fields"]["employee_id"] == "NZ66"
    assert result["key_fields"]["net_pay"] == "273082"
    assert result["tamper_assessment"]["risk_level"] == "low"
    assert Path(result["output_path"]).exists()


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
    assert result["structured_file_count"] == 2
    assert all(path.endswith("_structured.json") for path in result["structured_files"])