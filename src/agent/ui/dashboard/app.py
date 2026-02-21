"""
OctaMind Agent Hub — main Streamlit entry point.
"""
from __future__ import annotations

import streamlit as st

from src.agent.core.process_manager import cleanup_stale, get_agent_status
from src.agent.core.agent_manager import get_agent_manager

from .helpers import _logo_b64, _logo_icon
from .styles import inject_css
from .create_form import show_create_agent_form
from .agent_card import show_agent_card
from .configure_panel import show_configure_panel


def main() -> None:
    st.set_page_config(
        page_title="OctaMind — Agent Hub",
        page_icon=_logo_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_css()

    # Garbage-collect terminated processes on each load
    cleanup_stale()

    if "show_create_form" not in st.session_state:
        st.session_state.show_create_form = False
    if "configure_agent_id" not in st.session_state:
        st.session_state.configure_agent_id = None

    manager = get_agent_manager()
    agents = manager.list_agents()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            "<div style='font-size:0.95rem;font-weight:700;color:#e91e8c;margin-bottom:16px;padding-bottom:10px;border-bottom:1.5px solid rgba(233,30,140,0.4);'>📊 Overview</div>",
            unsafe_allow_html=True,
        )

        running_count = sum(
            1 for a in agents if get_agent_status(a["id"]) is not None)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg, rgba(233,30,140,0.08) 0%, rgba(156,39,176,0.05) 100%);
                           border:1px solid rgba(233,30,140,0.3);padding:12px;border-radius:10px;text-align:center;">
                    <div style="font-size:2rem;font-weight:900;color:#e91e8c;line-height:1;">{len(agents)}</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Total Agents</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg, rgba(40,167,69,0.08) 0%, rgba(76,175,80,0.05) 100%);
                           border:1px solid rgba(40,167,69,0.3);padding:12px;border-radius:10px;text-align:center;">
                    <div style="font-size:2rem;font-weight:900;color:#28a745;line-height:1;">{running_count}</div>
                    <div style="font-size:0.75rem;color:#888;margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Running</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()

        if st.button("➕ Create New Agent", use_container_width=True, type="primary"):
            st.session_state.show_create_form = True
            st.rerun()

        st.divider()
        st.markdown(
            "<p style='font-size:0.8rem;color:#a8dadc;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin:16px 0 12px 0;'>🎯 Agent Types</p>",
            unsafe_allow_html=True,
        )
        for type_key, type_info in manager.get_agent_types().items():
            count = sum(1 for a in agents if a["type"] == type_key)
            st.markdown(
                f"""
                <div style="padding:8px 12px;background:rgba(233,30,140,0.05);border-radius:8px;margin-bottom:8px;
                           border-left:3px solid #e91e8c;font-size:0.9rem;">
                    {type_info['icon']} <strong>{type_info['name']}</strong><br>
                    <span style="color:#888;font-size:0.8rem;">{count} agent(s)</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()
        st.caption(
            "💡 Each agent runs in its own Streamlit window. Dashboard stays live.")

    # ── Main area ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(233,30,140,0.15) 0%, rgba(156,39,176,0.1) 100%);
                    border:1px solid rgba(233,30,140,0.3);padding:32px 28px;border-radius:16px;
                    margin-bottom:32px;backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(233,30,140,0.15);">
            <div style="display:flex;align-items:center;gap:20px;margin-bottom:12px;">
              <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:16px;object-fit:cover;
                                              box-shadow:0 4px 16px rgba(233,30,140,0.4);">
              <div>
                <div style="font-size:2.6rem;font-weight:900;background:linear-gradient(135deg, #e91e8c 0%, #a8dadc 100%);
                           -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
                           line-height:1.1;">OctaMind</div>
                <div style="font-size:1.05rem;color:#a8dadc;margin-top:6px;font-weight:500;">
                  Multi-Agent AI Platform
                </div>
              </div>
            </div>
            <div style="color:#b0b0b0;font-size:0.95rem;margin-top:8px;">
              Create, start, and orchestrate your specialized AI agents from one unified hub.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.show_create_form:
        show_create_agent_form()
        return

    # Show configure panel if an agent is being configured
    cfg_id = st.session_state.get("configure_agent_id")
    if cfg_id:
        cfg_agent = next((a for a in agents if a["id"] == cfg_id), None)
        if cfg_agent:
            show_configure_panel(cfg_agent)
            st.divider()

    if not agents:
        st.markdown(
            """
            <div style="background:linear-gradient(135deg, rgba(233,30,140,0.1) 0%, rgba(156,39,176,0.05) 100%);
                       border:1px solid rgba(233,30,140,0.2);padding:40px 32px;border-radius:16px;
                       text-align:center;margin:32px 0;">
                <div style="font-size:3rem;margin-bottom:16px;">👋</div>
                <div style="font-size:1.6rem;font-weight:700;color:#e91e8c;margin-bottom:12px;">
                  Welcome to OctaMind!
                </div>
                <div style="font-size:1rem;color:#a8dadc;margin-bottom:8px;">
                  You don't have any agents yet. Let's create your first one!
                </div>
                <div style="color:#888;font-size:0.95rem;margin-top:20px;">
                  Available Agent Types:
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        cols = st.columns(3)
        agent_types = manager.get_agent_types()
        for idx, (key, info) in enumerate(agent_types.items()):
            with cols[idx % 3]:
                st.markdown(
                    f"""
                    <div style="background:rgba(233,30,140,0.08);border:1px solid rgba(233,30,140,0.2);
                               padding:20px 16px;border-radius:12px;text-align:center;">
                        <div style="font-size:2.5rem;margin-bottom:10px;">{info['icon']}</div>
                        <div style="font-weight:700;color:#e91e8c;margin-bottom:6px;">{info['name']}</div>
                        <div style="font-size:0.85rem;color:#888;">{info['description']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("✨ Create Your First Agent", type="primary", use_container_width=True):
                st.session_state.show_create_form = True
                st.rerun()
        return

    # ── Search / filter ───────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;margin:28px 0 18px 0;'>📋 Your Agents</div>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search = st.text_input(
            "🔍 Search agents",
            placeholder="Search by name or type...",
            label_visibility="collapsed"
        )
    with col2:
        filter_type = st.selectbox(
            "Filter by type",
            ["All"] + list(manager.get_agent_types().keys()),
            label_visibility="collapsed"
        )
    with col3:
        filter_status = st.selectbox(
            "Filter by status",
            ["All", "Running", "Stopped"],
            label_visibility="collapsed"
        )

    filtered = agents
    if search:
        filtered = [a for a in filtered
                    if search.lower() in a["name"].lower()
                    or search.lower() in a["type"].lower()]
    if filter_type != "All":
        filtered = [a for a in filtered if a["type"] == filter_type]
    if filter_status == "Running":
        filtered = [a for a in filtered if get_agent_status(
            a["id"]) is not None]
    elif filter_status == "Stopped":
        filtered = [a for a in filtered if get_agent_status(a["id"]) is None]

    st.markdown(
        f"<div style='color:#888;font-size:0.9rem;margin:20px 0 24px 0;'>Showing {len(filtered)} of {len(agents)} agent(s)</div>",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.markdown(
            """
            <div style="background:rgba(255, 107, 107, 0.1);border:1px solid rgba(255, 107, 107, 0.2);
                       padding:20px;border-radius:12px;text-align:center;">
                <div style="color:#ff6b6b;font-weight:600;">⚠️ No agents match your filters</div>
                <div style="color:#888;font-size:0.9rem;margin-top:6px;">
                  Try adjusting your search terms or filters.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    cols = st.columns(2)
    for idx, agent in enumerate(filtered):
        with cols[idx % 2]:
            show_agent_card(agent)


if __name__ == "__main__":
    main()
