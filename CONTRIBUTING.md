# Contributing to Octa Bot 🤖

Thank you for your interest in contributing to Octa Bot — the open-source personal AI platform! We welcome contributions of all kinds: new agents, bug fixes, documentation, tests, and ideas.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Quick Overview](#quick-overview)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Requesting Features](#requesting-features)
  - [Improving Documentation](#improving-documentation)
  - [Submitting Code](#submitting-code)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Adding a New Agent](#adding-a-new-agent)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Commit and PR Guidelines](#commit-and-pr-guidelines)
- [Review Process](#review-process)
- [Licensing](#licensing)

---

## Code of Conduct

Be kind, constructive, and inclusive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Harassment, discrimination, or disrespectful behaviour will not be tolerated.

---

## Quick Overview

Octa Bot is a modular multi-agent platform. **Octa** is the chatbot identity that users interact with via Telegram, WhatsApp, or the web dashboard. Under the hood, specialized agents handle Email, Drive, Calendar, Stock Market, LinkedIn, Files, Browser, and more.

```
src/
  agent/
    core/           → AgentManager, ProcessManager, Automations
    llm/            → LLM client wrapper
    memory/         → 6-layer memory system
    ui/             → Streamlit dashboard + per-agent orchestrators
    workflows/      → Agent registry, master orchestrator, router
  email/            → Gmail service tools
  drive/            → Google Drive service tools
  linkedin/         → LinkedIn service tools
  telegram/         → Telegram Bot service tools
  whatsapp/         → WhatsApp service tools
  ...
tests/              → Unit + integration tests (pytest)
docs/index.html     → Public website
documentation/      → Guides, setup docs, architecture notes
```

---

## How to Contribute

### Reporting Bugs

1. Search existing [GitHub Issues](https://github.com/your-org/Octa Bot/issues) first.
2. If not found, open a new issue with:
   - **Title:** Short, descriptive (`[Bug] Email agent crashes when no token`)
   - **Environment:** OS, Python version, relevant package versions
   - **Steps to reproduce** — minimal reproducible example preferred
   - **Expected vs actual behaviour**
   - **Logs or tracebacks** (redact any tokens/secrets)

### Requesting Features

1. Open a **Feature Request** issue.
2. Describe the use-case, not just the implementation.
3. If you plan to implement it yourself, say so — we'll assign the issue to you.

### Improving Documentation

Documentation lives in `documentation/` and `docs/index.html`. Even small typo fixes are welcome — open a PR directly.

### Submitting Code

For anything beyond a trivial fix:

1. **Open or find an issue** first — get confirmation before significant work.
2. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feat/linkedin-agent
   # or
   git checkout -b fix/email-decode-crash
   ```
3. Write code + tests.
4. Run the test suite locally (must pass).
5. Open a **Pull Request** against `main`.

---

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- A GitHub account

### Steps

```bash
# 1. Fork then clone your fork
git clone https://github.com/YOUR_USERNAME/Octa Bot.git
cd Octa Bot

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the config example and fill in your tokens
cp config/settings.example.json config/settings.json
# Edit config/settings.json with your service credentials

# 5. Run the test suite
python -m pytest tests/ -q

# 6. Launch the dashboard to verify everything works
python run_agent_hub.py
```

> **Important:** Never commit `config/settings.json`, `config/token.json`, or any file containing real tokens/secrets. They are all listed in `.gitignore`.

---

## Project Structure

```
src/
  agent/
    core/
      agent_manager.py      ← AGENT_TYPES dict — add new agent type here
      automation_scheduler.py
      process_manager.py
    llm/
      llm_parser.py         ← LLM client (used by all orchestrators)
    memory/
      agent_memory.py       ← 6-layer memory read/write
      consolidation_runner.py
    ui/
      agent_dashboard.py    ← Entry point for Streamlit dashboard
      dashboard/
        app.py              ← _SKILL_META dict — add skill metadata here
        create_form.py      ← "Add New Skill" form
      <agent_name>_agent/
        orchestrator.py     ← execute_with_llm_orchestration()
    workflows/
      agent_registry.py     ← AGENT_REGISTRY dict — register agent here
      master_orchestrator.py
      router.py
  <service_name>/
    __init__.py             ← public tool exports
    <service>_service.py    ← actual API calls
tests/
  <service_name>/           ← unit tests for each service
  integration/              ← cross-agent integration tests
documentation/
  setup/                    ← per-service setup guides
  architecture/             ← system design docs
  reference/                ← tool and agent reference
```

---

## Adding a New Agent

Adding an agent requires changes in **4 files** (plus creating the service and orchestrator):

### 1. Create the service layer

```
src/<service_name>/
  __init__.py          ← export all public functions
  <service>_service.py ← implement API calls
```

See `src/linkedin/linkedin_service.py` as a reference.

### 2. Create the orchestrator

```
src/agent/ui/<service>_agent/
  __init__.py
  orchestrator.py      ← must export execute_with_llm_orchestration()
```

Follow the exact signature:
```python
def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> dict:
    ...
```

See `src/agent/ui/linkedin_agent/orchestrator.py` for the complete pattern.

### 3. Register in `AGENT_TYPES` (`src/agent/core/agent_manager.py`)

```python
AGENT_TYPES = {
    ...
    'my_service': {
        'name': 'My Service Agent',
        'description': 'Short description for the UI',
        'icon': '🔧',
        'capabilities': ['action_1', 'action_2'],
    },
}
```

### 4. Register in `AGENT_REGISTRY` (`src/agent/workflows/agent_registry.py`)

```python
AGENT_REGISTRY = {
    ...
    "my_service": {
        "description": (
            "My Service agent. Handles: action_1, action_2, ..."
        ),
        "module": "src.agent.ui.my_service_agent.orchestrator",
        "function": "execute_with_llm_orchestration",
    },
}
```

### 5. Add to `_SKILL_META` in `src/agent/ui/dashboard/app.py`

```python
_SKILL_META = {
    ...
    "my_service": {
        "icon": "🔧",
        "title": "My Service",
        "description": "Plain English description shown in the PA creation wizard.",
    },
}
```

### 6. Add setup documentation

Create `documentation/setup/MY_SERVICE_SETUP.md` following the pattern of `LINKEDIN_SETUP.md`.

### 7. Write tests

Create `tests/my_service/` with at least:
- Unit tests for core service functions
- A mock-based orchestrator test

---

## Coding Standards

- **Python 3.10+** syntax (`X | Y` union types, `match` statements where appropriate).
- **Type hints** on all public functions. Use `from __future__ import annotations` at the top.
- **Docstrings** on all modules and public functions (Google style preferred).
- **`from __future__ import annotations`** at the top of all modules.
- **No hard-coded credentials** — always read from `config/settings.json` or environment variables.
- **Line length** ≤ 100 characters.
- Imports: stdlib → third-party → local (grouped with blank lines). Run `isort` if in doubt.
- No unused imports (`flake8` / Pylance will catch these).
- Format with **`black`** (default 88-char line length) where practical.

### Naming Conventions

| Thing | Convention | Example |
|---|---|---|
| Module/package | `snake_case` | `linkedin_service.py` |
| Class | `PascalCase` | `AgentManager` |
| Function / variable | `snake_case` | `create_text_post()` |
| Constant | `UPPER_SNAKE` | `AGENT_REGISTRY` |
| Private helper | `_snake_case` | `_dispatch_tool()` |

---

## Testing

All tests live in `tests/`. Run with:

```bash
# All tests
python -m pytest tests/ -q

# Specific module
python -m pytest tests/linkedin/ -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Test requirements

- Every new tool function must have at least one **unit test**.
- Mock all external API calls — tests must pass without real credentials.
- Use `pytest.mark.parametrize` for data-driven tests.
- Integration tests (`tests/integration/`) may require real credentials and are tagged with `@pytest.mark.integration`.

### Running only unit tests (fast, no credentials)

```bash
python -m pytest tests/ -q -m "not integration"
```

---

## Commit and PR Guidelines

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]
[optional footer]
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`

Examples:
```
feat(linkedin): add LinkedIn agent with text/image/video posting
fix(email): handle empty inbox gracefully
docs(linkedin): add LINKEDIN_SETUP.md setup guide
test(stock): add unit tests for technical_analysis tool
```

### Pull Requests

- **Title:** follows commit convention above
- **Description:** What changed? Why? Link the related issue (`Closes #123`)
- **Size:** Keep PRs focused — one feature or fix per PR. Large PRs will be asked to split.
- **Checklist before opening PR:**
  - [ ] `pytest tests/ -q` passes locally
  - [ ] No new lint/type errors
  - [ ] New features have tests
  - [ ] Relevant documentation updated
  - [ ] No secrets or tokens committed
  - [ ] `config/settings.example.json` updated if new config keys added

---

## Review Process

1. A maintainer will review your PR within a few days.
2. Feedback will be left as review comments — please respond to all comments.
3. Once approved, a maintainer will merge. We use **squash merge** to keep history clean.
4. Your contribution will appear in the changelog and you'll be credited.

For quick questions, open a GitHub Discussion rather than an issue.

---

## Licensing

By contributing to Octa Bot, you agree that your contributions will be licensed under the **MIT License** — the same license as the project. See [LICENSE](LICENSE) for details.

---

*Built with ♥ by the Pink Raven team and contributors.*
