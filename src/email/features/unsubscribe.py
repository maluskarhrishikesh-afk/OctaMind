"""
Unsubscribe / Newsletter Detection

Detect newsletters and promotional emails, extract unsubscribe links.
"""

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.unsubscribe")

# Newsletter detection markers
NEWSLETTER_HEADERS = ['list-unsubscribe', 'list-id',
                      'x-campaign-id', 'x-mailer', 'bulk-precedence']
NEWSLETTER_PATTERNS = [
    r'unsubscribe', r'opt.?out', r'manage.*preferences', r'email.*preferences',
    r'view.*in.*browser', r'view.*online', r'newsletter', r'mailing list',
    r'you.re receiving.*because', r'you received.*because', r'to stop receiving',
    r'©\s*\d{4}', r'all rights reserved',
]
UNSUBSCRIBE_LINK_PATTERN = re.compile(
    r'https?://[^\s<>"\']+(?:unsubscribe|optout|opt-out|remove|manage-?preferences)[^\s<>"\']*',
    re.IGNORECASE
)


def _contains_newsletter_signals(body: str, headers: List[Dict]) -> bool:
    """Check if content looks like a newsletter/promotional email."""
    header_names = {h['name'].lower() for h in headers}
    if any(n in header_names for n in NEWSLETTER_HEADERS):
        return True
    body_lower = body.lower()
    pattern_matches = sum(
        1 for p in NEWSLETTER_PATTERNS if re.search(p, body_lower))
    return pattern_matches >= 2


class UnsubscribeDetector:
    """Detect newsletters and extract unsubscribe information."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id

    def _get_full_message(self, message_id: str) -> Dict:
        import base64
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='full'
            ).execute()
            headers = msg.get('payload', {}).get('headers', [])
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            sender = next((h['value']
                          for h in headers if h['name'].lower() == 'from'), '')
            snippet = msg.get('snippet', '')
            # Get unsubscribe header directly
            unsubscribe_header = next(
                (h['value'] for h in headers if h['name'].lower() == 'list-unsubscribe'), '')
            # Decode body
            body = snippet
            payload = msg.get('payload', {})

            def extract_body(parts):
                for part in parts:
                    if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                    if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                    if 'parts' in part:
                        result = extract_body(part['parts'])
                        if result:
                            return result
                return ''

            if 'parts' in payload:
                body = extract_body(payload['parts']) or snippet
            elif 'data' in payload.get('body', {}):
                body = base64.urlsafe_b64decode(
                    payload['body']['data']).decode('utf-8', errors='replace')

            return {
                'subject': subject, 'sender': sender, 'body': body,
                'headers': headers, 'snippet': snippet,
                'unsubscribe_header': unsubscribe_header
            }
        except Exception as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            return {}

    def detect_newsletters(self, max_results: int = 30) -> Dict:
        """
        Scan inbox for newsletters and promotional emails.

        Returns:
            Dict with list of detected newsletters and their senders
        """
        try:
            # Gmail query: emails with unsubscribe links or newsletter markers
            response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q='in:inbox (unsubscribe OR newsletter OR "opt out" OR "mailing list")',
                maxResults=max_results
            ).execute()
            messages = response.get('messages', [])
            newsletters = []
            seen_senders = set()

            for msg_item in messages:
                data = self._get_full_message(msg_item['id'])
                if not data:
                    continue
                if _contains_newsletter_signals(data['body'], data['headers']):
                    sender = data['sender']
                    # Extract raw email for deduplication
                    raw_email = re.search(
                        r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', sender)
                    sender_email = raw_email.group(
                        0).lower() if raw_email else sender.lower()
                    if sender_email not in seen_senders:
                        seen_senders.add(sender_email)
                        newsletters.append({
                            'id': msg_item['id'],
                            'subject': data['subject'],
                            'sender': sender,
                            'sender_email': sender_email,
                            'has_unsubscribe_header': bool(data.get('unsubscribe_header'))
                        })

            return {
                'status': 'success',
                'newsletters': newsletters,
                'count': len(newsletters),
                'unique_senders': len(seen_senders)
            }
        except Exception as e:
            logger.error(f"Detect newsletters failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def extract_unsubscribe_link(self, message_id: str) -> Dict:
        """
        Extract the unsubscribe link from an email.

        Returns:
            Dict with unsubscribe_url or mailto link
        """
        data = self._get_full_message(message_id)
        if not data:
            return {'status': 'error', 'message': 'Could not fetch email'}

        # 1. Check List-Unsubscribe header first (most reliable)
        header_value = data.get('unsubscribe_header', '')
        if header_value:
            # Could be <http://...>, <mailto:...>
            urls = re.findall(r'<(https?://[^>]+)>', header_value)
            mailto = re.findall(r'<(mailto:[^>]+)>', header_value)
            if urls:
                return {
                    'status': 'success',
                    'method': 'header',
                    'unsubscribe_url': urls[0],
                    'mailto': mailto[0] if mailto else None,
                    'subject': data['subject'],
                    'sender': data['sender']
                }
            if mailto:
                return {
                    'status': 'success',
                    'method': 'header_mailto',
                    'unsubscribe_url': None,
                    'mailto': mailto[0],
                    'subject': data['subject'],
                    'sender': data['sender']
                }

        # 2. Search body for unsubscribe link
        matches = UNSUBSCRIBE_LINK_PATTERN.findall(data['body'])
        if matches:
            return {
                'status': 'success',
                'method': 'body',
                'unsubscribe_url': matches[0],
                'mailto': None,
                'subject': data['subject'],
                'sender': data['sender'],
                'instruction': f"Visit this URL to unsubscribe: {matches[0]}"
            }

        return {
            'status': 'success',
            'method': 'not_found',
            'unsubscribe_url': None,
            'mailto': None,
            'subject': data['subject'],
            'sender': data['sender'],
            'message': 'No unsubscribe link found in this email. It may not be a newsletter.'
        }

    def bulk_unsubscribe_info(self, sender_list: List[str]) -> Dict:
        """
        Get unsubscribe info for a list of senders.

        Returns:
            Dict mapping each sender to their unsubscribe URL
        """
        results = []
        for sender_email in sender_list[:10]:  # Limit to 10
            try:
                response = self.gmail_service.users().messages().list(
                    userId=self.user_id,
                    q=f'from:{sender_email} (unsubscribe OR newsletter)',
                    maxResults=1
                ).execute()
                messages = response.get('messages', [])
                if messages:
                    link_result = self.extract_unsubscribe_link(
                        messages[0]['id'])
                    results.append({
                        'sender': sender_email,
                        'unsubscribe_url': link_result.get('unsubscribe_url'),
                        'mailto': link_result.get('mailto'),
                        'method': link_result.get('method', 'not_found')
                    })
                else:
                    results.append(
                        {'sender': sender_email, 'unsubscribe_url': None, 'method': 'no_email_found'})
            except Exception as e:
                results.append({'sender': sender_email, 'error': str(e)})
        return {'status': 'success', 'results': results}


# Singleton + convenience functions
_detector: Optional[UnsubscribeDetector] = None


def _get_detector() -> UnsubscribeDetector:
    global _detector
    if _detector is None:
        from src.email.gmail_auth import get_gmail_service
        _detector = UnsubscribeDetector(get_gmail_service())
    return _detector


def detect_newsletters(max_results: int = 30) -> Dict:
    return _get_detector().detect_newsletters(max_results)


def extract_unsubscribe_link(message_id: str) -> Dict:
    return _get_detector().extract_unsubscribe_link(message_id)
