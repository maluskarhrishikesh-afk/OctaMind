---
key: assistant_guide
title: Using OctaMind
enableable: false
aliases:
  - octamind
  - this assistant
  - this product
  - assistant guide
  - using octamind
---
**Using OctaMind**

OctaMind works best when you tell it three things clearly:

1. Which domain you mean
2. What action you want
3. Any default or destination that matters

**How to phrase requests well**
- Say `mailbox`, `calendar`, `scheduler`, `drive`, or `files` when the request could fit more than one skill.
- If the action is destructive or broad, be explicit about the target.
- If you are following up on a previous result, refer to the same domain again when there is any risk of ambiguity.

**Good examples**
- `Review my mailbox`
- `Apply mailbox cleanup now`
- `Show my calendar preferences`
- `Setup my schedular prefrences`
- `Add a new preference: no meetings between 7:45 PM and 9:15 PM for gym time`
- `Protect two hours of focus time tomorrow morning`
- `Find the latest invoice in Drive`
- `Zip my Downloads folder and send it here`

**Ambiguous examples to avoid**
- `Apply cleanup now`
- `Do it`
- `Use those settings`

**What the assistant does with preferences**
- Email mailbox preferences are already durable and markdown-backed.
- Scheduler and Calendar preferences can store durable defaults for planning and event handling.
- Preferences change defaults and recommendations, but they should not override explicit instructions in your current message.

**How to inspect preference files**
- `show my mailbox preferences`
- `show my scheduler preferences`
- `show my calendar preferences`

**How to edit them**
- `edit my mailbox preferences`
- `setup my scheduler preferences`
- `setup my schedular prefrences`
- `add a new preference: no meetings between 7:45 PM and 9:15 PM for gym time`
- `edit my scheduler preferences`
- `setup my calendar preferences`
- `edit my calendar preferences`

**How to review them**
- `review my mailbox`
- `review my scheduler`
- `review my calendar`

**How to apply them**
- `apply my mailbox preferences`
- `apply my scheduler preferences`
- `apply my calendar preferences`

**How to operate the product safely**
- Use short follow-ups only when the active context is obvious.
- If the request could mean mailbox cleanup or file cleanup, say which one you mean.
- Ask for a review or plan first when you are changing broad behavior.