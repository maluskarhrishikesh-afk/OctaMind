"""
PA Manager — CRUD for Personal Assistants.

A Personal Assistant has:
  - A name (chosen by the user)
  - A set of attached Skills  (subset of AGENT_REGISTRY keys)
  - A set of attached Channels (subset of CHANNEL_REGISTRY keys)
  - Its own memory space (memory/<pa_id>/)

Skills are stateless executors; all memory and context live at the PA level.

Storage: data/assistants.json
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_PA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "assistants.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_assistant(
    name: str,
    skills: List[str],
    channels: List[str],
    config: Optional[dict] = None,
) -> dict:
    pa_id = f"pa_{uuid.uuid4().hex[:8]}"
    return {
        "id": pa_id,
        "name": name,
        "skills": skills,
        "channels": channels,
        "config": config or {},   # per-PA config, e.g. {"telegram": {"bot_token": "..."}}
        "memory_id": pa_id,    # memory stored at memory/<pa_id>/
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _save(assistants: List[dict]) -> None:
    _PA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PA_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(assistants, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(_PA_PATH)


# ── Public API ────────────────────────────────────────────────────────────────

def load_assistants() -> List[dict]:
    """
    Return all Personal Assistants from disk.
    Creates (and persists) a default assistant only on first run (no file yet).
    """
    if _PA_PATH.exists():
        try:
            data = json.loads(_PA_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data   # may be empty — that's valid after deleting all PAs
        except Exception:
            pass

    # First run — create the default assistant with every available skill
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        all_skills = list(AGENT_REGISTRY.keys())
    except Exception:
        all_skills = ["drive", "email", "files"]

    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        all_channels = list(CHANNEL_REGISTRY.keys())
    except Exception:
        all_channels = ["dashboard", "api", "telegram"]

    default = _make_assistant(
        name="My Assistant",
        skills=all_skills,
        channels=all_channels,
    )
    _save([default])
    return [default]


def save_assistants(assistants: List[dict]) -> None:
    """Persist the full list of assistants."""
    _save(assistants)


def _init_pa_memory(pa: dict) -> None:
    """Initialise memory files for a new Personal Assistant.

    Creates the memory directory and seeds personality.md with a template
    that includes a section for tracking the user's personality/preferences.
    PAs are the ONLY entities that own memory in this system.
    """
    try:
        from src.agent.memory.agent_memory import get_agent_memory
        mem = get_agent_memory(pa["id"])
        pa_name = pa["name"]
        # Seed personality.md with user-personality tracking template
        personality_content = f"""# Personality Profile — {pa_name}

## About This Assistant
- **Name:** {pa_name}
- **Created:** {pa.get('created_at', '')[:10]}
- **Skills:** {', '.join(pa.get('skills', []))}

## User Personality (auto-learned)

The assistant observes how the user communicates and adapts over time.
This section is updated automatically during memory consolidation.

| Trait                | Observed Preference              |
| -------------------- | -------------------------------- |
| Communication style  | *(to be learned)*                |
| Response length pref | *(to be learned)*                |
| Formality level      | *(to be learned)*                |
| Preferred topics     | *(to be learned)*                |
| Active hours         | *(to be learned)*                |

## Behavioural Guidelines

- Greet the user warmly and remember their name when shared.
- Adapt tone and verbosity to match the user's observed preference.
- Be proactive — surface useful insights without being asked.
- Always be honest about capabilities and limitations.
- Protect the user: flag unusual requests before acting on them.

## Notes
*(Updated automatically during memory consolidation.)*
"""
        mem.personality_path.write_text(personality_content, encoding="utf-8")
    except Exception as exc:
        print(f"⚠️ Could not initialise PA memory for {pa['id']}: {exc}")


def create_assistant(name: str, skills: List[str], channels: List[str],
                     config: Optional[dict] = None) -> dict:
    """Create a new PA, persist it, and initialise its memory.  Returns the new PA dict."""
    assistants = load_assistants()
    pa = _make_assistant(name, skills, channels, config=config)
    assistants.append(pa)
    _save(assistants)
    _init_pa_memory(pa)
    return pa


def get_assistant(pa_id: str) -> Optional[dict]:
    """Return a single PA by id, or None."""
    return next((a for a in load_assistants() if a["id"] == pa_id), None)


def update_assistant(pa_id: str, **fields) -> bool:
    """Patch arbitrary fields on an existing PA.  Returns False if not found."""
    assistants = load_assistants()
    for pa in assistants:
        if pa["id"] == pa_id:
            pa.update(fields)
            _save(assistants)
            return True
    return False


def delete_assistant(pa_id: str) -> bool:
    """Delete a PA by id. Returns False if not found."""
    assistants = load_assistants()
    remaining = [a for a in assistants if a["id"] != pa_id]
    if len(remaining) == len(assistants):
        return False   # not found
    _save(remaining)
    return True
