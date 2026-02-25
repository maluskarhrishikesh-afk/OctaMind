# Unit Tests vs E2E Tests — OctaMind Testing Guidelines

**Date:** 2026-02-25 (updated to cover Browser and Stock Market agents)

---

## Short Answer

**For OctaMind, E2E tests justify their cost because the system's correctness lies in the LLM-orchestration layer.** Unit tests are valuable but only where they add real signal that E2E tests don't already provide cheaply.

Use both: E2E for orchestration correctness; unit tests for service-layer logic correctness.

---

## Classification Framework

### When to write Unit Tests

Write a focused unit test when **all** of the following apply:

1. The function contains non-trivial logic (computation, branching, date math, iteration)
2. The function can run without an LLM call
3. A regression in this function would be **silent** without the test (no obvious error surface)

**Concrete examples across all agents:**

| Agent | Function | Why unit test? |
|-------|---------|----------------|
| Habit Tracker | `get_streak()` calculation | Boundary math (streak resets, longest-streak tracking) |
| Habit Tracker | `get_weekly_report()` | Date window logic — last week vs this week |
| Stock Market | `_rsi()` | Numeric algorithm — easy to break sign/period silently |
| Stock Market | `_ema()` | Multiplier formula — used by MACD; wrong result = wrong signals |
| Stock Market | `risk_score()` composite | Composite score bounds (1–10 capping, label assignment) |
| Stock Market | `pattern_detection()` signals | Candlestick rule logic — should fire on known OHLC inputs |
| Browser | `_strip_html_basic()` | Regex correctness for HTML stripping without bs4 |
| Browser | `_extract_title_from_html()` | Regex fallback for title extraction |
| File Organizer | `scan_and_propose()` plan generation | Plan structure correctness before apply |
| All agents | Error path handling | Missing params, bad symbols, invalid dates |

### When to write E2E Tests (LLM in the loop)

Write an E2E test when the correctness question **cannot be answered without an LLM call**:

| Question | Why E2E only? |
|----------|--------------|
| Does the LLM call `get_streak` when asked about streaks? | Tool selection = LLM decision |
| Does the agent pick `technical_analysis` vs `get_quote` for "AAPL RSI"? | NL → tool mapping |
| Is the final composed message readable and non-JSON? | Composition quality |
| Does the File Organizer refuse `apply_plan` without confirmation? | Prompt safety |
| Does the Stock Agent include a disclaimer? | Behaviour constraint |
| Does the Browser Agent fall back to `search_web` when URL is omitted? | Fallback logic |

---

## Decision Table

| Scenario | Recommended test type |
|----------|----------------------|
| Pure math / algorithm (RSI, EMA, streak, date arithmetic) | Unit |
| Error path (bad ticker, missing habit, HTTP 404) | Unit |
| Service function input→output shape | Unit |
| LLM selects the right tool | E2E |
| LLM params are correct (symbol uppercase, dates ISO) | E2E |
| Final message is readable / non-JSON | E2E |
| Full pipeline: NL → tool → response | E2E |
| Authentication guard (returns `auth_error` status) | Unit |
| Round-trip data persistence (habits.json write/read) | Unit |

---

## Recommended Test Targets Per Agent

### Browser Agent

**Unit tests** (`tests/browser/`):
- `test_strip_html_basic` — strips script/style, decodes entities
- `test_extract_title_regex` — fallback regex extracts `<title>` correctly
- `test_browse_url_error` — HTTP error returns `{"status": "error", "message": ...}`
- `test_search_web_empty_results` — handles no-results gracefully
- `test_download_creates_file` — file is actually written to disk
- `test_find_on_page_count` — multiple matches counted correctly

**E2E tests** (`tests/agent/e2e_browser_agent.py`):
- "search the web for Python" → selects `search_web`, returns results list
- "browse https://example.com" → selects `browse_url`, returns non-empty content
- "summarise https://example.com" → selects `summarize_page`

### Stock Market Agent

