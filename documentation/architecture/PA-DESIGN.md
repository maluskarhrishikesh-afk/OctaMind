# Octa Bot — Personal Assistant Design

*Last Updated: February 24, 2026*

---

## Core Philosophy

Octa Bot is a **Personal Assistant (PA)** — not a collection of independent chatbots.

The PA has a single identity, a single memory, and a single brain (the Hub). It can be
reached through different **Channels** (Telegram, WhatsApp, the dashboard, an API) and it
can perform different tasks through **Skills** (email, Drive, local files, calendar, …).

Adding a new Skill or a new Channel should require touching **exactly one file** — its
registry entry. Nothing else changes.

---

## System Anatomy

```
+---------------------------------------------------------------------+
¦                       Personal Assistant                             ¦
¦                                                                      ¦
¦   Identity: "Octa Bot"  ·  memory/_collective_memory_/  ·  LLM client  ¦
+---------------------------------------------------------------------+
                                ¦
            +-------------------+--------------------+
            ?                   ?                    ?
   +-----------------+  +------------------+  +--------------------+
   ¦  Skill Registry ¦  ¦ Channel Registry ¦  ¦   HubProcessor     ¦
   ¦  (what PA can   ¦  ¦ (how users reach ¦  ¦   (brain — routes  ¦
   ¦   do)           ¦  ¦  the PA)         ¦  ¦   skill dispatch)  ¦
   +-----------------+  +------------------+  +--------------------+
            ¦                    ¦
   +--------?--------+  +--------?----------------------------------+
   ¦ email           ¦  ¦ dashboard  — Streamlit UI (always on)      ¦
   ¦ drive           ¦  ¦ telegram   — polling bot (background proc) ¦
   ¦ files           ¦  ¦ whatsapp   — webhook (future)              ¦
   ¦ calendar (soon) ¦  ¦ api        — FastAPI /hub/chat (always on) ¦
   ¦ browser (future)¦  ¦ slack      — webhook (future)              ¦
   +-----------------+  +-------------------------------------------+
```

---

## Skill Registry (`src/agent/workflows/agent_registry.py`)

**Status: ? Built**

A dict of `skill_name ? { description, module, function, enabled }`.

Each skill exposes a single function:
```python
execute_with_llm_orchestration(command: str, agent_id: str) -> dict
```

### Adding a new Skill

Add one entry to `AGENT_REGISTRY`. The router, HubProcessor, and workflow planner
pick it up automatically — zero other changes.

```python
"calendar": {
    "description": "Google Calendar. Creates/reads/updates events, sets reminders...",
    "module": "src.agent.ui.calendar_agent.orchestrator",
    "function": "execute_with_llm_orchestration",
    "enabled": True,
},
```

### Skill Routing

The router (`src/agent/workflows/router.py`) uses **LLM-based routing**:
1. Builds a prompt from `AGENT_REGISTRY` descriptions at runtime.
2. Asks the LLM: "which agents are needed?" ? returns JSON array e.g. `["files", "drive"]`
3. Falls back to keyword extraction from registry descriptions if LLM fails.

---

## Channel Registry (`src/agent/hub/channel_registry.py`)

**Status: ? Built (Feb 24 2026)**

Each channel is a class that implements `BaseChannel`:

```python
class BaseChannel(ABC):
    name: str               # unique key
    display_name: str       # human-readable
    icon: str               # emoji
    enabled: bool           # can be toggled at runtime
    supports_markdown: bool # does the channel render markdown?
    max_message_length: int # characters before truncation
    is_external: bool       # False = dashboard (internal), True = bot/API

    def start(self) -> None          # launch background process/thread
    def stop(self) -> None           # graceful shutdown
    def is_running(self) -> bool     # health check
    def format_response(text) -> str # adapt markdown for channel limits
```

### Adding a new Channel

1. Create `src/agent/hub/channels/my_channel.py` implementing `BaseChannel`.
2. Add one entry to `CHANNEL_REGISTRY` in `channel_registry.py`.
3. That's it — `start.py` will pick it up and start it automatically.

### Built-in Channels

