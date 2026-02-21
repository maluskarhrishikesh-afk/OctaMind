"""
Multi-Agent Chat UI — Streamlit page.

Handles cross-agent commands that involve both the Drive Agent and Email Agent.
Commands are analysed → plan is shown → steps execute sequentially with live
progress tracking → results summarised.

Accent: purple (#7c3aed / rgb 124,58,237)
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from ..dashboard.styles import inject_agent_css
from .helpers import _logo_b64, _logo_icon, _start_browser_watchdog, get_running_agents

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("multi_agent")
logger.setLevel(logging.DEBUG)

_log_file = Path(__file__).parent.parent.parent.parent / "multi_agent.log"
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

# ── Lazy workflow imports ────────────────────────────────────────────────────
def _import_workflows():
    from src.agent.workflows import detect_agents_needed, run_workflow
    return detect_agents_needed, run_workflow


# ── Usage Guide dialog ───────────────────────────────────────────────────────
@st.dialog("📖 Multi-Agent Usage Guide", width="large")
def _show_multi_agent_guide() -> None:
    st.markdown("""
## ⚡ What is Multi-Agent Chat?

Multi-Agent Chat lets you give **combined Drive + Email commands** in a single
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
- Multi-agent commands work best when **both** agents are running (check the sidebar).
    """)


# ── Formatting helpers ───────────────────────────────────────────────────────

def _format_step_badge(agent: str) -> str:
    if agent == "drive":
        return "📁 Drive"
    elif agent == "email":
        return "✉️ Email"
    return f"🤖 {agent.title()}"


def _render_step_result(step_result: dict) -> str:
    """Build a markdown string for one step result."""
    status_icon = "✅" if step_result["status"] == "success" else "❌"
    agent = step_result.get("agent", "?")
    tool = step_result.get("tool", "?")
    label = _format_step_badge(agent)
    lines = [f"{status_icon} **{label}** — `{tool}`"]
    if step_result["status"] == "error":
        lines.append(f"   ⚠️ {step_result.get('error', 'Unknown error')}")
    return "\n".join(lines)


def _render_workflow_output(run_result: dict) -> str:
    """Build the full assistant message for a completed workflow."""
    status = run_result.get("status", "error")
    plan = run_result.get("plan")
    steps = run_result.get("steps", [])
    elapsed = run_result.get("elapsed", 0)

    parts = []

    if status == "success":
        parts.append("✅ **Workflow completed successfully!**")
    elif status == "partial":
        parts.append("⚠️ **Workflow partially completed** — one or more steps failed.")
    else:
        parts.append("❌ **Workflow failed.**")

    if plan:
        parts.append(f"\n**Plan:** {plan.command}")

    parts.append(f"\n**Steps executed** ({len(steps)}) in {elapsed:.1f}s:\n")
    for r in steps:
        parts.append(_render_step_result(r))

    if status == "error" and not steps:
        parts.append("\nCould not create a plan for this command. Try rephrasing it.")

    return "\n".join(parts)


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    logger.debug("=== MULTI-AGENT MAIN() CALLED ===")
    agent_id = os.getenv("AGENT_ID", "__multi_agent__")
    agent_name = os.getenv("AGENT_NAME", "Multi-Agent Hub")

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex="#7c3aed", accent_rgb="124,58,237")

    # ── Session state ─────────────────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm the **{agent_name}**. "
                "Give me commands that span your **Drive** and **Email** agents — "
                "for example: *'Download the Q3 report and email it to alice@example.com'*. "
                "I'll plan and execute the steps automatically! ⚡"
            ),
        }]

    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False

    if "pending_command" not in st.session_state:
        st.session_state.pending_command = None

    # ── Header ────────────────────────────────────────────────────────────────
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
                ⚡ {agent_name} &nbsp;•&nbsp; Drive + Email
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#c4b5fd;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(124,58,237,0.3);">
            Give me a command that spans Drive and Email — I'll plan and execute it automatically! ✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        if st.button("📖 Full Usage Guide", use_container_width=True, type="secondary"):
            _show_multi_agent_guide()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:12px 0 4px;font-weight:600;"
            "letter-spacing:0.06em;text-transform:uppercase;'>⚡ Example Commands</p>",
            unsafe_allow_html=True,
        )
        examples = [
            "📁→✉️ Download Q3 report and email to alice@example.com",
            "📊→✉️ Email me a Drive storage report",
            "✉️→📁 Save attachment from email {id} to Drive",
        ]
        for ex in examples:
            st.markdown(
                f"<div style='font-size:0.78rem;color:#a8dadc;padding:4px 0;"
                f"border-bottom:1px solid rgba(124,58,237,0.15);'>{ex}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:8px 0 4px;font-weight:600;"
            "letter-spacing:0.06em;text-transform:uppercase;'>🟢 Active Agents</p>",
            unsafe_allow_html=True,
        )
        running = get_running_agents()
        # Exclude the multi-agent hub itself from the badge list
        agent_agents = [a for a in running if a.get("id") != "__multi_agent__"]
        if agent_agents:
            for a in agent_agents:
                atype = a.get("type") or a.get("agent_type", "agent")
                aname = a.get("name", atype.title())
                aurl = a.get("url", "")
                icon = "📁" if "drive" in atype.lower() else ("✉️" if "email" in atype.lower() else "🤖")
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

    # ── Chat history ──────────────────────────────────────────────────────────
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ────────────────────────────────────────────────────────────
    user_input = st.chat_input(
        "Type a cross-agent command…",
        disabled=st.session_state.is_processing,
    )

    if user_input:
        st.session_state.pending_command = user_input
        st.session_state.is_processing = True
        st.rerun()

    # ── Process pending command ───────────────────────────────────────────────
    if st.session_state.is_processing and st.session_state.pending_command:
        command = st.session_state.pending_command
        st.session_state.pending_command = None

        # Add user message to history
        st.session_state.chat_messages.append({"role": "user", "content": command})

        detect_agents_needed, run_workflow = _import_workflows()

        with st.chat_message("user"):
            st.markdown(command)

        with st.chat_message("assistant"):
            # Show routing info first
            agents_needed = detect_agents_needed(command)
            if agents_needed:
                agent_labels = " + ".join(
                    ("📁 Drive" if a == "drive" else "✉️ Email") for a in agents_needed
                )
                st.markdown(f"🔀 **Routing:** {agent_labels}")

            # Execute with live step display
            result_placeholder = st.empty()
            step_lines: list[str] = []

            with st.status("⚡ Executing workflow…", expanded=True) as status_box:
                try:
                    # Run the workflow (blocking — each step runs in sequence)
                    run_result = run_workflow(command)

                    executed_steps = run_result.get("steps", [])
                    for sr in executed_steps:
                        step_text = _render_step_result(sr)
                        st.markdown(step_text)
                        step_lines.append(step_text)

                    wf_status = run_result.get("status", "error")
                    if wf_status == "success":
                        status_box.update(label="✅ Workflow complete", state="complete")
                    elif wf_status == "partial":
                        status_box.update(label="⚠️ Workflow partial", state="error")
                    else:
                        status_box.update(label="❌ Workflow failed", state="error")

                except Exception as exc:
                    logger.exception("Workflow execution error: %s", exc)
                    run_result = {
                        "status": "error",
                        "steps": [],
                        "elapsed": 0,
                        "plan": None,
                        "summary": str(exc),
                    }
                    status_box.update(label="❌ Unexpected error", state="error")
                    st.error(str(exc))

            # Render final assistant output
            final_text = _render_workflow_output(run_result)
            result_placeholder.markdown(final_text)

        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": final_text,
        })
        st.session_state.is_processing = False
        st.rerun()
