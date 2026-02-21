"""
Smart Email Categorizer

Automatically categorizes emails and applies Gmail labels using LLM.
"""

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.categorizer")

CATEGORIES = ['work', 'personal', 'bills', 'newsletters',
              'social', 'notifications', 'spam', 'other']

# Label color mapping (Gmail API uses color names)
LABEL_COLORS = {
    'work': {'textColor': '#ffffff', 'backgroundColor': '#1155cc'},
    'personal': {'textColor': '#ffffff', 'backgroundColor': '#16a766'},
    'bills': {'textColor': '#ffffff', 'backgroundColor': '#c6440f'},
    'newsletters': {'textColor': '#ffffff', 'backgroundColor': '#e66550'},
    'social': {'textColor': '#ffffff', 'backgroundColor': '#f691b2'},
    'notifications': {'textColor': '#000000', 'backgroundColor': '#fad165'},
    'spam': {'textColor': '#ffffff', 'backgroundColor': '#666666'},
    'other': {'textColor': '#000000', 'backgroundColor': '#efefef'},
}


class EmailCategorizer:
    """Auto-categorize emails and apply Gmail labels."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id
        self._llm = None
        self._label_cache: Dict[str, str] = {}  # category -> label_id

    @property
    def llm(self):
        if self._llm is None:
            from src.agent.llm.llm_parser import get_llm_client
            self._llm = get_llm_client()
        return self._llm

    def _get_or_create_label(self, category: str) -> str:
        """Get or create a Gmail label for the given category. Returns label_id."""
        if category in self._label_cache:
            return self._label_cache[category]

        label_name = f"OctaMind/{category.capitalize()}"
        try:
            # List existing labels
            labels = self.gmail_service.users().labels().list(userId=self.user_id).execute()
            for label in labels.get('labels', []):
                if label['name'] == label_name:
                    self._label_cache[category] = label['id']
                    return label['id']

            # Create new label
            color = LABEL_COLORS.get(category, LABEL_COLORS['other'])
            new_label = self.gmail_service.users().labels().create(
                userId=self.user_id,
                body={
                    'name': label_name,
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show',
                    'color': color
                }
            ).execute()
            label_id = new_label['id']
            self._label_cache[category] = label_id
            return label_id
        except Exception as e:
            logger.error(f"Failed to get/create label for {category}: {e}")
            return ''

    def auto_categorize_email(self, message_id: str) -> Dict:
        """
        Categorize a single email using LLM.

        Returns:
            Dict with category and confidence
        """
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id,
                format='metadata',
                metadataHeaders=['Subject', 'From', 'To', 'List-Unsubscribe']
            ).execute()
            headers = msg.get('payload', {}).get('headers', [])
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            sender = next((h['value']
                          for h in headers if h['name'].lower() == 'from'), '')
            has_unsubscribe = any(h['name'].lower() ==
                                  'list-unsubscribe' for h in headers)
            snippet = msg.get('snippet', '')

            prompt = f"""Categorize this email into exactly one of these categories:
work, personal, bills, newsletters, social, notifications, spam, other

Email:
Subject: {subject}
From: {sender}
Has unsubscribe header: {has_unsubscribe}
Preview: {snippet[:300]}

