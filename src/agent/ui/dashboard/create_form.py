"""
Agent-creation form component — compact, clean, skill-focused.
"""
from __future__ import annotations

import streamlit as st

from src.agent.core.agent_manager import get_agent_manager


def show_create_agent_form() -> None:
    """Display the create-new-agent/skill form."""
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,rgba(233,30,140,0.10) 0%,rgba(99,102,241,0.07) 100%);
                   border:1px solid rgba(233,30,140,0.25);padding:20px 24px 16px;border-radius:14px;
                   margin-bottom:20px;">
            <div style="font-size:1.4rem;font-weight:800;color:#e91e8c;margin-bottom:4px;">✨ Add New Skill</div>
            <div style="color:#64748b;font-size:0.88rem;">
                Skills are specialised tools your Personal Assistants can use.
                They have no memory of their own — all context and history lives at the Assistant level.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    manager = get_agent_manager()
    agent_types = manager.get_agent_types()

    # Agent type selector
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.75rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:0.08em;margin-bottom:10px;'>SKILL TYPE</p>",
        unsafe_allow_html=True,
    )

    if "create_selected_type" not in st.session_state:
        st.session_state.create_selected_type = list(agent_types.keys())[0]

    _CHANNEL_TYPES = {"telegram", "whatsapp"}
    _skill_types = [(k, v) for k, v in agent_types.items() if k not in _CHANNEL_TYPES]

    # Compact 4-column grid of skill type cards
    type_cols = st.columns(4)
    for idx, (type_key, type_info) in enumerate(_skill_types):
        with type_cols[idx % 4]:
            is_sel = st.session_state.create_selected_type == type_key
            bg = "rgba(233,30,140,0.14)" if is_sel else "rgba(255,255,255,0.03)"
            border = "rgba(233,30,140,0.7)" if is_sel else "rgba(255,255,255,0.08)"
            name_col = "#f472b6" if is_sel else "#94a3b8"
            st.markdown(
                f"""
                <div style="background:{bg};border:1.5px solid {border};border-radius:10px;
                            padding:10px 10px 8px;text-align:center;margin-bottom:6px;">
                    <div style="font-size:1.5rem;line-height:1;margin-bottom:4px;">{type_info['icon']}</div>
                    <div style="font-weight:700;color:{name_col};font-size:0.78rem;">{type_info['name']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            btn_label = "✓" if is_sel else "Select"
            if st.button(btn_label, key=f"atype_{type_key}", use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state.create_selected_type = type_key
                st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    with st.form("create_agent_form"):
        st.markdown(
            "<p style='color:#94a3b8;font-size:0.75rem;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.08em;margin-bottom:6px;'>SKILL NAME</p>",
            unsafe_allow_html=True,
        )
        name = st.text_input(
            "Skill Name",
            placeholder="e.g., My Email Assistant",
            label_visibility="collapsed",
        )

        st.markdown(
            "<p style='color:#94a3b8;font-size:0.75rem;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.08em;margin:14px 0 6px 0;'>PURPOSE / ROLE</p>",
            unsafe_allow_html=True,
        )
        role = st.text_area(
            "Role / Purpose",
            placeholder="Describe what you want this skill to do...",
            height=90,
            label_visibility="collapsed",
        )

        with st.expander("Settings (Optional)", expanded=False):
            auto_run = st.checkbox("Auto-run on startup", value=False)
            max_operations = st.number_input(
                "Max operations per command",
                min_value=1, max_value=1000, value=100,
            )
            st.caption(
                "Safety guard limits how many API calls this skill can make per command. Default: 100."
            )

        col1, col2 = st.columns([3, 1])
        with col1:
            submitted = st.form_submit_button("✨ Create Skill", type="primary", use_container_width=True)
        with col2:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)

        if cancelled:
            st.session_state.show_create_form = False
            st.rerun()

        if submitted:
            selected_type = st.session_state.get("create_selected_type", "")
            if not name:
                st.error("Please provide a name.")
            elif not selected_type:
                st.error("Please select a skill type.")
            elif not role:
                st.error("Please describe the skill's purpose.")
            else:
                try:
                    agent = manager.create_agent(
                        name=name,
                        agent_type=selected_type,
                        role=role,
                        config={"auto_run": auto_run, "max_operations": max_operations},
                    )
                    st.success(f"Skill {agent['name']} created!")
                    st.session_state.show_create_form = False
                    st.session_state.create_selected_type = list(agent_types.keys())[0]
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
