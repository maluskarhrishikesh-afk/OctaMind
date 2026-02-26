"""
Calendar / Meeting Event Detection

Extracts meeting details, dates, and event information from emails using LLM.
Supports exporting events to Google Calendar API and/or .ics files.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.calendar_detect")


class CalendarDetector:
    """Detect and extract calendar events from emails."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            from src.agent.llm.llm_parser import get_llm_client
            self._llm = get_llm_client()
        return self._llm

    def _get_email_content(self, message_id: str) -> Dict:
        import base64
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='full'
            ).execute()
            headers = msg['payload']['headers']
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            sender = next((h['value']
                          for h in headers if h['name'].lower() == 'from'), '')
            date_header = next(
                (h['value'] for h in headers if h['name'].lower() == 'date'), '')
            body = ''
            payload = msg.get('payload', {})
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                        body = base64.urlsafe_b64decode(
                            part['body']['data']).decode('utf-8')
                        break
            elif 'data' in payload.get('body', {}):
                body = base64.urlsafe_b64decode(
                    payload['body']['data']).decode('utf-8')
            return {
                'subject': subject, 'sender': sender,
                'date_header': date_header,
                'body': body or msg.get('snippet', ''),
                'thread_id': msg.get('threadId', '')
            }
        except Exception as e:
            return {}

    def extract_calendar_events(self, message_id: str) -> Dict:
        """
        Extract meeting/event details from an email.

        Returns:
            Dict with list of calendar events found
        """
        content = self._get_email_content(message_id)
        if not content:
            return {'status': 'error', 'message': 'Could not fetch email content'}

        prompt = f"""Analyze this email and extract any meetings, events, appointments, or scheduled calls.

Email:
Subject: {content.get('subject', '')}
From: {content.get('sender', '')}
Date sent: {content.get('date_header', '')}
Body:
{content.get('body', '')[:2500]}

Return ONLY a JSON object:
{{
  "events": [
    {{
      "title": "meeting/event name",
      "date": "YYYY-MM-DD or description like 'next Tuesday'",
      "time": "HH:MM or description like '3pm'",
      "timezone": "timezone if mentioned, else null",
      "duration": "duration if mentioned, else null",
      "location": "physical address or video link if mentioned",
      "participants": ["list of names/emails mentioned"],
      "type": "meeting|call|webinar|deadline|appointment|other",
      "notes": "any important notes about the event"
    }}
  ],
  "has_events": true_or_false,
  "confidence": "high|medium|low"
}}

If no events found: {{"events": [], "has_events": false, "confidence": "high"}}"""

        try:
            raw = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": "You extract calendar events from emails. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=600,
                timeout=30
            )
            text = raw.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            result['status'] = 'success'
            result['message_id'] = message_id
            result['subject'] = content.get('subject', '')
            result['sender'] = content.get('sender', '')
            return result
        except Exception as e:
            logger.error(f"Calendar detection failed: {e}")
            return {'status': 'error', 'message': str(e), 'events': []}

    def suggest_calendar_entry(self, message_id: str) -> Dict:
        """
        Suggest the best calendar entry from an email (most important event).
        """
        result = self.extract_calendar_events(message_id)
        if result.get('status') == 'error' or not result.get('events'):
            return {'status': 'success', 'has_event': False, 'message': 'No upcoming events found in this email'}

        # Pick the first (most prominent) event
        event = result['events'][0]
        return {
            'status': 'success',
            'has_event': True,
            'suggestion': event,
            'message_id': message_id,
            'subject': result.get('subject', ''),
            'add_to_calendar_hint': (
                f"📅 Suggested event: '{event.get('title', 'Meeting')}' "
                f"on {event.get('date', 'TBD')} at {event.get('time', 'TBD')}"
            )
        }

    def _parse_event_datetime(self, date_str: str, time_str: str) -> str:
        """Parse date + time strings into ISO 8601 format for Calendar API."""
        try:
            import dateutil.parser
            combined = f"{date_str} {time_str}".strip()
            dt = dateutil.parser.parse(combined, fuzzy=True)
            return dt.strftime('%Y-%m-%dT%H:%M:%S')
        except Exception:
            from datetime import datetime
            return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    def generate_ics_content(self, event: Dict, description: str = '') -> str:
        """
        Generate .ics file content for a calendar event.

        Args:
            event: Event dict with title, date, time, location, participants, etc.
            description: Optional extra description

        Returns:
            .ics file content as string
        """
        from datetime import datetime, timedelta
        uid = str(uuid.uuid4())
        now = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

        # Parse start time
        start_iso = self._parse_event_datetime(
            event.get('date', datetime.now().strftime('%Y-%m-%d')),
            event.get('time', '00:00')
        )
        try:
            from datetime import datetime as _dt
            start_dt = _dt.fromisoformat(start_iso)
        except Exception:
            start_dt = datetime.now()

        duration_str = event.get('duration', '')
        if duration_str:
            try:
                # Try to parse duration like "1 hour", "30 minutes", "2 hours"
                import re
                hrs = re.search(r'(\d+)\s*hour', duration_str)
                mins = re.search(r'(\d+)\s*min', duration_str)
                hours = int(hrs.group(1)) if hrs else 1
                minutes = int(mins.group(1)) if mins else 0
                end_dt = start_dt + timedelta(hours=hours, minutes=minutes)
            except Exception:
                end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

        dtstart = start_dt.strftime('%Y%m%dT%H%M%S')
        dtend = end_dt.strftime('%Y%m%dT%H%M%S')

        title = event.get('title', 'Meeting').replace(
            ',', '\\,').replace('\n', '\\n')
        location = event.get('location', '').replace(
            ',', '\\,').replace('\n', '\\n')
        participants = event.get('participants', [])
        attendees = '\n'.join(
            f'ATTENDEE;CN={p}:mailto:{p}' if '@' in p else f'ATTENDEE;CN={p}:mailto:'
            for p in participants
        ) if participants else ''

        notes = event.get('notes', description or '').replace(
            ',', '\\,').replace('\n', '\\n')

        ics_lines = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//Octa Bot Email Agent//EN',
            'CALSCALE:GREGORIAN',
            'METHOD:PUBLISH',
            'BEGIN:VEVENT',
            f'UID:{uid}@Octa Bot',
            f'DTSTAMP:{now}',
            f'DTSTART:{dtstart}',
            f'DTEND:{dtend}',
            f'SUMMARY:{title}',
        ]
        if location:
            ics_lines.append(f'LOCATION:{location}')
        if notes:
            ics_lines.append(f'DESCRIPTION:{notes}')
        if attendees:
            ics_lines.extend(attendees.split('\n'))
        ics_lines += ['END:VEVENT', 'END:VCALENDAR']
        return '\r\n'.join(ics_lines)

    def export_to_calendar(self, event_data: Dict, save_ics: bool = True) -> Dict:
        """
        Export a detected event to Google Calendar and/or save as .ics file.

        Args:
            event_data: Event dict from extract_calendar_events (one event object)
                        or the full result dict (uses first event)
            save_ics: Whether to also save an .ics file locally

        Returns:
            Dict with export status, ics_path, and google_calendar result
        """
        # Accept either a single event dict or the full extraction result
        if 'events' in event_data:
            events = event_data.get('events', [])
            if not events:
                return {'status': 'error', 'message': 'No events found in provided data'}
            event = events[0]
        else:
            event = event_data

        results = {'status': 'success',
                   'event_title': event.get('title', 'Meeting')}

        # --- Save .ics file ---
        ics_path = None
        if save_ics:
            try:
                ics_content = self.generate_ics_content(event)
                ics_dir = Path(__file__).parent.parent.parent.parent / \
                    'data' / 'calendar_exports'
                ics_dir.mkdir(parents=True, exist_ok=True)
                safe_title = ''.join(
                    c if c.isalnum() or c in ' _-' else '_'
                    for c in event.get('title', 'event')
                )[:40].strip()
                ics_file = ics_dir / \
                    f"{safe_title}_{str(uuid.uuid4())[:6]}.ics"
                ics_file.write_text(ics_content, encoding='utf-8')
                ics_path = str(ics_file)
                results['ics_saved'] = True
                results['ics_path'] = ics_path
                results['ics_content'] = ics_content
                logger.info(f"Saved .ics file: {ics_path}")
            except Exception as e:
                logger.error(f"Failed to save .ics file: {e}")
                results['ics_saved'] = False
                results['ics_error'] = str(e)

        # --- Try Google Calendar API ---
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from datetime import datetime

            TOKEN_PATH = 'token.json'
            CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'

            creds = None
            if Path(TOKEN_PATH).exists():
                with open(TOKEN_PATH, 'r') as f:
                    creds = Credentials.from_authorized_user_info(json.load(f))

            if not creds or not hasattr(creds, 'scopes') or (
                creds.scopes and CALENDAR_SCOPE not in creds.scopes
            ):
                results['google_calendar'] = 'skipped'
                results['google_calendar_note'] = (
                    'Google Calendar API requires calendar scope. '
                    'Re-run OAuth with calendar scope to enable direct export. '
                    'Use the .ics file to import manually.'
                )
            else:
                if creds.expired and creds.refresh_token:
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())

                cal_service = build('calendar', 'v3', credentials=creds)

                # Build the event body
                start_iso = self._parse_event_datetime(
                    event.get('date', datetime.now().strftime('%Y-%m-%d')),
                    event.get('time', '00:00')
                )
                event_body = {
                    'summary': event.get('title', 'Meeting'),
                    'location': event.get('location', ''),
                    'description': event.get('notes', ''),
                    'start': {'dateTime': start_iso, 'timeZone': event.get('timezone', 'UTC')},
                    'end': {'dateTime': start_iso, 'timeZone': event.get('timezone', 'UTC')},
                }
                if event.get('participants'):
                    event_body['attendees'] = [
                        {'email': p} if '@' in p else {'displayName': p}
                        for p in event['participants']
                    ]

                created = cal_service.events().insert(
                    calendarId='primary',
                    body=event_body
                ).execute()
                results['google_calendar'] = 'created'
                results['google_event_id'] = created.get('id', '')
                results['google_event_link'] = created.get('htmlLink', '')
                logger.info(
                    f"Created Google Calendar event: {created.get('id', '')}")

        except ImportError:
            results['google_calendar'] = 'unavailable'
            results['google_calendar_note'] = 'Google API client not available'
        except Exception as e:
            results['google_calendar'] = 'error'
            results['google_calendar_note'] = str(e)
            logger.warning(f"Google Calendar export failed: {e}")

        if ics_path:
            results['message'] = (
                f"✅ Event '{event.get('title', 'Meeting')}' exported. "
                f".ics file saved to: {ics_path}"
            )
        else:
            results['message'] = f"Event '{event.get('title', 'Meeting')}' processed."

        return results


# Singleton + convenience functions
_detector: Optional[CalendarDetector] = None


def _get_detector() -> CalendarDetector:
    global _detector
    if _detector is None:
        from src.email.gmail_auth import get_gmail_service
        _detector = CalendarDetector(get_gmail_service())
    return _detector


def extract_calendar_events(message_id: str) -> Dict:
    return _get_detector().extract_calendar_events(message_id)


def suggest_calendar_entry(message_id: str) -> Dict:
    return _get_detector().suggest_calendar_entry(message_id)


def export_to_calendar(event_data: Dict, save_ics: bool = True) -> Dict:
    """Export a detected event to Google Calendar and/or .ics file."""
    return _get_detector().export_to_calendar(event_data, save_ics)
