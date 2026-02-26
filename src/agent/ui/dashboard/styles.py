"""
Dark-theme CSS for the Octa Bot Agent Hub dashboard.
Call inject_css() once at the top of main() to apply global styles.
"""
import streamlit as st

# ── Complete dark-theme stylesheet ────────────────────────────────────────────
DARK_THEME_CSS = """
<style>
/* ============================================================
   Octa Bot — Global Dark Theme  (v2 — modern, elegant)
   ============================================================ */

/* App background */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0d1117 0%, #161b2e 50%, #0f172a 100%) !important;
}
[data-testid="stHeader"] { background: transparent !important; }

/* ── Dialog overlay — dark themed ────────────────────────────────────────── */
[data-testid="stDialog"],
[data-testid="stModal"],
div[data-baseweb="modal"],
div[data-baseweb="dialog"] {
    background: #161b2e !important;
}
div[data-baseweb="modal"] > div,
div[data-baseweb="dialog"] > div {
    background: #161b2e !important;
    border: 1px solid rgba(99,102,241,0.3) !important;
    border-radius: 16px !important;
}
/* All text inside dialogs */
[data-testid="stDialog"] p,
[data-testid="stDialog"] span,
[data-testid="stDialog"] label,
[data-testid="stDialog"] div {
    color: #e2e8f0;
}
/* Dialog inputs */
[data-testid="stDialog"] input,
[data-testid="stDialog"] textarea,
div[data-baseweb="modal"] input,
div[data-baseweb="modal"] textarea,
div[data-baseweb="dialog"] input,
div[data-baseweb="dialog"] textarea {
    background: #1e293b !important;
    color: #f1f5f9 !important;
    border: 1.5px solid rgba(99,102,241,0.4) !important;
    border-radius: 10px !important;
    caret-color: #818cf8 !important;
    font-size: 0.95rem !important;
}
[data-testid="stDialog"] input:focus,
[data-testid="stDialog"] textarea:focus,
div[data-baseweb="modal"] input:focus,
div[data-baseweb="modal"] textarea:focus {
    border-color: #818cf8 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.2) !important;
    outline: none !important;
}
[data-testid="stDialog"] input::placeholder,
[data-testid="stDialog"] textarea::placeholder,
div[data-baseweb="modal"] input::placeholder,
div[data-baseweb="modal"] textarea::placeholder {
    color: #475569 !important;
}
/* Dialog labels */
[data-testid="stDialog"] [data-testid="stWidgetLabel"] p,
[data-testid="stDialog"] [data-testid="stWidgetLabel"],
[data-testid="stDialog"] label,
div[data-baseweb="modal"] label,
div[data-baseweb="modal"] [data-testid="stWidgetLabel"] p {
    color: #94a3b8 !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
/* Dialog multiselect */
[data-testid="stDialog"] [data-baseweb="select"] > div,
div[data-baseweb="modal"] [data-baseweb="select"] > div {
    background: #1e293b !important;
    border: 1.5px solid rgba(99,102,241,0.4) !important;
    border-radius: 10px !important;
    color: #f1f5f9 !important;
}
[data-testid="stDialog"] [data-baseweb="select"] span,
[data-testid="stDialog"] [data-baseweb="select"] div,
div[data-baseweb="modal"] [data-baseweb="select"] span,
div[data-baseweb="modal"] [data-baseweb="select"] div { color: #f1f5f9 !important; }
/* Dialog selection tags/pills */
[data-testid="stDialog"] [data-baseweb="tag"],
div[data-baseweb="modal"] [data-baseweb="tag"] {
    background: rgba(99,102,241,0.25) !important;
    color: #a5b4fc !important;
    border-radius: 6px !important;
}
/* Dialog error/info/success banners */
[data-testid="stDialog"] [data-testid="stAlert"],
div[data-baseweb="modal"] [data-testid="stAlert"] {
    background: rgba(239,68,68,0.12) !important;
    border: 1px solid rgba(239,68,68,0.35) !important;
    border-radius: 10px !important;
}
[data-testid="stDialog"] [data-testid="stAlert"] p,
div[data-baseweb="modal"] [data-testid="stAlert"] p {
    color: #fca5a5 !important;
    font-weight: 600 !important;
}
/* Dialog success */
[data-testid="stDialog"] [data-testid="stAlert"][data-baseweb="notification"],
div[data-baseweb="modal"] [data-testid="stAlert"][data-baseweb="notification"] {
    background: rgba(34,197,94,0.12) !important;
}
/* Dialog dividers */
[data-testid="stDialog"] hr { border-color: rgba(99,102,241,0.2) !important; }
/* Dialog heading text */
[data-testid="stDialog"] h1, [data-testid="stDialog"] h2,
[data-testid="stDialog"] h3, [data-testid="stDialog"] h4 {
    color: #e2e8f0 !important;
}


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
/* Expander body — force dark background so white inputs don't appear */
[data-testid="stExpanderDetails"],
[data-testid="stExpander"] > details > div[data-testid="stExpanderDetails"] {
    background: #111827 !important;
    border-top: 1px solid rgba(233,30,140,0.15) !important;
    padding: 12px 16px !important;
    border-radius: 0 0 10px 10px !important;
}
/* Inputs/textareas/number inside expanders */
[data-testid="stExpanderDetails"] input,
[data-testid="stExpanderDetails"] textarea,
[data-testid="stExpanderDetails"] [data-baseweb="input"] input,
[data-testid="stExpanderDetails"] [data-baseweb="textarea"] textarea {
    background: #1e2744 !important;
    color: #e0e0e0 !important;
    border: 1px solid rgba(233,30,140,0.35) !important;
    border-radius: 8px !important;
    caret-color: #e91e8c !important;
}
[data-testid="stExpanderDetails"] input::placeholder,
[data-testid="stExpanderDetails"] textarea::placeholder { color: #555 !important; }
[data-testid="stExpanderDetails"] input:focus,
[data-testid="stExpanderDetails"] textarea:focus {
    border-color: #e91e8c !important;
    box-shadow: 0 0 0 2px rgba(233,30,140,0.2) !important;
}
/* Labels inside expanders */
[data-testid="stExpanderDetails"] [data-testid="stWidgetLabel"] p,
[data-testid="stExpanderDetails"] [data-testid="stWidgetLabel"],
[data-testid="stExpanderDetails"] label p,
[data-testid="stExpanderDetails"] label { color: #e0e0e0 !important; font-weight: 600 !important; }
/* Selectbox inside expanders */
[data-testid="stExpanderDetails"] [data-baseweb="select"] > div {
    background: #1e2744 !important;
    border: 1px solid rgba(233,30,140,0.35) !important;
    color: #e0e0e0 !important;
}
[data-testid="stExpanderDetails"] [data-baseweb="select"] span,
[data-testid="stExpanderDetails"] [data-baseweb="select"] div { color: #e0e0e0 !important; }

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
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1117 0%, #0f172a 100%) !important;
    border-right: 1px solid rgba(99,102,241,0.12) !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label { color: #94a3b8 !important; }

/* ══════════════════════════════════════════════════════════════
   BUTTON SYSTEM  — elegant, not gaudy
   ══════════════════════════════════════════════════════════════ */

/* All buttons — base reset */
button[data-testid^="stBaseButton"],
[data-testid="stFormSubmitButton"] button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.01em !important;
    transition: all 0.18s ease !important;
    padding: 6px 14px !important;
    min-height: 38px !important;
    cursor: pointer !important;
}

/* PRIMARY — deep indigo, used for main "create" and "save" actions */
[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%) !important;
    border: 1px solid rgba(99,102,241,0.6) !important;
    color: #fff !important;
    box-shadow: 0 2px 8px rgba(79,70,229,0.3) !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background: linear-gradient(135deg, #3730a3 0%, #4338ca 100%) !important;
    box-shadow: 0 4px 14px rgba(79,70,229,0.45) !important;
    transform: translateY(-1px) !important;
}
[data-testid="stBaseButton-primary"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 1px 4px rgba(79,70,229,0.3) !important;
}

/* SECONDARY — subtle glass, used for cancel / neutral actions */
[data-testid="stBaseButton-secondary"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(148,163,184,0.25) !important;
    color: #94a3b8 !important;
    border-radius: 10px !important;
}
[data-testid="stBaseButton-secondary"]:hover {
    background: rgba(255,255,255,0.09) !important;
    border-color: rgba(148,163,184,0.45) !important;
    color: #e2e8f0 !important;
}

/* Form submit button */
[data-testid="stFormSubmitButton"] button {
    background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%) !important;
    border: 1px solid rgba(99,102,241,0.6) !important;
    color: #fff !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 8px rgba(79,70,229,0.3) !important;
}
[data-testid="stFormSubmitButton"] button:hover {
    background: linear-gradient(135deg, #3730a3 0%, #4338ca 100%) !important;
    box-shadow: 0 4px 14px rgba(79,70,229,0.45) !important;
}

/* ── Semantic button colour helpers via data-key  ─────────────────────────── *
 * We encode intent in the label/key names; the CSS below applies colours      *
 * based on those matching patterns.                                            */

/* GREEN — start / launch buttons */
button[data-testid^="stBaseButton"][kind="primary"][aria-label*="Start"],
button[kind="primary"][aria-label*="▶️"] {
    background: linear-gradient(135deg, #15803d 0%, #16a34a 100%) !important;
    border-color: rgba(22,163,74,0.6) !important;
    box-shadow: 0 2px 8px rgba(22,163,74,0.3) !important;
}

/* Link button (Open Chat) — sky blue */
[data-testid="stLinkButton"] a,
[data-testid="stLinkButton"] button {
    background: linear-gradient(135deg, #0284c7 0%, #0ea5e9 100%) !important;
    border: 1px solid rgba(14,165,233,0.5) !important;
    color: #fff !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 6px rgba(14,165,233,0.25) !important;
    text-decoration: none !important;
}
[data-testid="stLinkButton"] a:hover,
[data-testid="stLinkButton"] button:hover {
    background: linear-gradient(135deg, #0369a1 0%, #0284c7 100%) !important;
    box-shadow: 0 4px 12px rgba(14,165,233,0.35) !important;
    transform: translateY(-1px) !important;
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

/* ── Forms (st.form container) ── */
[data-testid="stForm"] {
    background: rgba(15,23,42,0.6) !important;
    border: 1px solid rgba(233,30,140,0.18) !important;
    border-radius: 12px !important;
}
/* All inputs / textareas / number inputs inside a form */
[data-testid="stForm"] input,
[data-testid="stForm"] textarea {
    background: rgba(30,39,70,0.9) !important;
    color: #e0e0e0 !important;
    border: 1px solid rgba(233,30,140,0.35) !important;
    border-radius: 8px !important;
    caret-color: #e91e8c !important;
}
[data-testid="stForm"] input:focus,
[data-testid="stForm"] textarea:focus {
    border-color: #e91e8c !important;
    box-shadow: 0 0 0 2px rgba(233,30,140,0.2) !important;
    outline: none !important;
}
[data-testid="stForm"] input::placeholder,
[data-testid="stForm"] textarea::placeholder { color: #555 !important; }
/* Labels and captions inside forms */
[data-testid="stForm"] [data-testid="stWidgetLabel"] p,
[data-testid="stForm"] [data-testid="stWidgetLabel"],
[data-testid="stForm"] label p,
[data-testid="stForm"] label { color: #e0e0e0 !important; font-weight: 600 !important; }
[data-testid="stForm"] [data-testid="stCaptionContainer"] p,
[data-testid="stForm"] small,
[data-testid="stForm"] .stCaption p { color: #888 !important; }
/* Selectbox inside form */
[data-testid="stForm"] [data-baseweb="select"] > div {
    background: rgba(30,39,70,0.9) !important;
    border: 1px solid rgba(233,30,140,0.35) !important;
    color: #e0e0e0 !important;
}
[data-testid="stForm"] [data-baseweb="select"] span,
[data-testid="stForm"] [data-baseweb="select"] div,
[data-testid="stForm"] [data-baseweb="select"] p { color: #e0e0e0 !important; }
/* Stepper +/- buttons on number inputs inside forms */
[data-testid="stForm"] [data-testid="stNumberInput"] button {
    background: rgba(30,39,70,0.9) !important;
    border-color: rgba(233,30,140,0.35) !important;
    color: #e91e8c !important;
}
[data-testid="stForm"] [data-testid="stNumberInput"] button:hover {
    background: rgba(233,30,140,0.18) !important;
}

/* ── Skill chip hover tooltip ───────────────────────────────────────────── */
.oa-tooltip {
    display: none;
    position: absolute;
    bottom: calc(100% + 6px);
    left: 0;
    right: 0;
    background: #1e293b;
    border: 1px solid rgba(99,102,241,0.35);
    border-radius: 10px;
    padding: 10px 12px;
    z-index: 9999;
    box-shadow: 0 8px 24px rgba(0,0,0,0.45);
    pointer-events: none;
    min-width: 180px;
}
.oa-skill-chip:hover .oa-tooltip {
    display: block;
}
</style>
"""


