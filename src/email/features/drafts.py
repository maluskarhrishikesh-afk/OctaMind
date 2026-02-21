"""
Draft Management

Create, list, update, send, and delete Gmail drafts via the Drafts API.
"""

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.drafts")


def _build_raw_message(to: str, subject: str, body: str, from_email: str = 'me') -> str:
    """Encode a MIME message to base64url."""
    msg = MIMEMultipart()
    msg['to'] = to
    msg['from'] = from_email
    msg['subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')


class DraftManager:
    """Manage Gmail drafts."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id

    def create_draft(self, to: str, subject: str, body: str) -> Dict:
        """
        Create a new email draft.

        Returns:
            Dict with draft_id, subject, to, preview
        """
        try:
            raw = _build_raw_message(to, subject, body)
            draft = self.gmail_service.users().drafts().create(
                userId=self.user_id,
                body={'message': {'raw': raw}}
            ).execute()
            return {
                'status': 'success',
                'draft_id': draft['id'],
                'to': to,
                'subject': subject,
                'preview': body[:100],
                'message': 'Draft created successfully'
            }
        except Exception as e:
            logger.error(f"Create draft failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def list_drafts(self, max_results: int = 10) -> Dict:
        """List all drafts."""
        try:
            response = self.gmail_service.users().drafts().list(
                userId=self.user_id, maxResults=max_results
            ).execute()
            drafts_raw = response.get('drafts', [])
            drafts = []
            for d in drafts_raw:
                detail = self.gmail_service.users().drafts().get(
                    userId=self.user_id,
                    id=d['id'],
                    format='metadata'
                ).execute()
                headers = detail.get('message', {}).get(
                    'payload', {}).get('headers', [])
                subject = next(
                    (h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
                to_addr = next(
                    (h['value'] for h in headers if h['name'].lower() == 'to'), '')
                snippet = detail.get('message', {}).get('snippet', '')
                drafts.append({
                    'draft_id': d['id'],
                    'subject': subject,
                    'to': to_addr,
                    'snippet': snippet
                })
            return {
                'status': 'success',
                'drafts': drafts,
                'count': len(drafts)
            }
        except Exception as e:
            logger.error(f"List drafts failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_draft(self, draft_id: str) -> Dict:
        """Get a specific draft by ID."""
        try:
            detail = self.gmail_service.users().drafts().get(
                userId=self.user_id, id=draft_id, format='full'
            ).execute()
            msg = detail.get('message', {})
            headers = msg.get('payload', {}).get('headers', [])
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            to_addr = next((h['value']
                           for h in headers if h['name'].lower() == 'to'), '')
            # Decode body
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
                'status': 'success',
                'draft_id': draft_id,
                'subject': subject,
                'to': to_addr,
                'body': body,
                'snippet': msg.get('snippet', '')
            }
        except Exception as e:
            logger.error(f"Get draft failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def update_draft(self, draft_id: str, to: str, subject: str, body: str) -> Dict:
        """Update an existing draft."""
        try:
            raw = _build_raw_message(to, subject, body)
            updated = self.gmail_service.users().drafts().update(
                userId=self.user_id,
                id=draft_id,
                body={'message': {'raw': raw}}
            ).execute()
            return {
                'status': 'success',
                'draft_id': updated['id'],
                'to': to,
                'subject': subject,
                'message': 'Draft updated successfully'
            }
        except Exception as e:
            logger.error(f"Update draft failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def send_draft(self, draft_id: str) -> Dict:
        """Send an existing draft."""
        try:
            sent = self.gmail_service.users().drafts().send(
                userId=self.user_id,
                body={'id': draft_id}
            ).execute()
            return {
                'status': 'success',
                'message_id': sent.get('id', ''),
                'thread_id': sent.get('threadId', ''),
                'message': 'Draft sent successfully'
            }
        except Exception as e:
            logger.error(f"Send draft failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def delete_draft(self, draft_id: str) -> Dict:
        """Delete a draft permanently."""
        try:
            self.gmail_service.users().drafts().delete(
                userId=self.user_id, id=draft_id
            ).execute()
            return {
                'status': 'success',
                'draft_id': draft_id,
                'message': 'Draft deleted successfully'
            }
        except Exception as e:
            logger.error(f"Delete draft failed: {e}")
            return {'status': 'error', 'message': str(e)}


# Singleton + convenience functions
_manager: Optional[DraftManager] = None


def _get_manager() -> DraftManager:
    global _manager
    if _manager is None:
        from src.email.gmail_auth import get_gmail_service
        _manager = DraftManager(get_gmail_service())
    return _manager


def create_draft(to: str, subject: str, body: str) -> Dict:
    return _get_manager().create_draft(to, subject, body)


def list_drafts(max_results: int = 10) -> Dict:
    return _get_manager().list_drafts(max_results)


def get_draft(draft_id: str) -> Dict:
    return _get_manager().get_draft(draft_id)


def update_draft(draft_id: str, to: str, subject: str, body: str) -> Dict:
    return _get_manager().update_draft(draft_id, to, subject, body)


def send_draft(draft_id: str) -> Dict:
    return _get_manager().send_draft(draft_id)


def delete_draft(draft_id: str) -> Dict:
    return _get_manager().delete_draft(draft_id)
