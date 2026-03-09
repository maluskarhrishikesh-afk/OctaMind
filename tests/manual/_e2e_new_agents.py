"""
End-to-End tests for the 3 new agents:
  1. Habit Tracker (service layer + LLM orchestration)
  2. File Organizer (service layer + LLM orchestration)
  3. Scheduler        (LLM orchestration - needs Calendar auth)
"""
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(label, result, expect_status=None, expect_keys=None):
    ok = True
    reasons = []
    if expect_status and result.get("status") != expect_status:
        ok = False
        reasons.append("status={!r} want {!r}".format(result.get("status"), expect_status))
    if expect_keys:
        for key in expect_keys:
            if key not in result:
                ok = False
                reasons.append("missing key {!r}".format(key))
    tag = PASS if ok else FAIL
    suffix = "" if ok else " -- " + ", ".join(reasons)
    print("{}  {}{}".format(tag, label, suffix))
    results.append((ok, label))
    return result


print()
print("=" * 60)
print("1. HABIT TRACKER SERVICE")
print("=" * 60)

from src.habit_tracker import (
    add_habit,
    daily_checkin,
    delete_habit,
    get_habit_analytics,
    get_habits,
    get_streak,
    get_weekly_report,
    log_completion,
)

check("add_habit (new)", add_habit("E2E Yoga", "daily", "07:00", "E2E test", "min", 10), "success", ["habit"])
check("add_habit (duplicate)", add_habit("E2E Yoga", "daily"), "error")
check("log_completion (done)", log_completion("E2E Yoga", completed=True, count=10, notes="felt good"), "success")
check("log_completion (update)", log_completion("E2E Yoga", completed=True, count=12), "success")
check("get_habits", get_habits(), "success", ["habits", "count"])
check("daily_checkin", daily_checkin(), "success", ["done_count"])
check("get_streak", get_streak("E2E Yoga"), "success", ["current_streak", "longest_streak"])
check("get_weekly_report", get_weekly_report(0), "success", ["habits_report", "overall_rate"])
check("get_habit_analytics", get_habit_analytics("E2E Yoga", 7), "success", ["completion_rate"])
check("delete_habit", delete_habit("E2E Yoga"), "success")
check("get_habits (after delete)", get_habits(), "success")

check("get_streak (missing habit)", get_streak("NoHabitXYZ"), "error")
check("log missing habit", log_completion("NoHabitXYZ", completed=True), "error")
check("analytics missing habit", get_habit_analytics("NoHabitXYZ", 7), "error")

print()
print("=" * 60)
print("2. FILE ORGANIZER SERVICE")
print("=" * 60)

from src.agent.ui.file_organizer_agent.orchestrator import (
    _apply_plan,
    _archive_old_files,
    _cleanup_app_data,
    _discard_plan,
    _list_plans,
    _preview_plan,
    _run_archival_policies,
    _scan_and_propose,
    _set_archival_policy,
    _show_archival_policies,
)

tmp = Path(tempfile.mkdtemp())
(tmp / "report.pdf").write_text("pdf content")
(tmp / "photo.jpg").write_bytes(b"img bytes")
(tmp / "notes.txt").write_text("note text")
(tmp / "script.py").write_text("print('hi')")
(tmp / "data.csv").write_text("a,b,c")
(tmp / "archive.zip").write_bytes(b"PK fake zip")

check("list_plans (start empty)", _list_plans(), "success", ["plans", "count"])
result = check("scan_and_propose (by_type)", _scan_and_propose(str(tmp), "by_type"), "success", ["plan_id", "proposed_categories", "files_to_move"])
plan_type = result.get("plan_id", "")

result = check("scan_and_propose (by_date)", _scan_and_propose(str(tmp), "by_date"), "success", ["plan_id"])
plan_date = result.get("plan_id", "")

result = check("scan_and_propose (by_name)", _scan_and_propose(str(tmp), "by_name_prefix"), "success", ["plan_id"])
plan_name = result.get("plan_id", "")

check("list_plans (3 plans)", _list_plans(), "success")
print("     plan_ids:", plan_type, plan_date, plan_name)

result = check("preview_plan", _preview_plan(plan_type), "success", ["preview", "total_moves"])
print("     total_moves:", result.get("total_moves", "?"))

result = check("apply_plan (by_type)", _apply_plan(plan_type), "success", ["moved"])
print("     files moved:", result.get("moved", "?"))

check("apply_plan (already applied)", _apply_plan(plan_type), "error")
check("discard_plan (date)", _discard_plan(plan_date), "success")
check("discard_plan (name)", _discard_plan(plan_name), "success")
check("discard_plan (missing)", _discard_plan("badid123"), "error")
check("scan non-existent dir", _scan_and_propose("/non/existent/path", "by_type"), "error")

