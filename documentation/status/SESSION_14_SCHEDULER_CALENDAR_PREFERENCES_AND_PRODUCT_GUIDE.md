# Session 14 - Scheduler Preferences, Calendar Preferences, and Product Guide Help

Date: 2026-03-20

## What shipped

### 1. Scheduler markdown preferences

- Added durable Scheduler preferences in `your_data/scheduler_preferences.md`
- Added `show`, `edit`, `review`, and `apply` flows in the Scheduler orchestrator
- Added supported policy fields:
  - work hours
  - focus-block length
  - meeting buffer
  - default meeting reminder
  - planning style
  - hard vs soft constraints
  - optional protected no-meeting windows
  - recurring reminders
- Scheduler no-meeting windows now support exact minute ranges such as `7:45 PM to 9:15 PM` for cases like gym time
- Scheduler planning context now includes the saved preference summary so future scheduling requests can use those defaults
- Scheduler preference setup and edit detection now tolerate common typos such as `schedular` and `prefrences`

### 2. Calendar markdown preferences

- Added durable Calendar preferences in `your_data/calendar_preferences.md`
- Added guided `show`, `edit`, `review`, and `apply` flows in the Calendar orchestrator
- Added supported policy fields:
  - working hours for slot search
  - default meeting duration
  - default reminder timing
- Calendar defaults now feed:
  - `find_free_slots`
  - quick-add duration inference when the user omits a duration
  - `set_reminder`

### 3. Product-level help guide

- Added `assistant_guide.md` to the built-in help registry
- Added `enableable: false` support in help-doc metadata so product-level docs do not show Telegram enable commands
- Added explicit detection for queries like `How do I use this assistant?`

## Testing added

- Scheduler guided preference flow and review digest tests
- Calendar guided preference flow and default-application tests
- Product-level help reply test

## User-facing commands

- `show my scheduler preferences`
- `edit my scheduler preferences`
- `setup my schedular prefrences`
- `add a new preference: no meetings between 7:45 PM and 9:15 PM for gym time`
- `review my scheduler`
- `apply my scheduler preferences`
- `show my calendar preferences`
- `edit my calendar preferences`
- `review my calendar`
- `apply my calendar preferences`
- `How do I use this assistant?`