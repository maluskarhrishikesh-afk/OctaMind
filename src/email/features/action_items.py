"""
Action Item Extraction

Extracts tasks, deadlines, and to-dos from emails using LLM analysis.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.action_items")

# Persistent task storage
_TASKS_FILE = Path(__file__).parent.parent.parent.parent / \
    "data" / "action_items.json"


def _load_tasks() -> List[Dict]:
    if not _TASKS_FILE.exists():
        return []
    try:
        return json.loads(_TASKS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def _save_tasks(tasks: List[Dict]):
    _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TASKS_FILE.write_text(json.dumps(
        tasks, indent=2, default=str), encoding='utf-8')


class ActionItemExtractor:
    """Extracts action items and tasks from emails using LLM."""

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

    def _get_email_content(self, message_id: str) -> Dict:
        """Fetch subject + body for a message."""
        import base64
        try:
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id, format='full'
            ).execute()
            headers = msg['payload']['headers']
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            sender = next((h['value']
                          for h in headers if h['name'].lower() == 'from'), '')
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
            return {'subject': subject, 'sender': sender, 'body': body or msg.get('snippet', '')}
        except Exception as e:
            logger.error(f"Failed to get email content: {e}")
            return {}

    def extract_action_items(self, message_id: str) -> Dict:
        """
        Extract action items from a single email.

        Returns:
            Dict with 'action_items' list, each item having:
            task, deadline, priority (high/medium/low), assigned_to
        """
        content = self._get_email_content(message_id)
        if not content:
            return {'status': 'error', 'message': 'Could not fetch email content'}

        prompt = f"""Analyze this email and extract all action items, tasks, requests, and to-dos.

Subject: {content.get('subject', '')}
From: {content.get('sender', '')}
Body:
{content.get('body', '')[:3000]}

Return ONLY a JSON object with this exact structure:
{{
  "action_items": [
    {{
      "task": "clear description of what needs to be done",
      "deadline": "date/time if mentioned, or null",
      "priority": "high|medium|low",
      "assigned_to": "person responsible, or 'me' if unclear",
      "type": "task|reply|review|meeting|payment|other"
    }}
  ],
  "summary": "one-sentence summary of email's demands"
}}

Priority rules:
- high: urgent, ASAP, today, this must, critical, immediately
- medium: soon, please, when you get a chance, by [date within 7 days]
- low: FYI, no rush, whenever

If no action items found, return {{"action_items": [], "summary": "Informational email, no action required"}}"""

        try:
            raw = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": "You are an expert email analyst that extracts action items. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=600,
                timeout=30
            )
            text = raw.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            result['status'] = 'success'
            result['message_id'] = message_id
            result['subject'] = content.get('subject', '')
            result['sender'] = content.get('sender', '')
            # Assign persistent IDs and auto-save
            for item in result.get('action_items', []):
                item['task_id'] = str(uuid.uuid4())[:8]
                item['email_id'] = message_id
                item['email_subject'] = result['subject']
                item['email_sender'] = result['sender']
                item['status'] = 'pending'
                item['created_at'] = datetime.now().strftime('%Y-%m-%d')
            self._save_extracted_tasks(result.get('action_items', []))
            return result
        except Exception as e:
            logger.error(f"Action item extraction failed: {e}")
            return {'status': 'error', 'message': str(e), 'action_items': []}

    def get_all_pending_actions(self, max_emails: int = 20) -> Dict:
        """Scan recent emails for action items."""
        import base64
        try:
            # Get recent emails from inbox not from self
            response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q='in:inbox -from:me',
                maxResults=max_emails
            ).execute()
            messages = response.get('messages', [])
            all_items = []
            for msg in messages[:max_emails]:
                result = self.extract_action_items(msg['id'])
                if result.get('status') == 'success' and result.get('action_items'):
                    for item in result['action_items']:
                        item['email_id'] = msg['id']
                        item['email_subject'] = result.get('subject', '')
                        item['email_sender'] = result.get('sender', '')
                        all_items.append(item)

            # Sort by priority
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            all_items.sort(key=lambda x: priority_order.get(
                x.get('priority', 'low'), 2))

            return {
                'status': 'success',
                'action_items': all_items,
                'total': len(all_items),
                'emails_scanned': len(messages)
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def _save_extracted_tasks(self, new_items: List[Dict]):
        """Persist newly extracted tasks, skipping duplicates by email+task text."""
        if not new_items:
            return
        tasks = _load_tasks()
        existing_keys = {
            (t.get('email_id', ''), t.get('task', '').lower()[:50])
            for t in tasks
        }
        added = 0
        for item in new_items:
            key = (item.get('email_id', ''), item.get('task', '').lower()[:50])
            if key not in existing_keys:
                tasks.append(item)
                existing_keys.add(key)
                added += 1
        if added:
            _save_tasks(tasks)

    def get_saved_tasks(self, status_filter: str = 'pending') -> Dict:
        """
        Return persisted action items.

        Args:
            status_filter: 'pending', 'done', 'all'
        """
        tasks = _load_tasks()
        if status_filter == 'all':
            filtered = tasks
        else:
            filtered = [t for t in tasks if t.get('status') == status_filter]
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        filtered.sort(key=lambda x: priority_order.get(
            x.get('priority', 'low'), 2))
        return {
            'status': 'success',
            'tasks': filtered,
            'total': len(filtered),
            'status_filter': status_filter
        }

    def mark_action_complete(self, task_id: str) -> Dict:
        """
        Mark a task as completed.

        Args:
            task_id: The task_id assigned during extraction

        Returns:
            Dict with status and confirmation
        """
        tasks = _load_tasks()
        for task in tasks:
            if task.get('task_id') == task_id:
                if task.get('status') == 'done':
                    return {'status': 'success', 'message': f"Task '{task.get('task', task_id)}' was already marked done."}
                task['status'] = 'done'
                task['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                _save_tasks(tasks)
                return {
                    'status': 'success',
                    'task_id': task_id,
                    'task': task.get('task', ''),
                    'message': f"✅ Task marked complete: '{task.get('task', task_id)}'"
                }
        return {'status': 'error', 'message': f"Task '{task_id}' not found. Use get_saved_tasks to see task IDs."}


# Module-level singleton and convenience functions
_extractor: Optional[ActionItemExtractor] = None


def _get_extractor() -> ActionItemExtractor:
    global _extractor
    if _extractor is None:
        from src.email.gmail_auth import get_gmail_service
        _extractor = ActionItemExtractor(get_gmail_service())
    return _extractor


def extract_action_items(message_id: str) -> Dict:
    """Extract action items from a single email by message ID."""
    return _get_extractor().extract_action_items(message_id)


def get_all_pending_actions(max_emails: int = 20) -> Dict:
    """Scan recent inbox emails for all pending action items."""
    return _get_extractor().get_all_pending_actions(max_emails)


def get_saved_tasks(status_filter: str = 'pending') -> Dict:
    """Return persisted action items. status_filter: 'pending', 'done', 'all'."""
    return _get_extractor().get_saved_tasks(status_filter)


def mark_action_complete(task_id: str) -> Dict:
    """Mark a saved action item as completed by its task_id."""
    return _get_extractor().mark_action_complete(task_id)
