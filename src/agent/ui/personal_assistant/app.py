"""
Personal Assistant Chat UI — Streamlit page.

Handles cross-agent commands that involve both the Drive Agent and Email Agent.
Commands are analysed → plan is shown → steps execute sequentially with live
progress tracking → results summarised.

Accent: purple (#7c3aed / rgb 124,58,237)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from ..dashboard.styles import inject_agent_css
from .helpers import _logo_b64, _logo_icon, _logo_path, _logo_pinkraven, _start_browser_watchdog, get_running_agents
from src.agent.hub.pa_manager import load_assistants, create_assistant, delete_assistant

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("personal_assistant")
logger.setLevel(logging.DEBUG)

_log_dir = Path(__file__).parent.parent.parent.parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "personal_assistant.log"
_file_handler = logging.FileHandler(_log_file, encoding="utf-8", mode="a")
_file_handler.setLevel(logging.DEBUG)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"
)
_file_handler.setFormatter(_formatter)
_console_handler.setFormatter(_formatter)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
))

# ── Lazy workflow imports ───────────────────────────────────────────


def _import_workflows():
    from src.agent.workflows import detect_agents_needed, run_workflow
    return detect_agents_needed, run_workflow


def _chat_response(message: str, agent_name: str, agent_id: str = None) -> str:
    """
    Handle conversational (non-workflow) messages via the LLM.
    Used when the command doesn't involve multiple agents.
    """
    try:
        from src.agent.llm.llm_parser import get_llm_client
        from src.agent.memory.agent_memory import get_agent_memory
        from src.agent.memory.collective_memory import get_collective_context

        # Collective consciousness — pull memory from ALL registered agents
        memory_context = ""
        try:
            memory_context = get_collective_context()
        except Exception as mem_err:
            logger.debug("Collective memory load skipped: %s", mem_err)

        # Layer on per-message recall from own memory
        if agent_id:
            try:
                own_memory = get_agent_memory(agent_id)
                recalled = own_memory.recall_for_llm(message)
                if recalled:
                    memory_context += f"\n\n{recalled}"
            except Exception as mem_err:
                logger.debug("Recall skipped: %s", mem_err)

        conversation_history = []
        if "chat_messages" in st.session_state:
            for m in st.session_state.chat_messages[-10:]:
                conversation_history.append(
                    {"role": m["role"], "content": m["content"]})

        llm = get_llm_client()
        response = llm.chat(
            user_message=message,
            agent_name=agent_name,
            agent_type="Personal Assistant",
            memory_context=memory_context,
            conversation_history=conversation_history,
        )

        # Record interaction to memory
        if agent_id and response:
            try:
                memory = get_agent_memory(agent_id)
                memory.add_interaction(
                    command=message,
                    action="conversation",
                    result={"status": "success", "response": response[:200]},
                    importance="Medium",
                )
            except Exception as mem_err:
                logger.debug("Memory record skipped: %s", mem_err)

        return response
    except Exception as exc:
        logger.warning("LLM chat fallback failed: %s", exc)
        return (
            "I'm your Personal Assistant — I can run commands that combine both your "
            "Drive Agent and Email Agent. Try something like: "
            "*'Download the Q3 report and email it to alice@example.com'*."
        )


# ── Usage Guide dialog ───────────────────────────────────────────────────────
@st.dialog("📖 Personal Assistant Usage Guide", width="large")
def _show_multi_agent_guide() -> None:
    st.markdown("""
## ⚡ What can your Personal Assistant do?

Your Personal Assistant lets you give **combined Drive + Email commands** in a single
sentence. OctaMind automatically plans which agents to use and in what order.

---

## 📁➡️✉️ Drive → Email workflows

| Command | What happens |
|---------|--------------|
| `Download the Q3 report and send it to alice@example.com` | Drive finds & downloads file, Email attaches & sends |
| `Find the invoice PDF and email it to bob@example.com` | Drive searches, Email sends with attachment |
| `Get the project proposal and draft an email to the team` | Drive retrieves file, Email creates draft |
| `Download the latest report and send a summary to manager@co.com` | Drive downloads, AI summarises, Email sends |

## ✉️➡️📁 Email → Drive workflows

| Command | What happens |
|---------|--------------|
| `Save the attachment from email <id> to my Drive` | Email downloads attachment, Drive uploads |
| `Upload the file from today's email to the Project folder` | Email gets attachment, Drive stores it |

## 🤝 Combined queries

| Command | What happens |
|---------|--------------|
| `Share the Q4 spreadsheet with everyone who emailed me today` | Drive finds file, Email finds senders, Drive shares |
| `Email me a storage report` | Drive generates report, Email sends it to you |

---

## 💡 Tips
- Be specific about **file names** and **email recipients** for best results.
- The planner shows each step as it executes — you can see what's happening in real time.
- If a step fails, the workflow stops and explains what went wrong.
- Personal Assistant commands work best when **both** agents are running (check the sidebar).
    """)


# ── Formatting helpers ───────────────────────────────────────────────────────

import json as _json


def _format_step_badge(agent: str) -> str:
    if agent == "drive":
        return "📁 Drive"
    elif agent == "email":
        return "✉️ Email"
    return f"🤖 {agent.title()}"


def _render_step_result(step_result: dict) -> str:
    """Build a compact status line shown during live workflow execution."""
    status_icon = "✅" if step_result["status"] == "success" else "❌"
    agent = step_result.get("agent", "?")
    tool = step_result.get("tool", "?")
    label = _format_step_badge(agent)
    line = f"{status_icon} **{label}** — `{tool}`"
    if step_result["status"] == "error":
        line += f"\n   ⚠️ {step_result.get('error', 'Unknown error')}"
    return line


def _compose_final_response(run_result: dict, original_command: str) -> str:
    """
    Pass raw step results directly to the LLM and let it compose a friendly,
    conversational final response. No pre-processing — the LLM sees everything.
    """
    from src.agent.llm.llm_parser import get_llm_client

    steps = run_result.get("steps", [])

    steps_payload = [
        {
            "agent": sr.get("agent"),
            # Use the human-readable instruction/description for the compose LLM
            "task": sr.get("instruction") or sr.get("tool", "?"),
            "status": sr.get("status"),
            # Flatten nested result dicts (new NL runner returns {"message":..., "artifacts":...})
            "result": (
                sr.get("result", {}).get("message")
                if isinstance(sr.get("result"), dict)
                else sr.get("result")
            ),
            "error": sr.get("error"),
        }
        for sr in steps
    ]

    composition_prompt = f"""The user asked: "{original_command}"

