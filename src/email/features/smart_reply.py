"""
Smart Reply Suggestions

Generates contextual reply options for emails using LLM.
"""

import base64
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("email_agent.features.smart_reply")

# Pre-built quick reply templates
QUICK_REPLY_TEMPLATES = {
    "yes": "Thank you for reaching out. Yes, I agree / I'm available / I can do that.",
    "no": "Thank you for reaching out. Unfortunately, I'm unable to accommodate this at this time.",
    "thanks": "Thank you for the information. I appreciate you letting me know.",
    "acknowledged": "Received and understood. I'll look into this and get back to you shortly.",
    "more_info_needed": "Thank you for your email. Could you please provide more details so I can assist you better?",
    "on_it": "Got it! I'll take care of this right away and will keep you updated on the progress.",
    "meeting_confirm": "Works for me! I'll add this to my calendar. Looking forward to it.",
    "meeting_decline": "Thank you for the invitation. Unfortunately, I have a conflict at that time. Could we reschedule?",
}


class SmartReplyGenerator:
    """Generates intelligent reply suggestions for emails."""

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
        """Fetch email content for reply generation."""
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
            thread_id = msg.get('threadId', '')
            return {
                'subject': subject, 'sender': sender,
                'body': body or msg.get('snippet', ''),
                'thread_id': thread_id, 'message_id': message_id
            }
        except Exception as e:
            logger.error(f"Failed to get email content: {e}")
            return {}

    def generate_reply_suggestions(self, message_id: str, tone: str = "professional") -> Dict:
        """
        Generate 3 reply options for an email.

        Args:
            message_id: The Gmail message ID to reply to
            tone: 'professional', 'casual', or 'brief'

        Returns:
            Dict with 'suggestions' list of 3 reply options
        """
        content = self._get_email_content(message_id)
        if not content:
            return {'status': 'error', 'message': 'Could not fetch email content'}

        prompt = f"""Generate 3 different reply options for this email. Each reply should be complete and ready to send.

Original Email:
Subject: {content.get('subject', '')}
From: {content.get('sender', '')}
Body:
{content.get('body', '')[:2000]}

Generate 3 replies:
1. **Brief** - Short, direct, 2-3 sentences max
2. **Professional** - Formal, polished, appropriate for business
3. **Detailed** - Thorough response addressing all points

Return ONLY a JSON object:
{{
  "suggestions": [
    {{
      "type": "brief",
      "subject": "Re: {content.get('subject', '')}",
      "body": "reply body text here"
    }},
    {{
      "type": "professional",
      "subject": "Re: {content.get('subject', '')}",
      "body": "reply body text here"
    }},
    {{
      "type": "detailed",
      "subject": "Re: {content.get('subject', '')}",
      "body": "reply body text here"
    }}
  ],
  "tone_detected": "formal|casual|urgent|informational"
}}"""

        try:
            raw = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": "You are an expert email writer. Generate helpful, natural-sounding email replies. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800,
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
            result['original_subject'] = content.get('subject', '')
            result['original_sender'] = content.get('sender', '')
            result['thread_id'] = content.get('thread_id', '')
            return result
        except Exception as e:
            logger.error(f"Smart reply generation failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def quick_reply(self, message_id: str, reply_type: str) -> Dict:
        """
        Send a quick pre-built reply to an email.

        Args:
            message_id: Gmail message ID
            reply_type: One of yes/no/thanks/acknowledged/more_info_needed/on_it/meeting_confirm/meeting_decline
        """
        if reply_type not in QUICK_REPLY_TEMPLATES:
            available = list(QUICK_REPLY_TEMPLATES.keys())
            return {
                'status': 'error',
                'message': f"Unknown reply type '{reply_type}'. Available: {available}"
            }

        content = self._get_email_content(message_id)
        if not content:
            return {'status': 'error', 'message': 'Could not fetch email content'}

        reply_body = QUICK_REPLY_TEMPLATES[reply_type]
        subject = f"Re: {content.get('subject', '')}"

        # Get sender email for reply-to
        sender = content.get('sender', '')
        # Extract email from "Name <email>" format
        if '<' in sender:
            reply_to = sender.split('<')[1].replace('>', '').strip()
        else:
            reply_to = sender

        return {
            'status': 'success',
            'reply_type': reply_type,
            'reply_to': reply_to,
            'subject': subject,
            'body': reply_body,
            'thread_id': content.get('thread_id', ''),
            'message_id': message_id,
            'preview': reply_body[:100]
        }


# Singleton and convenience functions
_generator: Optional[SmartReplyGenerator] = None


def _get_generator() -> SmartReplyGenerator:
    global _generator
    if _generator is None:
        from src.email.gmail_auth import get_gmail_service
        _generator = SmartReplyGenerator(get_gmail_service())
    return _generator


def generate_reply_suggestions(message_id: str, tone: str = "professional") -> Dict:
    """Generate 3 contextual reply suggestions for an email."""
    return _get_generator().generate_reply_suggestions(message_id, tone)


def quick_reply(message_id: str, reply_type: str) -> Dict:
    """Get a pre-built quick reply for common responses."""
    return _get_generator().quick_reply(message_id, reply_type)
