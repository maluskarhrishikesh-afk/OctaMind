"""
Gmail Email Summarization Module

This module provides AI-powered email summarization features using LLM:
- Summarize single emails
- Summarize email threads
- Generate daily email digests

Usage:
    from src.email.email_summarizer import EmailSummarizer
    
    summarizer = EmailSummarizer(gmail_service)
    summary = summarizer.summarize_email("message_id_123")
"""

import base64
import json
from typing import Dict, List
from datetime import datetime


class EmailSummarizer:
    """AI-powered email summarization using LLM"""

    def __init__(self, gmail_service, user_id: str = 'me'):
        """
        Initialize the email summarizer

        Args:
            gmail_service: Authenticated Gmail API service instance
            user_id: Gmail user ID (default: 'me' for authenticated user)
        """
        self.gmail_service = gmail_service
        self.user_id = user_id

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

    def summarize_email(self, message_id: str) -> Dict:
        """
        Generate AI summary of an email

        Args:
            message_id: Gmail message ID

        Returns:
            Dictionary with summary, key_points, and metadata
        """
        try:
            # Get full email content
            email_data = self._get_email_body(message_id)

            if 'error' in email_data:
                return email_data

            # Try to use LLM for summarization
            try:
                from src.agent.llm.llm_parser import GitHubModelsLLM
                llm = GitHubModelsLLM()

                # Create prompt for summarization
                prompt = f"""Analyze and summarize this email:

From: {email_data['sender']}
Subject: {email_data['subject']}
Date: {email_data['date']}

Body:
{email_data['body'][:2000]}  

Provide:
1. A brief 2-3 sentence summary
2. Key points (3-5 bullet points)
3. Any action items or deadlines mentioned
4. Sentiment (positive/neutral/negative)

Format as JSON with keys: summary, key_points (array), action_items (array), sentiment"""

                response = llm.client.chat.completions.create(
                    model=llm.model,
                    messages=[
                        {"role": "system", "content": "You are an email analysis assistant. Return ONLY valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500
                )

                result = json.loads(response.choices[0].message.content)

                return {
                    'status': 'success',
                    'message_id': message_id,
                    'subject': email_data['subject'],
                    'sender': email_data['sender'],
                    'date': email_data['date'],
                    'summary': result.get('summary', ''),
                    'key_points': result.get('key_points', []),
                    'action_items': result.get('action_items', []),
                    'sentiment': result.get('sentiment', 'neutral'),
                    'word_count': len(email_data['body'].split())
                }

            except ImportError:
                # Fallback: use snippet as summary if LLM not available
                return {
                    'status': 'success',
                    'message_id': message_id,
                    'subject': email_data['subject'],
                    'sender': email_data['sender'],
                    'date': email_data['date'],
                    'summary': email_data['snippet'],
                    'key_points': [],
                    'action_items': [],
                    'sentiment': 'neutral',
                    'word_count': len(email_data['body'].split()),
                    'note': 'LLM not available, using snippet'
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Error summarizing email',
                'error': str(e)
            }

    def summarize_thread(self, thread_id: str) -> Dict:
        """
        Summarize an entire email thread

        Args:
            thread_id: Gmail thread ID

        Returns:
            Dictionary with thread summary and metadata
        """
        try:
            # Get all messages in thread
            thread = self.gmail_service.users().threads().get(
                userId=self.user_id,
                id=thread_id,
                format='full'
            ).execute()

            messages = thread.get('messages', [])

            if not messages:
                return {
                    'status': 'error',
                    'message': 'No messages found in thread'
                }

            # Extract participants and message count
            participants = set()
            message_summaries = []

            for msg in messages:
                headers = msg['payload']['headers']
                sender = next(
                    (h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                participants.add(sender)

                # Get subject from first message
                if not message_summaries:
                    subject = next(
                        (h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')

                # Get snippet for each message
                message_summaries.append({
                    'from': sender,
                    'snippet': msg.get('snippet', '')
                })

            # Try to use LLM for thread summarization
            try:
                from src.agent.llm.llm_parser import GitHubModelsLLM
                llm = GitHubModelsLLM()

                # Create conversation summary
                conversation = "\n\n".join([
                    f"From: {m['from']}\n{m['snippet']}"
                    for m in message_summaries
                ])

                prompt = f"""Summarize this email thread:

Subject: {subject}
Participants: {', '.join(participants)}
Messages: {len(messages)}

Conversation:
{conversation[:1500]}

Provide:
1. Overall thread summary (2-3 sentences)
2. Key discussion points
3. Current status or outcome
4. Any pending actions

Format as JSON with keys: summary, discussion_points (array), status, pending_actions (array)"""

                response = llm.client.chat.completions.create(
                    model=llm.model,
                    messages=[
                        {"role": "system", "content": "You are an email thread analyzer. Return ONLY valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500
                )

                result = json.loads(response.choices[0].message.content)

                return {
                    'status': 'success',
                    'thread_id': thread_id,
                    'subject': subject,
                    'message_count': len(messages),
                    'participants': list(participants),
                    'summary': result.get('summary', ''),
                    'discussion_points': result.get('discussion_points', []),
                    'status_summary': result.get('status', 'ongoing'),
                    'pending_actions': result.get('pending_actions', [])
                }

            except ImportError:
                # Fallback without LLM
                return {
                    'status': 'success',
                    'thread_id': thread_id,
                    'subject': subject,
                    'message_count': len(messages),
                    'participants': list(participants),
                    'summary': f"Thread with {len(messages)} messages",
                    'note': 'LLM not available'
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Error summarizing thread',
                'error': str(e)
            }

    def generate_daily_digest(self, list_emails_func, max_emails: int = 20) -> Dict:
        """
        Generate a digest of today's emails

        Args:
            list_emails_func: Function to list emails (passed from GmailServiceClient)
            max_emails: Maximum number of emails to include

        Returns:
            Dictionary with daily digest summary
        """
        try:
            # Get today's date for query
            today = datetime.now().strftime('%Y/%m/%d')
            query = f'after:{today}'

            # Get today's emails
            emails = list_emails_func(query=query, max_results=max_emails)

            if not emails:
                return {
                    'status': 'success',
                    'date': today,
                    'total_emails': 0,
                    'summary': 'No emails received today',
                    'by_sender': {},
                    'highlights': []
                }

            # Aggregate by sender
            by_sender = {}
            for email in emails:
                sender = email['sender']
                if sender in by_sender:
                    by_sender[sender] += 1
                else:
                    by_sender[sender] = 1

            # Try to use LLM for digest
            try:
                from src.agent.llm.llm_parser import GitHubModelsLLM
                llm = GitHubModelsLLM()

                # Create email list for LLM
                email_list = "\n".join([
                    f"- From: {e['sender']}\n  Subject: {e['subject']}\n  Snippet: {e['snippet']}"
                    for e in emails[:15]  # Limit to avoid token overflow
                ])

                prompt = f"""Create a daily email digest for {len(emails)} emails received today.

Emails:
{email_list}

Provide:
1. Brief overview summary (2-3 sentences)
2. Key highlights (3-5 most important emails)
3. Categories (work, personal, promotional, etc.)

Format as JSON with keys: overview, highlights (array of strings), categories (object with category counts)"""

                response = llm.client.chat.completions.create(
                    model=llm.model,
                    messages=[
                        {"role": "system", "content": "You are a daily email digest creator. Return ONLY valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=600
                )

                result = json.loads(response.choices[0].message.content)

                return {
                    'status': 'success',
                    'date': today,
                    'total_emails': len(emails),
                    'summary': result.get('overview', ''),
                    'highlights': result.get('highlights', []),
                    'categories': result.get('categories', {}),
                    'by_sender': by_sender,
                    'top_senders': sorted(by_sender.items(), key=lambda x: x[1], reverse=True)[:5]
                }

            except ImportError:
                # Fallback without LLM
                return {
                    'status': 'success',
                    'date': today,
                    'total_emails': len(emails),
                    'summary': f'Received {len(emails)} emails today',
                    'by_sender': by_sender,
                    'top_senders': sorted(by_sender.items(), key=lambda x: x[1], reverse=True)[:5],
                    'note': 'LLM not available for detailed digest'
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Error generating daily digest',
                'error': str(e)
            }
