"""
WhatsApp analytics tools.

Provides usage statistics, activity reports, response time analysis,
and top-sender rankings derived from the local message store.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..webhook.message_store import get_all_messages, get_messages_for_contact

logger = logging.getLogger("whatsapp_agent")


def _iso_to_dt(s: str) -> datetime:
    """Parse an ISO timestamp string."""
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return datetime.min


def get_message_stats(days: int = 30) -> Dict[str, Any]:
    """
    Get WhatsApp message volume statistics for the past N days.

    Args:
        days: Number of past days to analyse (default 30).
    """
    try:
        days = max(1, min(int(days), 365))
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        all_msgs = get_all_messages(limit=10000)
        period_msgs = [m for m in all_msgs if m.get("timestamp", "") >= cutoff_str]

        inbound = [m for m in period_msgs if m.get("direction") == "inbound"]
        outbound = [m for m in period_msgs if m.get("direction") == "outbound"]
        unread = [m for m in inbound if not m.get("read")]

        # Daily volume
        daily: Counter = Counter()
        for m in period_msgs:
            date = m.get("timestamp", "")[:10]
            daily[date] += 1
        busiest_day = daily.most_common(1)[0] if daily else ("N/A", 0)

        # Message type breakdown
        type_counts: Counter = Counter(m.get("type", "text") for m in period_msgs)

        return {
            "status": "success",
            "period_days": days,
            "total_messages": len(period_msgs),
            "inbound": len(inbound),
            "outbound": len(outbound),
            "unread": len(unread),
            "busiest_day": {"date": busiest_day[0], "count": busiest_day[1]},
            "message_types": dict(type_counts),
        }
    except Exception as exc:
        logger.error("get_message_stats failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_response_time(phone: str) -> Dict[str, Any]:
    """
    Calculate average response time for a specific contact.

    Measures the time between an inbound message and the next outbound
    reply to identify how quickly you respond to this person.

    Args:
        phone: Contact phone (E.164).
    """
    try:
        msgs = get_messages_for_contact(phone, limit=200)
        msgs.sort(key=lambda m: m.get("timestamp", ""))

        response_times: List[float] = []
        for i, msg in enumerate(msgs):
            if msg.get("direction") == "inbound":
                # Find the next outbound message
                for j in range(i + 1, len(msgs)):
                    if msgs[j].get("direction") == "outbound":
                        t_recv = _iso_to_dt(msg["timestamp"])
                        t_sent = _iso_to_dt(msgs[j]["timestamp"])
                        delta_mins = (t_sent - t_recv).total_seconds() / 60
                        if 0 < delta_mins < 60 * 24:  # ignore > 24h
                            response_times.append(delta_mins)
                        break

        if not response_times:
            return {
                "status": "success",
                "phone": phone,
                "avg_response_minutes": None,
                "note": "Not enough data to calculate response time.",
            }

        avg_mins = sum(response_times) / len(response_times)
        return {
            "status": "success",
            "phone": phone,
            "avg_response_minutes": round(avg_mins, 1),
            "avg_response_human": (
                f"{int(avg_mins)} min" if avg_mins < 60
                else f"{avg_mins / 60:.1f} hours"
            ),
            "samples": len(response_times),
        }
    except Exception as exc:
        logger.error("get_response_time failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_activity_report(days: int = 7) -> Dict[str, Any]:
    """
    Generate an activity report showing messaging patterns by hour and day.

    Args:
        days: Number of past days to analyse (default 7).
    """
    try:
        days = max(1, min(int(days), 90))
        cutoff_str = (datetime.now() - timedelta(days=days)).isoformat()

        all_msgs = get_all_messages(limit=10000)
        period_msgs = [m for m in all_msgs if m.get("timestamp", "") >= cutoff_str]

        # Hourly distribution
        hourly: Counter = Counter()
        daily_dow: Counter = Counter()
        for m in period_msgs:
            try:
                dt = _iso_to_dt(m.get("timestamp", ""))
                hourly[dt.hour] += 1
                daily_dow[dt.strftime("%A")] += 1
            except Exception:
                pass

        peak_hour = hourly.most_common(1)[0] if hourly else (0, 0)
        peak_day = daily_dow.most_common(1)[0] if daily_dow else ("N/A", 0)

        return {
            "status": "success",
            "period_days": days,
            "total_messages": len(period_msgs),
            "peak_hour": {"hour": peak_hour[0], "count": peak_hour[1]},
            "peak_day": {"day": peak_day[0], "count": peak_day[1]},
            "hourly_distribution": dict(hourly),
            "daily_distribution": dict(daily_dow),
        }
    except Exception as exc:
        logger.error("get_activity_report failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_top_senders(limit: int = 10) -> Dict[str, Any]:
    """
    Get the contacts who message you most frequently.

    Args:
        limit: Number of top senders to return (default 10).
    """
    try:
        limit = max(1, min(int(limit), 50))
        all_msgs = get_all_messages(limit=10000)
        inbound = [m for m in all_msgs if m.get("direction") == "inbound"]

        sender_counts: Counter = Counter(
            m.get("from", "unknown") for m in inbound
        )
        top = sender_counts.most_common(limit)

        senders = [
            {"phone": phone, "message_count": count}
            for phone, count in top
        ]
        return {
            "status": "success",
            "top_senders": senders,
            "count": len(senders),
        }
    except Exception as exc:
        logger.error("get_top_senders failed: %s", exc)
        return {"status": "error", "message": str(exc)}
