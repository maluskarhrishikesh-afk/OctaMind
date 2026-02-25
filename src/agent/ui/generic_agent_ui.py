"""
Generic Agent Chat UI

A universal conversational interface for agents that don't yet have a
dedicated backend (Google Drive, Slack, Calendar, Stock Market, Custom).
Displays the agent's memory, personality, and context from its memory folder.
"""

import base64 as _base64
import streamlit as st
import os
import sys
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Skills are stateless executors — memory belongs to Personal Assistants only.
try:
    from src.agent.core.agent_manager import get_agent_manager
    MANAGER_AVAILABLE = True
except Exception:
    MANAGER_AVAILABLE = False


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


# ── Agent type metadata ──────────────────────────────────────────────────────
_TYPE_META = {
    "google_drive": {
        "icon": "📁",
        "name": "Google Drive Agent",
        "color": "#4285F4",
        "greeting": (
            "👋 Hi! I'm your **Google Drive Agent**. I can help you organise files, "
            "search documents, manage folders, and share content. "
            "*(Google Drive integration coming soon — for now you can chat and I'll remember your preferences!)*"
        ),
        "capabilities": [
            "📂 List files & folders",
            "🔍 Search documents",
            "📤 Upload / download files",
            "🤝 Share files with others",
            "🗑️ Delete files",
        ],
    },
    "slack": {
        "icon": "💬",
        "name": "Slack Agent",
        "color": "#4A154B",
        "greeting": (
            "👋 Hey! I'm your **Slack Agent**. I can help you send messages, "
            "manage channels, and stay on top of team communication. "
            "*(Slack integration coming soon!)*"
        ),
        "capabilities": [
            "💬 Send messages to channels / DMs",
            "📋 List channels",
            "🔔 Manage notifications",
            "🔍 Search messages",
        ],
    },
    "calendar": {
        "icon": "📅",
        "name": "Calendar Agent",
        "color": "#0F9D58",
        "greeting": (
            "👋 Hello! I'm your **Calendar Agent**. I can help you schedule meetings, "
            "manage events, and set reminders. "
            "*(Calendar integration coming soon!)*"
        ),
        "capabilities": [
            "📅 Create events & meetings",
            "👀 View upcoming schedule",
            "🔔 Set reminders",
            "❌ Cancel / reschedule events",
        ],
    },
    "stock_market": {
        "icon": "📈",
        "name": "Stock Market Agent",
        "color": "#DB4437",
        "greeting": (
            "👋 Hi! I'm your **Stock Market Agent**. I can help you track stocks, "
            "analyse market trends, and monitor your portfolio. "
            "*(Market data integration coming soon!)*"
        ),
        "capabilities": [
            "📈 Track stock prices",
            "📊 Analyse market trends",
            "💼 Monitor portfolio",
            "📰 Latest financial news",
            "🔔 Price alerts",
        ],
    },
    "custom": {
        "icon": "🔧",
        "name": "Custom Agent",
        "color": "#FF6D00",
        "greeting": (
            "👋 Hello! I'm your **Custom Agent**. Tell me what you'd like me to learn "
            "and do — I'll adapt to your needs!"
        ),
        "capabilities": [
            "🎯 Adaptable to any task",
            "🧠 Learns your preferences",
            "💡 Suggests automations",
        ],
    },
}

_DEFAULT_META = {
    "icon": "🤖",
    "name": "AI Agent",
    "color": "#666666",
    "greeting": "👋 Hello! I'm your AI Agent. How can I help you today?",
    "capabilities": [],
}


def _get_meta(agent_type: str) -> dict:
    return _TYPE_META.get(agent_type, _DEFAULT_META)


