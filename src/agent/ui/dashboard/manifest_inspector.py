from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from src.files.features.file_ops import (
    delete_file_manifest,
    get_active_file_manifest_metadata,
    list_file_manifests,
    prune_stale_file_manifests,
)


def _format_age(written_at: str) -> str:
    try:
        ts = datetime.fromisoformat(str(written_at or ""))
        now = datetime.now(ts.tzinfo or timezone.utc)
        delta = now - ts
        if delta.days > 0:
            return f"{delta.days}d"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h"
        minutes = delta.seconds // 60
        return f"{minutes}m"
    except Exception:
        return "n/a"


def _manifest_rows(manifests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for manifest in manifests:
        path = Path(str(manifest.get("manifest_path", "") or ""))
        rows.append(
            {
                "manifest_id": str(manifest.get("manifest_id", "") or ""),
                "label": str(manifest.get("label", "") or ""),
                "count": int(manifest.get("count", 0) or 0),
                "age": _format_age(str(manifest.get("written_at", "") or "")),
                "is_active": bool(manifest.get("is_active")),
                "path": str(path),
            }
        )
    return rows


def show_manifest_inspector() -> None:
    st.markdown(
        "<div style='font-size:1.5rem;font-weight:800;color:#e2e8f0;margin:8px 0 6px 0;'>🗂️ Manifest Inspector</div>"
        "<div style='color:#64748b;font-size:0.88rem;margin-bottom:16px;'>Inspect the active file manifest, recent historical manifests, and prune stale entries without touching current follow-up context.</div>",
        unsafe_allow_html=True,
    )

    active = get_active_file_manifest_metadata()
    manifests_result = list_file_manifests(limit=100)
    manifests = manifests_result.get("manifests", []) if manifests_result.get("status") == "success" else []

    active_col, prune_col = st.columns([1.2, 0.8])
    with active_col:
        if active:
            st.markdown(
                f"<div style='background:rgba(15,23,42,0.82);border:1px solid rgba(16,185,129,0.24);border-radius:16px;padding:16px 18px;'>"
                f"<div style='font-size:0.76rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;'>Active File Manifest</div>"
                f"<div style='font-size:1.05rem;font-weight:800;color:#f8fafc;margin-top:8px;'>{active.get('label', active.get('manifest_id', 'active'))}</div>"
                f"<div style='font-size:0.84rem;color:#94a3b8;margin-top:6px;'>Paths: {active.get('count', 0)} · Age: {_format_age(str(active.get('written_at', '') or ''))}</div>"
                f"<div style='font-size:0.78rem;color:#64748b;margin-top:8px;'>{active.get('manifest_path', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No active file manifest is currently set.")

    with prune_col:
        days = st.number_input("Prune inactive manifests older than days", min_value=1, max_value=90, value=7, step=1)
        if st.button("Prune stale manifests", use_container_width=True, type="primary"):
            result = prune_stale_file_manifests(max_age_days=int(days))
            if result.get("status") == "success":
                st.success(result.get("message", "Pruned stale manifests."))
            else:
                st.error(result.get("message", "Manifest pruning failed."))
            st.rerun()

    st.markdown("### Recent File Manifests")
    rows = _manifest_rows(manifests)
    if not rows:
        st.info("No historical file manifests found yet.")
        return

    summary_rows = [
        {
            "Manifest": row["manifest_id"],
            "Label": row["label"],
            "Paths": row["count"],
            "Age": row["age"],
            "Active": "Yes" if row["is_active"] else "No",
            "Path": row["path"],
        }
        for row in rows
    ]
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    st.markdown("### Delete Historical Manifest")
    for row in rows[:20]:
        cols = st.columns([1.5, 2.2, 0.8])
        with cols[0]:
            st.markdown(f"**{row['label'] or row['manifest_id']}**")
            st.caption(f"{row['count']} path(s) · {row['age']}")
        with cols[1]:
            st.caption(row["path"])
        with cols[2]:
            disabled = bool(row["is_active"])
            button_label = "Active" if disabled else "Delete"
            if st.button(button_label, key=f"delete_manifest_{row['manifest_id']}", use_container_width=True, disabled=disabled):
                result = delete_file_manifest(manifest_id=row["manifest_id"])
                if result.get("status") == "success":
                    st.success(result.get("message", "Manifest deleted."))
                else:
                    st.error(result.get("message", "Manifest delete failed."))
                st.rerun()