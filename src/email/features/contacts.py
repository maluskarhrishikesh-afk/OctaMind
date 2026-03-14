"""
Contact Intelligence

Analyze email interaction patterns to identify frequent contacts,
track response times, and surface VIP contacts.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger("email_agent.features.contacts")

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')


def _extract_email(addr: str) -> str:
    """Extract raw email address from 'Name <email>' format."""
    m = EMAIL_RE.search(addr or '')
    return m.group(0).lower() if m else addr.lower().strip()


def _extract_name(addr: str) -> str:
    """Extract display name from 'Name <email>' format."""
    if '<' in addr:
        return addr.split('<')[0].strip().strip('"')
    return _extract_email(addr)


class ContactIntelligence:
    """Analyze email contacts and interaction patterns."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id

    def _get_user_email(self) -> str:
        """Get the authenticated user's email address."""
        try:
            gmail_service: Any = self.gmail_service
            profile = gmail_service.users().getProfile(userId=self.user_id).execute()
            return profile.get('emailAddress', '').lower()
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            return ''

    def get_frequent_contacts(self, limit: int = 10, max_scan: int = 200) -> Dict:
        """
        Get the most frequently contacted people.

        Returns:
            Dict with ranked contact list
        """
        try:
            my_email = self._get_user_email()
            # Scan both sent and received
            counts: Dict[str, int] = defaultdict(int)
            names: Dict[str, str] = {}
            last_seen: Dict[str, str] = {}
            directions: Dict[str, List[str]] = defaultdict(list)

            for q in ['from:me', 'to:me']:
                response = self.gmail_service.users().messages().list(
                    userId=self.user_id, q=q, maxResults=max_scan // 2
                ).execute()
                for msg_item in response.get('messages', []):
                    try:
                        msg = self.gmail_service.users().messages().get(
                            userId=self.user_id, id=msg_item['id'],
                            format='metadata',
                            metadataHeaders=['From', 'To', 'Date']
                        ).execute()
                        headers = msg.get('payload', {}).get('headers', [])
                        from_h = next(
                            (h['value'] for h in headers if h['name'].lower() == 'from'), '')
                        to_h = next(
                            (h['value'] for h in headers if h['name'].lower() == 'to'), '')
                        date_h = next(
                            (h['value'] for h in headers if h['name'].lower() == 'date'), '')

                        # Contacts to count: the OTHER party
                        if q == 'from:me':
                            # I sent to them
                            for addr in to_h.split(','):
                                email = _extract_email(addr.strip())
                                if email and email != my_email:
                                    counts[email] += 1
                                    names[email] = _extract_name(addr.strip())
                                    last_seen[email] = date_h
                                    directions[email].append('sent')
                        else:
                            # I received from them
                            email = _extract_email(from_h)
                            if email and email != my_email:
                                counts[email] += 1
                                names[email] = _extract_name(from_h)
                                last_seen[email] = date_h
                                directions[email].append('received')
                    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                        pass

            # Sort by count
            sorted_contacts = sorted(
                counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            contacts = []
            for email, count in sorted_contacts:
                sent = directions[email].count('sent')
                received = directions[email].count('received')
                is_vip = count >= 10
                contacts.append({
                    'email': email,
                    'name': names.get(email, email),
                    'interaction_count': count,
                    'emails_sent': sent,
                    'emails_received': received,
                    'last_interaction': last_seen.get(email, 'Unknown'),
                    'is_vip': is_vip
                })

            return {
                'status': 'success',
                'contacts': contacts,
                'total_unique_contacts': len(counts)
            }
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error("Get frequent contacts failed: %s", e)
            return {'status': 'error', 'message': str(e)}

    def get_contact_summary(self, email_address: str) -> Dict:
        """
        Get a summary of interactions with a specific contact.
        """
        try:
            email_lower = email_address.lower().strip()
            # Fetch emails from this person
            response_from = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f'from:{email_lower}',
                maxResults=50
            ).execute()
            # Fetch emails sent to this person
            response_to = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f'to:{email_lower}',
                maxResults=50
            ).execute()

            received_count = len(response_from.get('messages', []))
            sent_count = len(response_to.get('messages', []))

            # Get the most recent email from this person
            latest_subject = ''
            latest_date = ''
            if response_from.get('messages'):
                try:
                    msg = self.gmail_service.users().messages().get(
                        userId=self.user_id,
                        id=response_from['messages'][0]['id'],
                        format='metadata',
                        metadataHeaders=['Subject', 'Date']
                    ).execute()
                    headers = msg.get('payload', {}).get('headers', [])
                    latest_subject = next(
                        (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                    latest_date = next(
                        (h['value'] for h in headers if h['name'].lower() == 'date'), '')
                except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                    pass

            return {
                'status': 'success',
                'email': email_lower,
                'emails_received_from': received_count,
                'emails_sent_to': sent_count,
                'total_interactions': received_count + sent_count,
                'latest_email_subject': latest_subject,
                'latest_interaction': latest_date,
                'is_vip': (received_count + sent_count) >= 10
            }
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error("Get contact summary failed: %s", e)
            return {'status': 'error', 'message': str(e)}

    def suggest_vip_contacts(self) -> Dict:
        """Suggest contacts that should be considered VIP based on interaction frequency."""
        result = self.get_frequent_contacts(limit=20)
        if result.get('status') == 'error':
            return result
        vip = [c for c in result['contacts'] if c.get(
            'is_vip') or c['interaction_count'] >= 5]
        return {
            'status': 'success',
            'vip_contacts': vip,
            'count': len(vip)
        }

    def export_contacts(self, output_format: str = 'csv', limit: int = 100, **kwargs: str) -> Dict:
        """
        Export contact intelligence data to CSV or JSON file.

        Args:
            output_format: 'csv' or 'json'
            limit: Maximum number of contacts to export

        Returns:
            Dict with export status and file path
        """
        import csv
        from io import StringIO

        from src.agent.runtime_paths import get_runtime_state_dir

        result = self.get_frequent_contacts(limit=limit, max_scan=500)
        if result.get('status') == 'error':
            return result

        contacts = result.get('contacts', [])
        if not contacts:
            return {'status': 'error', 'message': 'No contacts found to export'}

        export_dir = get_runtime_state_dir('exports', create=True)
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        fmt = str(kwargs.get('format', output_format)).lower().strip()

        if fmt == 'json':
            export_file = export_dir / f'contacts_{timestamp}.json'
            import json
            export_file.write_text(
                json.dumps(contacts, indent=2, default=str),
                encoding='utf-8'
            )
        elif fmt == 'csv':
            export_file = export_dir / f'contacts_{timestamp}.csv'
            fieldnames = [
                'email', 'name', 'interaction_count',
                'emails_sent', 'emails_received', 'last_interaction', 'is_vip'
            ]
            output = StringIO()
            writer = csv.DictWriter(
                output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for c in contacts:
                writer.writerow(c)
            export_file.write_text(output.getvalue(), encoding='utf-8')
        else:
            return {'status': 'error', 'message': f"Unsupported format '{fmt}'. Use 'csv' or 'json'."}

        return {
            'status': 'success',
            'format': fmt,
            'contact_count': len(contacts),
            'file_path': str(export_file),
            'message': f"✅ Exported {len(contacts)} contacts to {export_file.name}"
        }


# Singleton + convenience functions
_INTELLIGENCE_CACHE: Dict[str, ContactIntelligence] = {}


def _get_intelligence() -> ContactIntelligence:
    intelligence = _INTELLIGENCE_CACHE.get('default')
    if intelligence is None:
        from src.email.gmail_auth import get_gmail_service
        intelligence = ContactIntelligence(get_gmail_service())
        _INTELLIGENCE_CACHE['default'] = intelligence
    return intelligence


def get_frequent_contacts(limit: int = 10) -> Dict:
    return _get_intelligence().get_frequent_contacts(limit)


def get_contact_summary(email_address: str) -> Dict:
    return _get_intelligence().get_contact_summary(email_address)


def suggest_vip_contacts() -> Dict:
    """Return contacts with high interaction frequency (VIP)."""
    return _get_intelligence().suggest_vip_contacts()


def export_contacts(output_format: str = 'csv', limit: int = 100, **kwargs: str) -> Dict:
    """Export contact data to CSV or JSON file."""
    return _get_intelligence().export_contacts(output_format, limit, **kwargs)
