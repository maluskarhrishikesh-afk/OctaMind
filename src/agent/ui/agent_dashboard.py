"""
Agent Hub Dashboard - Multi-Agent Management Interface

Main hub for creating, starting, stopping, and managing specialized agents.
Each agent spawns its own Streamlit window on a dedicated port.
"""

from __future__ import annotations
from src.agent.core.process_manager import (
    start_agent,
    stop_agent,
    get_agent_status,
    cleanup_stale,
)
from src.agent.core.agent_manager import get_agent_manager, DEFAULT_PERSONALITY_TRAITS
from src.agent.core.automations.automation_config import (
    load_automation_config,
    update_automation_state,
    get_automations_for_agent_type,
)

import os
import sys
from datetime import datetime
from pathlib import Path

import base64 as _base64
import streamlit as st

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))


@st.cache_resource
def _logo_b64() -> str:
    """Return the base64 data URL for octopus.png. Cached for the process lifetime."""
    img_path = Path(__file__).parent.parent / "assets" / "octopus.png"
    data = img_path.read_bytes()
    return "data:image/png;base64," + _base64.b64encode(data).decode()


def _logo_icon():
    """Return a PIL Image of octopus.png for page_icon, or emoji fallback."""
    try:
        from PIL import Image as _PILImage
        return _PILImage.open(Path(__file__).parent.parent / "assets" / "octopus.png")
    except Exception:
        return "\U0001f419"


# ── Agent-creation form ───────────────────────────────────────────────────────

def show_create_agent_form():
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


# ── Agent card ────────────────────────────────────────────────────────────────

def show_agent_card(agent: dict):
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

# ── Configure panel ────────────────────────────────────────────────────────


_TRAIT_META = [
    ("tone",          "\U0001f5e3 Tone",          "Formal", "Casual"),
    ("verbosity",     "\U0001f4dd Verbosity",      "Brief",  "Detailed"),
    ("humor",         "\U0001f604 Humor",          "Serious", "Witty"),
    ("empathy",       "\u2764\ufe0f Empathy",          "Neutral", "Warm"),
    ("proactiveness", "\u26a1 Proactiveness",   "Reactive", "Proactive"),
]


def show_configure_panel(agent: dict):
    """Full configure panel: personality traits + per-type automations."""
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

    tab_personality, tab_automations = st.tabs(
        ["\U0001f3ad Personality Traits", "\u2699\ufe0f Automations"])

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

                param_schema = auto_info.get("param_schema", {})
                if new_enabled and param_schema:
                    with st.expander("\u2699\ufe0f Settings", expanded=False):
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
                                agent_id, auto_id, new_enabled, new_params)
                            st.success("\u2705 Settings saved")
                            st.rerun()

                st.markdown("<div style='height:4px'></div>",
                            unsafe_allow_html=True)

# ── Main dashboard ────────────────────────────────────────────────────────────


