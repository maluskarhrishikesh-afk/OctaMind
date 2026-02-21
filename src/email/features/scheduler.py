"""
Email Scheduler

Schedule emails to be sent at a future time.
Uses a JSON file for persistence and a background daemon thread for delivery.
"""

import base64
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.scheduler")

_DATA_FILE = Path(__file__).parent.parent.parent.parent / \
    "data" / "email_schedule.json"
_scheduler_started = False
_lock = threading.Lock()


def _load_scheduled() -> List[Dict]:
    if not _DATA_FILE.exists():
        return []
    try:
        return json.loads(_DATA_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def _save_scheduled(items: List[Dict]):
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(
        items, indent=2, default=str), encoding='utf-8')


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = MIMEMultipart()
    msg['to'] = to
    msg['subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')


class EmailScheduler:
    """Schedule emails for future delivery."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id
        self._start_background_thread()

    def _start_background_thread(self):
        global _scheduler_started
        if not _scheduler_started:
            _scheduler_started = True
            t = threading.Thread(target=self._run_scheduler, daemon=True)
            t.start()
            logger.info("Email scheduler background thread started")

    def _run_scheduler(self):
        """Background thread: check every 60s and send due emails."""
        while True:
            try:
                self._process_due_emails()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            time.sleep(60)

    def _process_due_emails(self):
        with _lock:
            items = _load_scheduled()
            now = datetime.now()
            updated = False
            for item in items:
                if item.get('status') != 'pending':
                    continue
                send_time_str = item.get('send_time', '')
                try:
                    send_time = datetime.fromisoformat(send_time_str)
                except Exception:
                    continue
                if send_time <= now:
                    # Send it
                    try:
                        raw = _build_raw(
                            item['to'], item['subject'], item['body'])
                        self.gmail_service.users().messages().send(
                            userId=self.user_id,
                            body={'raw': raw}
                        ).execute()
                        item['status'] = 'sent'
                        item['sent_at'] = now.isoformat()
                        logger.info(
                            f"Scheduled email sent: {item['subject']} to {item['to']}")
                    except Exception as e:
                        item['status'] = 'failed'
                        item['error'] = str(e)
                        logger.error(
                            f"Failed to send scheduled email {item['id']}: {e}")
                    updated = True
            if updated:
                _save_scheduled(items)

    def schedule_email(self, to: str, subject: str, body: str, send_time: str) -> Dict:
        """
        Schedule an email for future delivery.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            send_time: ISO datetime string or natural language like "tomorrow 9am"

        Returns:
            Dict with scheduled_id and confirmation
        """
        # Parse send_time — try ISO first, then natural language
        parsed_time = None
        try:
            parsed_time = datetime.fromisoformat(send_time)
        except Exception:
            pass

        if parsed_time is None:
            try:
                import dateutil.parser
                parsed_time = dateutil.parser.parse(send_time, fuzzy=True)
            except Exception:
                return {
                    'status': 'error',
                    'message': f"Could not parse send time: '{send_time}'. Use ISO format like '2026-02-21T09:00:00' or natural language."
                }

        if parsed_time <= datetime.now():
            return {'status': 'error', 'message': 'Scheduled time must be in the future'}

        scheduled_id = str(uuid.uuid4())[:8]
        item = {
            'id': scheduled_id,
            'to': to,
            'subject': subject,
            'body': body,
            'send_time': parsed_time.isoformat(),
            'send_time_human': parsed_time.strftime('%Y-%m-%d %H:%M'),
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }
        with _lock:
            items = _load_scheduled()
            items.append(item)
            _save_scheduled(items)

        return {
            'status': 'success',
            'scheduled_id': scheduled_id,
            'to': to,
            'subject': subject,
            'send_time': parsed_time.strftime('%Y-%m-%d %H:%M'),
            'message': f"Email scheduled for {parsed_time.strftime('%Y-%m-%d at %H:%M')}"
        }

    def list_scheduled_emails(self) -> Dict:
        """List all scheduled emails including sent and failed."""
        with _lock:
            items = _load_scheduled()
        pending = [i for i in items if i.get('status') == 'pending']
        sent = [i for i in items if i.get('status') == 'sent']
        failed = [i for i in items if i.get('status') == 'failed']
        return {
            'status': 'success',
            'pending': pending,
            'sent': sent[-5:],  # Last 5 sent
            'failed': failed,
            'total_pending': len(pending)
        }

    def cancel_scheduled_email(self, scheduled_id: str) -> Dict:
        """Cancel a pending scheduled email."""
        with _lock:
            items = _load_scheduled()
            for item in items:
                if item.get('id') == scheduled_id:
                    if item.get('status') != 'pending':
                        return {
                            'status': 'error',
                            'message': f"Cannot cancel: email status is '{item['status']}'"
                        }
                    item['status'] = 'cancelled'
                    _save_scheduled(items)
                    return {
                        'status': 'success',
                        'message': f"Scheduled email '{item.get('subject', '')}' cancelled"
                    }
        return {'status': 'error', 'message': f"Scheduled email '{scheduled_id}' not found"}

    def update_scheduled_email(self, scheduled_id: str, send_time: str) -> Dict:
        """Update the send time of a pending scheduled email."""
        try:
            import dateutil.parser
            parsed_time = dateutil.parser.parse(send_time, fuzzy=True)
        except Exception:
            return {'status': 'error', 'message': f"Could not parse time: '{send_time}'"}

        if parsed_time <= datetime.now():
            return {'status': 'error', 'message': 'New send time must be in the future'}

        with _lock:
            items = _load_scheduled()
            for item in items:
                if item.get('id') == scheduled_id:
                    if item.get('status') != 'pending':
                        return {'status': 'error', 'message': 'Can only update pending emails'}
                    item['send_time'] = parsed_time.isoformat()
                    item['send_time_human'] = parsed_time.strftime(
                        '%Y-%m-%d %H:%M')
                    _save_scheduled(items)
                    return {
                        'status': 'success',
                        'message': f"Rescheduled to {parsed_time.strftime('%Y-%m-%d at %H:%M')}"
                    }
        return {'status': 'error', 'message': f"Scheduled email '{scheduled_id}' not found"}


# Singleton + convenience functions
_scheduler: Optional[EmailScheduler] = None


def _get_scheduler() -> EmailScheduler:
    global _scheduler
    if _scheduler is None:
        from src.email.gmail_auth import get_gmail_service
        _scheduler = EmailScheduler(get_gmail_service())
    return _scheduler


def schedule_email(to: str, subject: str, body: str, send_time: str) -> Dict:
    return _get_scheduler().schedule_email(to, subject, body, send_time)


def list_scheduled_emails() -> Dict:
    return _get_scheduler().list_scheduled_emails()


def cancel_scheduled_email(scheduled_id: str) -> Dict:
    return _get_scheduler().cancel_scheduled_email(scheduled_id)


def update_scheduled_email(scheduled_id: str, send_time: str) -> Dict:
    """Update the send time of a pending scheduled email."""
    return _get_scheduler().update_scheduled_email(scheduled_id, send_time)
