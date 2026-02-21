"""
Priority Detection

Detect urgent and high-priority emails using LLM analysis.
"""

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.priority")

# Urgency keywords for fast pre-filtering
HIGH_PRIORITY_KEYWORDS = [
    'urgent', 'asap', 'immediately', 'critical', 'emergency', 'deadline today',
    'action required', 'time sensitive', 'high priority', 'important', 'escalation',
    'do not ignore', 'respond immediately', 'need your help now'
]


class PriorityDetector:
    """Detect and classify email urgency."""

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

    def auto_prioritize(self, message_id: str) -> Dict:
        """
        Determine the priority of a single email.

        Returns:
            Dict with priority level (high/medium/low) and reason
        """
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id,
                format='metadata',
                metadataHeaders=['Subject', 'From', 'Importance', 'X-Priority']
            ).execute()
            headers = msg.get('payload', {}).get('headers', [])
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            sender = next((h['value']
                          for h in headers if h['name'].lower() == 'from'), '')
            importance_header = next((h['value'] for h in headers if h['name'].lower() in (
                'importance', 'x-priority')), '')
            snippet = msg.get('snippet', '')
            labels = msg.get('labelIds', [])

            # Fast keyword check
            combined_text = (subject + ' ' + snippet).lower()
            fast_high = any(
                kw in combined_text for kw in HIGH_PRIORITY_KEYWORDS)
            is_important = 'IMPORTANT' in labels

            # LLM evaluation
            prompt = f"""Rate the priority of this email:
Subject: {subject}
From: {sender}
Importance header: {importance_header}
Preview: {snippet[:400]}

Return ONLY JSON:
{{"priority": "high|medium|low", "score": 1_to_10, "reason": "brief explanation", "urgency_keywords": ["any urgency words found"]}}"""

            raw = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system",
                        "content": "You rate email urgency. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=150,
                timeout=15
            )
            text = raw.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())

            # Boost to high if signals agree
            if fast_high or is_important:
                result['priority'] = 'high'
                result['boosted'] = True

            result['status'] = 'success'
            result['message_id'] = message_id
            result['subject'] = subject
            result['sender'] = sender
            return result
        except Exception as e:
            logger.error(f"Auto-prioritize failed: {e}")
            return {'status': 'error', 'message': str(e), 'priority': 'medium'}

    def detect_urgent_emails(self, max_results: int = 30) -> Dict:
        """
        Scan inbox for urgent/high-priority emails.

        Returns:
            Dict with list of urgent emails
        """
        try:
            # Build a query to find potentially urgent emails
            query = f'in:inbox ({" OR ".join(HIGH_PRIORITY_KEYWORDS[:6])})'
            response = self.gmail_service.users().messages().list(
                userId=self.user_id, q=query, maxResults=max_results
            ).execute()

            # Also check IMPORTANT label
            imp_response = self.gmail_service.users().messages().list(
                userId=self.user_id, q='label:important in:inbox', maxResults=max_results
            ).execute()

            # Combine and deduplicate
            all_ids = {m['id'] for m in response.get('messages', [])}
            all_ids.update(m['id'] for m in imp_response.get('messages', []))

            urgent = []
            for msg_id in list(all_ids)[:20]:
                result = self.auto_prioritize(msg_id)
                if result.get('priority') == 'high':
                    urgent.append({
                        'id': msg_id,
                        'subject': result.get('subject', ''),
                        'sender': result.get('sender', ''),
                        'priority_score': result.get('score', 0),
                        'reason': result.get('reason', ''),
                        'urgency_keywords': result.get('urgency_keywords', [])
                    })

            urgent.sort(key=lambda x: x.get('priority_score', 0), reverse=True)
            return {
                'status': 'success',
                'urgent_emails': urgent,
                'count': len(urgent)
            }
        except Exception as e:
            logger.error(f"Detect urgent emails failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def create_priority_inbox(self, max_results: int = 20) -> Dict:
        """Get inbox sorted by priority score."""
        try:
            response = self.gmail_service.users().messages().list(
                userId=self.user_id, q='in:inbox is:unread', maxResults=max_results
            ).execute()
            messages = response.get('messages', [])
            scored = []
            for msg_item in messages[:15]:  # Limit LLM calls
                result = self.auto_prioritize(msg_item['id'])
                scored.append({
                    'id': msg_item['id'],
                    'subject': result.get('subject', ''),
                    'sender': result.get('sender', ''),
                    'priority': result.get('priority', 'medium'),
                    'score': result.get('score', 5)
                })
            scored.sort(key=lambda x: x.get('score', 0), reverse=True)
            return {
                'status': 'success',
                'priority_inbox': scored,
                'count': len(scored)
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


# Singleton + convenience functions
_detector: Optional[PriorityDetector] = None


def _get_detector() -> PriorityDetector:
    global _detector
    if _detector is None:
        from src.email.gmail_auth import get_gmail_service
        _detector = PriorityDetector(get_gmail_service())
    return _detector


def detect_urgent_emails(max_results: int = 30) -> Dict:
    return _get_detector().detect_urgent_emails(max_results)


def auto_prioritize(message_id: str) -> Dict:
    return _get_detector().auto_prioritize(message_id)