@st.cache_resource
def _start_browser_watchdog(agent_id: str) -> bool:
    """
    Background thread that detects browser disconnection and exits the process.
    Uses Streamlit's internal session manager — no forced UI reruns needed.
    @st.cache_resource ensures this only starts once per process lifetime.
    """
    import threading
    import time as _t

    def _watch():
        _t.sleep(20)  # Grace period for initial browser connection
        while True:
            _t.sleep(8)
            try:
                from streamlit.runtime import get_instance
                rt = get_instance()
                if rt is not None:
                    active = list(rt._session_mgr.list_active_session_info())
                    if len(active) == 0:
                        try:
                            from src.agent.core.process_manager import remove_agent_from_state
                            remove_agent_from_state(agent_id)
                        except Exception:
                            pass
                        os._exit(0)
            except Exception:
                pass  # Fail-safe: if internal API changes, keep running

    threading.Thread(target=_watch, daemon=True).start()
    return True


def _load_memory_section(agent_id: str, section: str) -> str:
    """Read a memory markdown file for display in sidebar."""
    path = _PROJECT_ROOT / "memory" / agent_id / f"{section}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "*No data yet.*"


def _handle_conversation(msg: str, agent_type: str, agent_name: str, agent_id: str) -> str:
    """Return a context-aware reply for general conversational messages."""
    m = msg.strip().lower()
    meta = _get_meta(agent_type)

    # Memory/Remember queries
    if any(w in m for w in ["remember", "recall", "do you know", "did we", "have we", "earlier", "before", "previous"]):
        return "🤔 I’m still learning your preferences! Tell me what you’d like me to remember, and I’ll do my best to help."

    # Greetings
    greetings = ["hi", "hello", "hey", "howdy", "good morning", "good afternoon",
                 "good evening", "yo", "sup"]
    if any(m == g or m.startswith(g + " ") or m.startswith(g + "!") for g in greetings):
        return f"{meta['icon']} Hey! I'm **{agent_name}**, your {meta['name']}. How can I help you today?"

    # Capabilities / help
    if any(w in m for w in ["what can you do", "help", "capabilities", "commands", "features"]):
        caps = "\n".join(f"- {c}" for c in meta["capabilities"]
                         ) if meta["capabilities"] else "- Adapting to your needs..."
        return (f"🛠️ Here's what I can do as your **{meta['name']}**:\n\n{caps}\n\n"
                "*(Full integration is in progress — stay tuned!)*")

    # Who are you
    if any(w in m for w in ["who are you", "what are you", "your name", "introduce"]):
        return (f"{meta['icon']} I'm **{agent_name}**, a {meta['name']}.\n\n"
                f"I'm here to help you with tasks in the {meta['name'].replace(' Agent', '')} domain. "
                "My memory lets me learn your preferences over time!")

    # How are you
    if any(w in m for w in ["how are you", "how do you feel", "you ok", "doing well", "how's it going"]):
        return "😊 I'm doing great, thanks for asking! Ready to help. What would you like me to do?"

    # Thanks
    if any(w in m for w in ["thank", "thanks", "thx", "ty", "great job", "well done", "awesome", "perfect"]):
        return "😊 You're welcome! Let me know if there's anything else I can help with."

    # Bye
    farewells = ["bye", "goodbye", "see you",
                 "see ya", "later", "cya", "take care"]
    if any(m == f or m.startswith(f + " ") or m.startswith(f + "!") for f in farewells):
        return f"👋 Goodbye! Come back anytime. I'll remember our conversation! {meta['icon']}"

    # If it's short and not a meaningful instruction, give a gentle nudge
    if len(m.split()) <= 4:
        return (f"🤔 I'm not sure what you mean. I'm specialised in {meta['name'].replace(' Agent', '')} tasks.\n\n"
                "Type **help** to see what I can do, or just describe what you need!")

    # For longer messages — acknowledge and note it's being recorded
    return (
        f"📝 Got it! I've noted your message. As a {meta['name']}, I'm currently "
        f"in setup mode — full action execution is coming soon.\n\n"
        f"I'm storing your preferences in my memory so I'll be ready when the integration is live! "
        f"Type **help** to see my planned capabilities."
    )


