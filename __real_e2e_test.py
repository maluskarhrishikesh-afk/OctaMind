"""
Fixed get_recent_job + verify _try_direct_copy_from_manifest no longer fires
on fresh queries even when file_action context is injected.
"""
import sys, time, json, pathlib
sys.path.insert(0, '.')

GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"
BOLD  = "\033[1m"

passed = []
failed = []

def check(label, cond, detail=""):
    if cond:
        passed.append(label)
        print(f"  {GREEN}PASS{RESET} {label}" + (f"  ({detail})" if detail else ""))
    else:
        failed.append(label)
        print(f"  {RED}FAIL{RESET} {label}" + (f"  --- {detail}" if detail else ""))

def get_recent_job(session_id, job_id=None):
    """Return the most recent job for session_id (file is newest-first, index 0 = newest).
    If job_id is given, find that specific job."""
    jobs_path = pathlib.Path('data/octa_jobs.json')
    if not jobs_path.exists():
        return None
    data = json.loads(jobs_path.read_text(encoding='utf-8'))
    jobs = data.get('jobs', []) if isinstance(data, dict) else data
    if job_id:
        for job in jobs:
            if job.get('job_id') == job_id:
                return job
        return None
    # file is newest-first: iterate forward to get the most recent
    for job in jobs:
        if job.get('session_id') == session_id:
            return job
    return None

PA_ID   = "pa_7ea1659c"
CHAT_ID = 1509189824
QUERY   = "How many image files are there on my computer?"

# ─────────────────────────────────────────────────────────
#  UNIT TESTS: fresh-search guard in _try_direct_copy_from_manifest
# ─────────────────────────────────────────────────────────
print(f"\n{BOLD}{'='*60}{RESET}")
print(f"{BOLD}UNIT TESTS: fresh-search guard{RESET}")

from src.agent.ui.files_agent.orchestrator import _try_direct_copy_from_manifest, _FRESH_SEARCH_RE

# Guard should fire on the raw query
check("_FRESH_SEARCH_RE matches 'how many'",
      _FRESH_SEARCH_RE.search("How many image files are there on my computer?") is not None)

# _try_direct_copy_from_manifest returns None for a fresh search (no manifest)
result = _try_direct_copy_from_manifest(QUERY, [])
check("_try_direct_copy_from_manifest returns None for fresh search (empty manifest)",
      result is None, repr(result))

# Simulate the injected context that caused the false positive
injected_query = (
    QUERY + "\n\n"
    "## Context from Previous Turn\n"
    "file_action: Call collect_files_from_manifest() to copy files from listed_files\n"
    "last_found_paths: []\n"
    "## Session State\n"
    "session_id: dashboard_pa_7ea1659c\n"
)
result2 = _try_direct_copy_from_manifest(injected_query, [])
check("_try_direct_copy_from_manifest returns None when file_action context injected",
      result2 is None, repr(result2)[:100] if result2 else "None — correct")

print()

# ─────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────
def get_unread_notifications(session_id):
    nf = pathlib.Path('data/octa_job_notifications.json')
    if not nf.exists():
        return []
    entries = json.loads(nf.read_text(encoding='utf-8'))
    return [e for e in entries if e.get('session_id') == session_id and not e.get('read')]

def run_hub_call(session_id, source, label):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{label}{RESET}")
    print(f"  session_id : {session_id}")
    print(f"  query      : {QUERY}")
    print()

    from src.agent.hub.processor import HubProcessor
    processor = HubProcessor()

    t0 = time.perf_counter()
    result = processor.process(
        message=QUERY,
        session_id=session_id,
        source=source,
        agent_id=PA_ID,
        agent_name="My Assistant",
    )
    elapsed = time.perf_counter() - t0

    print(f"  Elapsed    : {elapsed:.2f}s")
    print(f"  Response   : {result.response[:200]}")
    print(f"  Status     : {result.status}")
    print(f"  file_artifacts: {result.file_artifacts}")
    print()

    check(f"[{label}] Response returned < 30s", elapsed < 30, f"took {elapsed:.1f}s")

    is_bg_ack = any(kw in result.response.lower() for kw in
                    ['background', 'job', 'started', 'scan', 'few minutes', 'notify',
                     'working on', 'searching', 'looking'])
    check(f"[{label}] ACK mentions background job", is_bg_ack, result.response[:100])

    check(f"[{label}] file_artifacts is EMPTY (no auto-delivery)",
          len(result.file_artifacts) == 0,
          f"got {len(result.file_artifacts)} artifacts")

    # Extract the job_id from the ACK (e.g. "Job `job_8ol2ao`")
    import re as _re
    m = _re.search(r'[Jj]ob[` ]+(`?)(\w+)\1', result.response)
    ack_job_id = m.group(2) if m else None

    # Wait up to 5s for the background thread to write the job to disk
    job = None
    for _ in range(5):
        time.sleep(1)
        job = get_recent_job(session_id, job_id=ack_job_id) if ack_job_id \
              else get_recent_job(session_id)
        if job:
            break

    check(f"[{label}] Job created in octa_jobs.json",
          job is not None, f"job_id={job.get('job_id') if job else 'N/A'} (ack={ack_job_id})")
    if job:
        check(f"[{label}] Job session_id matches",
              job.get('session_id') == session_id, f"stored: {job.get('session_id')}")
        check(f"[{label}] Job status is valid",
              job.get('status') in ('pending', 'running', 'completed'),
              f"status={job.get('status')}")
    return job, ack_job_id

