# Repository Hygiene

Last updated: 2026-03-08

This document defines what is safe to delete, what must be preserved, and how OctaMind now converts transient log failures into a durable improvement backlog.

---

## Safe Cleanup Targets

These are generated artifacts or transient runtime outputs and are safe to remove when they accumulate:

- `__pycache__/`
- `.pytest_cache/`
- `build/`
- `dist/`
- `your_data/.last_context_prune`
- `your_data/octa_manifest_1.txt`
- disposable generated exports under `your_data/exports/` and `your_data/calendar_exports/`
- disposable packaging leftovers accidentally copied into runtime folders such as `cacerts.txt` and `entry_points.txt`

These should be treated as generated artifacts, not canonical source.

---

## Live State: Do Not Delete Blindly

Canonical runtime state now lives in `your_data/`. Older installs may still contain legacy `data/` compatibility copies, but those are no longer the primary runtime store. The following files should not be removed as part of generic cleanup:

- `assistants.json`
- `action_items.json`
- `habit_logs.json`
- `habits.json`
- `hub_conversations.json`
- `octa_context.json`
- `octa_context_history.jsonl`
- `octa_jobs.json`
- `octa_job_notifications.json`
- `operation_history.json`
- `telegram_messages.json`
- `telegram_scheduled.json`
- `whatsapp_scheduled.json`
- per-agent PA state such as `tg_pa_*.json`

For the migrated set above, treat `your_data/` as canonical. Legacy `data/` copies may still exist on older installs and are migrated forward on first use.

If these need pruning, the cleanup should be feature-aware and age-aware, not a blind delete.

---

## Persistent Error Registry

Transient logs are truncated on startup, so important failures are now copied into a committed JSON registry:

- Registry path: [errors/log_error_registry.json](../../errors/log_error_registry.json)
- Runtime hook: `src/agent/logging/error_registry.py`
- Logging integration: `src/agent/logging/log_manager.py`

The registry stores:

- normalized error fingerprint
- category
- logger name
- severity
- first seen / last seen timestamps
- occurrence count
- recent samples
- tool-description guidance derived from the failure class

Current high-value categories include:

- provider rate limits
- email follow-up selection failures
- DAG planner fallbacks
- general tool execution errors

This turns operational failures into a durable tuning input for `skills.md`, `skill_context.md`, fallback rules, and planner result-shape conventions.

---

## Recommended Maintenance Workflow

1. Remove generated clutter from the safe cleanup list.
2. Keep `your_data/` state unless the file is clearly export/cache/output only.
3. Review [errors/log_error_registry.json](../../errors/log_error_registry.json) before changing tool descriptions.
4. When a new recurring failure appears, add or refine the corresponding tool description or context rule rather than only patching symptoms.
5. Keep docs in sync whenever cleanup rules or persistent runtime artifacts change.