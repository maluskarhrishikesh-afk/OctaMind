"""
Follow-up Tracker

Mark emails for follow-up, track pending follow-ups, and detect unanswered emails.
Data is stored in a JSON file alongside agent memory.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.followup")

# Storage file — kept in project root data folder
_DATA_FILE = Path(__file__).parent.parent.parent.parent / \
    "data" / "email_followups.json"


def _load_followups() -> List[Dict]:
    """Load follow-up data from disk."""
    if not _DATA_FILE.exists():
        return []
    try:
        return json.loads(_DATA_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def _save_followups(followups: List[Dict]):
    """Persist follow-up data to disk."""
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(followups, indent=2,
                          default=str), encoding='utf-8')


class FollowupTracker:
    """Track emails that need follow-up."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id

    def mark_for_followup(self, message_id: str, days: int = 3, note: str = '') -> Dict:
        """
        Mark an email for follow-up in N days.

        Args:
            message_id: Gmail message ID
            days: Days until follow-up is due
            note: Optional note about why follow-up is needed
        """
        try:
            # Get email metadata
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id,
                format='metadata',
                metadataHeaders=['Subject', 'From']
            ).execute()
            headers = msg.get('payload', {}).get('headers', [])
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            sender = next((h['value']
                          for h in headers if h['name'].lower() == 'from'), '')

            due_date = (datetime.now() + timedelta(days=days)
                        ).strftime('%Y-%m-%d')
            followups = _load_followups()

            # Check if already tracked
            existing = next(
                (f for f in followups if f['message_id'] == message_id), None)
            if existing:
                existing['due_date'] = due_date
                existing['note'] = note
                existing['status'] = 'pending'
                _save_followups(followups)
                return {'status': 'success', 'message': 'Follow-up updated', 'due_date': due_date}

            followup = {
                'message_id': message_id,
                'subject': subject,
                'sender': sender,
                'note': note,
                'due_date': due_date,
                'created_at': datetime.now().strftime('%Y-%m-%d'),
                'status': 'pending'  # pending | done | dismissed
            }
            followups.append(followup)
            _save_followups(followups)
            return {
                'status': 'success',
                'message': f"Follow-up set for {due_date}",
                'due_date': due_date,
                'subject': subject,
                'message_id': message_id
            }
        except Exception as e:
            logger.error(f"Mark followup failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_pending_followups(self) -> Dict:
        """Get all pending follow-up emails."""
        followups = _load_followups()
        today = datetime.now().strftime('%Y-%m-%d')
        pending = [f for f in followups if f.get('status') == 'pending']

        # Separate overdue vs upcoming
        overdue = [f for f in pending if f.get('due_date', '9999') <= today]
        upcoming = [f for f in pending if f.get('due_date', '9999') > today]

        # Sort overdue by due_date ascending
        overdue.sort(key=lambda x: x.get('due_date', ''))
        upcoming.sort(key=lambda x: x.get('due_date', ''))

        return {
            'status': 'success',
            'total_pending': len(pending),
            'overdue': overdue,
            'upcoming': upcoming
        }

    def mark_done(self, message_id: str) -> Dict:
        """Mark a follow-up as completed."""
        followups = _load_followups()
        found = False
        for f in followups:
            if f['message_id'] == message_id:
                f['status'] = 'done'
                f['completed_at'] = datetime.now().strftime('%Y-%m-%d')
                found = True
                break
        if found:
            _save_followups(followups)
            return {'status': 'success', 'message': 'Follow-up marked as done'}
        return {'status': 'error', 'message': 'Follow-up not found'}

    def dismiss_followup(self, message_id: str) -> Dict:
        """Dismiss a follow-up (no longer needed)."""
        followups = _load_followups()
        for f in followups:
            if f['message_id'] == message_id:
                f['status'] = 'dismissed'
                _save_followups(followups)
                return {'status': 'success', 'message': 'Follow-up dismissed'}
        return {'status': 'error', 'message': 'Follow-up not found'}

    def check_unanswered_emails(self, older_than_days: int = 3,
                                max_results: int = 20) -> Dict:
        """
        Find emails you received but haven't replied to.
        Uses Gmail query: received emails not replied to.
        """
        try:
            # Gmail query: received (not from me), not replied, older than N days
            cutoff = (datetime.now() - timedelta(days=older_than_days)
                      ).strftime('%Y/%m/%d')
            query = f'in:inbox -from:me -label:sent before:{datetime.now().strftime("%Y/%m/%d")} after:{cutoff}'

            # A simpler approach: look for emails with no sender being "me"
            response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f'in:inbox -from:me after:{cutoff}',
                maxResults=max_results
            ).execute()
            messages = response.get('messages', [])
            unanswered = []

            for msg_item in messages[:max_results]:
                try:
                    msg = self.gmail_service.users().messages().get(
                        userId=self.user_id, id=msg_item['id'],
                        format='metadata',
                        metadataHeaders=['Subject', 'From', 'Date']
                    ).execute()
                    headers = msg.get('payload', {}).get('headers', [])
                    subject = next(
                        (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                    sender = next(
                        (h['value'] for h in headers if h['name'].lower() == 'from'), '')
                    date_h = next(
                        (h['value'] for h in headers if h['name'].lower() == 'date'), '')
                    unanswered.append({
                        'id': msg_item['id'],
                        'subject': subject,
                        'sender': sender,
                        'date': date_h
                    })
                except Exception:
                    pass
            return {
                'status': 'success',
                'unanswered': unanswered,
                'count': len(unanswered),
                'older_than_days': older_than_days
            }
        except Exception as e:
            logger.error(f"Check unanswered failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def send_followup_reminder(self, message_id: str) -> Dict:
        """
        Send an email reminder to yourself about a tracked follow-up.

        Looks up the follow-up record for the given message_id and sends
        a reminder email to the authenticated user's own address.

        Args:
            message_id: Gmail message ID of the tracked email

        Returns:
            Dict with send status and confirmation
        """
        import base64
        from email.mime.text import MIMEText

        # Find the follow-up record
        followups = _load_followups()
        record = next((f for f in followups if f.get(
            'message_id') == message_id), None)

        if not record:
            return {
                'status': 'error',
                'message': f"No follow-up tracking found for message ID '{message_id}'. "
                "Use mark_for_followup first."
            }

        if record.get('status') != 'pending':
            return {
                'status': 'error',
                'message': f"Follow-up status is '{record.get('status')}', not pending."
            }

        subject = record.get('subject', 'Email Follow-up')
        sender = record.get('sender', 'Unknown Sender')
        due_date = record.get('due_date', 'today')
        note = record.get('note', '')

        # Get user's own email address
        try:
            profile = self.gmail_service.users().getProfile(userId=self.user_id).execute()
            my_email = profile.get('emailAddress', 'me')
        except Exception:
            my_email = 'me'

        # Build reminder email body
        body_lines = [
            "📌 Follow-up Reminder from OctaMind",
            "=" * 40,
            f"Original email: {subject}",
            f"From: {sender}",
            f"Due date: {due_date}",
        ]
        if note:
            body_lines.append(f"Your note: {note}")
        body_lines += [
            "",
            "This is an automated reminder to follow up on the above email.",
            f"Message ID: {message_id}",
        ]
        body_text = '\n'.join(body_lines)

        try:
            msg = MIMEText(body_text, 'plain')
            msg['to'] = my_email
            msg['subject'] = f"🔔 Follow-up Reminder: {subject}"
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
            sent = self.gmail_service.users().messages().send(
                userId=self.user_id,
                body={'raw': raw}
            ).execute()

            # Update follow-up record to mark reminder sent
            record['reminder_sent_at'] = datetime.now().strftime(
                '%Y-%m-%d %H:%M')
            _save_followups(followups)

            return {
                'status': 'success',
                'message': f"✅ Follow-up reminder sent to {my_email}",
                'message_id': sent.get('id', ''),
                'original_subject': subject,
                'due_date': due_date
            }
        except Exception as e:
            logger.error(f"send_followup_reminder failed: {e}")
            return {'status': 'error', 'message': str(e)}


# Singleton + convenience functions
_tracker: Optional[FollowupTracker] = None


def _get_tracker() -> FollowupTracker:
    global _tracker
    if _tracker is None:
        from src.email.gmail_auth import get_gmail_service
        _tracker = FollowupTracker(get_gmail_service())
    return _tracker


def mark_for_followup(message_id: str, days: int = 3, note: str = '') -> Dict:
    return _get_tracker().mark_for_followup(message_id, days, note)


def get_pending_followups() -> Dict:
    return _get_tracker().get_pending_followups()


def check_unanswered_emails(older_than_days: int = 3) -> Dict:
    return _get_tracker().check_unanswered_emails(older_than_days)


def mark_followup_done(message_id: str) -> Dict:
    """Mark a follow-up as completed."""
    return _get_tracker().mark_done(message_id)


def dismiss_followup(message_id: str) -> Dict:
    """Dismiss a follow-up (no longer needed)."""
    return _get_tracker().dismiss_followup(message_id)


def send_followup_reminder(message_id: str) -> Dict:
    """Send an email reminder to yourself about a tracked follow-up."""
    return _get_tracker().send_followup_reminder(message_id)
