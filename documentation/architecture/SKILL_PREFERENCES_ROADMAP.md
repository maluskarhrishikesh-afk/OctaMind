# Skill Preferences Roadmap

Date: 2026-03-20

This document describes the recommended way to extend mailbox-style persistent preferences to additional skills without creating brittle or over-engineered policy state.

## Current state

- Email: implemented
  - markdown-backed mailbox preferences
  - review history
  - learning log for reversals and unstable policies
- Files: not implemented as persistent preferences
- Drive: not implemented as persistent preferences
- Calendar: implemented
  - markdown-backed calendar preferences for working hours, default meeting duration, and default reminders
  - guided show/edit/review/apply flows
  - defaults now feed slot-finding, quick-add duration, and reminder setup when the user does not override them
- Scheduler: implemented
  - markdown-backed scheduler preferences for focus-block defaults, meeting buffers, planning style, constraint mode, and protected no-meeting windows
  - guided show/edit/review/apply flows
  - preferences now feed Scheduler planning context for future requests

What *is* already shared across multiple skills is the execution-plan explainability contract:

- goal
- confidence
- risk posture
- ordered step summary

That is the right common layer today.

## Best-practice rule

Do not add persistent preferences to a skill just because it can do multiple things.

Add persistent preferences only when all of the following are true:

1. The skill has repeatable policy decisions that the user would reasonably expect to persist across sessions.
2. Those policy decisions change default behavior, not just one-off command arguments.
3. The policy can be explained clearly in plain language and reviewed safely.
4. There is a low-risk preview or plan path before the policy is applied broadly.

## Recommended architecture

If OctaMind expands mailbox-style preferences to more skills, the preferred pattern is:

1. One markdown file per skill under `your_data/`
2. One small loader/saver module per skill
3. One review/digest function per skill
4. One explicit apply or use path per skill
5. One shared summary renderer pattern for consistency

Each skill preference file should have:

- human-readable markdown summary at the top
- embedded JSON block for machine-safe parsing
- `updated_at`
- `version`
- only user-owned durable policy fields

Each skill should also keep runtime-only or learning-only state outside the markdown file in `your_data/runtime_state/`.

## Suggested rollout by skill

### Files

Worth adding, but only for a narrow set of policies.

Good candidates:
- default destination behavior for `send it here` versus email delivery
- preferred safe-delete mode such as Recycle Bin only
- duplicate handling posture
- folder-organization preview strictness

Avoid storing:
- transient search paths
- last selected files
- anything already captured by manifests or context

### Drive

Worth adding later if sharing and cleanup workflows become more common.

Good candidates:
- default sharing posture
- whether public-link creation is ever allowed
- default duplicate-handling posture
- preferred destination folder for uploads

Avoid storing:
- ephemeral file ids from one session

### Calendar

Worth adding if recurring scheduling conventions stabilize.

Good candidates:
- default meeting duration
- default reminder offsets
- meeting naming conventions
- preferred working hours for slot searches

Avoid storing:
- one-off event details that already belong in the calendar itself

### Scheduler

This is the strongest next candidate after Email.

Good candidates:
- preferred focus-block length
- no-meeting windows
- preferred meeting buffers
- daily planning style
- hard versus soft constraints for optimization

Scheduler has real policy semantics, so it fits the model better than Files or Drive.

## Rollout order recommendation

If this is implemented incrementally, the best order is:

1. Files
2. Drive

Reasoning:

- Scheduler and Calendar were implemented first because they have the clearest durable user preferences.
- Files and Drive remain the later candidates because they depend more on explicit per-request intent than on stable default policy.

## Safety guidance

Persistent preferences must never bypass destructive-action confirmation by themselves.

Preferences may:
- change recommendations
- change preview defaults
- reduce repetitive follow-up questions

Preferences must not:
- silently escalate destructive behavior
- override explicit user instructions in the current turn
- cause cross-skill ambiguity to resolve automatically when the command is underspecified

## User-experience guidance

Whenever a skill has persistent preferences, the assistant should support these four user intents explicitly:

- show my <skill> preferences
- edit my <skill> preferences
- review my <skill>
- apply my <skill> preferences

If the user gives a short ambiguous imperative such as `apply cleanup now`, the assistant should prefer clarification over guessing unless the active context is clearly bound to the same skill.