"""
Gmail Service Integration Module

This module provides core Gmail operations:
- Send emails
- List/search emails
- Delete emails
- Get inbox count
- Email summarization (via gmail_summarizer)

Usage:
    from src.email import send_email, list_emails
    
    result = send_email(
        to="recipient@example.com",
        subject="Hello",
        message="This is a test email"
    )
"""

import base64
import logging
from typing import Dict, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import authentication module
from .gmail_auth import get_gmail_service
from .email_summarizer import EmailSummarizer

# Setup logger
logger = logging.getLogger("email_agent.gmail_service")
logger.setLevel(logging.DEBUG)


def create_message(sender: str, to: str, subject: str, message_text: str) -> Dict:
    """Create a MIME message for email sending."""
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject

    msg = MIMEText(message_text)
    message.attach(msg)
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw_message}


class GmailServiceClient:
    """Client for interacting with Gmail"""

    def __init__(self):
        """Initialize the Gmail service client"""
        self.gmail_service = get_gmail_service()
        self.user_id = 'me'
        # Initialize summarizer (lazy loading)
        self._summarizer = None

    @property
    def summarizer(self):
        """Lazy load summarizer"""
        if self._summarizer is None:
            self._summarizer = EmailSummarizer(
                self.gmail_service, self.user_id)
        return self._summarizer

    def send_email(self,
                   to: str,
                   subject: str,
                   message: str) -> Dict:
        """
        Send an email using Gmail API

        Args:
            to: Recipient email address
            subject: Email subject
            message: Email body/message

        Returns:
            Dictionary containing messageId, threadId, and status
        """
        try:
            message_obj = create_message(
                self.user_id, to=to, subject=subject, message_text=message)
            sent_message = self.gmail_service.users().messages().send(
                userId=self.user_id,
                body=message_obj
            ).execute()

            return {
                'status': 'success',
                'messageId': sent_message['id'],
                'threadId': sent_message['threadId'],
                'message': 'Email sent successfully'
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Error while sending the email',
                'error': str(e)
            }

    def list_emails(self, query: str = '', max_results: int = 10) -> List[Dict]:
        """
        List emails from mailbox

        Args:
            query: Gmail search query (e.g., 'is:unread')
            max_results: Maximum number of emails to return

        Returns:
            List of email dictionaries
        """
        try:
            response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=query,
                maxResults=max_results
            ).execute()

            messages = response.get('messages', [])

            # Extract message details
            messages_list = []
            for msg_item in messages:
                msg = self.gmail_service.users().messages().get(
                    userId=self.user_id,
                    id=msg_item['id'],
                    format='full'
                ).execute()

                headers = msg['payload']['headers']
                subject = next(
                    (h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                sender = next(
                    (h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                date = next(
                    (h['value'] for h in headers if h['name'].lower() == 'date'), 'No Date')

                # Extract email body
                body = ''
                snippet = msg.get('snippet', '')

                if 'payload' in msg:
                    payload = msg['payload']
                    if 'parts' in payload:
                        # Multi-part email
                        for part in payload['parts']:
                            if part['mimeType'] == 'text/plain':
                                if 'data' in part['body']:
                                    body = base64.urlsafe_b64decode(
                                        part['body']['data']).decode('utf-8')
                                    break
                    elif 'body' in payload and 'data' in payload['body']:
                        # Simple email
                        body = base64.urlsafe_b64decode(
                            payload['body']['data']).decode('utf-8')

                messages_list.append({
                    'id': msg_item['id'],
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'body': body,
                    'snippet': snippet,
                    'labels': msg.get('labelIds', [])
                })

            return messages_list

        except Exception as e:
            logger.error(f"Error listing emails: {e}")
            return []

    def get_inbox_count(self) -> Dict:
        """
        Get the total count of emails in the inbox

        Returns:
            Dictionary containing total messages, unread messages, and threads
        """
        try:
            # Get INBOX label info
            label = self.gmail_service.users().labels().get(
                userId=self.user_id,
                id='INBOX'
            ).execute()

            return {
                'status': 'success',
                'total_messages': label.get('messagesTotal', 0),
                'unread_messages': label.get('messagesUnread', 0),
                'total_threads': label.get('threadsTotal', 0),
                'unread_threads': label.get('threadsUnread', 0)
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Error getting inbox count',
                'error': str(e)
            }

    def get_todays_emails(self, max_results: int = 1000) -> List[Dict]:
        """
        Get emails received today (after midnight)

        Args:
            max_results: Maximum number of emails to return

        Returns:
            List of email dictionaries received today
        """
        from datetime import datetime

        try:
            # Get today's date at midnight
            today = datetime.now()
            start_of_day = today.replace(
                hour=0, minute=0, second=0, microsecond=0)
            date_str = start_of_day.strftime('%Y/%m/%d')

            # Use Gmail query to filter by date
            query = f'after:{date_str}'

            # Use existing list_emails method with date filter
            return self.list_emails(query=query, max_results=max_results)

        except Exception as e:
            logger.error(f"Error getting today's emails: {e}")
            return []

    def delete_emails(self, query: str = '', max_results: int = 5) -> Dict:
        """
        Delete emails from mailbox using batch operations for maximum speed

        Args:
            query: Gmail search query (e.g., 'is:unread')
            max_results: Maximum number of emails to delete

        Returns:
            Dictionary with status and deleted email IDs
        """
        try:
            # First, list emails matching the query
            response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=query,
                maxResults=max_results
            ).execute()

            messages = response.get('messages', [])

            if not messages:
                return {
                    'status': 'success',
                    'deleted_count': 0,
                    'message': 'No emails found to delete'
                }

            # Get message IDs
            msg_ids = [msg['id'] for msg in messages]

            # Batch delete using batchModify (moves to trash)
            # Gmail API allows up to 1000 IDs per batch
            batch_size = 1000
            deleted_count = 0

            for i in range(0, len(msg_ids), batch_size):
                batch_ids = msg_ids[i:i + batch_size]

                # Use batchModify to add TRASH label (equivalent to moving to trash)
                self.gmail_service.users().messages().batchModify(
                    userId=self.user_id,
                    body={
                        'ids': batch_ids,
                        'addLabelIds': ['TRASH']
                    }
                ).execute()

                deleted_count += len(batch_ids)

            # Get details of deleted emails (do this after for speed)
            # Only fetch details for first 50 to avoid slowdown
            deleted_details = []
            sample_size = min(50, len(msg_ids))

            if sample_size > 0:
                for msg_id in msg_ids[:sample_size]:
                    try:
                        msg = self.gmail_service.users().messages().get(
                            userId=self.user_id,
                            id=msg_id,
                            format='metadata',
                            metadataHeaders=['Subject', 'From']
                        ).execute()

                        headers = msg['payload']['headers']
                        subject = next(
                            (h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                        sender = next(
                            (h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')

                        deleted_details.append({
                            'id': msg_id,
                            'subject': subject,
                            'sender': sender
                        })
                    except:
                        # Skip if we can't get details
                        pass

            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'deleted_ids': msg_ids,
                'deleted_details': deleted_details,
                'message': f'Successfully moved {deleted_count} email(s) to trash',
                'note': f'Showing details for first {len(deleted_details)} emails' if deleted_count > len(deleted_details) else ''
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Error deleting emails',
                'error': str(e)
            }

    def _get_email_body(self, message_id: str) -> Dict:
        """
        Get full email body content

        Args:
            message_id: Gmail message ID

        Returns:
            Dictionary with email details and full body
        """
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id,
                id=message_id,
                format='full'
            ).execute()

            headers = msg['payload']['headers']
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next(
                (h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
            date = next(
                (h['value'] for h in headers if h['name'].lower() == 'date'), 'No Date')

            # Extract email body
            body = ''
            if 'payload' in msg:
                payload = msg['payload']
                if 'parts' in payload:
                    # Multi-part email
                    for part in payload['parts']:
                        if part['mimeType'] == 'text/plain':
                            if 'data' in part['body']:
                                body = base64.urlsafe_b64decode(
                                    part['body']['data']).decode('utf-8')
                                break
                elif 'body' in payload and 'data' in payload['body']:
                    # Simple email
                    body = base64.urlsafe_b64decode(
                        payload['body']['data']).decode('utf-8')

            # Fallback to snippet if body is empty
            if not body:
                body = msg.get('snippet', '')

            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body,
                'snippet': msg.get('snippet', ''),
                'thread_id': msg.get('threadId', '')
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    # Summarization methods (delegate to EmailSummarizer)
    def summarize_email(self, message_id: str) -> Dict:
        """
        Generate AI summary of an email

        Args:
            message_id: Gmail message ID

        Returns:
            Dictionary with summary, key_points, and metadata
        """
        return self.summarizer.summarize_email(message_id)

    def summarize_thread(self, thread_id: str) -> Dict:
        """
        Summarize an entire email thread

        Args:
            thread_id: Gmail thread ID

        Returns:
            Dictionary with thread summary and metadata
        """
        return self.summarizer.summarize_thread(thread_id)

    def generate_daily_digest(self, max_emails: int = 20) -> Dict:
        """
        Generate a digest of today's emails

        Args:
            max_emails: Maximum number of emails to include

        Returns:
            Dictionary with daily digest summary
        """
        return self.summarizer.generate_daily_digest(self.list_emails, max_emails)

    # ------------------------------------------------------------------ #
    # Feature delegation helpers (lazy-load each feature on first use)   #
    # ------------------------------------------------------------------ #

    def _feature(self, attr: str, cls_name: str):
        """Generic lazy loader for feature instances."""
        if not hasattr(self, f'_feat_{attr}') or getattr(self, f'_feat_{attr}') is None:
            from src.email import features as _f
            cls = getattr(_f, cls_name)
            setattr(self, f'_feat_{attr}', cls(
                self.gmail_service, self.user_id))
        return getattr(self, f'_feat_{attr}')

    # --- Action Items ---
    def extract_action_items(self, message_id: str) -> Dict:
        return self._feature('action_items', 'ActionItemExtractor').extract_action_items(message_id)

    def get_all_pending_actions(self, max_emails: int = 20) -> Dict:
        return self._feature('action_items', 'ActionItemExtractor').get_all_pending_actions(max_emails)

    # --- Smart Reply ---
    def generate_reply_suggestions(self, message_id: str, tone: str = 'all') -> Dict:
        return self._feature('smart_reply', 'SmartReplyGenerator').generate_reply_suggestions(message_id, tone)

    def quick_reply(self, message_id: str, reply_type: str = 'acknowledged') -> Dict:
        return self._feature('smart_reply', 'SmartReplyGenerator').quick_reply(message_id, reply_type)

    # --- Drafts ---
    def create_draft(self, to: str, subject: str, body: str) -> Dict:
        return self._feature('drafts', 'DraftManager').create_draft(to, subject, body)

    def list_drafts(self, max_results: int = 10) -> Dict:
        return self._feature('drafts', 'DraftManager').list_drafts(max_results)

    def send_draft(self, draft_id: str) -> Dict:
        return self._feature('drafts', 'DraftManager').send_draft(draft_id)

    def delete_draft(self, draft_id: str) -> Dict:
        return self._feature('drafts', 'DraftManager').delete_draft(draft_id)

    # --- Attachments ---
    def list_attachments(self, message_id: str) -> Dict:
        return self._feature('attachments', 'AttachmentManager').list_attachments(message_id)

    def download_attachment(self, message_id: str, attachment_id: str, filename: str, save_path: str = None) -> Dict:
        return self._feature('attachments', 'AttachmentManager').download_attachment(message_id, attachment_id, filename, save_path)

    def search_emails_with_attachments(self, file_type: str = 'all', max_results: int = 10) -> Dict:
        return self._feature('attachments', 'AttachmentManager').search_emails_with_attachments(file_type, max_results)

    # --- Categorizer ---
    def auto_categorize_email(self, message_id: str) -> Dict:
        return self._feature('categorizer', 'EmailCategorizer').auto_categorize_email(message_id)

    def apply_smart_labels(self, batch_size: int = 20) -> Dict:
        return self._feature('categorizer', 'EmailCategorizer').apply_smart_labels(batch_size)

    # --- Calendar Detection ---
    def extract_calendar_events(self, message_id: str) -> Dict:
        return self._feature('calendar_detect', 'CalendarDetector').extract_calendar_events(message_id)

    def suggest_calendar_entry(self, message_id: str) -> Dict:
        return self._feature('calendar_detect', 'CalendarDetector').suggest_calendar_entry(message_id)

    # --- Follow-up ---
    def mark_for_followup(self, message_id: str, days: int = 3, note: str = '') -> Dict:
        return self._feature('followup', 'FollowupTracker').mark_for_followup(message_id, days, note)

    def get_pending_followups(self) -> Dict:
        return self._feature('followup', 'FollowupTracker').get_pending_followups()

    def check_unanswered_emails(self, older_than_days: int = 3) -> Dict:
        return self._feature('followup', 'FollowupTracker').check_unanswered_emails(older_than_days)

    # --- Scheduler ---
    def schedule_email(self, to: str, subject: str, body: str, send_time: str) -> Dict:
        return self._feature('scheduler', 'EmailScheduler').schedule_email(to, subject, body, send_time)

    def list_scheduled_emails(self) -> Dict:
        return self._feature('scheduler', 'EmailScheduler').list_scheduled_emails()

    def cancel_scheduled_email(self, scheduled_id: str) -> Dict:
        return self._feature('scheduler', 'EmailScheduler').cancel_scheduled_email(scheduled_id)

    # --- Contacts ---
    def get_frequent_contacts(self, limit: int = 10, max_scan: int = 100) -> Dict:
        return self._feature('contacts', 'ContactIntelligence').get_frequent_contacts(limit, max_scan)

    def get_contact_summary(self, email_address: str) -> Dict:
        return self._feature('contacts', 'ContactIntelligence').get_contact_summary(email_address)

    # --- Priority ---
    def detect_urgent_emails(self, max_results: int = 20) -> Dict:
        return self._feature('priority', 'PriorityDetector').detect_urgent_emails(max_results)

    def auto_prioritize(self, message_id: str) -> Dict:
        return self._feature('priority', 'PriorityDetector').auto_prioritize(message_id)

    # --- Unsubscribe ---
    def detect_newsletters(self, max_results: int = 30) -> Dict:
        return self._feature('unsubscribe', 'UnsubscribeDetector').detect_newsletters(max_results)

    def extract_unsubscribe_link(self, message_id: str) -> Dict:
        return self._feature('unsubscribe', 'UnsubscribeDetector').extract_unsubscribe_link(message_id)

    # --- Analytics ---
    def get_email_stats(self, days: int = 30) -> Dict:
        return self._feature('analytics', 'EmailAnalytics').get_email_stats(days)

    def get_productivity_insights(self) -> Dict:
        return self._feature('analytics', 'EmailAnalytics').get_productivity_insights()

    def calculate_response_time(self, message_id: str) -> Dict:
        return self._feature('analytics', 'EmailAnalytics').calculate_response_time(message_id)

    def visualize_patterns(self, days: int = 30) -> Dict:
        return self._feature('analytics', 'EmailAnalytics').visualize_patterns(days)

    def generate_weekly_report(self) -> Dict:
        return self._feature('analytics', 'EmailAnalytics').generate_weekly_report()

    # --- Phase 4: Sub-functions ---
    def mark_action_complete(self, task_id: str) -> Dict:
        return self._feature('action_items', 'ActionItemExtractor').mark_action_complete(task_id)

    def get_saved_tasks(self, status_filter: str = 'pending') -> Dict:
        return self._feature('action_items', 'ActionItemExtractor').get_saved_tasks(status_filter)

    def create_category_rules(self, min_occurrences: int = 3) -> Dict:
        return self._feature('categorizer', 'EmailCategorizer').create_category_rules(min_occurrences)

    def export_to_calendar(self, event_data: Dict, save_ics: bool = True) -> Dict:
        return self._feature('calendar_detect', 'CalendarDetector').export_to_calendar(event_data, save_ics)

    def send_followup_reminder(self, message_id: str) -> Dict:
        return self._feature('followup', 'FollowupTracker').send_followup_reminder(message_id)

    def mark_followup_done(self, message_id: str) -> Dict:
        return self._feature('followup', 'FollowupTracker').mark_done(message_id)

    def dismiss_followup(self, message_id: str) -> Dict:
        return self._feature('followup', 'FollowupTracker').dismiss_followup(message_id)

    def update_scheduled_email(self, scheduled_id: str, send_time: str) -> Dict:
        return self._feature('scheduler', 'EmailScheduler').update_scheduled_email(scheduled_id, send_time)

    def suggest_vip_contacts(self) -> Dict:
        return self._feature('contacts', 'ContactIntelligence').suggest_vip_contacts()

    def export_contacts(self, format: str = 'csv', limit: int = 100) -> Dict:
        return self._feature('contacts', 'ContactIntelligence').export_contacts(format, limit)


# Convenient module-level functions
_client = None


def _get_client():
    """Get or create the Gmail client singleton"""
    global _client
    if _client is None:
        _client = GmailServiceClient()
    return _client


def send_email(to: str, subject: str, message: str) -> Dict:
    """
    Send an email (module-level convenience function)

    Args:
        to: Recipient email address
        subject: Email subject
        message: Email body

    Returns:
        Result dictionary with status and message details
    """
    return _get_client().send_email(to, subject, message)


def list_emails(query: str = '', max_results: int = 10) -> List[Dict]:
    """
    List emails (module-level convenience function)

    Args:
        query: Gmail search query
        max_results: Maximum results

    Returns:
        List of emails
    """
    return _get_client().list_emails(query, max_results)


def get_inbox_count() -> Dict:
    """
    Get the total count of emails in the inbox (module-level convenience function)

    Returns:
        Dictionary with total and unread message counts
    """
    return _get_client().get_inbox_count()


def get_todays_emails(max_results: int = 1000) -> List[Dict]:
    """
    Get emails received today (module-level convenience function)

    Args:
        max_results: Maximum number of emails to return

    Returns:
        List of emails received today
    """
    return _get_client().get_todays_emails(max_results)


def delete_emails(query: str = '', max_results: int = 5) -> Dict:
    """
    Delete emails (module-level convenience function)

    Args:
        query: Gmail search query
        max_results: Maximum number of emails to delete

    Returns:
        Dictionary with deletion status and details
    """
    return _get_client().delete_emails(query, max_results)


def summarize_email(message_id: str) -> Dict:
    """
    Summarize an email using AI (module-level convenience function)

    Args:
        message_id: Gmail message ID

    Returns:
        Dictionary with summary, key points, and analysis
    """
    return _get_client().summarize_email(message_id)


def summarize_thread(thread_id: str) -> Dict:
    """
    Summarize an email thread using AI (module-level convenience function)

    Args:
        thread_id: Gmail thread ID

    Returns:
        Dictionary with thread summary and discussion points
    """
    return _get_client().summarize_thread(thread_id)


def generate_daily_digest(max_emails: int = 20) -> Dict:
    """Generate daily email digest (module-level convenience function)"""
    return _get_client().generate_daily_digest(max_emails)


# ---- New feature convenience wrappers ---- #

def extract_action_items(message_id: str) -> Dict:
    return _get_client().extract_action_items(message_id)


def get_all_pending_actions(max_emails: int = 20) -> Dict:
    return _get_client().get_all_pending_actions(max_emails)


def generate_reply_suggestions(message_id: str, tone: str = 'all') -> Dict:
    return _get_client().generate_reply_suggestions(message_id, tone)


def quick_reply(message_id: str, reply_type: str = 'acknowledged') -> Dict:
    return _get_client().quick_reply(message_id, reply_type)


def create_draft(to: str, subject: str, body: str) -> Dict:
    return _get_client().create_draft(to, subject, body)


def list_drafts(max_results: int = 10) -> Dict:
    return _get_client().list_drafts(max_results)


def send_draft(draft_id: str) -> Dict:
    return _get_client().send_draft(draft_id)


def delete_draft(draft_id: str) -> Dict:
    return _get_client().delete_draft(draft_id)


def list_attachments(message_id: str) -> Dict:
    return _get_client().list_attachments(message_id)


def download_attachment(message_id: str, attachment_id: str, filename: str, save_path: str = None) -> Dict:
    return _get_client().download_attachment(message_id, attachment_id, filename, save_path)


def search_emails_with_attachments(file_type: str = 'all', max_results: int = 10) -> Dict:
    return _get_client().search_emails_with_attachments(file_type, max_results)


def auto_categorize_email(message_id: str) -> Dict:
    return _get_client().auto_categorize_email(message_id)


def apply_smart_labels(batch_size: int = 20) -> Dict:
    return _get_client().apply_smart_labels(batch_size)


def extract_calendar_events(message_id: str) -> Dict:
    return _get_client().extract_calendar_events(message_id)


def suggest_calendar_entry(message_id: str) -> Dict:
    return _get_client().suggest_calendar_entry(message_id)


def mark_for_followup(message_id: str, days: int = 3, note: str = '') -> Dict:
    return _get_client().mark_for_followup(message_id, days, note)


def get_pending_followups() -> Dict:
    return _get_client().get_pending_followups()


def check_unanswered_emails(older_than_days: int = 3) -> Dict:
    return _get_client().check_unanswered_emails(older_than_days)


def schedule_email(to: str, subject: str, body: str, send_time: str) -> Dict:
    return _get_client().schedule_email(to, subject, body, send_time)


def list_scheduled_emails() -> Dict:
    return _get_client().list_scheduled_emails()


def cancel_scheduled_email(scheduled_id: str) -> Dict:
    return _get_client().cancel_scheduled_email(scheduled_id)


def get_frequent_contacts(limit: int = 10) -> Dict:
    return _get_client().get_frequent_contacts(limit)


def get_contact_summary(email_address: str) -> Dict:
    return _get_client().get_contact_summary(email_address)


def detect_urgent_emails(max_results: int = 20) -> Dict:
    return _get_client().detect_urgent_emails(max_results)


def auto_prioritize(message_id: str) -> Dict:
    return _get_client().auto_prioritize(message_id)


def detect_newsletters(max_results: int = 30) -> Dict:
    return _get_client().detect_newsletters(max_results)


def extract_unsubscribe_link(message_id: str) -> Dict:
    return _get_client().extract_unsubscribe_link(message_id)


def get_email_stats(days: int = 30) -> Dict:
    return _get_client().get_email_stats(days)


def get_productivity_insights() -> Dict:
    return _get_client().get_productivity_insights()


def calculate_response_time(message_id: str) -> Dict:
    return _get_client().calculate_response_time(message_id)


def visualize_patterns(days: int = 30) -> Dict:
    return _get_client().visualize_patterns(days)


def generate_weekly_report() -> Dict:
    return _get_client().generate_weekly_report()


# --- Phase 4 convenience wrappers ---

def mark_action_complete(task_id: str) -> Dict:
    return _get_client().mark_action_complete(task_id)


def get_saved_tasks(status_filter: str = 'pending') -> Dict:
    return _get_client().get_saved_tasks(status_filter)


def create_category_rules(min_occurrences: int = 3) -> Dict:
    return _get_client().create_category_rules(min_occurrences)


def export_to_calendar(event_data: Dict, save_ics: bool = True) -> Dict:
    return _get_client().export_to_calendar(event_data, save_ics)


def send_followup_reminder(message_id: str) -> Dict:
    return _get_client().send_followup_reminder(message_id)


def mark_followup_done(message_id: str) -> Dict:
    return _get_client().mark_followup_done(message_id)


def dismiss_followup(message_id: str) -> Dict:
    return _get_client().dismiss_followup(message_id)


def update_scheduled_email(scheduled_id: str, send_time: str) -> Dict:
    return _get_client().update_scheduled_email(scheduled_id, send_time)


def suggest_vip_contacts() -> Dict:
    return _get_client().suggest_vip_contacts()


def export_contacts(format: str = 'csv', limit: int = 100) -> Dict:
    return _get_client().export_contacts(format, limit)


if __name__ == "__main__":
    # Example usage
    print("Gmail Service Integration Module")
    print("=" * 50)

    # Test email sending
    result = send_email(
        to="test@example.com",
        subject="Test Email from Python",
        message="This is a test email sent using Gmail MCP server"
    )

    print("Send Result:", result)
    print()

    # Test listing emails
    emails = list_emails(query='is:unread', max_results=5)
    print(f"Found {len(emails)} unread emails:")
    for email in emails:
        print(f"  - {email['subject']} from {email['sender']}")