def main():
    st.set_page_config(
        page_title="OctaMind — Agent Hub",
        page_icon=_logo_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Global dark-theme CSS ─────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* ============================================================
           OctaMind — Global Dark Theme Fixes
           ============================================================ */

        /* App background */
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(135deg, #0f172a 0%, #1a1a2e 50%, #16213e 100%) !important;
        }
        [data-testid="stHeader"] { background: transparent !important; }

        /* ── All widget labels ── */
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"],
        [data-testid="stFormLabel"] p,
        [data-testid="stFormLabel"],
        .stTextInput label, .stTextArea label,
        .stNumberInput label, .stSelectbox label,
        .stMultiSelect label, .stSlider label,
        .stCheckbox label, .stRadio label {
            color: #e0e0e0 !important;
            font-weight: 600 !important;
        }

        /* ── Text inputs / textareas / number inputs ── */
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input {
            background: rgba(255,255,255,0.06) !important;
            border: 1px solid rgba(233,30,140,0.28) !important;
            border-radius: 8px !important;
            color: #e0e0e0 !important;
        }
        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder { color: #666 !important; }
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus,
        [data-testid="stNumberInput"] input:focus {
            border-color: #e91e8c !important;
            box-shadow: 0 0 0 2px rgba(233,30,140,0.2) !important;
        }

        /* ── Selectbox / dropdown ── */
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            background: rgba(255,255,255,0.06) !important;
            border: 1px solid rgba(233,30,140,0.28) !important;
            border-radius: 8px !important;
        }
        /* Selected value text */
        [data-testid="stSelectbox"] [data-baseweb="select"] span,
        [data-testid="stSelectbox"] [data-baseweb="select"] div,
        [data-testid="stSelectbox"] [data-baseweb="select"] p { color: #e0e0e0 !important; }
        /* Dropdown list (popover) */
        [data-baseweb="popover"],
        [data-baseweb="menu"] {
            background: #1e2744 !important;
            border: 1px solid rgba(233,30,140,0.3) !important;
            border-radius: 10px !important;
        }
        [data-baseweb="popover"] li,
        [data-baseweb="menu"] li,
        [data-baseweb="popover"] [role="option"],
        ul[data-testid="stSelectboxVirtualDropdown"] li {
            background: transparent !important;
            color: #e0e0e0 !important;
        }
        [data-baseweb="popover"] li:hover,
        [data-baseweb="menu"] li:hover,
        [data-baseweb="popover"] [role="option"]:hover {
            background: rgba(233,30,140,0.18) !important;
            color: #e91e8c !important;
        }
        [data-baseweb="popover"] [aria-selected="true"],
        [data-baseweb="menu"] [aria-selected="true"] {
            background: rgba(233,30,140,0.25) !important;
            color: #e91e8c !important;
        }

        /* ── Multiselect ── */
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            background: rgba(255,255,255,0.06) !important;
            border: 1px solid rgba(233,30,140,0.28) !important;
            border-radius: 8px !important;
        }
        [data-testid="stMultiSelect"] span { color: #e0e0e0 !important; }

        /* ── Checkbox ── */
        [data-testid="stCheckbox"] label p,
        [data-testid="stCheckbox"] label span,
        [data-testid="stCheckbox"] > label { color: #e0e0e0 !important; font-weight: 600 !important; }

        /* ── Radio buttons ── */
        div[data-testid="stRadio"] label p,
        div[data-testid="stRadio"] label div p,
        div[data-testid="stRadio"] label span,
        div[data-testid="stRadio"] label,
        div[role="radiogroup"] label p,
        div[role="radiogroup"] label span { color: #e0e0e0 !important; font-weight: 600 !important; }

        /* ── Sliders ── */
        [data-testid="stSlider"] p,
        [data-testid="stSlider"] span,
        [data-testid="stSlider"] label { color: #e0e0e0 !important; font-weight: 600 !important; }

        /* ── Expanders ── */
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary,
        details summary p,
        details summary span,
        .streamlit-expanderHeader p,
        .streamlit-expanderHeader { color: #e0e0e0 !important; font-weight: 600 !important; }
        [data-testid="stExpander"] {
            border: 1px solid rgba(233,30,140,0.2) !important;
            border-radius: 10px !important;
            background: rgba(255,255,255,0.03) !important;
        }

        /* ── Tabs ── */
        [data-testid="stTabs"] button[role="tab"] p,
        [data-testid="stTabs"] button[role="tab"] { color: #a0a0a0 !important; font-weight: 600 !important; }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] p,
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #e91e8c !important; font-weight: 700 !important;
        }

        /* ── st.info / success / warning / error banners ── */
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] { color: #e0e0e0 !important; }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] { background: #0f172a !important; }
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label { color: #b0b0b0 !important; }

        /* ── Buttons — secondary style ── */
        [data-testid="stBaseButton-secondary"] {
            background: rgba(255,255,255,0.06) !important;
            border: 1px solid rgba(233,30,140,0.3) !important;
            color: #e0e0e0 !important;
            border-radius: 8px !important;
        }
        [data-testid="stBaseButton-secondary"]:hover {
            background: rgba(233,30,140,0.12) !important;
            border-color: #e91e8c !important;
            color: #e91e8c !important;
        }

        /* ── Form submit button ── */
        [data-testid="stFormSubmitButton"] button {
            border-radius: 8px !important;
            font-weight: 700 !important;
        }

        /* ── Caption / helper text ── */
        [data-testid="stCaptionContainer"] p,
        .stCaption p { color: #888 !important; }

        /* ── Dividers ── */
        hr { border-color: rgba(233,30,140,0.2) !important; }

        /* ── Scrollbar ── */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: rgba(233,30,140,0.4); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #e91e8c; }
        </style>
        """,
        unsafe_allow_html=True,
    )

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
