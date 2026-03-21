# Scheduler Agent — Tool Skills

## Category: Availability & Planning

### get_todays_events
- **signature**: `get_todays_events()`
- **description**: Retrieve all events scheduled for today so you can understand the current load, detect free windows, and reason about what time remains available. Use when the user asks "what do I have today", "show today's schedule", "am I free this afternoon", "what meetings are on my calendar today", or before suggesting a time slot for today.
- **tags**: today, schedule, today's events, current day, meetings today, free today, what do I have today, calendar load

### get_tomorrows_events
- **signature**: `get_tomorrows_events()`
- **description**: Retrieve tomorrow's events to evaluate availability, suggest meeting slots, or book new time blocks for the next day. Use when the user says "what does tomorrow look like", "am I free tomorrow", "show tomorrow's meetings", "find me time tomorrow", or "schedule this for tomorrow".
- **tags**: tomorrow, schedule tomorrow, free tomorrow, tomorrow's events, next day, tomorrow meetings, find time tomorrow

### get_upcoming_events
- **signature**: `get_upcoming_events(days=7, max_results=30)`
- **description**: Retrieve upcoming events across the next N days to understand workload, find open time, or compare options across multiple days. Use when the user asks "what does my week look like", "find free slots this week", "show upcoming meetings", "when can I fit this in", or "give me options over the next few days".
- **tags**: upcoming, this week, next few days, free slots, week view, workload, open time, next 7 days, future schedule

### get_events_for_date
- **signature**: `get_events_for_date(date_str)`
- **description**: Retrieve all events for one specific date in `YYYY-MM-DD` format. Use when the user mentions an explicit day such as "check 2026-03-12", "what do I have on Friday", "find availability on March 15", or before booking a meeting on a fixed date.
- **tags**: specific date, date, schedule on date, check date, Friday, March 15, what do I have on, explicit date

### find_free_slots
- **signature**: `find_free_slots(date_str, duration_minutes=None, calendar_id="primary")`
- **description**: Find free slots that already respect saved work hours, meeting buffers, and protected no-meeting windows. Use before suggesting or booking when the user asks for availability, best meeting times, or focus blocks.
- **tags**: free slots, best time, availability, meeting windows, protected time, work hours, open slots

### get_schedule_report
- **signature**: `get_schedule_report(start_date, end_date, calendar_id="primary")`
- **description**: Generate a deterministic schedule report across a date range, including event count, busy time, protected time, and free time inside saved work hours. Use when the user asks for analytics, free-time totals, meeting load, or a schedule report.
- **tags**: schedule report, free time, meeting count, analytics, workload, busy time, productivity summary

### search_events
- **signature**: `search_events(query, days=30, max_results=10)`
- **description**: Search existing calendar events by title, attendee, or keyword over a date window. Use when the user says "find my appraisal meeting", "search calendar for dentist", "do I have anything about finance review", or "look for meetings with John".
- **tags**: search, find meeting, calendar search, keyword, meeting name, existing booking, search event

## Category: Booking & Rescheduling

### create_event
- **signature**: `create_event(title, start, end, description="", location="", attendees=None, calendar_id="primary")`
- **description**: Create a precisely scheduled calendar event when the start and end timestamps are already known. Use when the user gives an exact slot such as "book focus time from 2 PM to 4 PM on 12 March", "create a meeting from 10 to 11", or after availability has already been resolved.
- **tags**: create event, book slot, exact time, reserve time, add meeting, block calendar, focus block, confirmed slot

### quick_add_event
- **signature**: `quick_add_event(text)`
- **description**: Preferred tool for natural-language scheduling requests. Use for phrases like "book lunch tomorrow at 1", "add a focus block Friday 2 to 4", "remind me to call Raj next Monday at 10", or "schedule gym tonight at 8". This is the safest tool whenever the user speaks in human time language instead of ISO timestamps.
- **tags**: natural language, tomorrow at 1, next Monday, tonight, schedule this, add event, human time, quick add, book in plain English

### update_event
- **signature**: `update_event(event_id, **kwargs)`
- **description**: Modify an existing booking by changing its time, title, description, location, or attendees. Use when the user says "move that meeting to 4 PM", "reschedule the second one", "change the title", or "push this to tomorrow".
- **tags**: update, reschedule, move meeting, change time, edit booking, modify event, shift event, postpone

### delete_event
- **signature**: `delete_event(event_id)`
- **description**: Cancel and remove an existing scheduled event. Use when the user says "cancel that meeting", "delete the focus block", "remove the appointment", or "clear the booking" after identifying the correct event.
- **tags**: cancel, delete booking, remove event, clear slot, cancel meeting, remove appointment

### list_calendars
- **signature**: `list_calendars()`
- **description**: List all available calendars so the assistant can choose the correct calendar before creating or moving events. Use when the user asks about a non-primary calendar, shared calendar, work calendar, or wants to know what calendars exist.
- **tags**: calendars, list calendars, shared calendar, work calendar, choose calendar, available calendars

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist resolved dates, free slots, and listed events so follow-up commands like "book the second one", "2 PM works", or "move it to the first free slot" can be executed without asking the user to repeat context. This should remain available even when similarity scores are low.
- **tags**: context, follow up, second one, first slot, 2 PM works, remember options, remember schedule, turn memory