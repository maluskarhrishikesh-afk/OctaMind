# Calendar Agent — Tool Skills

## Category: Browse & Search

### get_todays_events
- **signature**: `get_todays_events()`
- **description**: List all calendar events scheduled for today. Use when the user asks "what do I have today", "show today's events", "what meetings are on my calendar", or wants a same-day agenda before making changes.
- **tags**: today, today's events, agenda today, meetings today, what do I have today, calendar today

### get_tomorrows_events
- **signature**: `get_tomorrows_events()`
- **description**: List all events scheduled for tomorrow. Use when the user says "what about tomorrow", "show tomorrow's calendar", "what meetings do I have tomorrow", or wants a next-day agenda.
- **tags**: tomorrow, tomorrow's events, agenda tomorrow, next day, meetings tomorrow, calendar tomorrow

### get_upcoming_events
- **signature**: `get_upcoming_events(days=7, max_results=20)`
- **description**: List upcoming events across the next N days. Use when the user asks "show my week", "what's on my calendar this week", "upcoming meetings", "agenda for next few days", or wants a broader view before planning.
- **tags**: upcoming, this week, next few days, week agenda, future events, calendar overview, upcoming meetings

### get_events_for_date
- **signature**: `get_events_for_date(date_str)`
- **description**: List events for one explicit date in `YYYY-MM-DD` format. Use when the user mentions a specific day like "March 12", "Friday", or "2026-03-12" and wants to see scheduled events for that date.
- **tags**: date, specific day, events on date, Friday, March 12, explicit date, calendar date lookup

### search_events
- **signature**: `search_events(query, days=30, max_results=10)`
- **description**: Search existing calendar events by title, attendee, keyword, or meeting topic. Use when the user says "find my appraisal meeting", "search calendar for dentist", "look for finance review", or "show meetings with Raj".
- **tags**: search, find event, keyword, meeting title, attendee, search calendar, locate event

### list_events
- **signature**: `list_events(start=None, end=None, max_results=20, calendar_id="primary")`
- **description**: List events in a specific time range when the user gives a start and end window or the assistant already has exact bounds. Use for requests like "list meetings between Monday and Wednesday", "show events this afternoon", or "what is booked between 2 and 6 PM".
- **tags**: list range, between dates, between times, this afternoon, time window, date range, range query

### get_event
- **signature**: `get_event(event_id)`
- **description**: Retrieve the full details of a single identified calendar event. Use when the user says "show details for that event", "open the second meeting", or "what are the details of my appraisal meeting" after the event has been identified.
- **tags**: event details, get event, show details, single event, inspect meeting, open event

## Category: Create & Update

### create_event
- **signature**: `create_event(title, start, end, description="", location="", attendees=None, calendar_id="primary")`
- **description**: Create a new calendar event with exact start and end timestamps. Use when the user gives a precise slot such as "create a meeting from 10 to 11 on 2026-03-12" or after the assistant has already resolved the exact datetimes.
- **tags**: create event, add event, new meeting, exact slot, book meeting, add calendar item, fixed time

### quick_add_event
- **signature**: `quick_add_event(text)`
- **description**: Preferred tool for natural-language event creation such as "Lunch tomorrow at 1 PM", "Gym tonight at 8", or "Team sync next Monday at 10". Use this whenever the user speaks naturally instead of providing exact ISO datetimes.
- **tags**: natural language, tomorrow at 1, next Monday, tonight, add meeting in plain English, quick add, create from text

### update_event
- **signature**: `update_event(event_id, **kwargs)`
- **description**: Update an existing event's time, title, description, location, attendees, or other fields. Use when the user says "move the meeting to 4 PM", "change the title", "reschedule the second event", or "update this appointment".
- **tags**: update event, reschedule, move meeting, edit calendar item, change title, modify event

### delete_event
- **signature**: `delete_event(event_id)`
- **description**: Delete or cancel a calendar event. Use when the user says "cancel that meeting", "remove the appointment", "delete the event", or "clear that booking".
- **tags**: delete event, cancel meeting, remove appointment, clear booking, cancel calendar item

### create_recurring_event
- **signature**: `create_recurring_event(title, start, end, recurrence, description="", location="", attendees=None)`
- **description**: Create a recurring calendar event such as a weekly team sync, daily reminder, or monthly review. Use when the user asks for repeated events like "every Monday at 9", "weekly standup", or "monthly finance review".
- **tags**: recurring, weekly, daily, monthly, repeat event, repeated schedule, recurring meeting

### list_calendars
- **signature**: `list_calendars()`
- **description**: List all calendars available to the user. Use when the user wants to use a shared calendar, work calendar, personal calendar, or asks what calendars exist.
- **tags**: calendars, list calendars, shared calendar, work calendar, available calendars, choose calendar

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist resolved calendar context so follow-up instructions such as "move the second one", "book the first slot", or "delete that event" can be completed without relisting everything. Keep this available for low-confidence follow-ups.
- **tags**: context, follow up, second one, first one, remember event list, turn memory, saved context