| Channel     | Type       | Port  | Markdown | External | Status |
|-------------|------------|-------|----------|----------|--------|
| `dashboard` | Streamlit  | 8501  | ?       | ?       | ? Built |
| `api`       | FastAPI    | 8502  | ?       | ?       | ? Built |
| `telegram`  | Long-poll  | —     | ?       | ?       | ? Built |
| `whatsapp`  | Webhook    | 8503  | ?       | ?       | ? Planned |
| `slack`     | Webhook    | —     | ?       | ?       | ? Planned |

---

## HubProcessor (`src/agent/hub/processor.py`)

**Status: ? Built**

The PA's brain. Receives `(message, session_id, source)` from any channel and
returns a plain `HubResponse`. No Streamlit, no HTTP — pure Python.

### Dispatch logic

```
message arrives
      ¦
      ?
router.detect_agents_needed(message)
      ¦
      +- None           ? conversational LLM reply (memory-aware)
      +- ["files"]      ? single-skill direct call
      +- ["email"]      ? single-skill direct call
      +- ["drive","email"] ? multi-skill workflow planner + runner
```

### Session history

- Kept in memory (`_SESSION_HISTORY` dict keyed by `session_id`)
- Persisted to `data/hub_conversations.json` after every turn
- Dashboard's **Live Channels** tab reads this file every 5 seconds

---

## Conversation Persistence

```
data/
  hub_conversations.json        ? written by HubProcessor (every turn)
  telegram_messages.json        ? written by Telegram poller
```

`hub_conversations.json` schema:
```json
{
  "sessions": {
    "telegram_12345": {
      "source": "telegram",
      "session_id": "telegram_12345",
      "last_updated": "2026-02-24T11:47:45Z",
      "messages": [
        { "role": "user",      "content": "...", "ts": "..." },
        { "role": "assistant", "content": "...", "ts": "...", "elapsed": 2.1 }
      ]
    }
  }
}
```

---

## Startup Sequence (`start.py`)

`start.py` iterates `CHANNEL_REGISTRY` and starts each enabled channel:

```
start.py
  +-- dashboard channel  ? python -m streamlit run ...         (port 8501)
  +-- api channel        ? uvicorn src.agent.hub.server:app    (port 8502)
  +-- telegram channel   ? python -m src.telegram.polling.run_poller
```

To disable a channel at startup: set `"enabled": false` in its registry entry
or toggle it from the PA Settings panel in the dashboard.

---

## Dashboard Panels

| Panel                | Location                   | Status  |
|----------------------|----------------------------|---------|
| Agent Hub (overview) | Main dashboard             | ? Built |
| Multi-Agent Hub Chat | Multi-Agent Hub page tab 1 | ? Built |
| Live Channels feed   | Multi-Agent Hub page tab 2 | ? Built |
| PA Settings          | Multi-Agent Hub page tab 3 | ? Built |

---

## Planned (Out of Scope for Now)

### Cross-channel User Identity
Same human uses Telegram + WhatsApp ? same memory context.
Requires a `User` model with linked `channel_user_id` per channel.

### Skill Permissions per Channel
`delete_files` allowed only from `dashboard`, not from `telegram`.
Requires an ACL entry per skill × channel.

### WhatsApp Channel
Requires a WhatsApp Business API webhook.
Once added to `CHANNEL_REGISTRY`, zero other code changes needed.

---

## File Map

```
src/
  agent/
    hub/
      __init__.py
      processor.py          ? HubProcessor (brain)
      server.py             ? FastAPI /hub/chat endpoint
      channel_registry.py   ? CHANNEL_REGISTRY + channel management
      channels/
        __init__.py
        base.py             ? BaseChannel abstract class
        dashboard.py        ? Dashboard channel (Streamlit)
        telegram.py         ? Telegram channel (polling)
        api.py              ? API channel (FastAPI/uvicorn)
    workflows/
      agent_registry.py     ? SKILL_REGISTRY (formerly AGENT_REGISTRY)
      router.py             ? Dynamic LLM-based skill routing
      master_orchestrator.py
      ...
  telegram/
    polling/
      poller.py             ? Low-level getUpdates loop
      run_poller.py         ? Standalone process entry point
      message_store.py
    auto_responder.py       ? Calls HubProcessor on inbound messages
```
