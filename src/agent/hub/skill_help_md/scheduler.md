---
key: scheduler
title: Scheduler
aliases:
  - scheduler
  - smart scheduler
  - scheduling
---
**Scheduler Skill**

The Scheduler skill helps you plan your time in a smart way, not just create events.

**What it helps with**
- Finding the best meeting slot
- Protecting focus time and deep-work blocks
- Resolving schedule conflicts with alternatives
- Planning a balanced day
- Setting recurring focus or admin blocks
- Finding availability for multiple people

**Try asking things like**
- Setup my schedule
- Apply these changes to my schedule
- Find the best 45-minute slot for a review meeting tomorrow
- Protect 2 hours of focus time every morning
- Help me organize my day with breaks and deep work
- Setup my scheduler preferences
- Setup my schedular prefrences
- Show my scheduler preferences
- Edit my scheduler preferences
- Add a new preference: no meetings between 7:45 PM and 9:15 PM for gym time
- Review my scheduler

**Common mistakes**
- Use Scheduler when you want planning or optimization, not just a simple event.
- Say how long the block or meeting should be.
- Mention if other people are involved so I can look for shared availability.

**Preferences**
- Scheduler now supports durable markdown-backed preferences for focus-block length, meeting buffer, planning style, constraint mode, and optional protected no-meeting windows.
- Asking to `setup my schedule` now produces a ready-made daily schedule draft that you can refine in natural language and then apply with `apply these changes to my schedule` or `looks good`.
- These preferences change defaults for future planning, but your current message still wins if you give more specific instructions.
- Protected no-meeting windows are avoided by default for future Scheduler suggestions and planning unless you explicitly ask for a time inside that window.
