"""
Agent-creation form component.
"""
from __future__ import annotations

import streamlit as st

from src.agent.core.agent_manager import get_agent_manager


def show_create_agent_form() -> None:
    """Display the create-new-agent form."""
    st.markdown(
        """
        <div style="background:linear-gradient(135deg, rgba(233,30,140,0.15) 0%, rgba(156,39,176,0.1) 100%);
                   border:1px solid rgba(233,30,140,0.3);padding:28px 28px 22px;border-radius:16px;
                   margin-bottom:24px;box-shadow:0 8px 32px rgba(233,30,140,0.15);">
            <div style="font-size:1.7rem;font-weight:800;color:#e91e8c;margin-bottom:6px;">✨ Create New Agent</div>
            <div style="color:#a8dadc;font-size:0.92rem;">
              Set up a new specialized AI agent with custom role and configuration.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    manager = get_agent_manager()
    agent_types = manager.get_agent_types()

    # ── Agent type selector — outside the form so buttons work ──────────────
    st.markdown(
        "<p style='color:#e91e8c;font-weight:700;font-size:1rem;margin-bottom:14px;'>Agent Type</p>",
        unsafe_allow_html=True,
    )

    if "create_selected_type" not in st.session_state:
        st.session_state.create_selected_type = list(agent_types.keys())[0]

    type_cols = st.columns(3)
    for idx, (type_key, type_info) in enumerate(agent_types.items()):
        with type_cols[idx % 3]:
            is_sel = st.session_state.create_selected_type == type_key
            card_bg = "rgba(233,30,140,0.18)" if is_sel else "rgba(255,255,255,0.04)"
            card_border = "#e91e8c" if is_sel else "rgba(233,30,140,0.2)"
            name_color = "#e91e8c" if is_sel else "#e0e0e0"
            card_shadow = "0 0 20px rgba(233,30,140,0.28)" if is_sel else "none"
            st.markdown(
                f"""
                <div style="background:{card_bg};border:2px solid {card_border};border-radius:14px;
                            padding:20px 14px 14px;text-align:center;
                            box-shadow:{card_shadow};transition:all 0.2s ease;margin-bottom:8px;">
                    <div style="font-size:2.2rem;margin-bottom:8px;line-height:1;">{type_info['icon']}</div>
                    <div style="font-weight:700;color:{name_color};font-size:0.92rem;margin-bottom:6px;">{type_info['name']}</div>
                    <div style="font-size:0.75rem;color:#999;line-height:1.45;">{type_info['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            btn_label = "✓ Selected" if is_sel else "Select"
            if st.button(btn_label, key=f"atype_{type_key}", use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state.create_selected_type = type_key
                st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── Rest of the form ─────────────────────────────────────────────────────
    with st.form("create_agent_form"):
        st.markdown(
            "<p style='color:#e91e8c;font-weight:700;margin-bottom:8px;'>Agent Name</p>",
            unsafe_allow_html=True,
        )
        name = st.text_input(
            "Agent Name",
            placeholder="e.g., My Email Assistant",
            help="Give your agent a friendly name",
            label_visibility="collapsed",
        )

        st.markdown(
            "<p style='color:#e91e8c;font-weight:700;margin-bottom:8px;margin-top:16px;'>Role / Purpose</p>",
            unsafe_allow_html=True,
        )
        role = st.text_area(
            "Role / Purpose",
            placeholder="Describe what you want this agent to do...",
            height=100,
            label_visibility="collapsed",
        )

        st.markdown(
            "<p style='color:#e91e8c;font-weight:700;margin-bottom:4px;margin-top:16px;'>\U0001f3ad Personality Traits</p>",
            unsafe_allow_html=True,
        )
        with st.expander("Define personality \u2014 optional (sensible defaults pre-filled)", expanded=False):
            st.markdown(
                "<p style='color:#a0a0a0;font-size:0.82rem;margin-bottom:12px;'>Each slider goes from 0 (left extreme) to 10 (right extreme). The agent\u2019s communication style reflects these values.</p>",
                unsafe_allow_html=True,
            )
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                p_tone = st.slider(
                    "Tone  \u2014  Formal \u2194 Casual",         0, 10, 3, key="cp_tone")
                p_verbosity = st.slider(
                    "Verbosity  \u2014  Brief \u2194 Detailed",    0, 10, 5, key="cp_verbosity")
                p_humor = st.slider(
                    "Humor  \u2014  Serious \u2194 Witty",        0, 10, 2, key="cp_humor")
            with pcol2:
                p_empathy = st.slider(
                    "Empathy  \u2014  Neutral \u2194 Warm",       0, 10, 6, key="cp_empathy")
                p_proactiveness = st.slider(
                    "Proactiveness  \u2014  Reactive \u2194 Proactive", 0, 10, 5, key="cp_proactiveness")

        with st.expander("\u2699\ufe0f Advanced Configuration (Optional)"):
            auto_run = st.checkbox("Auto-run on startup", value=False)
            max_operations = st.number_input(
                "Max operations per command", min_value=1, max_value=1000, value=100,
            )
            st.caption(
                "\U0001f6e1\ufe0f **Safety guard** \u2014 limits how many individual Gmail API calls this agent "
                "can make when processing a single command. Prevents runaway operations "
                "(e.g. \"delete all emails\") from touching thousands of messages at once. "
                "Default: **100**. You can change this later in \u2699\ufe0f Configure \u2192 General Settings."
            )

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            submitted = st.form_submit_button(
                "✨ Create Agent", type="primary", use_container_width=True)
        with col2:
            cancelled = st.form_submit_button(
                "Cancel", use_container_width=True)

        if cancelled:
            st.session_state.show_create_form = False
            st.rerun()

        if submitted:
            selected_type = st.session_state.get("create_selected_type", "")
            if not name:
                st.error("❌ Please provide a name.")
            elif not selected_type:
                st.error("❌ Please select an agent type.")
            elif not role:
                st.error("❌ Please describe the agent's role.")
            else:
                try:
                    personality_traits = {
                        "tone":          st.session_state.get("cp_tone", 3),
                        "verbosity":     st.session_state.get("cp_verbosity", 5),
                        "humor":         st.session_state.get("cp_humor", 2),
                        "empathy":       st.session_state.get("cp_empathy", 6),
                        "proactiveness": st.session_state.get("cp_proactiveness", 5),
                    }
                    agent = manager.create_agent(
                        name=name,
                        agent_type=selected_type,
                        role=role,
                        config={"auto_run": auto_run,
                                "max_operations": max_operations},
                        personality_traits=personality_traits,
                    )
                    st.success(f"✨ {agent['name']} created successfully!")
                    st.session_state.show_create_form = False
                    st.session_state.create_selected_type = list(agent_types.keys())[
                        0]
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
