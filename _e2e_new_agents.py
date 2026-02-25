"""
End-to-End tests for the 3 new agents:
  1. Habit Tracker (service layer + LLM orchestration)
  2. File Organizer (service layer + LLM orchestration)
  3. Scheduler        (LLM orchestration — needs Calendar auth)
"""
import sys, shutil, tempfile
from pathlib import Path

sys.path.insert(0, ".")

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
        for k in expect_keys:
            if k not in result:
                ok = False
                reasons.append("missing key {!r}".format(k))
    tag = PASS if ok else FAIL
    suffix = "" if ok else " -- " + ", ".join(reasons)
    print("{}  {}{}".format(tag, label, suffix))
    results.append((ok, label))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 1. HABIT TRACKER — service layer
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("1. HABIT TRACKER SERVICE")
print("=" * 60)

from src.habit_tracker import (
    add_habit, log_completion, get_habits, daily_checkin,
    get_streak, get_weekly_report, get_habit_analytics, delete_habit,
)

check("add_habit (new)",          add_habit("E2E Yoga", "daily", "07:00", "E2E test", "min", 10), "success", ["habit"])
check("add_habit (duplicate)",    add_habit("E2E Yoga", "daily"), "error")      # must reject
check("log_completion (done)",    log_completion("E2E Yoga", completed=True, count=10, notes="felt good"), "success")
check("log_completion (update)",  log_completion("E2E Yoga", completed=True, count=12),  "success")  # same-day update
check("get_habits",               get_habits(), "success", ["habits", "count"])
check("daily_checkin",            daily_checkin(), "success", ["done_count"])
check("get_streak",               get_streak("E2E Yoga"), "success", ["current_streak", "longest_streak"])
check("get_weekly_report",        get_weekly_report(0), "success", ["habits_report", "overall_rate"])
check("get_habit_analytics",      get_habit_analytics("E2E Yoga", 7), "success", ["completion_rate"])
check("delete_habit",             delete_habit("E2E Yoga"), "success")
check("get_habits (after delete)", get_habits(), "success")  # should work; habit is inactive

# Edge cases
check("get_streak (missing habit)", get_streak("NoHabitXYZ"), "error")
check("log missing habit",          log_completion("NoHabitXYZ", completed=True), "error")
check("analytics missing habit",    get_habit_analytics("NoHabitXYZ", 7), "error")

# ─────────────────────────────────────────────────────────────────────────────
# 2. FILE ORGANIZER — service layer
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("2. FILE ORGANIZER SERVICE")
print("=" * 60)

from src.agent.ui.file_organizer_agent.orchestrator import (
    _scan_and_propose, _preview_plan, _apply_plan, _discard_plan,
    _list_plans, _archive_old_files, _cleanup_app_data,
    _set_archival_policy, _show_archival_policies, _run_archival_policies,
)

# Create a temp directory with varied files
tmp = Path(tempfile.mkdtemp())
(tmp / "report.pdf").write_text("pdf content")
(tmp / "photo.jpg").write_bytes(b"img bytes")
(tmp / "notes.txt").write_text("note text")
(tmp / "script.py").write_text("print('hi')")
(tmp / "data.csv").write_text("a,b,c")
(tmp / "archive.zip").write_bytes(b"PK fake zip")

r = check("list_plans (start empty)", _list_plans(), "success", ["plans", "count"])

# Propose by_type
r = check("scan_and_propose (by_type)", _scan_and_propose(str(tmp), "by_type"), "success", ["plan_id", "proposed_categories", "files_to_move"])
plan_type = r.get("plan_id", "")

# Propose by_date
r = check("scan_and_propose (by_date)", _scan_and_propose(str(tmp), "by_date"), "success", ["plan_id"])
plan_date = r.get("plan_id", "")

# Propose by_name_prefix
r = check("scan_and_propose (by_name)", _scan_and_propose(str(tmp), "by_name_prefix"), "success", ["plan_id"])
plan_name = r.get("plan_id", "")

r = check("list_plans (3 plans)", _list_plans(), "success")
print("     plan_ids:", plan_type, plan_date, plan_name)

# Preview
r = check("preview_plan", _preview_plan(plan_type), "success", ["preview", "total_moves"])
print("     total_moves:", r.get("total_moves", "?"))

# Apply one plan
r = check("apply_plan (by_type)", _apply_plan(plan_type), "success", ["moved"])
print("     files moved:", r.get("moved", "?"))

# Re-apply should fail
r = check("apply_plan (already applied)", _apply_plan(plan_type), "error")

# Discard remaining
r = check("discard_plan (date)", _discard_plan(plan_date), "success")
r = check("discard_plan (name)", _discard_plan(plan_name), "success")
r = check("discard_plan (missing)", _discard_plan("badid123"), "error")

# Scan a non-existent directory
r = check("scan non-existent dir", _scan_and_propose("/non/existent/path", "by_type"), "error")

# Archive (dry run — age=0 catches all newly created files)
r = check("archive_old_files (dry_run=True)", _archive_old_files(str(tmp), days_old=0, dry_run=True), None, ["files_found"])
print("     files_found:", r.get("files_found", "?"))