A cross-agent workflow was executed. Here are the raw results from each step:

{_json.dumps(steps_payload, indent=2, default=str)}

Compose a response following these formatting rules:
- Write in a friendly, conversational tone like a helpful assistant
- Use **bold** for important names, counts, and key values
- Use bullet points or numbered lists to present multiple items
- Use tables (markdown) when comparing or listing structured data (e.g. files, emails)
- Use relevant emojis to make the response visually engaging (e.g. 📁 for files, ✉️ for emails, ✅ for success)
- Add a brief summary sentence at the start so the user knows what happened
- If there are many items, show the most important ones and mention the total count
- Do NOT show raw field names, JSON keys, or technical IDs unless they are needed for the user to act on them
- Do NOT mention tool names or agent internals"""

    llm = get_llm_client()
    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Compose clear, friendly markdown responses from raw tool results."},
                {"role": "user", "content": composition_prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
            timeout=40,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Final response composition failed: %s", exc)
        return "✅ Workflow completed. " + ("Steps: " + ", ".join(s.get("tool", "?") for s in steps) if steps else "No steps recorded.")


def _render_workflow_output(run_result: dict, original_command: str = "") -> str:
    """Build the full assistant message for a completed workflow."""
    status = run_result.get("status", "error")
    plan = run_result.get("plan")
    steps = run_result.get("steps", [])
    elapsed = run_result.get("elapsed", 0)

    parts = []

    # ReAct mode: orchestrator already composed the final answer — use it directly
    # (avoids a second LLM call just for formatting)
    if run_result.get("final_answer") and status in ("success", "partial"):
        return run_result["final_answer"]

    if status == "success":
        return _compose_final_response(run_result, original_command)
    elif status == "partial":
        parts.append(
            "⚠️ **Workflow partially completed** — one or more steps failed.")
    else:
        parts.append("❌ **Workflow failed.**")

    if plan:
        parts.append(f"\n**Plan:** {plan.command}")

    parts.append(f"\n**Steps executed** ({len(steps)}) in {elapsed:.1f}s:\n")
    for r in steps:
        parts.append(_render_step_result(r))

    if status == "error" and not steps:
        parts.append(
            "\nCould not create a plan for this command. Try rephrasing it.")

    return "\n".join(parts)


# ── Live Channels feed (auto-refreshing fragment) ───────────────────────────

_SOURCE_ICONS = {
    "telegram": "✈️",
    "whatsapp": "💬",
    "api": "🔌",
    "unknown": "📡",
}
_SOURCE_COLORS = {
    "telegram": "#229ED9",
    "whatsapp": "#25D366",
    "api": "#7c3aed",
    "unknown": "#888",
}
_CONV_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "hub_conversations.json"


@st.fragment(run_every=5)
def _render_live_channels() -> None:
    """Auto-refreshing live feed of all external-channel conversations."""
    import json as _json
    from datetime import datetime as _dt

    try:
        if not _CONV_PATH.exists():
            st.info(
                "No external channel conversations yet. "
                "Messages sent via Telegram or other bots will appear here automatically."
            )
            return

        raw = _json.loads(_CONV_PATH.read_text(encoding="utf-8"))
        sessions = raw.get("sessions", {})

        if not sessions:
            st.info("No external channel conversations yet.")
            return

        # Sort newest-first
        sorted_sessions = sorted(
            sessions.values(),
            key=lambda s: s.get("last_updated", ""),
            reverse=True,
        )

        st.caption(f"🔄 Auto-refreshing every 5s &nbsp;·&nbsp; **{len(sorted_sessions)}** active session(s)")

        for idx, sess in enumerate(sorted_sessions):
            source = sess.get("source", "unknown")
            session_id = sess.get("session_id", "?")
            messages = sess.get("messages", [])
            last_updated = sess.get("last_updated", "")

            icon = _SOURCE_ICONS.get(source, "📡")
            color = _SOURCE_COLORS.get(source, "#888")

            try:
                time_str = _dt.fromisoformat(last_updated).strftime("%b %d %H:%M")
            except Exception:
                time_str = last_updated[:16]

            label = f"{icon} **{session_id}** &nbsp;`{source}`&nbsp;&nbsp; _{time_str}_"
            with st.expander(label, expanded=(idx == 0)):
                if not messages:
                    st.caption("No messages yet.")
                    continue

                for msg in messages[-12:]:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    ts = msg.get("ts", "")
                    elapsed = msg.get("elapsed")

                    try:
                        ts_str = _dt.fromisoformat(ts).strftime("%H:%M:%S")
                    except Exception:
                        ts_str = ""

                    ts_html = (
                        f"<span style='font-size:0.72rem;color:#9ca3af;white-space:nowrap;"
                        f"min-width:62px;padding-top:4px;display:inline-block;'>{ts_str}</span>"
                    )

                    if role == "user":
                        st.markdown(
                            f"<div style='display:flex;gap:8px;margin:6px 0;align-items:flex-start;'>"
                            f"{ts_html}"
                            f"<div style='background:#1e1e2e;border-left:3px solid {color};"
                            f"border-radius:0 8px 8px 0;padding:8px 12px;flex:1;font-size:0.86rem;"
                            f"color:#e2e8f0;line-height:1.5;'>{content}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        elapsed_badge = (
                            f" <span style='font-size:0.7rem;color:#a78bfa;'>({elapsed:.1f}s)</span>"
                            if elapsed else ""
                        )
                        st.markdown(
                            f"<div style='display:flex;gap:8px;margin:6px 0;align-items:flex-start;'>"
                            f"{ts_html}"
                            f"<div style='background:#2d1f4e;border-left:3px solid #8b5cf6;"
                            f"border-radius:0 8px 8px 0;padding:8px 12px;flex:1;font-size:0.86rem;"
                            f"color:#e2e8f0;line-height:1.5;'>"
                            f"{content}{elapsed_badge}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
    except Exception as exc:
        st.error(f"Could not load conversations: {exc}")


# ── Channel helpers ───────────────────────────────────────────────────────────

def _start_pa_channels(pa: dict) -> None:
    """Start every enabled channel assigned to this PA."""
    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        for ch_name in pa.get("channels", []):
            ch = CHANNEL_REGISTRY.get(ch_name)
            if ch and ch.enabled and not ch.is_running():
                try:
                    ch.start()
                except Exception as exc:
                    logger.warning("Could not start channel %s: %s", ch_name, exc)
    except Exception as exc:
        logger.warning("_start_pa_channels failed: %s", exc)


@st.dialog("\u2728 Create New Assistant", width="large")
def _create_pa_dialog() -> None:
    """Full-screen dialog for creating a Personal Assistant."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
    except Exception as exc:
        st.error(f"Could not load registries: {exc}")
        return

    st.markdown(
        "<p style='color:#c4b5fd;margin-bottom:20px;'>Define the <b>name</b>, "
        "<b>skills</b> it can use, and <b>channels</b> it will listen on.</p>",
        unsafe_allow_html=True,
    )

    pa_name = st.text_input(
        "\U0001f4cb Assistant Name",
        placeholder="e.g. Aria, Jarvis, Max\u2026",
        help="Pick a name you\'d naturally use when talking to this assistant.",
    )

    st.markdown("---")
    st.markdown("**\U0001f6e0\ufe0f Skills** &nbsp;<span style='color:#94a3b8;font-size:0.85rem'>What can this assistant do?</span>", unsafe_allow_html=True)
    skill_opts = list(AGENT_REGISTRY.keys())
    selected_skills = st.multiselect(
        "Skills",
        options=skill_opts,
        default=skill_opts,
        format_func=lambda s: f"{s.title()} \u2014 {AGENT_REGISTRY[s]['description'][:60]}\u2026",
        label_visibility="collapsed",
    )
    if not selected_skills:
        st.warning("At least one skill is required.")

    st.markdown("---")
    st.markdown("**\U0001f4e1 Channels** &nbsp;<span style='color:#94a3b8;font-size:0.85rem'>How will users talk to this assistant?  Selected channels will start automatically.</span>", unsafe_allow_html=True)
    ch_opts = list(CHANNEL_REGISTRY.keys())
    selected_channels = st.multiselect(
        "Channels",
        options=ch_opts,
        default=[],
        format_func=lambda c: f"{CHANNEL_REGISTRY[c].icon} {CHANNEL_REGISTRY[c].display_name} \u2014 {CHANNEL_REGISTRY[c].description[:50]}\u2026",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:700;color:#c4b5fd;margin-bottom:4px;'>✈️ Telegram Bot Token <span style='color:#f87171;'>*required</span></div>"
        "<div style='font-size:0.8rem;color:#64748b;margin-bottom:8px;'>Create a bot via <b>@BotFather</b> on Telegram and paste the token here.</div>",
        unsafe_allow_html=True,
    )
    tg_token_input = st.text_input(
        "Bot Token",
        placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        type="password",
        label_visibility="collapsed",
    )

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("\u2795 Create Assistant", type="primary", use_container_width=True):
            name = pa_name.strip()
            if not name:
                st.error("\u26a0\ufe0f Please enter a name for the assistant.")
            elif not selected_skills:
                st.error("\u26a0\ufe0f Select at least one skill.")
            elif not tg_token_input.strip():
                st.error("\u26a0\ufe0f A Telegram Bot Token is required. Get one from @BotFather on Telegram.")
            else:
                cfg = {"telegram": {"bot_token": tg_token_input.strip(), "auto_reply": True}}
                new_pa = create_assistant(name, selected_skills, selected_channels, config=cfg)
                # Auto-start the channels assigned to this PA
                _start_pa_channels(new_pa)
                # Auto-start the Telegram bot poller
                try:
                    from src.telegram.pa_poller_manager import start_pa_poller as _spp
                    _spp(new_pa["id"])
                except Exception as _tge:
                    st.warning(f"\u26a0\ufe0f Bot failed to start automatically: {_tge}")
                st.toast(f"✅ **{new_pa['name']}** created! Reload the page to see the new tab.", icon="✅")
                st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


