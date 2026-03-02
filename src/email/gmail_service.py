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
import mimetypes
import os
from typing import Dict, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders as _email_encoders

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

    def send_email_with_attachment(
        self,
        to: str,
        subject: str,
        message: str,
        attachment_path: str,
    ) -> Dict:
        """
        Send an email with a local file attached.

        Args:
            to:              Recipient email address.
            subject:         Email subject.
            message:         Plain-text email body.
            attachment_path: Absolute path to the local file to attach.
                             Also accepts the result dict from download_file
                             (will extract 'local_path' automatically).

        Returns:
            Dictionary containing messageId, threadId, and status.
        """
        # Accept a result dict from download_file
        if isinstance(attachment_path, dict):
            attachment_path = attachment_path.get("local_path", "")

        try:
            msg = MIMEMultipart()
            msg["to"] = to
            msg["from"] = self.user_id
            msg["subject"] = subject
            msg.attach(MIMEText(message, "plain"))

            if attachment_path and os.path.isfile(attachment_path):
                mime_type, _ = mimetypes.guess_type(attachment_path)
                if mime_type is None:
                    mime_type = "application/octet-stream"
                main_type, sub_type = mime_type.split("/", 1)

                with open(attachment_path, "rb") as f:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(f.read())

                _email_encoders.encode_base64(part)
                filename = os.path.basename(attachment_path)
                part.add_header(
                    "Content-Disposition", "attachment", filename=filename
                )
                msg.attach(part)
            elif attachment_path:
                # File path provided but file not found — fail loudly so the
                # workflow shows ❌ instead of silently sending without attachment.
                return {
                    "status": "error",
                    "message": f"Attachment file not found: {attachment_path}",
                    "error": f"File does not exist at path: {attachment_path}",
                }

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            sent = self.gmail_service.users().messages().send(
                userId=self.user_id,
                body={"raw": raw},
            ).execute()

            fname = os.path.basename(attachment_path) if attachment_path else "(none)"
            return {
                "status": "success",
                "messageId": sent["id"],
                "threadId": sent["threadId"],
                "message": f"Email with attachment '{fname}' sent successfully",
                "attachment": fname,
            }

        except Exception as exc:
            return {
                "status": "error",
                "message": "Error sending email with attachment",
                "error": str(exc),
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

    # --- Label / folder management ---

    def create_label(self, label_name: str) -> Dict:
        """
        Create a Gmail label (folder) if it does not already exist.

        Args:
            label_name: Display name for the label (e.g. "MasterCard").

        Returns:
            Dictionary with status and the label id/name.
        """
        try:
            # Check if the label already exists
            all_labels = self.gmail_service.users().labels().list(
                userId=self.user_id
            ).execute().get('labels', [])

            existing = next(
                (l for l in all_labels if l['name'].lower() == label_name.lower()),
                None,
            )
            if existing:
                return {
                    'status': 'success',
                    'label_id': existing['id'],
                    'label_name': existing['name'],
                    'message': f"Label '{label_name}' already exists.",
                }

            created = self.gmail_service.users().labels().create(
                userId=self.user_id,
                body={
                    'name': label_name,
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show',
                },
            ).execute()

            return {
                'status': 'success',
                'label_id': created['id'],
                'label_name': created['name'],
                'message': f"Label '{label_name}' created successfully.",
            }

        except Exception as exc:
            return {'status': 'error', 'message': f"Error creating label: {exc}"}

    def move_emails_to_label(
        self,
        query: str,
        label_name: str,
        max_results: int = 50,
    ) -> Dict:
        """
        Move emails matching *query* to the Gmail label *label_name*.
        Creates the label automatically if it does not exist.
        Removes the INBOX label so the emails no longer appear in inbox.

        Args:
            query:       Gmail search query (e.g. "from:mastercard.com").
            label_name:  Target label / folder name.
            max_results: Maximum number of emails to move.

        Returns:
            Dictionary with status, moved_count and label details.
        """
        try:
            # Ensure the label exists (creates it if missing)
            label_result = self.create_label(label_name)
            if label_result['status'] != 'success':
                return label_result
            label_id = label_result['label_id']

            # Find matching messages
            response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=query,
                maxResults=max_results,
            ).execute()
            messages = response.get('messages', [])

            if not messages:
                return {
                    'status': 'success',
                    'moved_count': 0,
                    'label_name': label_name,
                    'message': f"No emails found matching query '{query}'.",
                }

            msg_ids = [m['id'] for m in messages]

            # Move: add the target label, remove from INBOX
            self.gmail_service.users().messages().batchModify(
                userId=self.user_id,
                body={
                    'ids': msg_ids,
                    'addLabelIds': [label_id],
                    'removeLabelIds': ['INBOX'],
                },
            ).execute()

            return {
                'status': 'success',
                'moved_count': len(msg_ids),
                'label_name': label_name,
                'label_id': label_id,
                'message': (
                    f"Moved {len(msg_ids)} email(s) to label '{label_name}'."
                ),
            }

        except Exception as exc:
            return {'status': 'error', 'message': f"Error moving emails: {exc}"}

    # ── Out-of-Office / Vacation Responder ────────────────────────────────────

    def set_vacation_responder(
        self,
        enabled: bool,
        subject: str = "",
        body: str = "",
        start_date: str = "",
        end_date: str = "",
        restrict_to_contacts: bool = False,
    ) -> Dict:
        """
        Enable or disable Gmail's built-in Vacation / Out-of-Office auto-reply.

        Uses the Gmail Settings API ``users.settings.updateVacation`` endpoint.

        Args:
            enabled:              True to turn on, False to turn off.
            subject:              Auto-reply subject (e.g. 'Out of Office').
            body:                 Auto-reply message body.
            start_date:           ISO date string 'YYYY-MM-DD' (optional).
            end_date:             ISO date string 'YYYY-MM-DD' (optional).
            restrict_to_contacts: If True only known contacts get the auto-reply.
        """
        try:
            from datetime import datetime as _dt, timezone as _tz

            vacation_body: Dict = {
                'enableAutoReply': enabled,
                'responseSubject': subject,
                'responseBodyPlainText': body,
                'restrictToContacts': restrict_to_contacts,
                'restrictToDomain': False,
            }
            if start_date:
                ts = int(_dt.fromisoformat(start_date).replace(tzinfo=_tz.utc).timestamp() * 1000)
                vacation_body['startTime'] = ts
            if end_date:
                ts = int(_dt.fromisoformat(end_date).replace(tzinfo=_tz.utc).timestamp() * 1000)
                vacation_body['endTime'] = ts

            self.gmail_service.users().settings().updateVacation(
                userId=self.user_id,
                body=vacation_body,
            ).execute()

            state = "enabled" if enabled else "disabled"
            date_range = ""
            if start_date or end_date:
                date_range = f" ({start_date or '?'} → {end_date or 'indefinite'})"
            return {
                'status': 'success',
                'enabled': enabled,
                'subject': subject,
                'body': body,
                'message': (
                    f"✅ Out-of-Office auto-reply {state}{date_range}. "
                    f"Subject: '{subject}'"
                ),
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error setting vacation responder: {exc}"}

    def get_vacation_responder(self) -> Dict:
        """Return the current state of the Gmail vacation / OOO responder."""
        try:
            result = self.gmail_service.users().settings().getVacation(
                userId=self.user_id,
            ).execute()
            return {'status': 'success', 'settings': result}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error fetching vacation settings: {exc}"}

    def fetch_emails_to_markdown(
        self,
        query: str = "in:inbox",
        max_results: int = 5,
        cap: int = 20,
        output_dir: str = "",
    ) -> Dict:
        """Fetch multiple emails matching a Gmail query, save them as a Markdown
        file and return the file path + structured list.  This is the correct tool
        for "summarize the latest N emails from X" requests — it retrieves all
        emails in one shot (no per-email LLM round-trips) so the orchestrator can
        summarise the entire batch in its single final response.

        Args:
            query:      Gmail search query, e.g. ``"from:quora"`` or
                        ``"subject:invoice is:unread"``. Defaults to ``"in:inbox"``.
            max_results: Number of emails to fetch (default 5, capped at ``cap``).
            cap:        Hard upper limit to prevent runaway fetches (default 20).
            output_dir: Directory to write the .md file.  Falls back to
                        ``C:\\Users\\<user>\\_octamind_reports``.

        Returns:
            dict with keys: status, file_path, email_count, emails (list), content.
        """
        import os
        from datetime import datetime as _dt
        from pathlib import Path as _Path

        MAX_CAP = 50  # absolute ceiling
        cap = min(cap, MAX_CAP)

        if max_results > cap:
            return {
                'status': 'error',
                'message': (
                    f"❌ Requested {max_results} emails but the cap is {cap}. "
                    f"Please reduce max_results to {cap} or fewer."
                ),
            }

        try:
            emails = self.list_emails(query=query, max_results=max_results)
        except Exception as exc:
            return {'status': 'error', 'message': f"Error fetching emails: {exc}"}

        if not emails:
            return {
                'status': 'success',
                'email_count': 0,
                'emails': [],
                'content': f"No emails found for query: {query}",
                'file_path': '',
                'message': f"No emails matched: '{query}'",
            }

        # ── Build Markdown ──────────────────────────────────────────────────
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(c if c.isalnum() or c in "-_" else "_" for c in query)[:40]
        filename = f"emails_{safe_query}_{ts}.md"

        if not output_dir:
            output_dir = os.path.join(os.path.expanduser("~"), "_octamind_reports")
        _Path(output_dir).mkdir(parents=True, exist_ok=True)
        file_path = os.path.join(output_dir, filename)

        lines = [
            f"# Email Batch: `{query}`",
            f"*Fetched {len(emails)} email(s) — {_dt.now().strftime('%Y-%m-%d %H:%M')}*",
            "",
        ]

        structured: List[Dict] = []
        for i, em in enumerate(emails, 1):
            subject = em.get('subject', 'No Subject')
            sender  = em.get('sender', 'Unknown')
            date    = em.get('date', '')
            body    = em.get('body', em.get('snippet', '')).strip()

            lines += [
                "---",
                f"## {i}. {subject}",
                f"**From:** {sender}  ",
                f"**Date:** {date}",
                "",
                body,
                "",
            ]
            structured.append({
                'index': i,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body_preview': body[:300],
                'message_id': em.get('id', ''),
            })

        content = "\n".join(lines)
        try:
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except Exception as exc:
            file_path = ""
            logger.warning("Could not write email markdown file: %s", exc)

        return {
            'status': 'success',
            'email_count': len(emails),
            'emails': structured,
            'content': content,
            'file_path': file_path,
            'message': (
                f"Fetched {len(emails)} email(s) for '{query}'. "
                + (f"Saved to {file_path}" if file_path else "(file save failed)")
            ),
        }

    # ── Unsubscribe ───────────────────────────────────────────────────────────

    def unsubscribe_email(self, message_id: str) -> Dict:
        """Extract the List-Unsubscribe header from an email and return the
        unsubscribe URL/mailto so the user can action it.  Automatically opens
        the one-click unsubscribe endpoint when available (RFC 8058 POST)."""
        import re, urllib.request
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='metadata',
                metadataHeaders=['List-Unsubscribe', 'List-Unsubscribe-Post', 'From', 'Subject'],
            ).execute()
            hdrs = {h['name'].lower(): h['value'] for h in msg['payload']['headers']}
            unsub_hdr = hdrs.get('list-unsubscribe', '')
            post_hdr  = hdrs.get('list-unsubscribe-post', '')
            subject   = hdrs.get('subject', 'Unknown')
            sender    = hdrs.get('from', 'Unknown')

            if not unsub_hdr:
                return {
                    'status': 'not_supported',
                    'subject': subject,
                    'sender': sender,
                    'message': (
                        f"'{subject}' from {sender} has no List-Unsubscribe header. "
                        "Try replying with 'Unsubscribe' or visiting the link in the email body."
                    ),
                }

            urls    = re.findall(r'<(https?://[^>]+)>', unsub_hdr)
            mailtos = re.findall(r'<(mailto:[^>]+)>', unsub_hdr)

            # RFC 8058 one-click POST
            one_click_done = False
            if urls and post_hdr.strip().lower() == 'list-unsubscribe=one-click':
                try:
                    urllib.request.urlopen(
                        urllib.request.Request(
                            urls[0], data=b'List-Unsubscribe=One-Click', method='POST',
                            headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        ), timeout=10,
                    )
                    one_click_done = True
                except Exception:
                    pass

            action = "One-click unsubscribe sent!" if one_click_done else (
                f"Visit: {urls[0]}" if urls else
                f"Send blank email to: {mailtos[0].replace('mailto:', '') if mailtos else 'N/A'}"
            )
            return {
                'status': 'success',
                'subject': subject,
                'sender': sender,
                'one_click_done': one_click_done,
                'unsubscribe_urls': urls,
                'unsubscribe_mailto': mailtos,
                'message': f"Unsubscribe for '{subject}' from {sender}. {action}",
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error processing unsubscribe: {exc}"}

    # ── Archive / Thread ops ──────────────────────────────────────────────────

    def archive_emails(self, query: str, max_results: int = 50) -> Dict:
        """Remove emails from Inbox without deleting them (archive)."""
        try:
            messages = self.gmail_service.users().messages().list(
                userId=self.user_id, q=query, maxResults=max_results,
            ).execute().get('messages', [])
            if not messages:
                return {'status': 'success', 'archived_count': 0,
                        'message': f"No emails found for '{query}'."}
            ids = [m['id'] for m in messages]
            self.gmail_service.users().messages().batchModify(
                userId=self.user_id,
                body={'ids': ids, 'removeLabelIds': ['INBOX']},
            ).execute()
            return {'status': 'success', 'archived_count': len(ids),
                    'message': f"Archived {len(ids)} email(s). They remain in All Mail."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error archiving emails: {exc}"}

    def thread_mute(self, thread_id: str) -> Dict:
        """Mute a Gmail thread — future replies skip the Inbox."""
        try:
            self.gmail_service.users().threads().modify(
                userId=self.user_id, id=thread_id,
                body={'addLabelIds': ['MUTED'], 'removeLabelIds': ['INBOX']},
            ).execute()
            return {'status': 'success', 'thread_id': thread_id,
                    'message': f"Thread {thread_id} muted. Future replies will skip your Inbox."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error muting thread: {exc}"}

    def thread_archive(self, thread_id: str) -> Dict:
        """Archive an entire Gmail thread (removes from Inbox, keeps in All Mail)."""
        try:
            self.gmail_service.users().threads().modify(
                userId=self.user_id, id=thread_id,
                body={'removeLabelIds': ['INBOX']},
            ).execute()
            return {'status': 'success', 'thread_id': thread_id,
                    'message': f"Thread {thread_id} archived."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error archiving thread: {exc}"}

    def thread_delete(self, thread_id: str) -> Dict:
        """Move an entire Gmail thread to Trash."""
        try:
            self.gmail_service.users().threads().trash(
                userId=self.user_id, id=thread_id,
            ).execute()
            return {'status': 'success', 'thread_id': thread_id,
                    'message': f"Thread {thread_id} moved to Trash."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error deleting thread: {exc}"}

    # ── Smart Labels ──────────────────────────────────────────────────────────

    def create_smart_label_rule(
        self,
        label_name: str,
        from_email: str = "",
        subject_contains: str = "",
        to_email: str = "",
        also_archive: bool = False,
    ) -> Dict:
        """Label all existing emails matching criteria and report the Gmail
        filter-creation URL for automating future emails.

        Args:
            label_name:       Target label to create/apply.
            from_email:       Filter by sender address.
            subject_contains: Filter by text in subject.
            to_email:         Filter by recipient address.
            also_archive:     If True also remove matching emails from Inbox.
        """
        try:
            parts = []
            if from_email:       parts.append(f"from:{from_email}")
            if subject_contains: parts.append(f"subject:{subject_contains}")
            if to_email:         parts.append(f"to:{to_email}")
            if not parts:
                return {'status': 'error',
                        'message': "Specify at least one of: from_email, subject_contains, to_email"}

            query = " ".join(parts)
            label_r = self.create_label(label_name)
            if label_r['status'] != 'success':
                return label_r
            label_id = label_r['label_id']

            messages = self.gmail_service.users().messages().list(
                userId=self.user_id, q=query, maxResults=500,
            ).execute().get('messages', [])

            if messages:
                remove = ['INBOX'] if also_archive else []
                self.gmail_service.users().messages().batchModify(
                    userId=self.user_id,
                    body={'ids': [m['id'] for m in messages],
                          'addLabelIds': [label_id],
                          'removeLabelIds': remove},
                ).execute()

            return {
                'status': 'success',
                'label_name': label_name,
                'query': query,
                'emails_labeled': len(messages),
                'message': (
                    f"Applied label '{label_name}' to {len(messages)} existing email(s) "
                    f"matching '{query}'. To auto-label future emails, open Gmail → Settings → "
                    "Filters and Blocked Addresses → Create new filter."
                ),
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error creating label rule: {exc}"}

    def find_unanswered_emails(self, days: int = 3, max_results: int = 20) -> Dict:
        """Find sent emails that received no reply within the last N days."""
        from datetime import datetime as _dt, timedelta as _td
        try:
            cutoff = (_dt.now() - _td(days=days)).strftime("%Y/%m/%d")
            sent_msgs = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f"in:sent after:{cutoff}",
                maxResults=max_results,
            ).execute().get('messages', [])

            unanswered = []
            for item in sent_msgs:
                msg = self.gmail_service.users().messages().get(
                    userId=self.user_id, id=item['id'], format='metadata',
                    metadataHeaders=['Subject', 'To', 'Date'],
                ).execute()
                hdrs   = {h['name'].lower(): h['value'] for h in msg['payload']['headers']}
                thread = self.gmail_service.users().threads().get(
                    userId=self.user_id, id=msg['threadId'], format='minimal',
                ).execute()
                if len(thread.get('messages', [])) == 1:
                    unanswered.append({
                        'message_id': item['id'],
                        'thread_id': msg['threadId'],
                        'subject': hdrs.get('subject', 'No Subject'),
                        'to': hdrs.get('to', ''),
                        'date': hdrs.get('date', ''),
                    })

            return {
                'status': 'success',
                'unanswered_count': len(unanswered),
                'unanswered': unanswered,
                'message': f"Found {len(unanswered)} sent email(s) in the last {days} day(s) awaiting reply.",
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error finding unanswered emails: {exc}"}

    # ── Trash management ──────────────────────────────────────────────────────

    def empty_trash(self) -> Dict:
        """Permanently delete all emails currently in Trash."""
        try:
            # Paginate and batchDelete in chunks of 1000
            deleted = 0
            page_token = None
            while True:
                kwargs: Dict = {'userId': self.user_id, 'q': 'in:trash', 'maxResults': 1000}
                if page_token:
                    kwargs['pageToken'] = page_token
                resp = self.gmail_service.users().messages().list(**kwargs).execute()
                msgs = resp.get('messages', [])
                if msgs:
                    self.gmail_service.users().messages().batchDelete(
                        userId=self.user_id,
                        body={'ids': [m['id'] for m in msgs]},
                    ).execute()
                    deleted += len(msgs)
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
            return {'status': 'success', 'deleted_count': deleted,
                    'message': f"Trash emptied — {deleted} email(s) permanently deleted."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error emptying trash: {exc}"}

    # ── Spam ──────────────────────────────────────────────────────────────────

    def batch_mark_spam(self, query: str, max_results: int = 50) -> Dict:
        """Move emails matching *query* to Spam."""
        try:
            messages = self.gmail_service.users().messages().list(
                userId=self.user_id, q=query, maxResults=max_results,
            ).execute().get('messages', [])
            if not messages:
                return {'status': 'success', 'count': 0,
                        'message': f"No emails found for '{query}'."}
            ids = [m['id'] for m in messages]
            self.gmail_service.users().messages().batchModify(
                userId=self.user_id,
                body={'ids': ids, 'addLabelIds': ['SPAM'], 'removeLabelIds': ['INBOX']},
            ).execute()
            return {'status': 'success', 'count': len(ids),
                    'message': f"Moved {len(ids)} email(s) to Spam."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error marking emails as spam: {exc}"}

    # ── Forwarding ────────────────────────────────────────────────────────────

    def add_forwarding_address(self, forward_to: str) -> Dict:
        """Register a forwarding address (requires gmail.settings.sharing scope).
        Gmail sends a verification email — the recipient must confirm."""
        try:
            result = self.gmail_service.users().settings().forwardingAddresses().create(
                userId=self.user_id,
                body={'forwardingEmail': forward_to},
            ).execute()
            status = result.get('verificationStatus', 'pending')
            return {
                'status': 'success',
                'forward_to': forward_to,
                'verification_status': status,
                'message': (
                    f"Forwarding address '{forward_to}' registered. "
                    f"Verification: {status}. "
                    f"A confirmation email has been sent to {forward_to}."
                ),
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error adding forwarding address: {exc}"}

    def enable_email_forwarding(self, forward_to: str) -> Dict:
        """Enable auto-forwarding of all incoming email to *forward_to* (requires
        gmail.settings.sharing scope and the address to be pre-verified)."""
        try:
            self.gmail_service.users().settings().updateAutoForwarding(
                userId=self.user_id,
                body={
                    'enabled': True,
                    'emailAddress': forward_to,
                    'disposition': 'leaveInInbox',
                },
            ).execute()
            return {'status': 'success', 'forward_to': forward_to,
                    'message': f"Auto-forwarding enabled → {forward_to}. Copies kept in Inbox."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error enabling forwarding: {exc}"}

    # ── Signatures ────────────────────────────────────────────────────────────

    def get_signature(self, send_as_email: str = "me") -> Dict:
        """Get the Gmail signature for the given send-as address."""
        try:
            # Resolve 'me' to the actual address
            if send_as_email == 'me':
                profile = self.gmail_service.users().getProfile(userId='me').execute()
                send_as_email = profile.get('emailAddress', 'me')
            settings = self.gmail_service.users().settings().sendAs().get(
                userId=self.user_id, sendAsEmail=send_as_email,
            ).execute()
            return {
                'status': 'success',
                'email': send_as_email,
                'display_name': settings.get('displayName', ''),
                'signature': settings.get('signature', ''),
                'is_primary': settings.get('isPrimary', False),
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error getting signature: {exc}"}

    def set_signature(self, signature_html: str, send_as_email: str = "me") -> Dict:
        """Set the Gmail signature (HTML allowed) for the given send-as address."""
        try:
            if send_as_email == 'me':
                profile = self.gmail_service.users().getProfile(userId='me').execute()
                send_as_email = profile.get('emailAddress', 'me')
            self.gmail_service.users().settings().sendAs().patch(
                userId=self.user_id, sendAsEmail=send_as_email,
                body={'signature': signature_html},
            ).execute()
            return {'status': 'success',
                    'message': f"Signature updated for {send_as_email}."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error setting signature: {exc}"}

    # ── Email Templates ───────────────────────────────────────────────────────

    def save_email_template(self, name: str, subject: str, body: str) -> Dict:
        """Save an email template to data/email_templates.json.
        Use {{variable}} placeholders in subject/body."""
        import json
        from pathlib import Path as _P
        tpl_file = _P("data/email_templates.json")
        try:
            templates = json.loads(tpl_file.read_text(encoding='utf-8')) if tpl_file.exists() else {}
            templates[name] = {'subject': subject, 'body': body}
            tpl_file.write_text(json.dumps(templates, indent=2, ensure_ascii=False), encoding='utf-8')
            return {'status': 'success', 'name': name,
                    'message': f"Template '{name}' saved. Use {{{{variable}}}} placeholders."}
        except Exception as exc:
            return {'status': 'error', 'message': f"Error saving template: {exc}"}

    def list_email_templates(self) -> Dict:
        """List all saved email templates from data/email_templates.json."""
        import json
        from pathlib import Path as _P
        tpl_file = _P("data/email_templates.json")
        try:
            if not tpl_file.exists():
                return {'status': 'success', 'templates': [], 'count': 0,
                        'message': "No templates saved yet. Use save_email_template()."}
            templates = json.loads(tpl_file.read_text(encoding='utf-8'))
            return {
                'status': 'success',
                'templates': [{'name': k, 'subject': v.get('subject', '')} for k, v in templates.items()],
                'count': len(templates),
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error listing templates: {exc}"}

    def send_from_template(self, template_name: str, to: str, variables: Dict = None) -> Dict:
        """Send an email using a saved template, substituting {{key}} placeholders.

        Args:
            template_name: Name of the saved template.
            to:            Recipient email address.
            variables:     Dict of placeholder values e.g. {"name": "John", "date": "5 March"}.
        """
        import json
        from pathlib import Path as _P
        tpl_file = _P("data/email_templates.json")
        try:
            templates = json.loads(tpl_file.read_text(encoding='utf-8')) if tpl_file.exists() else {}
            if template_name not in templates:
                return {
                    'status': 'error',
                    'message': f"Template '{template_name}' not found. Available: {list(templates.keys())}",
                }
            tpl = templates[template_name]
            subject = tpl.get('subject', '')
            body    = tpl.get('body', '')
            if variables:
                for k, v in variables.items():
                    subject = subject.replace(f"{{{{{k}}}}}", str(v))
                    body    = body.replace(f"{{{{{k}}}}}", str(v))
            return self.send_email(to, subject, body)
        except Exception as exc:
            return {'status': 'error', 'message': f"Error sending from template: {exc}"}

    # ── Recovery ──────────────────────────────────────────────────────────────

    def recover_deleted_emails(self, query: str = "", max_results: int = 20) -> Dict:
        """Search for emails in Trash and restore them to Inbox.

        Args:
            query:       Optional Gmail search string to narrow the Trash search.
            max_results: Maximum emails to restore (default 20).
        """
        try:
            search_q = f"in:trash {query}".strip() if query else "in:trash"
            resp = self.gmail_service.users().messages().list(
                userId=self.user_id, q=search_q, maxResults=max_results,
            ).execute()
            messages = resp.get('messages', [])
            if not messages:
                return {'status': 'success', 'restored': 0,
                        'message': 'No matching emails found in Trash.'}
            ids = [m['id'] for m in messages]
            self.gmail_service.users().messages().batchModify(
                userId=self.user_id,
                body={'ids': ids, 'addLabelIds': ['INBOX'], 'removeLabelIds': ['TRASH']},
            ).execute()
            return {
                'status': 'success',
                'restored': len(ids),
                'message_ids': ids,
                'message': f"Restored {len(ids)} email(s) from Trash to Inbox.",
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error recovering emails: {exc}"}

    # ── Sentiment & Content Analysis ──────────────────────────────────────────

    def analyze_email_sentiment(self, message_id: str) -> Dict:
        """Heuristic (keyword-based) sentiment / tone analysis of an email.

        Returns tone: urgent | negative | positive | neutral, plus the signals detected.
        No LLM required — works fully offline.
        """
        import re as _re, base64 as _b64

        URGENT_WORDS = {
            "urgent", "asap", "immediately", "critical", "emergency", "deadline",
            "overdue", "action required", "must", "required by", "due today",
            "time sensitive", "by end of day", "eod", "as soon as possible",
        }
        POSITIVE_WORDS = {
            "thank", "congrats", "congratulations", "great", "excellent", "well done",
            "appreciate", "happy", "excited", "fantastic", "awesome", "good news",
            "pleased", "wonderful", "brilliant", "outstanding",
        }
        NEGATIVE_WORDS = {
            "complaint", "disappointed", "frustrated", "angry", "unacceptable",
            "problem", "issue", "failure", "broken", "failed", "error", "wrong",
            "terrible", "poor", "worst", "dissatisfied", "escalate", "refund",
        }
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='full',
            ).execute()
            subject = ""
            for h in msg.get('payload', {}).get('headers', []):
                if h['name'].lower() == 'subject':
                    subject = h['value']
                    break
            body = ""
            for part in msg.get('payload', {}).get('parts', [msg.get('payload', {})]):
                if part.get('mimeType', '').startswith('text/'):
                    data = part.get('body', {}).get('data', '')
                    if data:
                        body += _b64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore')
            text = (subject + ' ' + body).lower()
            urgent_hits  = [w for w in URGENT_WORDS if w in text]
            positive_hits = [w for w in POSITIVE_WORDS if w in text]
            negative_hits = [w for w in NEGATIVE_WORDS if w in text]
            if urgent_hits:
                tone, confidence = 'urgent', ('high' if len(urgent_hits) >= 2 else 'medium')
            elif negative_hits:
                tone, confidence = 'negative', ('high' if len(negative_hits) >= 2 else 'medium')
            elif positive_hits:
                tone, confidence = 'positive', ('high' if len(positive_hits) >= 2 else 'medium')
            else:
                tone, confidence = 'neutral', 'medium'
            recommendation = {
                'urgent':   'Flag for immediate attention — respond or escalate today.',
                'negative': 'Prompt, empathetic reply recommended.',
                'positive': 'No urgent action needed.',
                'neutral':  'Normal priority.',
            }[tone]
            return {
                'status': 'success',
                'message_id': message_id,
                'subject': subject,
                'tone': tone,
                'confidence': confidence,
                'urgent_signals': urgent_hits,
                'positive_signals': positive_hits,
                'negative_signals': negative_hits,
                'recommendation': recommendation,
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error analysing sentiment: {exc}"}

    def extract_urls_from_email(self, message_id: str) -> Dict:
        """Extract and classify all hyperlinks found in an email body.

        Returns three buckets: links (regular), tracking_pixels, unsubscribe_urls.
        """
        import re as _re, base64 as _b64
        URL_RE = _re.compile(r'https?://[^\s"\'<>\]\)]+', _re.IGNORECASE)
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='full',
            ).execute()
            subject = ""
            for h in msg.get('payload', {}).get('headers', []):
                if h['name'].lower() == 'subject':
                    subject = h['value']
            raw_text = ""
            for part in msg.get('payload', {}).get('parts', [msg.get('payload', {})]):
                data = part.get('body', {}).get('data', '')
                if data:
                    raw_text += _b64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore')
            urls = list(dict.fromkeys(URL_RE.findall(raw_text)))  # dedup, order-preserved
            links, tracking, unsubscribe = [], [], []
            for u in urls:
                lo = u.lower()
                if any(k in lo for k in ('unsubscribe', 'optout', 'opt-out', 'remove-me')):
                    unsubscribe.append(u)
                elif any(k in lo for k in ('track', 'click.', 'open.php', 'pixel', 'beacon', 'img.', '/t/')):
                    tracking.append(u)
                else:
                    links.append(u)
            return {
                'status': 'success',
                'message_id': message_id,
                'subject': subject,
                'total_urls': len(urls),
                'links': links,
                'tracking_pixels': tracking,
                'unsubscribe_urls': unsubscribe,
                'all_urls': urls,
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error extracting URLs: {exc}"}

    def get_email_chains_summary(self, max_results: int = 10) -> Dict:
        """Return the most active email threads sorted by reply count.

        Useful for finding long conversations that may need attention.
        """
        try:
            resp = self.gmail_service.users().threads().list(
                userId=self.user_id, maxResults=min(max_results * 3, 50),
            ).execute()
            threads = resp.get('threads', [])
            summaries = []
            for t in threads[:max_results * 2]:
                td = self.gmail_service.users().threads().get(
                    userId=self.user_id, id=t['id'], format='metadata',
                    metadataHeaders=['Subject', 'From', 'Date'],
                ).execute()
                msgs = td.get('messages', [])
                if not msgs:
                    continue
                subject = from_addr = date_str = ""
                for h in msgs[0].get('payload', {}).get('headers', []):
                    n = h['name'].lower()
                    if n == 'subject':   subject = h['value']
                    elif n == 'from':    from_addr = h['value']
                    elif n == 'date':    date_str = h['value']
                summaries.append({
                    'thread_id': t['id'],
                    'subject': subject or '(no subject)',
                    'from': from_addr,
                    'date': date_str,
                    'message_count': len(msgs),
                    'latest_snippet': msgs[-1].get('snippet', ''),
                })
            summaries.sort(key=lambda x: x['message_count'], reverse=True)
            summaries = summaries[:max_results]
            return {
                'status': 'success',
                'count': len(summaries),
                'chains': summaries,
                'message': f"Top {len(summaries)} email thread(s) by activity.",
            }
        except Exception as exc:
            return {'status': 'error', 'message': f"Error getting email chains: {exc}"}

    def send_completion_reminder(self, message_id: str, days: int = 3) -> Dict:
        """Schedule a self-reminder if no reply is received within N days.

        Delegates to mark_for_followup() with an auto-generated note derived
        from the email subject and recipient.
        """
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='metadata',
                metadataHeaders=['Subject', 'To'],
            ).execute()
            subject = to_addr = ""
            for h in msg.get('payload', {}).get('headers', []):
                n = h['name'].lower()
                if n == 'subject': subject = h['value']
                elif n == 'to':    to_addr = h['value']
            note = f"Auto-reminder: check for reply to '{subject}' sent to {to_addr}"
            return self.mark_for_followup(message_id=message_id, days=days, note=note)
        except Exception as exc:
            return {'status': 'error', 'message': f"Error scheduling reminder: {exc}"}


# Convenient module-level functions
_client = None

_AUTH_ERROR_PHRASES = (
    "gmail authorization failed",
    "authorization failed",
    "run `python setup_google_auth.py`",
    "token has expired",
    "gmail authentication failed",
)


def is_gmail_authorized() -> bool:
    """Return True if a Gmail token file exists (does not validate it online)."""
    from src.agent.llm.provider_registry import get_google_credential_path
    token_path = get_google_credential_path("gmail_token_path") or "config/token.json"
    from pathlib import Path as _Path
    return _Path(token_path).exists()


def reset_gmail_client() -> None:
    """Force the next call to re-initialize the Gmail client (e.g. after re-auth)."""
    global _client
    _client = None


def _get_client():
    """Get or create the Gmail client singleton. Resets on auth failure so a
    re-authorization attempt will be picked up on the next call."""
    global _client
    if _client is None:
        try:
            _client = GmailServiceClient()
        except Exception as exc:
            _client = None  # ensure next call retries
            raise exc
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


def send_email_with_attachment(
    to: str,
    subject: str,
    message: str,
    attachment_path: str,
) -> Dict:
    """
    Send an email with a local file attached (module-level convenience function).

    Args:
        to:              Recipient email address.
        subject:         Email subject.
        message:         Email body.
        attachment_path: Path to the local file to attach (or download_file result dict).

    Returns:
        Result dictionary with status and message details.
    """
    return _get_client().send_email_with_attachment(to, subject, message, attachment_path)


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


def create_label(label_name: str) -> Dict:
    return _get_client().create_label(label_name)


def move_emails_to_label(query: str, label_name: str, max_results: int = 50) -> Dict:
    return _get_client().move_emails_to_label(query, label_name, max_results)


def set_vacation_responder(
    enabled: bool,
    subject: str = "",
    body: str = "",
    start_date: str = "",
    end_date: str = "",
    restrict_to_contacts: bool = False,
) -> Dict:
    """Enable or disable Gmail's Out-of-Office / Vacation auto-reply (module-level)."""
    return _get_client().set_vacation_responder(
        enabled, subject, body, start_date, end_date, restrict_to_contacts,
    )


def get_vacation_responder() -> Dict:
    """Return the current Gmail vacation / OOO responder settings (module-level)."""
    return _get_client().get_vacation_responder()


def fetch_emails_to_markdown(
    query: str = "in:inbox",
    max_results: int = 5,
    cap: int = 20,
    output_dir: str = "",
) -> Dict:
    """Fetch N emails matching *query*, save as a Markdown file, return content + file_path."""
    return _get_client().fetch_emails_to_markdown(query, max_results, cap, output_dir)


def unsubscribe_email(message_id: str) -> Dict:
    return _get_client().unsubscribe_email(message_id)


def archive_emails(query: str, max_results: int = 50) -> Dict:
    return _get_client().archive_emails(query, max_results)


def thread_mute(thread_id: str) -> Dict:
    return _get_client().thread_mute(thread_id)


def thread_archive(thread_id: str) -> Dict:
    return _get_client().thread_archive(thread_id)


def thread_delete(thread_id: str) -> Dict:
    return _get_client().thread_delete(thread_id)


def create_smart_label_rule(
    label_name: str,
    from_email: str = "",
    subject_contains: str = "",
    to_email: str = "",
    also_archive: bool = False,
) -> Dict:
    return _get_client().create_smart_label_rule(
        label_name, from_email, subject_contains, to_email, also_archive
    )


def find_unanswered_emails(days: int = 3, max_results: int = 20) -> Dict:
    return _get_client().find_unanswered_emails(days, max_results)


def empty_trash() -> Dict:
    return _get_client().empty_trash()


def batch_mark_spam(query: str, max_results: int = 50) -> Dict:
    return _get_client().batch_mark_spam(query, max_results)


def add_forwarding_address(forward_to: str) -> Dict:
    return _get_client().add_forwarding_address(forward_to)


def enable_email_forwarding(forward_to: str) -> Dict:
    return _get_client().enable_email_forwarding(forward_to)


def get_signature(send_as_email: str = "me") -> Dict:
    return _get_client().get_signature(send_as_email)


def set_signature(signature_html: str, send_as_email: str = "me") -> Dict:
    return _get_client().set_signature(signature_html, send_as_email)


def save_email_template(name: str, subject: str, body: str) -> Dict:
    return _get_client().save_email_template(name, subject, body)


def list_email_templates() -> Dict:
    return _get_client().list_email_templates()


def send_from_template(template_name: str, to: str, variables: Dict = None) -> Dict:
    return _get_client().send_from_template(template_name, to, variables)


def recover_deleted_emails(query: str = "", max_results: int = 20) -> Dict:
    return _get_client().recover_deleted_emails(query, max_results)


def analyze_email_sentiment(message_id: str) -> Dict:
    return _get_client().analyze_email_sentiment(message_id)


def extract_urls_from_email(message_id: str) -> Dict:
    return _get_client().extract_urls_from_email(message_id)


def get_email_chains_summary(max_results: int = 10) -> Dict:
    return _get_client().get_email_chains_summary(max_results)


def send_completion_reminder(message_id: str, days: int = 3) -> Dict:
    return _get_client().send_completion_reminder(message_id, days)


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