result = check("archive_old_files (dry_run=True)", _archive_old_files(str(tmp), days_old=0, dry_run=True), None, ["files_found"])
print("     files_found:", result.get("files_found", "?"))

check("set_archival_policy", _set_archival_policy(str(tmp), days_old=30), "success")
check("show_archival_policies", _show_archival_policies(), "success", ["policies", "count"])
check("run_archival_policies (dry)", _run_archival_policies(dry_run=True), "success", ["results"])
check("cleanup_app_data (dry_run=True)", _cleanup_app_data(dry_run=True), None, ["status"])

shutil.rmtree(tmp, ignore_errors=True)
print("     temp dir cleaned up")

print()
print("=" * 60)
print("3. HABIT AGENT - LLM full pipeline")
print("=" * 60)

from src.agent.ui.habit_agent.orchestrator import execute_with_llm_orchestration as habit_exec

add_habit("LLM Running", "daily", "07:00", "LLM E2E test", "km", 5)

result = habit_exec("Show me my current habit list")
check("LLM get_habits", result, "success", ["message", "tool_used", "raw"])
print("     tool_used:", result.get("tool_used"))

result = habit_exec("Log LLM Running done for today")
check("LLM log_completion", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))

result = habit_exec("What is my streak for LLM Running?")
check("LLM get_streak", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))

result = habit_exec("Show me my weekly habit report")
check("LLM weekly_report", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))

result = habit_exec("Daily check-in - what's pending today?")
check("LLM daily_checkin", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))

result = habit_exec("Show 30-day analytics for LLM Running")
check("LLM habit_analytics", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))

delete_habit("LLM Running")

print()
print("=" * 60)
print("4. FILE ORGANIZER AGENT - LLM full pipeline")
print("=" * 60)

from src.agent.ui.file_organizer_agent.orchestrator import execute_with_llm_orchestration as fo_exec

result = fo_exec("Show me all my pending organisation plans")
check("LLM list_plans", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))

tmp2 = Path(tempfile.mkdtemp())
(tmp2 / "invoice.pdf").write_text("pdf")
(tmp2 / "budget.xlsx").write_text("xlsx")
(tmp2 / "photo.jpg").write_bytes(b"img")
(tmp2 / "music.mp3").write_bytes(b"mp3")

result = fo_exec("Organise the folder {} by file type".format(tmp2))
check("LLM scan_and_propose", result, "success", ["message", "tool_used"])
print("     tool_used:", result.get("tool_used"))
llm_plan = result.get("raw", {}).get("plan_id", "")

if llm_plan:
    result = fo_exec("Show me what plan {} will do".format(llm_plan))
    check("LLM preview_plan", result, "success", ["message"])
    print("     tool_used:", result.get("tool_used"))

    result = fo_exec("What files are in that folder?")
    print("[INFO] ambiguous query tool_used:", result.get("tool_used"), "(should not be apply_plan)")
    if result.get("tool_used") == "apply_plan":
        print("[WARN] LLM called apply_plan on ambiguous query - check prompt safety")
    _discard_plan(llm_plan)

shutil.rmtree(tmp2, ignore_errors=True)
print("     temp dir cleaned up")

print()
print("=" * 60)
print("5. SCHEDULER AGENT - LLM full pipeline")
print("=" * 60)

from src.agent.ui.scheduler_agent.orchestrator import execute_with_llm_orchestration as sched_exec

result = sched_exec("Give me scheduling insights for the next 2 weeks")
if result.get("status") == "auth_error":
    print("[INFO] Calendar not authorised - scheduler returns auth_error (expected behaviour)")
    print("     message preview:", result.get("message", "")[:80])
    check("scheduler auth_error structure", result, "auth_error", ["message", "action"])
else:
    check("LLM get_scheduling_insights", result, "success", ["message", "tool_used"])
    print("     tool_used:", result.get("tool_used"))

    result = sched_exec("Find a good time for a 1 hour meeting next week")
    check("LLM suggest_meeting_time", result, None, ["message", "tool_used"])
    print("     tool_used:", result.get("tool_used"))

    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    result = sched_exec("Analyse my schedule for {}".format(tomorrow))
    check("LLM optimize_day_schedule", result, None, ["message", "tool_used"])
    print("     tool_used:", result.get("tool_used"))

    result = sched_exec("Protect my morning on {} for deep work".format(tomorrow))
    check("LLM protect_deep_work_block", result, None, ["message", "tool_used"])
    print("     tool_used:", result.get("tool_used"))

print()