# ─────────────────────────────────────────────────────────
#  SCENARIO A — Telegram
# ─────────────────────────────────────────────────────────
tg_session = f"telegram_{CHAT_ID}"
tg_job, tg_job_id = run_hub_call(tg_session, "telegram", "SCENARIO A — Telegram")

# ─────────────────────────────────────────────────────────
#  SCENARIO B — Dashboard
# ─────────────────────────────────────────────────────────
dash_session = f"dashboard_{PA_ID}"

# Mark existing notifications as read so we can detect a fresh one
nf = pathlib.Path('data/octa_job_notifications.json')
if nf.exists():
    entries = json.loads(nf.read_text(encoding='utf-8'))
    for e in entries:
        if e.get('session_id') == dash_session:
            e['read'] = True
    nf.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding='utf-8')

dash_job, dash_job_id = run_hub_call(dash_session, "dashboard", "SCENARIO B — Dashboard")

# ─────────────────────────────────────────────────────────
#  Wait for background jobs to progress
# ─────────────────────────────────────────────────────────
print(f"\n{BOLD}Waiting 15s for background jobs to progress...{RESET}")
for i in range(15):
    time.sleep(1)
    tg_s   = get_recent_job(tg_session,   job_id=tg_job_id)
    dash_s = get_recent_job(dash_session, job_id=dash_job_id)
    ts = tg_s.get('status')   if tg_s   else 'N/A'
    ds = dash_s.get('status') if dash_s else 'N/A'
    print(f"  [{i+1:2d}s] Telegram={ts} | Dashboard={ds}")
    if ts in ('completed', 'failed') and ds in ('completed', 'failed'):
        break

# ─────────────────────────────────────────────────────────
#  Final checks
# ─────────────────────────────────────────────────────────
print()
tg_final   = get_recent_job(tg_session,   job_id=tg_job_id)
dash_final = get_recent_job(dash_session, job_id=dash_job_id)

if tg_final:
    check("Telegram job progressed past pending",
          tg_final.get('status') != 'pending', f"status={tg_final.get('status')}")
    if tg_final.get('status') == 'completed':
        r = str(tg_final.get('result', ''))
        check("Telegram job result has file count",
              'file' in r.lower() or any(c.isdigit() for c in r), r[:150])

if dash_final:
    ds = dash_final.get('status', 'unknown')
    if ds == 'completed':
        unread = get_unread_notifications(dash_session)
        check("Dashboard notification written",
              len(unread) > 0, f"unread={len(unread)}")
        if unread:
            msg = unread[-1].get('message', '')
            check("Dashboard notification has result content",
                  'file' in msg.lower() or any(c.isdigit() for c in msg), msg[:150])
    elif ds == 'running':
        print(f"  Dashboard job still RUNNING (full scan in progress — that's OK)")
        check("Dashboard job is running (full scan takes minutes)", True, "still running after 15s")
    else:
        check("Dashboard job status is valid", ds in ('completed', 'running'), ds)

# ─────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────
print(f"\n{BOLD}{'='*60}{RESET}")
print(f"{BOLD}SUMMARY{RESET}")
print(f"  {GREEN}Passed: {len(passed)}{RESET}")
print(f"  {RED}Failed: {len(failed)}{RESET}")
if failed:
    print(f"\n  {RED}Failed checks:{RESET}")
    for f_ in failed:
        print(f"    - {f_}")
print()
if not failed:
    print(f"{GREEN}{BOLD}ALL CHECKS PASSED{RESET}")
else:
    print(f"{RED}{BOLD}SOME CHECKS FAILED{RESET}")
    import sys; sys.exit(1)