# Archival policy
r = check("set_archival_policy", _set_archival_policy(str(tmp), days_old=30), "success")
r = check("show_archival_policies", _show_archival_policies(), "success", ["policies", "count"])
r = check("run_archival_policies (dry)", _run_archival_policies(dry_run=True), "success", ["results"])

# App data cleanup
r = check("cleanup_app_data (dry_run=True)", _cleanup_app_data(dry_run=True), None, ["status"])

# Clean up temp dir
shutil.rmtree(tmp, ignore_errors=True)
print("     temp dir cleaned up")

# ─────────────────────────────────────────────────────────────────────────────
# 3. LLM ORCHESTRATION — HABIT TRACKER
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("3. HABIT AGENT — LLM full pipeline")
print("=" * 60)

from src.agent.ui.habit_agent.orchestrator import execute_with_llm_orchestration as habit_exec

# Seed a habit for LLM tests
add_habit("LLM Running", "daily", "07:00", "LLM E2E test", "km", 5)

r = habit_exec("Show me my current habit list")
check("LLM get_habits", r, "success", ["message", "tool_used", "raw"])
print("     tool_used:", r.get("tool_used"))

r = habit_exec("Log LLM Running done for today")
check("LLM log_completion", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))

r = habit_exec("What is my streak for LLM Running?")
check("LLM get_streak", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))

r = habit_exec("Show me my weekly habit report")
check("LLM weekly_report", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))

r = habit_exec("Daily check-in — what's pending today?")
check("LLM daily_checkin", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))

r = habit_exec("Show 30-day analytics for LLM Running")
check("LLM habit_analytics", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))

# Cleanup
delete_habit("LLM Running")

# ─────────────────────────────────────────────────────────────────────────────
# 4. LLM ORCHESTRATION — FILE ORGANIZER
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("4. FILE ORGANIZER AGENT — LLM full pipeline")
print("=" * 60)

from src.agent.ui.file_organizer_agent.orchestrator import execute_with_llm_orchestration as fo_exec

r = fo_exec("Show me all my pending organisation plans")
check("LLM list_plans", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))

# Create a real temp dir for the LLM propose test
tmp2 = Path(tempfile.mkdtemp())
(tmp2 / "invoice.pdf").write_text("pdf")
(tmp2 / "budget.xlsx").write_text("xlsx")
(tmp2 / "photo.jpg").write_bytes(b"img")
(tmp2 / "music.mp3").write_bytes(b"mp3")

r = fo_exec("Organise the folder {} by file type".format(tmp2))
check("LLM scan_and_propose", r, "success", ["message", "tool_used"])
print("     tool_used:", r.get("tool_used"))
lplan = r.get("raw", {}).get("plan_id", "")

if lplan:
    r = fo_exec("Show me what plan {} will do".format(lplan))
    check("LLM preview_plan", r, "success", ["message"])
    print("     tool_used:", r.get("tool_used"))

    # Confirm the LLM does NOT auto-apply when not asked
    r = fo_exec("What files are in that folder?")
    print("[INFO] ambiguous query tool_used:", r.get("tool_used"), "(should not be apply_plan)")
    if r.get("tool_used") == "apply_plan":
        print("[WARN] LLM called apply_plan on ambiguous query — check prompt safety")
    _discard_plan(lplan)

shutil.rmtree(tmp2, ignore_errors=True)
print("     temp dir cleaned up")

# ─────────────────────────────────────────────────────────────────────────────
# 5. LLM ORCHESTRATION — SCHEDULER (Calendar-dependent)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("5. SCHEDULER AGENT — LLM full pipeline")
print("=" * 60)

from src.agent.ui.scheduler_agent.orchestrator import execute_with_llm_orchestration as sched_exec

# Test: auth preflight — if not authorized, should return clean auth_error
# Test: if authorized, should return scheduling insight
r = sched_exec("Give me scheduling insights for the next 2 weeks")
if r.get("status") == "auth_error":
    print("[INFO] Calendar not authorised — scheduler returns auth_error (expected behaviour)")
    print("     message preview:", r.get("message", "")[:80])
    # Still validate structure
    check("scheduler auth_error structure", r, "auth_error", ["message", "action"])
else:
    check("LLM get_scheduling_insights", r, "success", ["message", "tool_used"])
    print("     tool_used:", r.get("tool_used"))

    r = sched_exec("Find a good time for a 1 hour meeting next week")
    check("LLM suggest_meeting_time", r, None, ["message", "tool_used"])
    print("     tool_used:", r.get("tool_used"))

    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = sched_exec("Analyse my schedule for {}".format(tomorrow))
    check("LLM optimize_day_schedule", r, None, ["message", "tool_used"])
    print("     tool_used:", r.get("tool_used"))

    r = sched_exec("Protect my morning on {} for deep work".format(tomorrow))
    check("LLM protect_deep_work_block", r, None, ["message", "tool_used"])
    print("     tool_used:", r.get("tool_used"))

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
total  = len(results)
passed = sum(1 for ok, _ in results if ok)
failed = [(lbl) for ok, lbl in results if not ok]
print("RESULTS: {}/{} passed".format(passed, total))
if failed:
    print("FAILED:")
    for f in failed:
        print("  x", f)
else:
    print("All checks passed!")
print("=" * 60)
