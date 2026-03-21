# Session 15 - Scheduler Template Setup, Sticky Follow-Up Fix, and Schedule Reporting

Date: 2026-03-21

## What shipped

### 1. Scheduler setup is now template-based

- `setup my scheduler preferences` and `edit my scheduler preferences` now return a one-shot editable template instead of forcing a numeric wizard
- `setup my schedule` now returns a user-facing suggested daily schedule instead of just listing today's events and free slots
- that suggested schedule is seeded with a sensible default workday, lunch block, focus block, and personal reminders so the user can approve or refine it in plain English
- the suggested schedule is now written to a draft markdown file first, and natural-language follow-ups update that draft until the user says `apply these changes to my schedule` or `looks good`
- the template supports:
  - work hours
  - default focus block length
  - meeting buffer
  - default meeting reminder
  - planning style
  - constraint mode
  - multiple protected windows
  - multiple recurring reminders
- direct free-text preference edits still work for targeted changes such as gym windows or meeting reminders

### 2. Sticky preference follow-up bug fixed

- pending Scheduler and Calendar setup state is now cleared when the user sends an unrelated non-preference request
- scheduler follow-up detection now evaluates only the raw user fragment, not the injected previous-turn context block
- this fixes Telegram conversations getting trapped in repeated setup prompts after a preference flow started once

### 3. Preferences now apply to actual scheduling defaults

- Scheduler preferences now store work hours and default meeting reminder timing
- saving Scheduler preferences syncs Calendar defaults for working hours and reminder timing
- preference-aware slot finding now respects:
  - work hours
  - meeting buffer
  - protected no-meeting windows
- explicit `create_event` scheduling through the Scheduler now blocks protected-window conflicts and out-of-hours bookings

### 4. Schedule reporting added

- Scheduler now supports a deterministic report fast path for questions about:
  - how many meetings were scheduled
  - how much free time remained
  - busy time inside work hours
  - protected time inside work hours
- reports are also written to `your_data/reports/` for later reference and delivery

## Testing added

- scheduler template setup save path
- scheduler-to-calendar preference sync
- scheduler stale pending-state regression test
- calendar stale pending-state regression test
- calendar slot-default test updated for minute-aware working hours

## User-facing commands

- `setup my schedule`
- `apply these changes to my schedule`
- `setup my scheduler preferences`
- `edit my scheduler preferences`
- `show my scheduler preferences`
- `apply my scheduler preferences`
- `review my scheduler`
- `give me a schedule report for this week`
- `how many meetings do I have this week`
- `how much free time do I have tomorrow`