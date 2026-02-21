"""
Attachment Management

List, download, and search email attachments via the Gmail API.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.attachments")

# Default download directory
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "OctaMind_Attachments"


class AttachmentManager:
    """Manage Gmail email attachments."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id

    def list_attachments(self, message_id: str) -> Dict:
        """
        List all attachments in a specific email.

        Returns:
            Dict with list of attachments: filename, mimeType, size, attachment_id
        """
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='full'
            ).execute()
            attachments = []
            payload = msg.get('payload', {})

            def walk_parts(parts):
                for part in parts:
                    if part.get('filename'):
                        body = part.get('body', {})
                        attachments.append({
                            'filename': part['filename'],
                            'mimeType': part.get('mimeType', 'application/octet-stream'),
                            'size': body.get('size', 0),
                            'attachment_id': body.get('attachmentId', ''),
                            'part_id': part.get('partId', '')
                        })
                    if 'parts' in part:
                        walk_parts(part['parts'])

            if 'parts' in payload:
                walk_parts(payload['parts'])

            return {
                'status': 'success',
                'message_id': message_id,
                'attachments': attachments,
                'count': len(attachments)
            }
        except Exception as e:
            logger.error(f"List attachments failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def download_attachment(self, message_id: str, attachment_id: str,
                            filename: str = '', save_path: str = '') -> Dict:
        """
        Download an attachment and save to disk.

        Args:
            message_id: Gmail message ID containing the attachment
            attachment_id: The attachment ID from list_attachments
            filename: Suggested filename (optional)
            save_path: Directory to save to (defaults to ~/Downloads/OctaMind_Attachments)
        """
        try:
            attachment = self.gmail_service.users().messages().attachments().get(
                userId=self.user_id,
                messageId=message_id,
                id=attachment_id
            ).execute()

            data = attachment.get('data', '')
            if not data:
                return {'status': 'error', 'message': 'No attachment data found'}

            file_data = base64.urlsafe_b64decode(data)

            # Determine save directory
            if save_path:
                save_dir = Path(save_path)
            else:
                save_dir = DEFAULT_DOWNLOAD_DIR
            save_dir.mkdir(parents=True, exist_ok=True)

            # Determine filename
            if not filename:
                filename = f"attachment_{attachment_id[:8]}"

            file_path = save_dir / filename
            # Avoid overwrite — add suffix if file exists
            counter = 1
            while file_path.exists():
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                file_path = save_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            file_path.write_bytes(file_data)
            return {
                'status': 'success',
                'filename': file_path.name,
                'path': str(file_path),
                'size_bytes': len(file_data),
                'size_kb': round(len(file_data) / 1024, 1),
                'message': f'Saved to {file_path}'
            }
        except Exception as e:
            logger.error(f"Download attachment failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def search_emails_with_attachments(self, file_type: str = 'any',
                                       max_results: int = 20) -> Dict:
        """
        Search for emails that have attachments, optionally filtered by type.

        Args:
            file_type: 'pdf', 'doc', 'image', 'spreadsheet', 'any'
            max_results: Max emails to return
        """
        # Build Gmail query
        query = 'has:attachment'
        type_filters = {
            'pdf': 'filename:pdf',
            'doc': '(filename:doc OR filename:docx)',
            'spreadsheet': '(filename:xls OR filename:xlsx OR filename:csv)',
            'image': '(filename:jpg OR filename:jpeg OR filename:png OR filename:gif)',
            'zip': '(filename:zip OR filename:rar OR filename:7z)',
        }
        if file_type in type_filters:
            query += f' {type_filters[file_type]}'

        try:
            response = self.gmail_service.users().messages().list(
                userId=self.user_id, q=query, maxResults=max_results
            ).execute()
            messages = response.get('messages', [])
            results = []
            for msg_item in messages[:max_results]:
                try:
                    msg = self.gmail_service.users().messages().get(
                        userId=self.user_id, id=msg_item['id'],
                        format='metadata',
                        metadataHeaders=['Subject', 'From', 'Date']
                    ).execute()
                    headers = msg['payload']['headers']
                    subject = next(
                        (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                    sender = next(
                        (h['value'] for h in headers if h['name'].lower() == 'from'), '')
                    date = next(
                        (h['value'] for h in headers if h['name'].lower() == 'date'), '')
                    results.append({
                        'id': msg_item['id'],
                        'subject': subject,
                        'sender': sender,
                        'date': date
                    })
                except Exception:
                    pass
            return {
                'status': 'success',
                'emails': results,
                'count': len(results),
                'file_type_filter': file_type,
                'query': query
            }
        except Exception as e:
            logger.error(f"Search attachments failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_attachment_stats(self) -> Dict:
        """Get statistics about attachments across recent emails."""
        try:
            result = self.search_emails_with_attachments(max_results=100)
            emails_with_attachments = result.get('count', 0)
            type_counts = {}
            for ftype in ['pdf', 'doc', 'spreadsheet', 'image', 'zip']:
                r = self.search_emails_with_attachments(
                    file_type=ftype, max_results=100)
                type_counts[ftype] = r.get('count', 0)
            return {
                'status': 'success',
                'total_emails_with_attachments': emails_with_attachments,
                'by_type': type_counts,
                'download_directory': str(DEFAULT_DOWNLOAD_DIR)
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


# Singleton + convenience functions
_manager: Optional[AttachmentManager] = None


def _get_manager() -> AttachmentManager:
    global _manager
    if _manager is None:
        from src.email.gmail_auth import get_gmail_service
        _manager = AttachmentManager(get_gmail_service())
    return _manager


def list_attachments(message_id: str) -> Dict:
    return _get_manager().list_attachments(message_id)


def download_attachment(message_id: str, attachment_id: str,
                        filename: str = '', save_path: str = '') -> Dict:
    return _get_manager().download_attachment(message_id, attachment_id, filename, save_path)


def search_emails_with_attachments(file_type: str = 'any', max_results: int = 20) -> Dict:
    return _get_manager().search_emails_with_attachments(file_type, max_results)
