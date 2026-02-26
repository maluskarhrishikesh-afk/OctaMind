"""
Email Analytics

Aggregate statistics, response time analysis, and productivity insights.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import dateutil.parser

logger = logging.getLogger("email_agent.features.analytics")

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')


class EmailAnalytics:
    """Email analytics and productivity insights."""

    def __init__(self, gmail_service, user_id: str = 'me'):
        self.gmail_service = gmail_service
        self.user_id = user_id

    def _get_user_email(self) -> str:
        try:
            profile = self.gmail_service.users().getProfile(userId=self.user_id).execute()
            return profile.get('emailAddress', '').lower()
        except Exception:
            return ''

    def get_email_stats(self, days: int = 30) -> Dict:
        """
        Get comprehensive email statistics for the past N days.

        Returns:
            Dict with volume, busiest days, top senders, and response metrics
        """
        try:
            start_date = (datetime.now() - timedelta(days=days)
                          ).strftime('%Y/%m/%d')
            my_email = self._get_user_email()

            # Received emails
            recv_response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f'in:inbox after:{start_date}',
                maxResults=500
            ).execute()
            # Sent emails
            sent_response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f'in:sent after:{start_date}',
                maxResults=500
            ).execute()

            received_msgs = recv_response.get('messages', [])
            sent_msgs = sent_response.get('messages', [])

            # Analyze received emails
            by_day_recv: Dict[str, int] = defaultdict(int)
            by_hour_recv: Dict[int, int] = defaultdict(int)
            top_senders: Dict[str, int] = defaultdict(int)
            sender_names: Dict[str, str] = {}

            sample = min(100, len(received_msgs))
            for msg_item in received_msgs[:sample]:
                try:
                    msg = self.gmail_service.users().messages().get(
                        userId=self.user_id, id=msg_item['id'],
                        format='metadata',
                        metadataHeaders=['From', 'Date']
                    ).execute()
                    headers = msg.get('payload', {}).get('headers', [])
                    from_h = next(
                        (h['value'] for h in headers if h['name'].lower() == 'from'), '')
                    date_h = next(
                        (h['value'] for h in headers if h['name'].lower() == 'date'), '')
                    try:
                        dt = dateutil.parser.parse(date_h)
                        by_day_recv[dt.strftime('%A')] += 1
                        by_hour_recv[dt.hour] += 1
                    except Exception:
                        pass
                    raw_email = EMAIL_RE.search(from_h)
                    if raw_email:
                        email_addr = raw_email.group(0).lower()
                        if email_addr != my_email:
                            top_senders[email_addr] += 1
                            # Extract name
                            if '<' in from_h:
                                name = from_h.split('<')[0].strip().strip('"')
                            else:
                                name = email_addr
                            sender_names[email_addr] = name
                except Exception:
                    pass

            # Top 5 senders
            top_5 = sorted(top_senders.items(),
                           key=lambda x: x[1], reverse=True)[:5]
            top_senders_list = [
                {'email': e, 'name': sender_names.get(e, e), 'count': c}
                for e, c in top_5
            ]

            # Busiest day and hour
            busiest_day = max(
                by_day_recv, key=by_day_recv.get) if by_day_recv else 'N/A'
            busiest_hour = max(
                by_hour_recv, key=by_hour_recv.get) if by_hour_recv else None
            busiest_hour_str = f"{busiest_hour:02d}:00-{busiest_hour:02d}:59" if busiest_hour is not None else 'N/A'

            # Unread count
            unread_response = self.gmail_service.users().messages().list(
                userId=self.user_id,
                q=f'in:inbox is:unread after:{start_date}',
                maxResults=500
            ).execute()
            unread_count = len(unread_response.get('messages', []))

            return {
                'status': 'success',
                'period_days': days,
                'total_received': len(received_msgs),
                'total_sent': len(sent_msgs),
                'total_unread': unread_count,
                'avg_received_per_day': round(len(received_msgs) / max(days, 1), 1),
                'busiest_day': busiest_day,
                'busiest_hour': busiest_hour_str,
                'top_senders': top_senders_list,
                'by_day_of_week': dict(by_day_recv),
                'by_hour': dict(sorted(by_hour_recv.items()))
            }
        except Exception as e:
            logger.error(f"Get email stats failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_productivity_insights(self) -> Dict:
        """
        Generate productivity insights and recommendations.

        Returns:
            Dict with insights, patterns, and actionable suggestions
        """
        try:
            stats = self.get_email_stats(days=14)
            if stats.get('status') == 'error':
                return stats

            insights = []
            suggestions = []

            total_recv = stats.get('total_received', 0)
            total_sent = stats.get('total_sent', 0)
            unread = stats.get('total_unread', 0)
            avg_per_day = stats.get('avg_received_per_day', 0)
            busiest_day = stats.get('busiest_day', 'N/A')
            busiest_hour = stats.get('busiest_hour', 'N/A')

            # Generate insights based on data
            if avg_per_day > 50:
                insights.append(
                    f"📬 You receive a high volume of emails (~{avg_per_day:.0f}/day). Consider inbox filters.")
                suggestions.append(
                    "Set up Gmail filters to auto-label common senders")
            elif avg_per_day > 20:
                insights.append(
                    f"📬 You receive a moderate volume of emails (~{avg_per_day:.0f}/day).")
            else:
                insights.append(
                    f"📬 You receive a light volume of emails (~{avg_per_day:.0f}/day).")

            if unread > 50:
                insights.append(
                    f"📖 You have {unread} unread emails — consider batch-processing them.")
                suggestions.append("Block 30 minutes to process unread emails")
            elif unread > 0:
                insights.append(
                    f"📖 {unread} unread emails in the past 2 weeks.")

            if busiest_day != 'N/A':
                insights.append(f"📅 Your busiest email day is {busiest_day}.")
                suggestions.append(
                    f"Consider scheduling email-free time on {busiest_day}")

            if busiest_hour != 'N/A':
                insights.append(f"⏰ Most emails arrive around {busiest_hour}.")
                suggestions.append(
                    f"Check email at {busiest_hour} for timely responses")

            if total_sent > 0:
                ratio = round(total_recv / max(total_sent, 1), 1)
                insights.append(
                    f"📊 Send/receive ratio: {total_sent} sent vs {total_recv} received (ratio {ratio}:1)")

            top_senders = stats.get('top_senders', [])
            if top_senders:
                top = top_senders[0]
                insights.append(
                    f"👤 Top sender: {top.get('name', top.get('email', ''))} ({top.get('count', 0)} emails)")

            return {
                'status': 'success',
                'insights': insights,
                'suggestions': suggestions,
                'stats_summary': {
                    'received_14d': total_recv,
                    'sent_14d': total_sent,
                    'unread': unread,
                    'avg_per_day': avg_per_day,
                    'busiest_day': busiest_day
                }
            }
        except Exception as e:
            logger.error(f"Productivity insights failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def calculate_response_time(self, message_id: str) -> Dict:
        """
        Calculate how quickly you responded to an email (in hours).
        """
        try:
            # Get the original email's thread
            msg = self.gmail_service.users().messages().get(
                userId=self.user_id, id=message_id,
                format='metadata',
                metadataHeaders=['Date', 'From', 'Subject']
            ).execute()
            headers = msg.get('payload', {}).get('headers', [])
            recv_date_str = next(
                (h['value'] for h in headers if h['name'].lower() == 'date'), '')
            subject = next(
                (h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            thread_id = msg.get('threadId', '')

            recv_date = dateutil.parser.parse(recv_date_str)

            # Find reply in same thread
            thread = self.gmail_service.users().threads().get(
                userId=self.user_id, id=thread_id, format='metadata',
                metadataHeaders=['Date', 'From']
            ).execute()

            thread_msgs = thread.get('messages', [])
            my_email = self._get_user_email()
            reply_date = None
            for t_msg in thread_msgs:
                t_headers = t_msg.get('payload', {}).get('headers', [])
                t_from = next(
                    (h['value'] for h in t_headers if h['name'].lower() == 'from'), '')
                t_date_str = next(
                    (h['value'] for h in t_headers if h['name'].lower() == 'date'), '')
                if my_email and my_email in t_from.lower() and t_msg['id'] != message_id:
                    try:
                        t_date = dateutil.parser.parse(t_date_str)
                        if t_date > recv_date:
                            if reply_date is None or t_date < reply_date:
                                reply_date = t_date
                    except Exception:
                        pass

            if reply_date:
                hours = (reply_date - recv_date).total_seconds() / 3600
                return {
                    'status': 'success',
                    'message_id': message_id,
                    'subject': subject,
                    'responded': True,
                    'response_time_hours': round(hours, 1),
                    'response_time_human': f"{hours:.1f} hours" if hours >= 1 else f"{hours * 60:.0f} minutes"
                }
            return {
                'status': 'success',
                'message_id': message_id,
                'subject': subject,
                'responded': False,
                'response_time_hours': None,
                'response_time_human': 'Not replied yet'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def visualize_patterns(self, days: int = 30) -> Dict:
        """
        Generate chart-ready data for email pattern visualization.

        Returns structured datasets suitable for bar charts, pie charts,
        and line graphs — no rendering is done here.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with chart data for: volume_over_time, sender_distribution,
            hourly_distribution, day_of_week_distribution
        """
        try:
            stats = self.get_email_stats(days)
            if stats.get('status') == 'error':
                return stats

            # Day-of-week bar chart data
            day_order = ['Monday', 'Tuesday', 'Wednesday',
                         'Thursday', 'Friday', 'Saturday', 'Sunday']
            by_day = stats.get('by_day_of_week', {})
            day_chart = {
                'labels': day_order,
                'data': [by_day.get(d, 0) for d in day_order],
                'title': f'Emails Received by Day of Week (last {days} days)',
                'type': 'bar'
            }

            # Hourly distribution chart
            by_hour = stats.get('by_hour', {})
            hour_chart = {
                'labels': [f'{h:02d}:00' for h in range(24)],
                'data': [by_hour.get(h, 0) for h in range(24)],
                'title': 'Emails Received by Hour of Day',
                'type': 'bar'
            }

            # Sender distribution pie chart
            top_senders = stats.get('top_senders', [])
            sender_chart = {
                'labels': [s.get('name', s.get('email', '')) for s in top_senders],
                'data': [s.get('count', 0) for s in top_senders],
                'title': f'Top Email Senders (last {days} days)',
                'type': 'pie'
            }

            # Volume over time (simplified: received vs sent summary)
            volume_chart = {
                'labels': ['Received', 'Sent', 'Unread'],
                'data': [
                    stats.get('total_received', 0),
                    stats.get('total_sent', 0),
                    stats.get('total_unread', 0)
                ],
                'title': f'Email Volume Summary (last {days} days)',
                'type': 'bar'
            }

            return {
                'status': 'success',
                'period_days': days,
                'charts': {
                    'volume_summary': volume_chart,
                    'day_of_week': day_chart,
                    'hourly_distribution': hour_chart,
                    'top_senders': sender_chart
                },
                'summary_stats': {
                    'total_received': stats.get('total_received', 0),
                    'total_sent': stats.get('total_sent', 0),
                    'busiest_day': stats.get('busiest_day', 'N/A'),
                    'busiest_hour': stats.get('busiest_hour', 'N/A'),
                    'avg_per_day': stats.get('avg_received_per_day', 0)
                }
            }
        except Exception as e:
            logger.error(f"visualize_patterns failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def generate_weekly_report(self) -> Dict:
        """
        Generate a comprehensive weekly email activity report.

        Returns a formatted text report plus structured data for the past 7 days.

        Returns:
            Dict with report_text (formatted string) and report_data (structured)
        """
        try:
            stats = self.get_email_stats(days=7)
            if stats.get('status') == 'error':
                return stats

            insights_result = self.get_productivity_insights()
            insights = insights_result.get('insights', []) if insights_result.get(
                'status') == 'success' else []
            suggestions = insights_result.get(
                'suggestions', []) if insights_result.get('status') == 'success' else []

            total_recv = stats.get('total_received', 0)
            total_sent = stats.get('total_sent', 0)
            unread = stats.get('total_unread', 0)
            avg_day = stats.get('avg_received_per_day', 0)
            busiest_day = stats.get('busiest_day', 'N/A')
            busiest_hour = stats.get('busiest_hour', 'N/A')
            top_senders = stats.get('top_senders', [])

            from datetime import datetime, timedelta
            week_start = (datetime.now() - timedelta(days=7)).strftime('%b %d')
            week_end = datetime.now().strftime('%b %d, %Y')

            # Build formatted report text
            lines = [
                f"📊 Weekly Email Report: {week_start} – {week_end}",
                "=" * 50,
                "",
                "📬 VOLUME",
                f"  Received:  {total_recv} emails",
                f"  Sent:      {total_sent} emails",
                f"  Unread:    {unread} emails",
                f"  Avg/day:   {avg_day:.1f} emails received per day",
                "",
                "📅 PATTERNS",
                f"  Busiest day:  {busiest_day}",
                f"  Peak hour:    {busiest_hour}",
            ]

            if top_senders:
                lines += ["", "👤 TOP SENDERS"]
                for i, s in enumerate(top_senders[:5], 1):
                    lines.append(
                        f"  {i}. {s.get('name', s.get('email', ''))} — {s.get('count', 0)} emails")

            if insights:
                lines += ["", "💡 INSIGHTS"]
                for insight in insights[:5]:
                    lines.append(f"  {insight}")

            if suggestions:
                lines += ["", "✅ SUGGESTIONS"]
                for suggestion in suggestions[:3]:
                    lines.append(f"  • {suggestion}")

            lines += [
                "",
                "─" * 50,
                f"Generated by Octa Bot Email Agent · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            ]

            report_text = '\n'.join(lines)

            return {
                'status': 'success',
                'report_text': report_text,
                'period': f"{week_start} – {week_end}",
                'report_data': {
                    'total_received': total_recv,
                    'total_sent': total_sent,
                    'unread': unread,
                    'avg_per_day': avg_day,
                    'busiest_day': busiest_day,
                    'busiest_hour': busiest_hour,
                    'top_senders': top_senders,
                    'insights': insights,
                    'suggestions': suggestions
                }
            }
        except Exception as e:
            logger.error(f"generate_weekly_report failed: {e}")
            return {'status': 'error', 'message': str(e)}


# Singleton + convenience functions
_analytics: Optional[EmailAnalytics] = None


def _get_analytics() -> EmailAnalytics:
    global _analytics
    if _analytics is None:
        from src.email.gmail_auth import get_gmail_service
        _analytics = EmailAnalytics(get_gmail_service())
    return _analytics


def get_email_stats(days: int = 30) -> Dict:
    return _get_analytics().get_email_stats(days)


def get_productivity_insights() -> Dict:
    return _get_analytics().get_productivity_insights()


def calculate_response_time(message_id: str) -> Dict:
    """Calculate how quickly you responded to a specific email."""
    return _get_analytics().calculate_response_time(message_id)


def visualize_patterns(days: int = 30) -> Dict:
    """Return chart-ready data for email pattern visualization."""
    return _get_analytics().visualize_patterns(days)


def generate_weekly_report() -> Dict:
    """Generate a comprehensive weekly email activity report."""
    return _get_analytics().generate_weekly_report()
