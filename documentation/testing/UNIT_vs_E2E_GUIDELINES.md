# Unit Tests vs E2E Tests — Guidance for OctaMind

Date: 2026-02-25

Short answer: for this codebase, E2E tests as you're doing them are more valuable. Unit tests are worth adding selectively, not everywhere.

## Practical breakdown

### Where unit tests genuinely help
- Pure logic functions — e.g., `get_streak()` streak calculation, `get_weekly_report()` date boundary math. These are easy to break silently and fast to test in isolation.
- Error-path validation — duplicate habit, missing habit, bad directory. E2E covers these too but unit tests catch them with zero LLM cost.
- Service layer regressions — the 3 bugs caught on 2026-02-25 (`daily_checkin` missing key, `add_habit` rejecting re-activation, `get_habits` missing `count`) are the exact kind of problem a small unit test per function would detect instantly on every change.

### Where E2E tests are better
- LLM tool selection — "does the LLM call `get_streak` when asked about streaks?" Only E2E can validate that.
- Prompt safety — "does the File Organizer refuse to call `apply_plan` without confirmation?" Only testable E2E.
- Integration correctness — does the full pipeline from NL → tool → response return the right shape object?

## Recommendation for OctaMind
- Continue using E2E tests for orchestration and LLM-integrated flows.
- Add focused unit tests for service/data layers (e.g., `src/habit_tracker/habit_service.py`, file-organizer plan generation logic). These tests are fast, cheap (no API calls), and catch silent regressions.
- Aim for ~30–40 focused unit assertions covering critical logic and error paths, not thousands of trivial tests.

---

Saved in `documentation/testing/UNIT_vs_E2E_GUIDELINES.md` for future reference and standardization of testing practice.
