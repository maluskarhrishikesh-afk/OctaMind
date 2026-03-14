# Skill Help Markdown

This folder stores the user-facing help content for Personal Assistant skills.

## Format

Each skill should have one Markdown file with simple frontmatter:

```md
---
key: habit_tracker
title: Habit Tracker
aliases:
  - habit tracker
  - habit
  - habits
---
**Habit Tracker Skill**

The Habit Tracker skill helps you build routines and keep track of progress over time.

**What it helps with**
- Creating and deleting habits
- Logging daily habit completions

**Try asking things like**
- Add a habit to drink water every day
```

## Notes

- `key` should match the internal skill key used in the app.
- `title` is the user-friendly skill name.
- `aliases` are the phrases users may type in chat.
- Keep the body simple, conversational, and easy to scan in Telegram and Dashboard.
- Dynamic status like enable commands is added by Python, not stored in the Markdown body.