# ── Per-PA chat panel ──────────────────────────────────────────────────────────

def _pa_k(pa_id: str, key: str) -> str:
    """Namespace a session_state key under a PA id."""
    return f"pa_{pa_id}_{key}"


# ── Google auth helpers ───────────────────────────────────────────────────────

def _is_gmail_ready() -> bool:
    """Check if a Gmail token exists on disk (fast, no API call)."""
    try:
        from src.email.gmail_service import is_gmail_authorized
        return is_gmail_authorized()
    except Exception:
        return False


def _reauth_gmail_ui(context: str = "", key_suffix: str = "") -> None:
    """
    Show a Gmail re-authorization panel in the chat.

    Displays the auth message (if any), a Re-authorize button that opens
    `setup_google_auth.py` in a new terminal, and a Retry hint.
    """
    import hashlib as _hl
    _btn_key = "reauth_btn_" + _hl.md5((context + key_suffix).encode()).hexdigest()[:8]

    if context:
        st.warning(context)
    else:
        st.warning(
            "🔑 **Gmail authorization required.**  \n"
            "Your Google token is missing or has expired."
        )

    if st.button("🔑 Re-authorize Gmail", key=_btn_key, type="primary"):
        try:
            from src.email.gmail_service import reset_gmail_client
            reset_gmail_client()  # clear cached client so next call retries
            project_root = Path(__file__).parent.parent.parent.parent.parent
            auth_script = project_root / "setup_google_auth.py"
            if sys.platform == "win32":
                subprocess.Popen(
                    [sys.executable, str(auth_script)],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen([sys.executable, str(auth_script)])
            st.success(
                "✅ **Authorization window opened.** \n\n"
                "Complete the Google sign-in in the new window, "
                "then come back and resend your message."
            )
        except Exception as exc:
            st.error(
                f"❌ Could not launch the auth script: {exc}  \n\n"
                f"Run manually: `python setup_google_auth.py`"
            )


def _render_pa_chat(pa: dict) -> None:
    """Render an independent chat panel for one Personal Assistant."""
    pa_id   = pa["id"]
    pa_name = pa["name"]
    pa_skills = set(pa.get("skills", []))

    mk = lambda key: _pa_k(pa_id, key)

    detect_agents_needed, run_workflow = _import_workflows()

    # ── Channel status bar ────────────────────────────────────────────────────
    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        pa_channels = pa.get("channels", [])
        if pa_channels:
            ch_objects = [(ch_name, CHANNEL_REGISTRY[ch_name])
                          for ch_name in pa_channels if ch_name in CHANNEL_REGISTRY]
            any_stopped = any(not ch.is_running() for _, ch in ch_objects)

            badge_cols = st.columns(len(ch_objects) + 1)
            for i, (ch_name, ch) in enumerate(ch_objects):
                running = ch.is_running()
                color  = "#16a34a" if running else "#dc2626"
                status = "Running" if running else "Stopped"
                with badge_cols[i]:
                    st.markdown(
                        f"<div style='background:#1a1a2e;border:1px solid {color};"
                        f"border-radius:10px;padding:8px 10px;text-align:center;'>"
                        f"<div style='font-size:1.25rem'>{ch.icon}</div>"
                        f"<div style='color:#e2e8f0;font-size:0.78rem;font-weight:600;"  
                        f"margin-top:2px'>{ch.display_name}</div>"
                        f"<div style='color:{color};font-size:0.7rem;margin-top:3px'>&#x25cf; {status}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
            with badge_cols[-1]:
                if any_stopped:
                    if st.button("\u25b6\ufe0f Start Channels",
                                 key=f"start_ch_{pa_id}", type="primary"):
                        _start_pa_channels(pa)
                        st.rerun()
                else:
                    st.markdown(
                        "<div style='color:#16a34a;padding:18px 4px;"
                        "font-size:0.82rem;font-weight:600'>\u2705 All channels running</div>",
                        unsafe_allow_html=True,
                    )
            st.divider()
        else:
            st.caption("No channels assigned \u2014 go to PA Settings to add one.")
            st.divider()
    except Exception as exc:
        logger.debug("Channel panel error: %s", exc)

    # ── Session state (per PA) ────────────────────────────────────────────────
    if mk("messages") not in st.session_state:
        skill_list = ", ".join(f"**{s.title()}**" for s in pa_skills) if pa_skills else "all skills"
        st.session_state[mk("messages")] = [{
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm **{pa_name}**, your Personal Assistant. "
                f"My skills: {skill_list}. "
                "Give me a command and I'll handle it! ⚡"
            ),
        }]
    if mk("processing") not in st.session_state:
        st.session_state[mk("processing")] = False
    if mk("command") not in st.session_state:
        st.session_state[mk("command")] = None
    if mk("count") not in st.session_state:
        st.session_state[mk("count")] = 0

    # ── Gmail first-time / expired token notice ───────────────────────────────
    # Shown persistently at the top of the chat whenever the email skill is
    # attached but no valid token exists — guides new users through setup.
    if "email" in pa_skills and not _is_gmail_ready():
        with st.container(border=True):
            st.markdown("##### 📧 Gmail Setup Required")
            _reauth_gmail_ui(
                "Gmail is not yet authorized for this assistant. "
                "Click below to open a browser sign-in window.",
                key_suffix=pa_id,
            )

    # ── Chat history ──────────────────────────────────────────────────────────
    for msg in st.session_state[mk("messages")]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Process pending command (before chat_input so spinner stays in chat) ──
    if st.session_state[mk("processing")] and st.session_state[mk("command")]:
        command = st.session_state[mk("command")]
        st.session_state[mk("command")] = None

        # User message was already appended to history before the rerun — the
        # for-loop above already rendered it, so we only need the assistant reply.
        agents_needed = detect_agents_needed(command)

        # Filter to only this PA's attached skills
        if agents_needed is not None and pa_skills:
            filtered = [a for a in agents_needed if a in pa_skills]
            if not filtered:
                # Required skill(s) are not attached to this PA — tell the user
                _missing = [a for a in agents_needed if a not in pa_skills]
                _m_str = " and ".join(f"**{s.title()}**" for s in _missing)
                _sfx = "s" if len(_missing) > 1 else ""
                _verb = "are" if len(_missing) > 1 else "is"
                _no_skill_reply = (
                    f"⚠️ This request needs the {_m_str} skill{_sfx}, "
                    f"which {_verb} not enabled for **{pa_name}**.\n\n"
                    f"Go to the **Configure** tab → **Skills** to enable it."
                )
                with st.chat_message("assistant"):
                    st.markdown(_no_skill_reply)
                st.session_state[mk("messages")].append({"role": "assistant", "content": _no_skill_reply})
                st.session_state[mk("processing")] = False
                st.rerun()
            agents_needed = filtered

        with st.chat_message("assistant"):
            # ── Conversational ────────────────────────────────────────────────
            if agents_needed is None:
                with st.spinner("Thinking…"):
                    reply = _chat_response(command, pa_name, pa_id)
                st.markdown(reply)
                st.session_state[mk("messages")].append({"role": "assistant", "content": reply})
                st.session_state[mk("processing")] = False
                st.rerun()

            # ── Single-skill shortcut ─────────────────────────────────────────
            if len(agents_needed) == 1:
                single_agent = agents_needed[0]
                icons  = {"drive": "📁", "email": "✉️", "files": "🗂️"}
                labels = {"drive": "Drive", "email": "Email", "files": "Files"}
                icon  = icons.get(single_agent, "🤖")
                label = labels.get(single_agent, single_agent.title())
                _result_status = "success"
                with st.spinner("Working on it…"):
                    try:
                        from src.agent.workflows.agent_registry import get_executor
                        executor = get_executor(single_agent)
                        # Skills are stateless — always agent_id=None
                        result = executor(command, agent_id=None) if executor else {"action": "error", "message": f"Skill '{single_agent}' not loaded."}
                        _result_status = result.get("status", "success")
                        action = result.get("action", "react_response")
                        if action == "react_response" or "message" in result:
                            reply = result.get("message", str(result))
                        else:
                            try:
                                import importlib
                                mod = importlib.import_module(f"src.agent.ui.{single_agent}_agent.app")
                                compose_fn = getattr(mod, f"_compose_{single_agent}_response", None)
                                reply = compose_fn(result, action, command) if compose_fn else str(result.get("message", result))
                            except Exception:
                                reply = str(result.get("message", result))
                    except Exception as exc:
                        logger.exception("Single-skill shortcut error: %s", exc)
                        reply = f"❌ Something went wrong: {exc}"

                # ── Auth error: show re-auth panel instead of the reply ────────
                if _result_status == "auth_error":
                    _reauth_gmail_ui(result.get("message", ""))
                    st.session_state[mk("messages")].append({
                        "role": "assistant",
                        "content": "🔑 Gmail authorization required — use the Re-authorize button above.",
                    })
                else:
                    st.markdown(reply)
                    st.session_state[mk("messages")].append({"role": "assistant", "content": reply})
                st.session_state[mk("processing")] = False
                st.rerun()

            # ── Multi-skill workflow ──────────────────────────────────────────
            result_placeholder = st.empty()
            step_lines: list[str] = []
            with st.status("⚡ Working on it…", expanded=True) as status_box:
                try:
                    run_result = run_workflow(command)
                    for sr in run_result.get("steps", []):
                        step_text = _render_step_result(sr)
                        st.markdown(step_text)
                        step_lines.append(step_text)
                    wf_status = run_result.get("status", "error")
                    label_map = {"success": ("✅ Done", "complete"),
                                 "partial": ("⚠️ Partially completed", "error")}
                    lbl, st_state = label_map.get(wf_status, ("❌ Something went wrong", "error"))
                    status_box.update(label=lbl, state=st_state)
                except Exception as exc:
                    logger.exception("Workflow execution error: %s", exc)
                    run_result = {"status": "error", "steps": [], "elapsed": 0, "plan": None, "summary": str(exc)}
                    status_box.update(label="❌ Unexpected error", state="error")
                    st.error(str(exc))

            final_text = _render_workflow_output(run_result, command)
            result_placeholder.markdown(final_text)

        # Record to PA-level memory (not skill-level)
        try:
            from src.agent.memory.agent_memory import get_agent_memory
            _mem = get_agent_memory(pa_id)
            _mem.add_interaction(
                command=command,
                action="multi_skill_workflow",
                result={
                    "status": run_result.get("status", "error"),
                    "agents": agents_needed,
                    "steps": len(run_result.get("steps", [])),
                },
                importance="High",
            )
            st.session_state[mk("count")] += 1
        except Exception as _mem_err:
            logger.debug("PA workflow memory record skipped: %s", _mem_err)

        st.session_state[mk("messages")].append({"role": "assistant", "content": final_text})
        st.session_state[mk("processing")] = False
        st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    user_input = st.chat_input(
        f"Ask {pa_name}…",
        key=f"chat_input_{pa_id}",
        disabled=st.session_state[mk("processing")],
    )
    if user_input:
        # Append to history immediately so it renders in the for-loop above
        # on the next rerun (above the chat input), not below it.
        st.session_state[mk("messages")].append({"role": "user", "content": user_input})
        st.session_state[mk("command")] = user_input
        st.session_state[mk("processing")] = True
        st.rerun()


# ── PA Settings ───────────────────────────────────────────────────────────────

def _render_pa_settings() -> None:
    """PA Settings tab — create / manage Personal Assistants, Skills, Channels."""

    st.markdown("## ⚙️ Personal Assistant Settings")

    # ── Create New Assistant ──────────────────────────────────────────────────
    with st.expander("✨ Create New Assistant", expanded=False):
        try:
            from src.agent.workflows.agent_registry import AGENT_REGISTRY
            from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        except Exception as exc:
            st.error(f"Could not load registries: {exc}")
            return

        with st.form("create_pa_form", clear_on_submit=True):
            pa_name_input = st.text_input("Assistant Name", placeholder="e.g. Aria, Jarvis, Max…")
            skill_opts = list(AGENT_REGISTRY.keys())
            selected_skills = st.multiselect(
                "Attach Skills",
                options=skill_opts,
                default=skill_opts,
                format_func=lambda s: f"{s.title()} — {AGENT_REGISTRY[s]['description'][:60]}…",
            )
            channel_opts = list(CHANNEL_REGISTRY.keys())
            selected_channels = st.multiselect(
                "Attach Channels",
                options=channel_opts,
                default=channel_opts,
                format_func=lambda c: f"{CHANNEL_REGISTRY[c].icon} {CHANNEL_REGISTRY[c].display_name}",
            )
            tg_token_settings = st.text_input(
                "✈️ Telegram Bot Token *",
                placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                type="password",
                help="Required. Create a bot via @BotFather on Telegram.",
            )
            submitted = st.form_submit_button("➕ Create Assistant", type="primary")
            if submitted:
                name = pa_name_input.strip()
                if not name:
                    st.error("Please enter a name.")
                elif not selected_skills:
                    st.error("Attach at least one skill.")
                elif not tg_token_settings.strip():
                    st.error("⚠️ A Telegram Bot Token is required. Get one from @BotFather on Telegram.")
                else:
                    cfg = {"telegram": {"bot_token": tg_token_settings.strip(), "auto_reply": True}}
                    new_pa = create_assistant(name, selected_skills, selected_channels, config=cfg)
                    try:
                        from src.telegram.pa_poller_manager import start_pa_poller as _spp2
                        _spp2(new_pa["id"])
                    except Exception as _tge2:
                        st.warning(f"⚠️ Bot failed to start: {_tge2}")
                    st.toast(f"✅ Created **{new_pa['name']}**. Reload the page to see the new tab.", icon="✅")
                    st.rerun()

    st.divider()

    # ── Existing Assistants ───────────────────────────────────────────────────
    st.markdown("### 🤖 Your Personal Assistants")
    assistants = load_assistants()
    for pa in assistants:
        with st.container():
            col_info, col_del = st.columns([5, 1])
            with col_info:
                skill_badges = " ".join(
                    f"<span style='background:#4c1d95;color:#ddd8fe;padding:2px 8px;"
                    f"border-radius:10px;font-size:0.75rem;margin:2px'>{s.title()}</span>"
                    for s in pa.get("skills", [])
                )
                st.markdown(
                    f"<div style='padding:10px 0;border-bottom:1px solid #334155;'>"
                    f"<b style='color:#e2e8f0;font-size:1rem'>{pa['name']}</b>"
                    f"<span style='color:#64748b;font-size:0.78rem;margin-left:8px'>{pa['id']}</span>"
                    f"<div style='margin-top:6px'>{skill_badges}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_del:
                if len(assistants) > 1:
                    if st.button("🗑️", key=f"del_{pa['id']}", help=f"Delete {pa['name']}"):
                        if delete_assistant(pa["id"]):
                            st.toast(f"🗑️ Deleted {pa['name']}. Reload to update tabs.", icon="🗑️")
                            st.rerun()
                        else:
                            st.error("Could not delete.")

    st.divider()

    # ── Skills ────────────────────────────────────────────────────────────────
    st.markdown("### 🛠️ Available Skills")
    st.caption("Skills are stateless executors — they have no memory. "
               "All context and history live in the Personal Assistant.")

    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        for skill_name, info in AGENT_REGISTRY.items():
            st.markdown(
                f"<div style='padding:6px 0;border-bottom:1px solid #1e293b;'>"
                f"<b style='color:#e2e8f0'>{skill_name.title()}</b>"
                f"<span style='color:#94a3b8;margin-left:12px;font-size:0.85rem'>"
                f"{info.get('description','')}</span></div>",
                unsafe_allow_html=True,
            )
    except Exception as exc:
        st.error(f"Could not load Skills registry: {exc}")

    st.divider()

    # ── Channels ──────────────────────────────────────────────────────────────
    st.markdown("### 📡 Channels")
    st.caption("Channels are communication interfaces. Each runs independently.")

    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        for ch_name, ch in CHANNEL_REGISTRY.items():
            running = ch.is_running()
            badge = (
                "<span style='background:#16a34a;color:#fff;"
                "padding:2px 10px;border-radius:12px;font-size:0.78rem'>● Running</span>"
                if running else
                "<span style='background:#dc2626;color:#fff;"
                "padding:2px 10px;border-radius:12px;font-size:0.78rem'>● Stopped</span>"
            )
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:12px;"
                f"padding:8px 0;border-bottom:1px solid #334155;'>"
                f"<span style='font-size:1.4rem'>{ch.icon}</span>"
                f"<div style='flex:1'><b style='color:#e2e8f0'>{ch.display_name}</b>"
                f"<span style='color:#94a3b8;margin-left:10px;font-size:0.82rem'>{ch.description}</span>"
                f"</div>{badge}</div>",
                unsafe_allow_html=True,
            )
            try:
                s = ch.status()
                parts = []
                if s.port: parts.append(f"Port {s.port}")
                if s.pid:  parts.append(f"PID {s.pid}")
                if s.detail: parts.append(s.detail)
                if parts: st.caption("  " + " · ".join(parts))
            except Exception:
                pass
    except Exception as exc:
        st.error(f"Could not load Channel registry: {exc}")


def _render_pa_configure(pa: dict) -> None:
    """Configure tab for a single PA — edit skills and channels in place."""
    from src.agent.hub.pa_manager import update_assistant, load_assistants

    # Always reload the freshest version from disk
    fresh = next((a for a in load_assistants() if a["id"] == pa["id"]), pa)

    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        skill_opts   = list(AGENT_REGISTRY.keys())
        channel_opts = list(CHANNEL_REGISTRY.keys())
    except Exception as exc:
        st.error(f"Could not load registries: {exc}")
        return

    st.markdown(
        f"<div style='font-size:1.2rem;font-weight:800;color:#a78bfa;margin-bottom:16px;'>"
        f"⚙️ Configure &nbsp; <span style='color:#c4b5fd'>{fresh['name']}</span></div>",
        unsafe_allow_html=True,
    )

    with st.form(f"configure_pa_{fresh['id']}"):
        new_name = st.text_input("Assistant Name", value=fresh["name"])

        new_skills = st.multiselect(
            "🛠️ Skills",
            options=skill_opts,
            default=[s for s in fresh.get("skills", []) if s in skill_opts],
            format_func=lambda s: f"{s.title()} — {AGENT_REGISTRY[s].get('description','')[:60]}",
            help="Skills are stateless executors. Memory lives at the PA level.",
        )

        new_channels = st.multiselect(
            "📡 Channels",
            options=channel_opts,
            default=[c for c in fresh.get("channels", []) if c in channel_opts],
            format_func=lambda c: f"{CHANNEL_REGISTRY[c].icon} {CHANNEL_REGISTRY[c].display_name}",
            help="Channels the assistant will listen on.",
        )

        # ── Telegram config (matches config/settings.json structure) ────────────
        st.markdown(
            "<div style='font-size:0.88rem;color:#c4b5fd;font-weight:600;margin:14px 0 4px'>"
            "✈️ Telegram Bot</div>"
            "<div style='font-size:0.8rem;color:#64748b;margin-bottom:6px;'>"
            "Create a bot via @BotFather on Telegram. Each assistant runs its own dedicated bot."
            "</div>",
            unsafe_allow_html=True,
        )
        _tg_cfg = (fresh.get("config") or {}).get("telegram", {})
        new_token = st.text_input(
            "Bot Token",
            value=_tg_cfg.get("bot_token", ""),
            placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            type="password",
        )
        new_auto_reply = st.checkbox(
            "Auto-reply enabled",
            value=_tg_cfg.get("auto_reply", True),
            help="Automatically reply to inbound Telegram messages using the AI.",
        )
        _default_persona = (
            f"You are {fresh['name']}, a friendly AI assistant built with OctaMind. "
            "Keep replies concise (2-3 sentences max) and conversational."
        )
        new_persona = st.text_area(
            "Auto-reply Persona",
            value=_tg_cfg.get("auto_reply_persona", _default_persona),
            height=80,
            help="System prompt that shapes how your bot speaks in Telegram replies.",
        )

        saved = st.form_submit_button("💾 Save Changes", type="primary")
        if saved:
            if not new_name.strip():
                st.error("Name cannot be empty.")
            elif not new_skills:
                st.error("Attach at least one skill.")
            else:
                # Merge full Telegram config block (mirrors config/settings.json structure)
                cfg = dict(fresh.get("config") or {})
                tg_cfg = dict(cfg.get("telegram") or {})
                if new_token.strip():
                    tg_cfg["bot_token"] = new_token.strip()
                elif "bot_token" in tg_cfg:
                    del tg_cfg["bot_token"]
                tg_cfg["auto_reply"] = new_auto_reply
                tg_cfg["auto_reply_persona"] = new_persona.strip()
                if tg_cfg:
                    cfg["telegram"] = tg_cfg
                elif "telegram" in cfg:
                    del cfg["telegram"]
                update_assistant(
                    fresh["id"],
                    name=new_name.strip(),
                    skills=new_skills,
                    channels=new_channels,
                    config=cfg,
                )
                st.toast(f"✅ Configuration saved for **{new_name.strip()}**!", icon="✅")
                st.rerun()

    st.divider()

    # ── Read-only skill reference ─────────────────────────────────────────────
    st.markdown("**Available Skills**")
    for skill_name, info in AGENT_REGISTRY.items():
        active = skill_name in fresh.get("skills", [])
        dot = "<span style='color:#16a34a'>●</span>" if active else "<span style='color:#4b5563'>●</span>"
        st.markdown(
            f"<div style='padding:4px 0;border-bottom:1px solid #1e293b;font-size:0.88rem;'>"
            f"{dot} <b style='color:#e2e8f0'>{skill_name.title()}</b>"
            f"<span style='color:#94a3b8;margin-left:10px'>{info.get('description','')}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Channel status ────────────────────────────────────────────────────────
    st.markdown("**Channel Status**")

    # Telegram: show per-PA poller status and start/stop
    tg_token = (fresh.get("config") or {}).get("telegram", {}).get("bot_token", "").strip()
    try:
        from src.telegram.pa_poller_manager import get_pa_poller_status, start_pa_poller, stop_pa_poller
        tg_status = get_pa_poller_status(fresh["id"])
        tg_running = tg_status is not None
    except Exception:
        tg_running = False
        tg_status = None
    # ── Telegram row with inline Start / Stop button ─────────────────────────
    tg_badge = (
        "<span style='background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Running</span>"
        if tg_running else
        "<span style='background:#4b5563;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Stopped</span>"
    )
    tg_info = (
        "Token configured" if tg_token
        else "⚠️ Enter a token above and click Save to enable"
    )
    tg_row_col, tg_btn_col = st.columns([3, 1])
    with tg_row_col:
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:8px 0;"
            f"border-bottom:1px solid #1e293b;'>"
            f"<span style='font-size:1.2rem'>✈️</span>"
            f"<div style='flex:1'><b style='color:#e2e8f0'>Telegram Bot</b>"
            f"<span style='color:#94a3b8;margin-left:8px;font-size:0.82rem'>{tg_info}</span>"
            f"</div>{tg_badge}</div>",
            unsafe_allow_html=True,
        )
    with tg_btn_col:
        if tg_token:
            if not tg_running:
                if st.button("▶️ Start", key=f"start_tg_{fresh['id']}", use_container_width=True, type="primary"):
                    try:
                        start_pa_poller(fresh["id"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
            else:
                if st.button("⏹️ Stop", key=f"stop_tg_{fresh['id']}", use_container_width=True):
                    try:
                        stop_pa_poller(fresh["id"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

    # ── Other channels from registry (telegram excluded — handled above) ──────
    for ch_name, ch in CHANNEL_REGISTRY.items():
        if ch_name == "telegram":
            continue   # already rendered with Start/Stop controls above
        active = ch_name in fresh.get("channels", [])
        running = ch.is_running()
        state_badge = (
            "<span style='background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Running</span>"
            if running else
            "<span style='background:#4b5563;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Stopped</span>"
        )
        assigned = "<span style='color:#a78bfa;font-size:0.75rem;margin-left:6px'>(assigned)</span>" if active else ""
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid #1e293b;'>"
            f"<span style='font-size:1.2rem'>{ch.icon}</span>"
            f"<div style='flex:1'><b style='color:#e2e8f0'>{ch.display_name}</b>{assigned}"
            f"<span style='color:#94a3b8;margin-left:8px;font-size:0.82rem'>{ch.description}</span></div>"
            f"{state_badge}</div>",
            unsafe_allow_html=True,
        )


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    logger.debug("=== MULTI-AGENT MAIN() CALLED ===")
    agent_id = os.getenv("AGENT_ID", "__multi_agent__")

    # ── Single-PA mode: launched by process_manager for a specific PA ─────────
    pa_id_filter = os.getenv("PA_ID", "").strip()
    all_assistants = load_assistants()
    single_pa = None
    if pa_id_filter:
        single_pa = next((a for a in all_assistants if a["id"] == pa_id_filter), None)
        if single_pa:
            agent_id = single_pa["id"]
            assistants = [single_pa]
        else:
            assistants = all_assistants
    else:
        assistants = all_assistants

    st.set_page_config(
        page_title=f"{single_pa['name']} — OctaMind" if single_pa else "Personal Assistants — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex="#7c3aed", accent_rgb="124,58,237")

    # ── Single-PA mode: Chat + Live Channels + Configure tabs ─────────────────
    if single_pa:
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg, rgba(124,58,237,0.18) 0%, rgba(139,92,246,0.12) 100%);
                       border:1.5px solid rgba(124,58,237,0.5);padding:20px 24px;border-radius:16px;margin-bottom:24px;
                       backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(124,58,237,0.15);">
              <div style="display:flex;align-items:center;gap:16px;">
                <img src="{_logo_b64()}" style="width:56px;height:56px;border-radius:14px;object-fit:cover;box-shadow:0 4px 15px rgba(124,58,237,0.4);">
                <div>
                  <div style="font-size:1.9rem;font-weight:900;line-height:1.1;background:linear-gradient(135deg,#8b5cf6 0%,#7c3aed 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
                    🤖 {single_pa['name']}
                  </div>
                  <div style="font-size:0.9rem;color:#c4b5fd;margin-top:4px;">
                    {len(single_pa.get('skills', []))} skills &nbsp;•&nbsp; {len(single_pa.get('channels', []))} channels
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        tab_chat, tab_live, tab_cfg = st.tabs(["💬 Chat", "📡 Live Channels", "⚙️ Configure"])
        with tab_chat:
            _render_pa_chat(single_pa)
        with tab_live:
            _render_live_channels()
        with tab_cfg:
            _render_pa_configure(single_pa)
        return

    # ── Header ────────────────────────────────────────────────────────────────
    pa_subtitle = " &nbsp;•&nbsp; ".join(pa["name"] for pa in assistants)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(124,58,237,0.18) 0%, rgba(139,92,246,0.12) 100%);
                   border:1.5px solid rgba(124,58,237,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(124,58,237,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(124,58,237,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;line-height:1.1;background:linear-gradient(135deg,#8b5cf6 0%,#7c3aed 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">OctaMind</div>
              <div style="font-size:1.05rem;color:#c4b5fd;margin-top:6px;font-weight:600;">
                🤖 Personal Assistants &nbsp;•&nbsp; {pa_subtitle}
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#c4b5fd;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(124,58,237,0.3);">
            Each assistant has its own memory, skills, and channels. Select a tab to chat. ✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        # Prominent create button at the top
        if st.button("\u2795 New Assistant", use_container_width=True, type="primary"):
            _create_pa_dialog()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:12px 0 4px;font-weight:600;"
            "letter-spacing:0.06em;text-transform:uppercase;'>\U0001f916 Your Assistants</p>",
            unsafe_allow_html=True,
        )
        for pa in assistants:
            skill_count   = len(pa.get("skills", []))
            ch_count      = len(pa.get("channels", []))
            pa_channels   = pa.get("channels", [])
            try:
                from src.agent.hub.channel_registry import CHANNEL_REGISTRY
                ch_running = sum(
                    1 for c in pa_channels
                    if c in CHANNEL_REGISTRY and CHANNEL_REGISTRY[c].is_running()
                )
                ch_dot = (
                    "<span style='color:#16a34a'>&#x25cf;</span>"
                    if ch_running == ch_count and ch_count > 0
                    else ("<span style='color:#f59e0b'>&#x25cf;</span>" if ch_running > 0 else "<span style='color:#dc2626'>&#x25cf;</span>")
                )
            except Exception:
                ch_dot = ""
            st.markdown(
                f"<div style='font-size:0.82rem;color:#a8dadc;padding:4px 0;"
                f"border-bottom:1px solid rgba(124,58,237,0.15);'>"
                f"{ch_dot} <b>{pa['name']}</b>"
                f"<span style='color:#64748b;margin-left:6px'>{skill_count} skills "
                f"\u00b7 {ch_count} ch</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if st.button("\U0001f4d6 Usage Guide", use_container_width=True, type="secondary"):
            _show_multi_agent_guide()

        st.markdown("---")
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:8px 0 4px;font-weight:600;"
            "letter-spacing:0.06em;text-transform:uppercase;'>🟢 Active Agents</p>",
            unsafe_allow_html=True,
        )
        running = get_running_agents()
        agent_agents = [a for a in running if a.get("id") != "__multi_agent__"]
        if agent_agents:
            for a in agent_agents:
                atype = a.get("type") or a.get("agent_type", "agent")
                aname = a.get("name", atype.title())
                aurl = a.get("url", "")
                icon = "📁" if "drive" in atype.lower() else (
                    "✉️" if "email" in atype.lower() else "🤖")
                link = f'<a href="{aurl}" target="_blank" style="color:#c4b5fd;">{aname}</a>' if aurl else aname
                st.markdown(
                    f"<div style='font-size:0.82rem;color:#a8dadc;padding:3px 0;'>"
                    f"{icon} {link}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div style='font-size:0.8rem;color:#888;'>No agents detected</div>",
                unsafe_allow_html=True,
            )

    # ── Dynamic tabs: one per PA + Live Channels + PA Settings ───────────────
    pa_tab_labels = [f"🤖 {pa['name']}" for pa in assistants]
    all_tab_labels = pa_tab_labels + ["📡 Live Channels", "⚙️ PA Settings"]
    all_tabs = st.tabs(all_tab_labels)

    for i, pa in enumerate(assistants):
        with all_tabs[i]:
            _render_pa_chat(pa)

    with all_tabs[-2]:
        _render_live_channels()

    with all_tabs[-1]:
        _render_pa_settings()
