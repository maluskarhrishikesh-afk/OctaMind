"""
Google Drive Productivity Insights Module (Phase 4)

AI-powered insights about Drive usage patterns.

Functions:
- generate_drive_report  — generate a comprehensive Drive health report
- get_usage_insights     — LLM-narrated analysis of Drive usage

Usage:
    from src.drive.features.insights import generate_drive_report, get_usage_insights
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.drive.features.analytics import (
    storage_breakdown,
    list_large_files,
    list_old_files,
    sharing_report,
)

logger = logging.getLogger("drive_agent.insights")


def generate_drive_report() -> Dict[str, Any]:
    """
    Generate a markdown health report of the user's Google Drive.

    Combines storage breakdown, large files, old files, and sharing audit.

    Returns:
        Dict with status and report_markdown.
    """
    try:
        storage = storage_breakdown(max_files=500)
        large = list_large_files(min_size_mb=50, max_results=10)
        old = list_old_files(days=365, max_results=10)
        sharing = sharing_report(max_files=200)

        lines = ["# 📊 Google Drive Health Report\n"]

        # Storage
        if storage["status"] == "success":
            lines.append(
                f"## 💾 Storage Overview\n"
                f"- **Total files scanned:** {storage['total_files']:,}\n"
                f"- **Total size:** {storage['total_size_human']}\n"
            )
            for item in storage["breakdown"][:8]:
                lines.append(
                    f"  - **{item['type']}:** {item['count']:,} files — {item['size_human']}"
                )
            lines.append("")

        # Large files
        if large["status"] == "success":
            count = large["count"]
            lines.append(f"## 📦 Large Files (> {large['min_size_mb']} MB)\n")
            if count == 0:
                lines.append("✅ No large files found.\n")
            else:
                lines.append(f"Found **{count}** large file(s):\n")
                for f in large["files"][:5]:
                    lines.append(
                        f"  - **{f['name']}** — {f.get('size_human', '?')}"
                    )
            lines.append("")

        # Old files
        if old["status"] == "success":
            count = old["count"]
            lines.append(f"## 🕰️ Stale Files (not modified in 1+ year)\n")
            if count == 0:
                lines.append("✅ No stale files found.\n")
            else:
                lines.append(f"Found **{count}** stale file(s):\n")
                for f in old["files"][:5]:
                    lines.append(
                        f"  - {f['name']} (last modified: {f.get('modifiedTime', '?')})")
            lines.append("")

        # Sharing
        if sharing["status"] == "success":
            lines.append("## 🔗 Sharing Overview\n")
            lines.append(f"- **Total files:** {sharing['total_files']:,}")
            lines.append(f"- **Shared:** {sharing['shared_count']:,}")
            lines.append(f"- **Private:** {sharing['private_count']:,}")
            lines.append("")

        return {
            "status": "success",
            "report_markdown": "\n".join(lines),
        }
    except Exception as e:
        logger.error("generate_drive_report error: %s", e)
        return {"status": "error", "message": str(e)}


def get_usage_insights() -> Dict[str, Any]:
    """
    Generate LLM-narrated insights about Drive usage patterns.

    Returns:
        Dict with status and insights text.
    """
    try:
        from src.agent.llm.llm_parser import get_llm_client

        report = generate_drive_report()
        if report["status"] == "error":
            return report

        llm = get_llm_client()
        prompt = (
            "You are an intelligent Google Drive assistant. "
            "Based on the following Drive health report, provide 3–5 actionable insights "
            "to help the user better organize and manage their Drive storage.\n\n"
            f"{report['report_markdown']}"
        )
        insights = llm.generate(prompt)
        return {
            "status": "success",
            "insights": insights,
            "report": report["report_markdown"],
        }
    except Exception as e:
        logger.error("get_usage_insights error: %s", e)
        return {"status": "error", "message": str(e)}
