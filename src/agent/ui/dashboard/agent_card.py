"""
Agent card component — renders a single agent tile with Start/Stop/Configure/Delete controls.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.agent.core.process_manager import start_agent, stop_agent, get_agent_status
from src.agent.core.agent_manager import get_agent_manager


def show_agent_card(agent: dict) -> None:
    """Render one agent card with Start / Stop / Delete controls."""
    agent_id = agent["id"]
    icon = agent["metadata"]["icon"]
    type_name = agent["metadata"]["name"]

    # Check live status
    status_info = get_agent_status(agent_id)
    is_running = status_info is not None

    status_badge = "🟢 Running" if is_running else "⚫ Stopped"
    status_color = "#28a745" if is_running else "#ff6b6b"
    bg_gradient = "linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%)" if is_running else "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)"
    border_glow = "0 0 20px rgba(233,30,140,0.4)" if is_running else "0 4px 15px rgba(0,0,0,0.2)"

    st.markdown(
        f"""
        <div style="background:{bg_gradient};padding:20px;border-radius:14px;border:1px solid rgba(233,30,140,0.3);
                    margin-bottom:16px;box-shadow:{border_glow};transition:all 0.3s ease;
                    position:relative;overflow:hidden;">
            <div style="position:absolute;top:0;right:0;width:100px;height:100px;
                       background:radial-gradient(circle, rgba(233,30,140,0.1) 0%, transparent 70%);
                       border-radius:50%;"></div>
            <div style="position:relative;z-index:1;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
                    <div style="font-size:1.8rem;font-weight:800;color:#e91e8c;">
                        {icon} {agent['name']}
                    </div>
                    <div style="background:{status_color};color:white;padding:6px 14px;border-radius:20px;
                               font-size:0.8rem;font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,0.3);">
                        {status_badge}
                    </div>
                </div>
                <div style="color:#b0b0b0;font-size:0.95rem;line-height:1.6;margin-bottom:14px;">
                    <div><span style="color:#a8dadc;">Type:</span> {type_name}</div>
                    <div><span style="color:#a8dadc;">Role:</span> {agent['role']}</div>
                </div>
                <div style="color:#666;font-size:0.8rem;border-top:1px solid rgba(255,255,255,0.1);padding-top:10px;margin-top:10px;">
                    Created: {datetime.fromisoformat(agent['created_at']).strftime('%b %d, %Y • %H:%M')}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_running:
        url = status_info["url"]
        port = status_info["port"]
        st.markdown(
            f"""
            <div style="background:rgba(40, 167, 69, 0.1);border:1px solid rgba(40, 167, 69, 0.3);
                       padding:12px 16px;border-radius:10px;margin-bottom:14px;">
                <div style="color:#28a745;font-weight:600;margin-bottom:10px;">✅ Agent running on port {port}</div>
                <a href="{url}" target="_blank" style="text-decoration:none;">
                    <div style="background:linear-gradient(135deg, #28a745, #20c997);color:white;padding:10px 18px;
                               border-radius:8px;text-align:center;font-weight:600;box-shadow:0 4px 12px rgba(40, 167, 69, 0.3);
                               transition:all 0.3s ease;cursor:pointer;display:inline-block;width:100%;">
                        🚀 Open {agent["name"]} Window
                    </div>
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        if not is_running:
            if st.button("▶️ Start Agent", key=f"start_{agent_id}",
                         type="primary", use_container_width=True):
                with st.spinner(f"🚀 Starting {agent['name']}..."):
                    try:
                        info = start_agent(
                            agent_id, agent["name"], agent["type"])
                        st.success(f"✅ Started on port {info['port']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to start: {e}")
        else:
            if st.button("⏹️ Stop Agent", key=f"stop_{agent_id}",
                         type="primary", use_container_width=True):
                with st.spinner(f"Stopping {agent['name']}..."):
                    stop_agent(agent_id)
                    st.rerun()

    with col2:
        is_configuring = st.session_state.get("configure_agent_id") == agent_id
        cfg_label = "✖ Close Config" if is_configuring else "⚙️ Configure"
        if st.button(cfg_label, key=f"config_{agent_id}", use_container_width=True):
            if is_configuring:
                st.session_state.configure_agent_id = None
            else:
                st.session_state.configure_agent_id = agent_id
                st.session_state.show_create_form = False
            st.rerun()

    with col3:
        confirm_key = f"delete_confirm_{agent_id}"
        if confirm_key not in st.session_state:
            st.session_state[confirm_key] = False

        if not st.session_state[confirm_key]:
            if st.button("🗑️", key=f"delete_{agent_id}", use_container_width=True):
                if is_running:
                    stop_agent(agent_id)
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            if st.button("⚠️ Confirm Delete?", key=f"confirm_del_{agent_id}",
                         type="primary", use_container_width=True):
                manager = get_agent_manager()
                manager.delete_agent(agent_id)
                st.session_state[confirm_key] = False
                st.success(f"✅ Deleted {agent['name']}")
                st.rerun()

    if st.session_state.get(confirm_key, False):
        st.warning(
            f"⚠️ This will permanently delete **{agent['name']}** and all its memory. "
            "Click 'Confirm Delete?' above, or refresh to cancel."
        )
