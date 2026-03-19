import importlib
from pathlib import Path


def test_transcript_phrase_lists_emails_received_today_without_dag(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.email_agent.orchestrator")

    monkeypatch.setattr(
        orchestrator,
        "_build_all_tools",
        lambda: {
            "count_matching_emails": lambda query: {
                "status": "success",
                "total_count": 2,
            },
            "list_emails": lambda query="", max_results=10: {
                "status": "success",
                "results": [
                    {
                        "id": "msg-1",
                        "subject": "Closing Today: The Psychology of Money Live Masterclass",
                        "sender": "The Economic Times <newsletter@economictimesnews.com>",
                        "date": "Wed, 18 Mar 2026 11:16:44 +0530 (IST)",
                        "snippet": "Dear Reader, The book that changed how the world thinks about money.",
                    },
                    {
                        "id": "msg-2",
                        "subject": "Is this the opportunity you've been waiting for?",
                        "sender": "Career Tribe Consultancy <vacancy@vacancies.shine.com>",
                        "date": "Wed, 18 Mar 2026 11:04:47 +0530",
                        "snippet": "Recruiter from One Min Cv Llp is actively hiring.",
                    },
                ],
            },
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DAG should not run for transcript fast path")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run for transcript fast path")),
    )

    result = orchestrator.execute_with_llm_orchestration("List all the emails that I received today")

    assert result["status"] == "success"
    assert result["_fast_path"] == "relative_day_email_list"
    assert "received today" in result["message"]
    assert "Closing Today: The Psychology of Money Live Masterclass" in result["message"]


def test_transcript_phrase_parses_payslips_in_my_computer() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "How many payslips are there in my computer?"
    )

    assert parsed is not None
    assert parsed["mode"] == "count_search"
    assert parsed["term"] == "payslip"


def test_transcript_phrase_parses_image_file_name_octa() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "Is there any image file name octa on my computer ?"
    )

    assert parsed is not None
    assert parsed["mode"] == "named_search"
    assert parsed["term"] == "octa"
    assert "png" in parsed["extensions"]


def test_transcript_phrase_parses_images_containing_name_octa() -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")

    parsed = orchestrator.parse_precise_full_computer_search(
        "Are there any images on my computer containing the name octa?"
    )

    assert parsed is not None
    assert parsed["mode"] == "named_search"
    assert parsed["term"] == "octa"


def test_transcript_phrase_counts_inside_it_after_neo_lookup(monkeypatch, tmp_path: Path) -> None:
    orchestrator = importlib.import_module("src.agent.ui.files_agent.orchestrator")
    context_manifest = importlib.import_module("src.agent.manifest.context_manifest")

    neo_folder = tmp_path / "Neo"
    neo_folder.mkdir()
    (neo_folder / "one.txt").write_text("1", encoding="utf-8")
    (neo_folder / "nested").mkdir()
    (neo_folder / "nested" / "two.txt").write_text("2", encoding="utf-8")

    monkeypatch.setattr(
        orchestrator,
        "_resolve_named_folder_path",
        lambda folder_name, drive_letter="": neo_folder,
    )

    saved_context = {}

    def _fake_auto_save(result, query=""):
        saved_context["resolved_entities"] = {
            "directory_path": result.get("path", ""),
        }
        return result

    monkeypatch.setattr(context_manifest, "auto_save_files_context", _fake_auto_save)
    monkeypatch.setattr(
        context_manifest,
        "read_context",
        lambda agent="": {"resolved_entities": dict(saved_context.get("resolved_entities", {}))},
    )

    lookup_result = getattr(orchestrator, "_try_specific_drive_item_query")(
        "Is there a folder named Neo on my C drive?",
        artifacts_out={},
    )
    assert lookup_result is not None
    assert lookup_result["status"] == "success"

    followup_result = getattr(orchestrator, "_try_contextual_folder_count_query")(
        "How many files and folders are there inside it?",
        artifacts_out={},
    )

    assert followup_result is not None
    assert followup_result["status"] == "success"
    assert "Total Files: 2" in followup_result["message"]
    assert "Total Folders: 1" in followup_result["message"]