Return ONLY a JSON object:
{{"category": "one_of_the_categories_above", "confidence": "high|medium|low", "reason": "one line explanation"}}"""

            raw = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": "You classify emails into categories. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100,
                timeout=15
            )
            text = raw.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            category = result.get('category', 'other')
            if category not in CATEGORIES:
                category = 'other'
            result['category'] = category
            result['status'] = 'success'
            result['message_id'] = message_id
            result['subject'] = subject
            result['sender'] = sender
            return result
        except Exception as e:
            logger.error(f"Categorization failed: {e}")
            return {'status': 'error', 'message': str(e), 'category': 'other'}

    def apply_smart_labels(self, batch_size: int = 20) -> Dict:
        """
        Categorize and label the most recent emails.

        Returns:
            Dict with labeling summary
        """
        try:
            response = self.gmail_service.users().messages().list(
                userId=self.user_id, q='in:inbox', maxResults=batch_size
            ).execute()
            messages = response.get('messages', [])
            results = []
            category_counts: Dict[str, int] = {}

            for msg in messages:
                cat_result = self.auto_categorize_email(msg['id'])
                category = cat_result.get('category', 'other')
                category_counts[category] = category_counts.get(
                    category, 0) + 1

                # Apply label
                label_id = self._get_or_create_label(category)
                if label_id:
                    try:
                        self.gmail_service.users().messages().modify(
                            userId=self.user_id,
                            id=msg['id'],
                            body={'addLabelIds': [label_id]}
                        ).execute()
                    except Exception as e:
                        logger.error(
                            f"Failed to apply label to {msg['id']}: {e}")
                results.append({
                    'message_id': msg['id'],
                    'category': category,
                    'subject': cat_result.get('subject', '')
                })

            return {
                'status': 'success',
                'labeled_count': len(results),
                'category_breakdown': category_counts,
                'details': results
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def create_category_rules(self, min_occurrences: int = 3) -> Dict:
        """
        Create Gmail filters based on patterns from already-categorized emails.

        Scans emails labeled with OctaMind/<Category>, finds recurring senders,
        and creates Gmail filter rules that auto-label future emails from those senders.

        Args:
            min_occurrences: Minimum sender occurrences needed to create a rule

        Returns:
            Dict with list of created filters and summary
        """
        try:
            import re
            EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
            from collections import defaultdict

            filters_created = []
            filters_skipped = []

            # Fetch existing Gmail filters to avoid duplicates
            try:
                existing_filters_resp = self.gmail_service.users().settings().filters().list(
                    userId=self.user_id
                ).execute()
                existing_froms = {
                    f.get('criteria', {}).get('from', '').lower()
                    for f in existing_filters_resp.get('filter', [])
                }
            except Exception:
                existing_froms = set()

            for category in CATEGORIES:
                label_name = f"OctaMind/{category.capitalize()}"

                # Look up the label ID
                label_id = self._label_cache.get(category)
                if not label_id:
                    try:
                        labels_resp = self.gmail_service.users().labels().list(
                            userId=self.user_id
                        ).execute()
                        for lbl in labels_resp.get('labels', []):
                            if lbl['name'] == label_name:
                                label_id = lbl['id']
                                self._label_cache[category] = label_id
                                break
                    except Exception:
                        pass

                if not label_id:
                    # Category label not created yet — skip
                    continue

                # Scan emails already labeled with this category
                try:
                    response = self.gmail_service.users().messages().list(
                        userId=self.user_id,
                        q=f'label:{label_name.replace("/", "-")}',
                        maxResults=100
                    ).execute()
                    messages = response.get('messages', [])
                except Exception:
                    # Try alternate query format
                    try:
                        response = self.gmail_service.users().messages().list(
                            userId=self.user_id,
                            labelIds=[label_id],
                            maxResults=100
                        ).execute()
                        messages = response.get('messages', [])
                    except Exception:
                        messages = []

                sender_counts: dict = defaultdict(int)

                for msg_item in messages[:100]:
                    try:
                        msg = self.gmail_service.users().messages().get(
                            userId=self.user_id,
                            id=msg_item['id'],
                            format='metadata',
                            metadataHeaders=['From']
                        ).execute()
                        from_h = next(
                            (h['value'] for h in msg.get('payload', {}).get('headers', [])
                             if h['name'].lower() == 'from'),
                            ''
                        )
                        m = EMAIL_RE.search(from_h)
                        if m:
                            sender_counts[m.group(0).lower()] += 1
                    except Exception:
                        pass

                # Create filters for frequent senders
                for sender_email, count in sender_counts.items():
                    if count < min_occurrences:
                        continue
                    if sender_email in existing_froms:
                        filters_skipped.append({
                            'sender': sender_email,
                            'category': category,
                            'reason': 'filter already exists'
                        })
                        continue

                    try:
                        filter_body = {
                            'criteria': {'from': sender_email},
                            'action': {'addLabelIds': [label_id]}
                        }
                        created = self.gmail_service.users().settings().filters().create(
                            userId=self.user_id,
                            body=filter_body
                        ).execute()
                        existing_froms.add(sender_email)
                        filters_created.append({
                            'filter_id': created.get('id', ''),
                            'sender': sender_email,
                            'category': category,
                            'label': label_name,
                            'based_on_occurrences': count
                        })
                        logger.info(
                            f"Created Gmail filter: {sender_email} → {label_name}")
                    except Exception as e:
                        logger.error(
                            f"Failed to create filter for {sender_email}: {e}")
                        filters_skipped.append({
                            'sender': sender_email,
                            'category': category,
                            'reason': str(e)
                        })

            return {
                'status': 'success',
                'filters_created': len(filters_created),
                'filters_skipped': len(filters_skipped),
                'created': filters_created,
                'skipped': filters_skipped,
                'message': (
                    f"Created {len(filters_created)} Gmail filter(s). "
                    f"{len(filters_skipped)} skipped (already exist or error)."
                )
            }
        except Exception as e:
            logger.error(f"create_category_rules failed: {e}")
            return {'status': 'error', 'message': str(e)}


# Singleton + convenience functions
_categorizer: Optional[EmailCategorizer] = None


def _get_categorizer() -> EmailCategorizer:
    global _categorizer
    if _categorizer is None:
        from src.email.gmail_auth import get_gmail_service
        _categorizer = EmailCategorizer(get_gmail_service())
    return _categorizer


def auto_categorize_email(message_id: str) -> Dict:
    return _get_categorizer().auto_categorize_email(message_id)


def apply_smart_labels(batch_size: int = 20) -> Dict:
    return _get_categorizer().apply_smart_labels(batch_size)


def create_category_rules(min_occurrences: int = 3) -> Dict:
    return _get_categorizer().create_category_rules(min_occurrences)
