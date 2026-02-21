"""
Agent configure panel — personality traits, automations, and general settings tabs.
"""
from __future__ import annotations

import streamlit as st

from src.agent.core.agent_manager import get_agent_manager, DEFAULT_PERSONALITY_TRAITS
from src.agent.core.automations.automation_config import (
    load_automation_config,
    update_automation_state,
    get_automations_for_agent_type,
)

# ── Personality trait metadata ────────────────────────────────────────────────
_TRAIT_META = [
    ("tone",          "\U0001f5e3 Tone",          "Formal",   "Casual"),
    ("verbosity",     "\U0001f4dd Verbosity",      "Brief",    "Detailed"),
    ("humor",         "\U0001f604 Humor",          "Serious",  "Witty"),
    ("empathy",       "\u2764\ufe0f Empathy",      "Neutral",  "Warm"),
    ("proactiveness", "\u26a1 Proactiveness",      "Reactive", "Proactive"),
]


def show_configure_panel(agent: dict) -> None:
    """Full configure panel: personality traits + per-type automations + general settings."""
    agent_id = agent["id"]
    agent_type = agent["type"]
    manager = get_agent_manager()

    # — Header
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(233,30,140,0.15) 0%,rgba(156,39,176,0.1) 100%);
                    border:1px solid rgba(233,30,140,0.3);padding:24px 28px;border-radius:16px;
                    margin-bottom:24px;">
            <div style="font-size:1.6rem;font-weight:800;color:#e91e8c;margin-bottom:4px;">
                \u2699\ufe0f Configure  —  {agent['name']}
            </div>
            <div style="color:#a8dadc;font-size:0.9rem;">
                Adjust personality traits and set up recurring automations.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_personality, tab_automations, tab_general = st.tabs(
        ["\U0001f3ad Personality Traits", "\u2699\ufe0f Automations", "\U0001f527 General Settings"])

    # ── Personality tab ─────────────────────────────────────────────
    with tab_personality:
        st.markdown(
            "<p style='color:#a8dadc;font-size:0.88rem;margin-bottom:16px;'>"
            "These sliders control the agent\u2019s communication style. "
            "0 = left extreme  \u00b7  10 = right extreme. Changes rewrite "
            "<code>personality.md</code> in the agent\u2019s memory.</p>",
            unsafe_allow_html=True,
        )
        current = agent.get("config", {}).get(
            "personality_traits", DEFAULT_PERSONALITY_TRAITS)

        with st.form(f"cfg_personality_{agent_id}"):
            pc1, pc2 = st.columns(2)
            new_traits: dict = {}
            for i, (key, label, lo, hi) in enumerate(_TRAIT_META):
                col = pc1 if i % 2 == 0 else pc2
                with col:
                    st.markdown(
                        f"<p style='color:#e91e8c;font-weight:600;margin-bottom:2px;'>"
                        f"{label}</p>"
                        f"<p style='color:#a0a0a0;font-size:0.75rem;margin-top:0;letter-spacing:0.02em;'>{lo} ← → {hi}</p>",
                        unsafe_allow_html=True,
                    )
                    new_traits[key] = st.slider(
                        label,
                        min_value=0, max_value=10,
                        value=int(current.get(
                            key, DEFAULT_PERSONALITY_TRAITS.get(key, 5))),
                        key=f"cfg_p_{agent_id}_{key}",
                        label_visibility="collapsed",
                    )
            if st.form_submit_button("\U0001f4be Save Personality", type="primary"):
                ok = manager.update_personality_traits(agent_id, new_traits)
                if ok:
                    st.success(
                        "\u2705 Personality updated and written to memory.")
                    st.rerun()
                else:
                    st.error("\u274c Could not update personality.")

    # ── Automations tab ─────────────────────────────────────────────
    with tab_automations:
        catalog = get_automations_for_agent_type(agent_type)
        if not catalog:
            st.info(
                "\U0001f6a7 No automations are available for this agent type yet. "
                "Gmail agents have 10 built-in automations."
            )
            return

        st.markdown(
            "<p style='color:#a8dadc;font-size:0.88rem;margin-bottom:8px;'>"
            "Toggle an automation on to run it in the background while the agent is active. "
            "Changes take effect immediately.</p>",
            unsafe_allow_html=True,
        )

        config = load_automation_config(agent_id)

        for auto_id, auto_info in catalog.items():
            state = config.get(auto_id, {})
            enabled = state.get("enabled", False)
            params = state.get("params", auto_info.get("default_params", {}))

            with st.container():
                st.markdown(
                    f"""
                    <div style="background:{'rgba(40,167,69,0.08)' if enabled else 'rgba(255,255,255,0.03)'};
                               border:1px solid {'rgba(40,167,69,0.3)' if enabled else 'rgba(255,255,255,0.1)'};
                               padding:14px 18px;border-radius:12px;margin-bottom:10px;">
                        <div style="font-size:1rem;font-weight:700;color:{'#28a745' if enabled else '#e91e8c'};">
                            {auto_info['label']}
                        </div>
                        <div style="font-size:0.82rem;color:#888;margin-top:4px;">
                            {auto_info['description']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                new_enabled = st.checkbox(
                    "Enable this automation",
                    value=enabled,
                    key=f"ato_{agent_id}_{auto_id}",
                )
                if new_enabled != enabled:
                    update_automation_state(
                        agent_id, auto_id, new_enabled, params)
                    action_word = "enabled \u2705" if new_enabled else "disabled \u23f9"
                    st.toast(f"{auto_info['label']} {action_word}")
                    st.rerun()

                # ── Frequency + Settings expander ───────────────────────
                _FREQ_OPTIONS: dict = {
                    "30 seconds": 0.5,
                    "1 minute": 1,
                    "5 minutes": 5,
                    "10 minutes": 10,
                    "15 minutes": 15,
                    "30 minutes": 30,
                    "1 hour": 60,
                    "6 hours": 360,
                    "12 hours": 720,
                    "24 hours": 1440,
                }
                param_schema = auto_info.get("param_schema", {})
                if new_enabled:
                    with st.expander("\u2699\ufe0f Settings", expanded=False):
                        # ── Run frequency selector ──────────────────────
                        st.markdown(
                            "<p style='color:#a8dadc;font-size:0.82rem;margin-bottom:4px;font-weight:600;'>\u23f1\ufe0f Run Frequency</p>",
                            unsafe_allow_html=True,
                        )
                        _saved_interval = state.get("interval_minutes",
                                                    auto_info.get("interval_minutes", 15))
                        _freq_label = next(
                            (k for k, v in _FREQ_OPTIONS.items()
                             if v == _saved_interval),
                            "15 minutes",
                        )
                        _freq_keys = list(_FREQ_OPTIONS.keys())
                        _freq_idx = _freq_keys.index(
                            _freq_label) if _freq_label in _freq_keys else 4
                        selected_freq = st.selectbox(
                            "Run every",
                            _freq_keys,
                            index=_freq_idx,
                            key=f"freq_{agent_id}_{auto_id}",
                            label_visibility="collapsed",
                        )
                        new_interval = _FREQ_OPTIONS[selected_freq]

                        # ── Automation-specific params ──────────────────
                        new_params: dict = {}
                        for pk, ps in param_schema.items():
                            cv = params.get(pk, auto_info.get(
                                "default_params", {}).get(pk, ""))
                            ptype = ps.get("type", "text")
                            if ptype == "text":
                                new_params[pk] = st.text_input(
                                    ps["label"], value=str(cv),
                                    key=f"ap_{agent_id}_{auto_id}_{pk}",
                                )
                            elif ptype == "textarea":
                                new_params[pk] = st.text_area(
                                    ps["label"], value=str(cv),
                                    key=f"ap_{agent_id}_{auto_id}_{pk}",
                                )
                            elif ptype == "number":
                                new_params[pk] = st.number_input(
                                    ps["label"],
                                    min_value=ps.get("min", 0),
                                    max_value=ps.get("max", 9999),
                                    value=int(cv) if str(cv).lstrip(
                                        "-").isdigit() else ps.get("min", 0),
                                    key=f"ap_{agent_id}_{auto_id}_{pk}",
                                )
                            elif ptype == "slider":
                                new_params[pk] = st.slider(
                                    ps["label"],
                                    min_value=float(ps.get("min", 0.0)),
                                    max_value=float(ps.get("max", 1.0)),
                                    value=float(cv) if cv != "" else float(
                                        ps.get("min", 0.0)),
                                    step=float(ps.get("step", 0.1)),
                                    key=f"ap_{agent_id}_{auto_id}_{pk}",
                                )
                        if st.button(
                            "\U0001f4be Save Settings",
                            key=f"ap_save_{agent_id}_{auto_id}",
                        ):
                            update_automation_state(
                                agent_id, auto_id, new_enabled, new_params,
                                interval_minutes=new_interval)
                            st.success(
                                f"\u2705 Settings saved — runs every {selected_freq}")
                            st.rerun()

                st.markdown("<div style='height:4px'></div>",
                            unsafe_allow_html=True)

    # ── General Settings tab ────────────────────────────────────────
    with tab_general:
        st.markdown(
            "<p style='color:#a8dadc;font-size:0.88rem;margin-bottom:16px;'>"
            "Adjust runtime safety and behaviour settings for this agent.</p>",
            unsafe_allow_html=True,
        )

        current_max_ops = int(
            agent.get("config", {}).get("max_operations", 100))

        with st.form(f"cfg_general_{agent_id}"):
            st.markdown(
                "<p style='color:#e91e8c;font-weight:600;margin-bottom:2px;'>"
                "\U0001f6e1\ufe0f Max Operations per Command</p>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Limits how many individual Gmail API calls this agent can make when processing "
                "a single command. Bulk fetches (listing, labelling, digests) are silently capped "
                "at this number — preventing a command like \"delete all emails\" from touching "
                "thousands of messages at once. The agent shows a warning in chat when a result "
                "has been capped."
            )
            new_max_ops = st.number_input(
                "Max operations per command",
                min_value=1,
                max_value=10000,
                value=current_max_ops,
                step=10,
                key=f"cfg_max_ops_{agent_id}",
                label_visibility="collapsed",
            )
            st.markdown(
                "<p style='color:#888;font-size:0.78rem;margin-top:4px;'>"
                "\U0001f4a1 Suggested: <b>50–200</b> for everyday use. "
                "Raise to <b>1000+</b> only for bulk maintenance tasks.</p>",
                unsafe_allow_html=True,
            )
            if st.form_submit_button("\U0001f4be Save General Settings", type="primary"):
                existing_config = agent.get("config", {})
                existing_config["max_operations"] = int(new_max_ops)
                ok = manager.update_agent(
                    agent_id, {"config": existing_config})
                if ok:
                    st.success(
                        f"\u2705 Max operations updated to {int(new_max_ops)}. "
                        "Takes effect on the next command."
                    )
                    st.rerun()
                else:
                    st.error("\u274c Could not save settings.")