**Unit tests** (`tests/stock_market/`):
- `test_rsi_overbought` — RSI > 70 when all prices rising
- `test_rsi_oversold` — RSI < 30 when all prices falling
- `test_ema_values` — spot-check EMA formula
- `test_risk_score_bounds` — composite score always 1–10
- `test_risk_level_labels` — score-to-label mapping
- `test_pattern_detection_doji` — doji detected with correct OHLC input
- `test_compare_stocks_min_two` — returns error for fewer than 2 symbols
- `test_portfolio_suggestions_concentration` — >40% single sector triggers warning

**E2E tests** (`tests/agent/e2e_stock_agent.py`):
- "price of AAPL" → selects `get_quote`, returns price
- "technical analysis for TSLA" → selects `technical_analysis`
- "how is the market today" → selects `market_overview`
- "compare AAPL vs MSFT" → selects `compare_stocks`, symbols list formed correctly
- "analyse portfolio AAPL MSFT JPM" → selects `portfolio_analysis`

### Habit Tracker Agent

**Unit tests** (`tests/habit_tracker/`):
- `test_streak_calculation` — streak resets after missed day
- `test_longest_streak_preserved` — current < longest never overwrites historical best
- `test_weekly_report_this_vs_last_week`
- `test_add_habit_reactivation` — deactivated habit can be re-activated with `add_habit`
- `test_daily_checkin_missing_key` — won't crash if habit log has missing field

---

## Ratio Guidelines

| Agent category | Target unit assertions | Target E2E scenarios |
|----------------|----------------------|---------------------|
| Service/data layer (new agents) | 15–25 per agent | 3–5 per agent |
| Orchestrator (LLM routing) | 0 (mocked if any) | 3–5 per agent |
| Cross-agent integration | 0 | 2–3 total |

**Total budget (all agents):** ~80–120 unit assertions + 20–30 E2E scenarios.

Do NOT write 1 assertion per function — write assertions for the meaningful invariants only. A test that duplicates what the code obviously says is noise.

---

## Anti-Patterns to Avoid

| Anti-pattern | Why |
|-------------|-----|
| Unit-testing LLM output | Non-deterministic; use E2E and assert on structure, not exact text |
| E2E testing pure math | Wasteful (LLM cost) when a unit test is free and faster |
| Asserting `== "exact LLM message"` | Brittle; assert on `status`, `tool_used`, or key data fields |
| Testing every `if/else` branch | Over-testing bureaucracy; focus on real failure modes |
| No tests on error paths | Silent failures — always test at least one invalid input per service function |

---

## Test File Layout

```
tests/
├── agent/
│   ├── e2e_browser_agent.py        # E2E tests for Browser Agent (LLM + network)
│   ├── e2e_stock_agent.py          # E2E tests for Stock Agent (LLM + yfinance)
│   ├── e2e_linked_agent.py         # Existing cross-agent E2E
│   └── test_agent_manager.py       # Unit tests for agent lifecycle
│
├── browser/
│   └── test_browser_service.py     # Unit tests for browser_service.py
│
├── stock_market/
│   └── test_stock_service.py       # Unit tests for stock_service.py
│
├── habit_tracker/                  # (recommended future addition)
│   └── test_habit_service.py
│
└── integration/                    # Multi-agent integration scenarios
```

---

## Running Tests

```bash
# All unit tests (fast, no LLM):
python -m pytest tests/ -v -m "not e2e"

# All E2E tests (slow, uses LLM + network):
python -m pytest tests/ -v -m e2e

# Specific agent:
python -m pytest tests/ -k "browser" -v
python -m pytest tests/ -k "stock" -v

# Full suite:
python -m pytest tests/ -v
```

Mark E2E tests with `@pytest.mark.e2e` and add `e2e` to `pytest.ini` markers section.

---

## Marking Convention

```python
import pytest

@pytest.mark.e2e
def test_browser_search_e2e():
    """Requires LLM and network."""
    ...

def test_rsi_calculation():
    """Pure unit test — no LLM, no network."""
    ...
```

---

*Last updated: 2026-02-25. Covers all 10 registered agents: drive, email, whatsapp, files, calendar, scheduler, file_organizer, habit_tracker, browser, stock_market.*

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