def main():
    agent_id = os.getenv("AGENT_ID", "agent_default")
    agent_name = os.getenv("AGENT_NAME", "AI Agent")
    agent_type = os.getenv("AGENT_TYPE", "custom")

    meta = _get_meta(agent_type)

    # Start browser-close watchdog (once per process)
    _start_browser_watchdog(agent_id)

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:4px;">
          <img src="{_logo_b64()}" style="width:64px;height:64px;border-radius:16px;object-fit:cover;box-shadow:0 3px 10px rgba(233,30,140,0.35);">
          <div>
            <div style="font-size:2.2rem;font-weight:800;color:#e91e8c;line-height:1.1;">OctaMind</div>
            <div style="font-size:0.95rem;color:#888;margin-top:2px;">
              {meta['icon']} {agent_name} &nbsp;&bull;&nbsp; {meta['name']}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"ID: `{agent_id}`")
    st.divider()

    # ── Sidebar — memory viewer ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;padding:4px 0 8px 0;">
              <img src="{_logo_b64()}" style="width:36px;height:36px;border-radius:9px;object-fit:cover;">
              <div>
                <div style="font-size:1.2rem;font-weight:700;color:#e91e8c;">OctaMind</div>
                <div style="font-size:0.75rem;color:#888;">{meta['icon']} {agent_name}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.header(f"{meta['icon']} Agent Info")
        st.markdown(f"**Name:** {agent_name}")
        st.markdown(f"**Type:** {meta['name']}")
        st.markdown(f"**ID:** `{agent_id}`")
        st.divider()

        st.header("🧠 Agent Memory")
        tabs = st.tabs(["Personality", "Habits", "Working",
                       "Episodic", "Semantic", "Consciousness"])
        sections = ["personality", "habits", "working_memory",
                    "episodic_memory", "semantic_memory", "consciousness"]
        for tab, section in zip(tabs, sections):
            with tab:
                content = _load_memory_section(agent_id, section)
                st.markdown(content)

        st.divider()
        st.header("🛠️ Capabilities")
        for cap in meta["capabilities"]:
            st.markdown(f"  {cap}")
        if not meta["capabilities"]:
            st.caption("Configurable — depends on setup.")

    # ── Session state ─────────────────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": meta["greeting"]}
        ]
    if "history" not in st.session_state:
        st.session_state.history = []

    # ── Chat display ──────────────────────────────────────────────────────────
    st.subheader(f"💬 Chat with {agent_name}")

    with st.container():
        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Clear chat
    col1, col2 = st.columns([5, 1])
    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_messages = [
                {"role": "assistant", "content": meta["greeting"]}
            ]
            st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    user_input = st.chat_input(f"Message {agent_name}...")

    if user_input:
        st.session_state.chat_messages.append(
            {"role": "user", "content": user_input})

        with st.spinner(f"{meta['icon']} {agent_name} is thinking..."):
            reply = _handle_conversation(
                user_input, agent_type, agent_name, agent_id)

        st.session_state.chat_messages.append(
            {"role": "assistant", "content": reply})

        # Persist to history
        st.session_state.history.append({
            "user": user_input,
            "assistant": reply,
            "timestamp": datetime.now().isoformat(),
        })

        st.rerun()

    # ── History in sidebar ────────────────────────────────────────────────────
    if st.session_state.history:
        with st.sidebar:
            st.divider()
            st.header("📜 Session History")
            with st.expander("View exchanges", expanded=False):
                for i, item in enumerate(reversed(st.session_state.history), 1):
                    st.caption(f"**#{i}** {item['timestamp'][:19]}")
                    st.markdown(f"**You:** {item['user'][:60]}")
                    st.markdown(f"**Agent:** {item['assistant'][:60]}")
                    st.divider()


if __name__ == "__main__":
    main()