def inject_css() -> None:
    """Inject the full dark-theme stylesheet into the current Streamlit page."""
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)


# ── Per-agent chat CSS (called once from each agent's main()) ─────────────────

def inject_agent_css(
    accent_hex: str = "#e91e8c",
    accent_rgb: str = "233,30,140",
) -> None:
    """
    Inject the global dark theme + agent-specific chat-UI styles.

    Args:
        accent_hex: Primary accent colour as a hex string (e.g. "#e91e8c").
        accent_rgb: Same colour as an RGB triplet string (e.g. "233,30,140"),
                    used for rgba() rules.
    """
    inject_css()  # global dark theme first
    st.markdown(
        f"""
        <style>
        /* ═══════════════════════════════════════════════════════════
           ChatGPT-style chat — no avatars, left/right bubbles
           Streamlit 1.40+ uses stChatMessageAvatarUser / stChatMessageAvatarAssistant
           ═══════════════════════════════════════════════════════════ */

        /* 1. Hide ALL avatar icons (Streamlit 1.40+ testids) */
        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"],
        [data-testid="stChatMessageAvatarCustom"] {{
            display: none !important;
            width: 0 !important;
            min-width: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
        }}

        /* 2. Reset the outer chat-message wrapper */
        [data-testid="stChatMessage"] {{
            gap: 0 !important;
            padding: 4px 0 !important;
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            margin-bottom: 6px !important;
            align-items: flex-end !important;
        }}

        /* 3. USER messages — right-aligned pill
              Streamlit sets background=true on the styled container for "user"/"human"
              which maps to the .stChatMessage class with a specific emotion cache variant.
              We detect it via :has() against the avatar testid. */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
            justify-content: flex-end !important;
            flex-direction: row-reverse !important;
        }}
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
          [data-testid="stChatMessageContent"] {{
            max-width: 68% !important;
            background: rgba({accent_rgb}, 0.15) !important;
            border: 1px solid rgba({accent_rgb}, 0.30) !important;
            border-radius: 18px 18px 4px 18px !important;
            padding: 10px 16px !important;
            margin-left: auto !important;
            margin-right: 0 !important;
        }}
        /* Right-align text inside user bubble */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
          [data-testid="stMarkdownContainer"],
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
          [data-testid="stMarkdownContainer"] p {{
            text-align: right !important;
        }}

        /* 4. ASSISTANT messages — subtle dark bubble, left edge */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {{
            justify-content: flex-start !important;
        }}
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
          [data-testid="stChatMessageContent"] {{
            max-width: 85% !important;
            background: rgba(255, 255, 255, 0.05) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            border-radius: 18px 18px 18px 4px !important;
            padding: 10px 16px !important;
            margin-right: auto !important;
        }}

        /* 5. Text colours — readable on dark background */
        [data-testid="stChatMessage"] p,
        [data-testid="stChatMessage"] li,
        [data-testid="stChatMessage"] span,
        [data-testid="stChatMessage"] strong,
        [data-testid="stChatMessage"] em,
        [data-testid="stChatMessage"] code {{
            color: #e0e0e0 !important;
        }}
        [data-testid="stChatMessage"] code {{
            background: rgba(255,255,255,0.08) !important;
            border-radius: 4px !important;
            padding: 1px 4px !important;
        }}
        /* ── Circular clear / icon button ────────────────────────────────── */
        div[data-testid="stColumns"] button[kind="secondary"] {{
            background: transparent !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            border-radius: 50% !important;
            color: #888 !important;
            padding: 4px !important;
            font-size: 1rem !important;
            min-height: 0 !important;
            height: 36px !important;
            width: 36px !important;
            transition: border-color 0.2s, color 0.2s;
        }}
        div[data-testid="stColumns"] button[kind="secondary"]:hover {{
            border-color: {accent_hex} !important;
            color: {accent_hex} !important;
            background: rgba({accent_rgb},0.08) !important;
        }}
        /* ── Chat input footer area — dark background + no defaults ─────── */
        [data-testid="stBottomBlockContainer"],
        section[data-testid="stBottom"] > div,
        .stChatFloatingInputContainer {{
            background: linear-gradient(135deg, #0f172a 0%, #1a1a2e 100%) !important;
            backdrop-filter: blur(10px) !important;
            border-top: 1px solid rgba({accent_rgb},0.15) !important;
        }}
        [data-testid="stBottomBlockContainer"] > div,
        [data-testid="stBottomBlockContainer"] > div > div {{
            background: transparent !important;
        }}
        /* ── Chat input container — dark background with accent border ─── */
        [data-testid="stChatInput"],
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] [data-baseweb="base-input"] {{
            background: rgba(30,39,70,0.9) !important;
            border: 1px solid rgba({accent_rgb},0.4) !important;
            border-radius: 12px !important;
        }}
        [data-testid="stChatInput"]:focus-within,
        [data-testid="stChatInput"] > div:focus-within,
        [data-testid="stChatInput"] [data-baseweb="base-input"]:focus-within {{
            background: rgba(30,39,70,0.95) !important;
            border-color: {accent_hex} !important;
            box-shadow: 0 0 0 2px rgba({accent_rgb},0.2) !important;
        }}
        /* Textarea / contenteditable / input inside chat input */
        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] div[contenteditable],
        [data-testid="stChatInput"] input,
        [data-testid="stChatInput"] [data-baseweb="textarea"] textarea,
        [data-testid="stChatInput"] [data-baseweb="base-input"] input,
        [data-testid="stChatInput"] [data-baseweb="base-input"] textarea {{
            background: transparent !important;
            color: #e0e0e0 !important;
            caret-color: {accent_hex} !important;
            border: none !important;
            box-shadow: none !important;
            font-size: 0.95rem !important;
        }}
        [data-testid="stChatInput"] textarea::placeholder,
        [data-testid="stChatInput"] input::placeholder,
        [data-testid="stChatInput"] [data-baseweb="base-input"] textarea::placeholder,
        [data-testid="stChatInput"] [data-baseweb="base-input"] input::placeholder,
        [data-testid="stChatInput"] [placeholder]::placeholder {{ 
            color: #666 !important; 
        }}
        /* Send button */
        [data-testid="stChatInput"] button {{
            background: {accent_hex} !important;
            border-radius: 8px !important;
            color: white !important;
            border: none !important;
        }}
        [data-testid="stChatInput"] button:hover {{
            background: {accent_hex}dd !important;
            box-shadow: 0 2px 8px rgba({accent_rgb},0.5) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
