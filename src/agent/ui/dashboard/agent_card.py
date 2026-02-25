"""
Agent card component — compact chip tile for a single Skill with Configure and Delete controls.
Skills are stateless executors with no memory of their own.
"""
from __future__ import annotations

import streamlit as st

from src.agent.core.agent_manager import get_agent_manager

# Plain-language abilities per agent type — shown in the hover tooltip
_SKILL_ABILITIES: dict[str, list[str]] = {
    "gmail": [
        "📨 Read, search & send emails",
        "🔗 Smart labels & auto-sort",
        "⏰ Schedule emails for later",
        "✅ Extract to-dos from threads",
        "⚠️ Detect urgent & unread mail",
    ],
    "google_drive": [
        "📄 Browse, upload & download files",
        "🔗 Share files with anyone",
        "🔍 Find & remove duplicates",
        "📂 Auto-organise folders",
        "📊 Storage reports & analytics",
    ],
    "files": [
        "🖥️ Browse & search your computer",
        "📈 Copy, move, zip & unzip",
        "🔍 Find duplicate files",
        "🖼️ Sort by type or date",
        "💾 Check disk usage & large files",
    ],
    "whatsapp": [
        "💬 Send & read messages",
        "⏰ Schedule messages for later",
        "🤖 Set up auto-replies",
        "👥 Manage & search contacts",
        "📝 Summarise long conversations",
    ],
    "telegram": [
        "📨 Send & receive messages",
        "⏰ Schedule messages for later",
        "📊 Create polls & pin messages",
        "📖 Summarise chats",
        "📤 Forward messages to email",
    ],
    "calendar": [
        "📅 View daily & weekly agenda",
        "✏️ Create, update & delete events",
        "🔍 Find free time slots",
        "🔔 Set reminders & recurring events",
        "⚠️ Detect scheduling conflicts",
    ],
    "scheduler": [
        "🧠 Find optimal meeting time slots",
        "🛡️ Protect deep-work / focus blocks",
        "⚡ Smart conflict resolution",
        "📊 Meeting-load & scheduling insights",
        "🔄 Set up recurring focus sessions",
    ],
    "file_organizer": [
        "🔍 Scan folders & propose tidy plans",
        "👁️ Preview every move before applying",
        "✅ Apply plans only on your confirmation",
        "🗄️ Archive old files by age automatically",
        "📋 Set & run archival policies for folders",
    ],
    "habit_tracker": [
        "➕ Add & manage daily habits",
        "✅ Log completions with notes",
        "🔥 Track current & longest streaks",
        "📊 Weekly & 30/60/90-day analytics",
        "📅 Schedule habits on Google Calendar",
    ],
}
_DEFAULT_ABILITIES = [
    "🔧 Custom-configured skill",
    "💬 Handles natural language commands",
    "⚙️ Adapts to your instructions",
]


def show_agent_card(agent: dict) -> None:
    """Render one skill as a compact chip with a hover tooltip."""
    agent_id  = agent["id"]
    icon      = agent["metadata"]["icon"]
    type_name = agent["metadata"]["name"]
    abilities = _SKILL_ABILITIES.get(agent["type"], _DEFAULT_ABILITIES)

    # Build tooltip lines
    tooltip_items = "".join(
        f"<div style='padding:2px 0;font-size:0.72rem;color:#cbd5e1;'>{a}</div>"
        for a in abilities
    )

    # Truncate role text for the chip
    role = agent.get("role", "")
    role_short = (role[:45] + "…") if len(role) > 45 else role

    st.markdown(
        f"""
        <div style="position:relative;display:inline-block;width:100%;" class="oa-skill-chip">
          <!-- chip body -->
          <div style="background:rgba(255,255,255,0.03);padding:10px 12px 8px;
                      border-radius:10px;border:1px solid rgba(233,30,140,0.2);
                      margin-bottom:6px;cursor:default;">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
              <span style="font-size:1.15rem;line-height:1;">{icon}</span>
              <span style="font-size:0.85rem;font-weight:700;color:#e2e8f0;
                           white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{agent['name']}</span>
            </div>
            <div style="font-size:0.68rem;color:#475569;margin-bottom:3px;">{type_name}</div>
            <div style="font-size:0.72rem;color:#64748b;line-height:1.35;
                        display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;
                        overflow:hidden;">{role_short}</div>
            <!-- hover tooltip -->
            <div class="oa-tooltip">
              <div style="font-size:0.72rem;font-weight:700;color:#a5b4fc;
                          margin-bottom:6px;letter-spacing:0.04em;">WHAT THIS SKILL CAN DO</div>
              {tooltip_items}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([3, 1])

    with col1:
        is_configuring = st.session_state.get("configure_agent_id") == agent_id
        cfg_label = "✖ Close" if is_configuring else "⚙️ Configure"
        if st.button(cfg_label, key=f"config_{agent_id}", use_container_width=True):
            if is_configuring:
                st.session_state.configure_agent_id = None
            else:
                st.session_state.configure_agent_id = agent_id
                st.session_state.show_create_form = False
            st.rerun()

    with col2:
        confirm_key = f"delete_confirm_{agent_id}"
        if confirm_key not in st.session_state:
            st.session_state[confirm_key] = False

        if not st.session_state[confirm_key]:
            if st.button("🗑️", key=f"delete_{agent_id}", use_container_width=True,
                         help=f"Delete {agent['name']}"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            if st.button("⚠️ Confirm", key=f"confirm_del_{agent_id}",
                         type="primary", use_container_width=True):
                manager = get_agent_manager()
                manager.delete_agent(agent_id)
                st.session_state[confirm_key] = False
                st.success(f"Deleted {agent['name']}")
                st.rerun()

    if st.session_state.get(confirm_key, False):
        st.caption(f"⚠️ This will permanently delete **{agent['name']}**. Click Confirm above.")
