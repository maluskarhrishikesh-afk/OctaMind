"""
OctaMind Agent Hub — main Streamlit entry point.
"""
from __future__ import annotations

import logging

import streamlit as st

from src.agent.core.process_manager import cleanup_stale, get_agent_status
from src.agent.core.agent_manager import get_agent_manager

from .helpers import _logo_b64, _logo_icon
from .styles import inject_css
from .create_form import show_create_agent_form
from .agent_card import show_agent_card
from .configure_panel import show_configure_panel

logger = logging.getLogger("octamind.dashboard")

# ---------------------------------------------------------------------------
# One-time application startup (runs once per Streamlit worker process).
# A module-level flag ensures this block does NOT re-execute on every
# Streamlit hot-reload / page interaction.
# ---------------------------------------------------------------------------
_APP_INITIALIZED: bool = False


def _startup() -> None:
    """
    Bootstrap tasks that must run exactly once when the app process starts:
      1. Ensure __multi_agent__ memory files exist (creates them if absent).
      2. Start the global consolidation background thread.
    """
    global _APP_INITIALIZED
    if _APP_INITIALIZED:
        return
    _APP_INITIALIZED = True

    # 1 — Ensure multi-agent memory is ready from the very first launch
    try:
        from src.agent.memory.agent_memory import get_agent_memory, MULTI_AGENT_ID
        get_agent_memory(MULTI_AGENT_ID)   # triggers _ensure_memory_files_exist()
        logger.info("[startup] Multi-agent memory initialised.")
    except Exception as exc:
        logger.error(f"[startup] Failed to init multi-agent memory: {exc}")

    # 2 — Start the 24-hour consolidation background thread
    try:
        from src.agent.memory.consolidation_runner import get_consolidation_runner
        runner = get_consolidation_runner()
        runner.start()
        logger.info("[startup] ConsolidationRunner started.")
    except Exception as exc:
        logger.error(f"[startup] Failed to start ConsolidationRunner: {exc}")


_startup()   # execute at import time (once per process)


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

    # ── Multi-Agent Hub — always-visible system agent card ───────────────────
    st.markdown("---")
    try:
        from src.agent.core.process_manager import start_agent, stop_agent
        ma_status = get_agent_status("__multi_agent__")
        is_ma_running = ma_status is not None

        bg = ("linear-gradient(135deg, #1a1a2e 0%, #1e0a3c 100%)"
              if is_ma_running
              else "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)")
        glow = ("0 0 24px rgba(124,58,237,0.5)" if is_ma_running
                else "0 4px 16px rgba(0,0,0,0.25)")
        status_badge = "🟢 Running" if is_ma_running else "⚫ Stopped"
        status_color = "#28a745" if is_ma_running else "#a855f7"

        st.markdown(
            f"""
            <div style="background:{bg};padding:22px;border-radius:14px;
                        border:1.5px solid rgba(124,58,237,0.5);
                        margin-bottom:16px;box-shadow:{glow};
                        position:relative;overflow:hidden;">
              <div style="position:absolute;top:0;right:0;width:120px;height:120px;
                          background:radial-gradient(circle,rgba(124,58,237,0.15) 0%,transparent 70%);
                          border-radius:50%;"></div>
              <div style="position:relative;z-index:1;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                  <div style="font-size:1.7rem;font-weight:800;
                              background:linear-gradient(135deg,#a78bfa 0%,#7c3aed 100%);
                              -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                              background-clip:text;">
                    ⚡ Multi-Agent Hub
                  </div>
                  <div style="background:{status_color};color:white;padding:5px 14px;
                              border-radius:20px;font-size:0.8rem;font-weight:600;
                              box-shadow:0 2px 8px rgba(0,0,0,0.3);">
                    {status_badge}
                  </div>
                </div>
                <div style="color:#c4b5fd;font-size:0.92rem;line-height:1.6;margin-bottom:10px;">
                  Orchestrate Drive + Email in a single command — auto-planned, step-by-step execution.
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                  <span style="background:rgba(124,58,237,0.2);color:#a78bfa;
                               padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;">
                    🧠 Collective Consciousness
                  </span>
                  <span style="background:rgba(124,58,237,0.2);color:#a78bfa;
                               padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;">
                    ⚡ Cross-Agent Workflows
                  </span>
                  <span style="background:rgba(124,58,237,0.2);color:#a78bfa;
                               padding:3px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;">
                    🔀 Auto-Routing
                  </span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if is_ma_running:
            ma_url = ma_status.get("url", "")
            st.markdown(
                f"""
                <div style="background:rgba(40,167,69,0.08);border:1px solid rgba(40,167,69,0.3);
                            padding:10px 16px;border-radius:10px;margin-bottom:12px;">
                  <span style="color:#28a745;font-weight:600;">
                    ✅ Running on port {ma_status.get('port', '?')}
                  </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if ma_url:
                    st.link_button("🚀 Open Multi-Agent Chat", url=ma_url,
                                   type="primary", use_container_width=True)
            with col_b:
                if st.button("⏹️ Stop Hub", key="stop_multi_agent",
                             use_container_width=True):
                    with st.spinner("Stopping Multi-Agent Hub…"):
                        stop_agent("__multi_agent__")
                    st.rerun()
        else:
            if st.button("▶️ Start Multi-Agent Hub", key="start_multi_agent",
                         type="primary", use_container_width=True):
                with st.spinner("🚀 Launching Multi-Agent Hub…"):
                    try:
                        info = start_agent(
                            "__multi_agent__", "Multi-Agent Hub", "multi_agent")
                        st.success(f"✅ Started on port {info['port']}")
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Could not start Multi-Agent Hub: {_e}")
    except Exception:
        pass  # Dashboard still works even if process_manager is unavailable


if __name__ == "__main__":
    main()
