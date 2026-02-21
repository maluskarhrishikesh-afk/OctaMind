"""
Result formatters for the Drive Agent UI.

format_drive_result() — top-level dispatcher for all drive actions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("drive_agent")


def format_drive_result(result: Dict[str, Any], action: str) -> str:
    """Format a Drive operation result dict for display in the chat window."""
    if result.get("status") == "error":
        return f"❌ Error: {result.get('message', 'Unknown error')}"

    reasoning_note = ""
    if result.get("reasoning"):
        reasoning_note = f"\n\n💡 *{result.get('reasoning')}*"

    # ── Phase 1 — Core ops ────────────────────────────────────────────────────

    if action == "list_files":
        files = result.get("files", [])
        count = len(files)
        if count == 0:
            return "📂 No files found." + reasoning_note
        out = f"📂 **{count}** file(s) found:\n\n"
        for f in files[:20]:
            icon = "📁" if "folder" in f.get("mimeType", "") else "📄"
            size = f.get("size_human", "")
            size_str = f" — {size}" if size and size != "—" else ""
            out += f"{icon} **{f['name']}**{size_str}\n"
            out += f"   🆔 `{f['id']}`"
            if f.get("webViewLink"):
                out += f"  🔗 [Open]({f['webViewLink']})"
            out += "\n\n"
        if count > 20:
            out += f"*... and {count - 20} more. Use a narrower search to see all.*\n"
        return out + reasoning_note

    elif action == "search_files":
        files = result.get("files", [])
        count = len(files)
        query = result.get("query", "")
        if count == 0:
            return f"🔍 No files found matching `{query}`." + reasoning_note
        out = f"🔍 **{count}** result(s) for `{query}`:\n\n"
        for f in files[:20]:
            icon = "📁" if "folder" in f.get("mimeType", "") else "📄"
            out += f"{icon} **{f['name']}**\n"
            out += f"   🆔 `{f['id']}`"
            if f.get("webViewLink"):
                out += f"  🔗 [Open]({f['webViewLink']})"
            out += "\n\n"
        return out + reasoning_note

    elif action == "upload":
        f = result.get("file", {})
        return (
            f"✅ **Upload successful!**\n\n"
            f"**Name:** {f.get('name', 'N/A')}\n"
            f"**ID:** `{f.get('id', 'N/A')}`\n"
            f"**Size:** {f.get('size_human', '—')}\n"
            + (f"🔗 [Open in Drive]({f['webViewLink']})\n" if f.get("webViewLink") else "")
            + reasoning_note
        )

    elif action == "download":
        return (
            f"✅ **Download complete!**\n\n"
            f"**File:** {result.get('file_name', 'N/A')}\n"
            f"**Saved to:** `{result.get('local_path', 'N/A')}`\n"
            f"**Size:** {result.get('size_human', '—')}\n"
        ) + reasoning_note

    elif action == "create_folder":
        folder = result.get("folder", {})
        return (
            f"✅ **Folder created!**\n\n"
            f"**Name:** {folder.get('name', 'N/A')}\n"
            f"**ID:** `{folder.get('id', 'N/A')}`\n"
            + (f"🔗 [Open]({folder['webViewLink']})\n" if folder.get("webViewLink") else "")
            + reasoning_note
        )

    elif action == "move":
        f = result.get("file", {})
        return (
            f"✅ **File moved!**\n\n"
            f"**Name:** {f.get('name', 'N/A')}\n"
            f"**ID:** `{f.get('id', 'N/A')}`\n"
        ) + reasoning_note

    elif action == "copy":
        f = result.get("file", {})
        return (
            f"✅ **File copied!**\n\n"
            f"**New ID:** `{f.get('id', 'N/A')}`\n"
            f"**Name:** {f.get('name', 'N/A')}\n"
        ) + reasoning_note

    elif action in ("trash", "restore"):
        verb = "🗑️ File moved to trash" if action == "trash" else "♻️ File restored from trash"
        return f"{verb}\n\n**ID:** `{result.get('file_id', 'N/A')}`" + reasoning_note

    elif action in ("starred", "unstarred"):
        verb = "⭐ File starred" if action == "starred" else "☆ File un-starred"
        return f"{verb}\n\n**ID:** `{result.get('file_id', 'N/A')}`" + reasoning_note

    elif action == "storage_quota":
        return (
            f"💾 **Drive Storage**\n\n"
            f"**Used:** {result.get('used_human', '—')}\n"
            f"**Free:** {result.get('free_human', 'Unlimited')}\n"
            f"**Limit:** {result.get('limit_human', 'Unlimited')}\n"
        ) + reasoning_note

    elif action == "file_info":
        f = result.get("file", {})
        return (
            f"📄 **{f.get('name', 'N/A')}**\n\n"
            f"**ID:** `{f.get('id', 'N/A')}`\n"
            f"**Type:** {f.get('mimeType', '—')}\n"
            f"**Size:** {f.get('size_human', '—')}\n"
            f"**Modified:** {f.get('modifiedTime', '—')}\n"
            + (f"🔗 [Open]({f['webViewLink']})\n" if f.get("webViewLink") else "")
            + reasoning_note
        )

    # ── Phase 2 — Sharing ─────────────────────────────────────────────────────

    elif action == "share":
        p = result.get("permission", {})
        return (
            f"✅ **Shared with {result.get('shared_with', 'N/A')}**\n\n"
            f"**Role:** {result.get('role', '—')}\n"
            f"**Permission ID:** `{p.get('id', 'N/A')}`\n"
        ) + reasoning_note

    elif action == "list_permissions":
        perms = result.get("permissions", [])
        if not perms:
            return "🔒 No permissions found (file is private)." + reasoning_note
        out = f"🔓 **{len(perms)} permission(s):**\n\n"
        for p in perms:
            out += f"- **{p.get('displayName') or p.get('emailAddress') or p.get('domain', '—')}** — `{p.get('role', '—')}`\n"
        return out + reasoning_note

    elif action == "make_public":
        return (
            f"🌍 **File is now public (anyone with link)**\n\n"
            f"🔗 {result.get('link', 'N/A')}\n"
        ) + reasoning_note

    elif action == "remove_public":
        return f"🔒 **Public access removed** ({result.get('revoked_count', 0)} permission(s) revoked)" + reasoning_note

    # ── Phase 3 — Smart features ──────────────────────────────────────────────

    elif action == "summarize_file":
        return (
            f"📝 **Summary: {result.get('file_name', 'N/A')}**\n\n"
            f"{result.get('summary', '—')}\n"
        ) + reasoning_note

    elif action == "summarize_folder":
        return result.get("summary", "No summary available.") + reasoning_note

    elif action == "find_duplicates":
        groups = result.get("duplicate_groups", [])
        if not groups:
            return f"✅ No duplicates found! (scanned {result.get('files_scanned', 0)} files)" + reasoning_note
        out = (
            f"🔁 Found **{result.get('group_count', 0)} duplicate group(s)** "
            f"({result.get('total_duplicates', 0)} redundant files):\n\n"
        )
        for g in groups[:10]:
            out += f"- **{g['name']}** × {g['count']} copies\n"
        return out + reasoning_note

    elif action == "trash_duplicates":
        mode = "*(dry run — no files were deleted)*" if result.get("dry_run") else ""
        return (
            f"🗑️ **Duplicate cleanup** {mode}\n\n"
            f"**Trashed:** {result.get('trashed_count', 0)} file(s)\n"
        ) + reasoning_note

    elif action == "suggest_organization":
        return result.get("suggestion_text", "No suggestions available.") + reasoning_note

    elif action == "auto_organize":
        mode = "*(dry run)*" if result.get("dry_run") else ""
        return (
            f"📂 **Auto-organize complete** {mode}\n\n"
            f"**Files moved:** {result.get('moved_count', 0)}\n"
        ) + reasoning_note

    elif action == "bulk_rename":
        mode = "*(dry run)*" if result.get("dry_run") else ""
        renames = result.get("renames", [])
        out = f"✏️ **Bulk rename** {mode} — **{len(renames)}** file(s):\n\n"
        for r in renames[:10]:
            out += f"- `{r['old']}` → `{r['new']}`\n"
        return out + reasoning_note

    elif action == "list_versions":
        revs = result.get("revisions", [])
        out = (
            f"🕐 **{result.get('file_name', 'N/A')}** — "
            f"**{len(revs)} revision(s)**:\n\n"
        )
        for r in revs[-10:]:
            out += f"- `{r.get('id')}` — {r.get('modifiedTime', '—')}"
            if r.get("keepForever"):
                out += " 📌 pinned"
            out += "\n"
        return out + reasoning_note

    # ── Phase 4 — Analytics ───────────────────────────────────────────────────

    elif action == "storage_breakdown":
        return (
            f"📊 **Storage Breakdown** (scanned {result.get('total_files', 0):,} files)\n\n"
            + "\n".join(
                f"- **{b['type']}:** {b['count']:,} files — {b['size_human']}"
                for b in result.get("breakdown", [])[:10]
            )
            + f"\n\n**Total:** {result.get('total_size_human', '—')}"
            + reasoning_note
        )

    elif action == "list_large_files":
        files = result.get("files", [])
        if not files:
            return f"✅ No files larger than {result.get('min_size_mb', 50)} MB found." + reasoning_note
        out = f"📦 **{len(files)} large file(s)** (> {result.get('min_size_mb', '?')} MB):\n\n"
        for f in files:
            out += f"- **{f['name']}** — {f.get('size_human', '—')}\n"
        return out + reasoning_note

    elif action == "list_old_files":
        files = result.get("files", [])
        if not files:
            return f"✅ No files older than {result.get('older_than_days', 365)} days found." + reasoning_note
        out = f"🕰️ **{len(files)} stale file(s)** (not modified in {result.get('older_than_days', '?')} days):\n\n"
        for f in files[:10]:
            out += f"- {f['name']} — last modified {f.get('modifiedTime', '—')}\n"
        return out + reasoning_note

    elif action == "sharing_report":
        return (
            f"🔗 **Sharing Audit**\n\n"
            f"- **Total files:** {result.get('total_files', 0):,}\n"
            f"- **Shared:** {result.get('shared_count', 0):,}\n"
            f"- **Private:** {result.get('private_count', 0):,}\n"
        ) + reasoning_note

    elif action == "drive_report":
        return result.get("report_markdown", "Report unavailable.") + reasoning_note

    elif action == "usage_insights":
        return (
            f"💡 **Drive Usage Insights**\n\n"
            f"{result.get('insights', '—')}\n"
        ) + reasoning_note

    # ── Fallback ──────────────────────────────────────────────────────────────
    return f"✅ Operation `{action}` completed." + reasoning_note
