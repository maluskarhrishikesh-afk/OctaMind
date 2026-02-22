"""
Email Agent UI — main Streamlit entry point.

Sets up the logger, imports the modular sub-components, and runs the
Streamlit rendering loop.
"""
from __future__ import annotations
from .orchestrator import execute_with_llm_orchestration
from .conversation import handle_conversation
from .helpers import _logo_b64, _logo_icon, _logo_path, _logo_pinkraven, _start_browser_watchdog
from src.email import get_inbox_count
import streamlit as st
from ..dashboard.styles import inject_agent_css

# ── Logging (must be first) ───────────────────────────────────────────────────
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Configure module logger
logger = logging.getLogger("email_agent")
logger.setLevel(logging.DEBUG)

_log_file = Path(__file__).parent.parent.parent.parent.parent / "email_agent.log"
_file_handler = logging.FileHandler(_log_file, encoding="utf-8", mode="a")
_file_handler.setLevel(logging.DEBUG)
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
_file_handler.setFormatter(_formatter)
_console_handler.setFormatter(_formatter)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..")))


@st.dialog("📖 Full Email Usage Guide", width="large")
def _show_email_guide() -> None:
    st.markdown("""
## 📥 Read & Search
| Command | Description |
|---------|-------------|
| `List 5 unread emails` | Show your latest unread messages |
| `Show emails from john@example.com` | Filter by sender |
| `What emails did I get today?` | Today's inbox |
| `Find emails with subject "invoice"` | Subject-line search |
| `Show emails with label:starred` | Filter by Gmail label |

## ✉️ Send & Draft
| Command | Description |
|---------|-------------|
| `Send email to alice@example.com subject "Hi" body "Hello"` | Send immediately |
| `Draft an email to bob@example.com about project update` | Save as draft |
| `Show my drafts` | List saved drafts |
| `Send draft <draft_id>` | Dispatch a saved draft |

## 🗑️ Delete
| Command | Description |
|---------|-------------|
| `Delete 5 emails` | Trash the 5 oldest matching emails |
| `Remove 3 unread emails` | Trash unread messages |
| `Delete emails from spam@example.com` | Bulk delete by sender |
| `Trash all emails from LinkedIn` | Domain-level cleanup |

## 🧠 Summarise & Tasks
| Command | Description |
|---------|-------------|
| `Summarize email <message_id>` | AI summary of an email |
| `Generate my daily email digest` | Digest of today's messages |
| `What tasks do I have in email <id>?` | Extract action items |
| `Show my saved tasks` | List all extracted tasks |
| `Mark task <task_id> as complete` | Update task status |

## 💬 Reply & Smart Labels
| Command | Description |
|---------|-------------|
| `Suggest how I should reply to email <id>` | AI reply draft |
| `Reply yes to email <message_id>` | Quick affirmative reply |
| `Auto-label my recent emails` | AI-powered inbox organisation |
| `Show me urgent emails` | Highlight high-priority messages |

## 📅 Calendar & Follow-ups
| Command | Description |
|---------|-------------|
| `Extract calendar events from email <id>` | Pull dates/times as events |
| `Remind me to follow up on email <id> in 3 days` | Set a follow-up reminder |
| `What follow-ups do I have pending?` | List open reminders |
| `Export the event from email <id> to ICS` | Download calendar file |

## ⏰ Scheduling
| Command | Description |
|---------|-------------|
| `Schedule email to alice@example.com for tomorrow 9am` | Timed delivery |
| `Show my scheduled emails` | List queued sends |
| `Reschedule email <id> to Monday 10am` | Change send time |
| `Cancel scheduled email <id>` | Remove from queue |

## 👥 Contacts & Newsletters
| Command | Description |
|---------|-------------|
| `Who do I email most frequently?` | Top contacts by frequency |
| `Export my contacts to CSV` | Download contacts list |
| `Give me a summary for john@example.com` | Contact profile |
| `Find newsletters in my inbox` | Identify subscription emails |
| `How do I unsubscribe from email <id>?` | Unsubscribe guidance |

## 📊 Analytics & Reports
| Command | Description |
|---------|-------------|
| `Show my email stats for the last 30 days` | Volume and trend metrics |
| `Give me email productivity insights` | AI productivity analysis |
| `Generate my weekly email report` | Weekly summary report |
| `Show email patterns for the last 30 days` | Behavioural patterns |

## 💡 Tips
- Include words like **email**, **inbox**, or **message** in commands so the agent recognises email tasks.
- Use `<message_id>` from list results to act on specific emails.
- Bulk operations (delete, label) respect the `Max operations` setting in ⚙️ Settings.
    """)


# ── Optional integrations ─────────────────────────────────────────────────────
try:
    from src.agent.memory.agent_memory import get_agent_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False

try:
    from src.agent.core.agent_manager import get_agent_manager
    AGENT_MANAGER_AVAILABLE = True
except Exception:
    AGENT_MANAGER_AVAILABLE = False


def _compose_email_response(result: dict, action: str, original_command: str) -> str:
    """Pass raw Email result directly to LLM for friendly composition."""
    import json as _json
    from src.agent.llm.llm_parser import get_llm_client

    if action == "react_response":
        return result.get("message", "Done.")  # Already LLM-composed by ReAct loop

    composition_prompt = f"""The user asked: "{original_command}"

A Gmail operation was executed. Here is the raw result:

{_json.dumps(result, indent=2, default=str)}

Compose a response following these formatting rules:
- Write in a friendly, conversational tone like a helpful assistant
- Use **bold** for important names, subjects, senders, and counts
- Use bullet points or numbered lists to present multiple emails
- Use tables (markdown) when listing emails with sender, subject, date columns
- Use relevant emojis to make the response visually engaging (e.g. 📬 inbox, ✉️ emails, 📤 sent, 🗑️ deleted, 📎 attachments, ✅ success)
- Add a brief summary sentence at the start so the user knows what happened
- For email lists, always show: sender name/address, subject line, and date
- Include message IDs only when the user might need them to act on specific emails
- Do NOT show raw JSON keys or technical internals"""

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
        logger.warning("Email response composition failed: %s", exc)
        return f"✅ Email operation `{action}` completed."


# ── Streamlit ─────────────────────────────────────────────────────────────────


def main() -> None:  # noqa: C901 (complexity — intentional for a Streamlit app)
    logger.debug("=== MAIN() CALLED ===")
    agent_id = os.getenv("AGENT_ID", "gmail_agent_default")
    agent_name = os.getenv("AGENT_NAME", "Email Assistant")

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex="#e91e8c", accent_rgb="233,30,140")

    # Start automation scheduler (once per process, runs in background thread)
    try:
        from src.agent.core.automation_scheduler import start_scheduler
        _sched = start_scheduler(agent_id)  # noqa: F841
    except Exception as _sched_err:
        logger.warning("Automation scheduler could not start: %s", _sched_err)

    if "agent_id" not in st.session_state:
        st.session_state.agent_id = agent_id

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(156,39,176,0.18) 0%, rgba(233,30,140,0.12) 100%);
                   border:1.5px solid rgba(233,30,140,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(233,30,140,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(233,30,140,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;color:#e91e8c;line-height:1.1;background:linear-gradient(135deg, #e91e8c 0%, #c5068e 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">OctaMind</div>
              <div style="font-size:1.05rem;color:#a8dadc;margin-top:6px;font-weight:600;">
                📧 {agent_name} &nbsp;•&nbsp; Gmail Agent
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#a8dadc;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(233,30,140,0.3);">
            Give me commands in natural language, and I'll handle your emails! ️✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        if st.button("📖 Full Usage Guide", use_container_width=True, type="secondary"):
            _show_email_guide()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 4px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>⚡ Quick Commands</p>",
            unsafe_allow_html=True,
        )

        with st.expander("📥 Read & Search"):
            st.markdown("""
- `List 5 unread emails`
- `Show emails from john@example.com`
- `What emails did I get today?`
- `Find emails with subject "invoice"`
- `Show emails with label:starred`
""")
        with st.expander("✉️ Send & Draft"):
            st.markdown("""
- `Send email to alice@example.com subject "Hi" body "Hello"`
- `Draft an email to bob@example.com about project update`
- `Show my drafts` · `Send draft <draft_id>`
""")
        with st.expander("🗑️ Delete"):
            st.markdown("""
- `Delete 5 emails`
- `Remove 3 unread emails`
- `Delete emails from spam@example.com`
- `Trash all emails from LinkedIn`
""")
        with st.expander("🧠 Summarize & Tasks"):
            st.markdown("""
- `Summarize email <message_id>`
- `Generate my daily email digest`
- `What tasks do I have in email <id>?`
- `Show my saved tasks`
- `Mark task <task_id> as complete`
""")
        with st.expander("💬 Reply & Smart Labels"):
            st.markdown("""
- `Suggest how I should reply to email <id>`
- `Reply yes to email <message_id>`
- `Auto-label my recent emails`
- `Show me urgent emails`
""")
        with st.expander("📅 Calendar & Follow-ups"):
            st.markdown("""
- `Extract calendar events from email <id>`
- `Remind me to follow up on email <id> in 3 days`
- `What follow-ups do I have pending?`
- `Export the event from email <id> to ICS`
""")
        with st.expander("⏰ Scheduling"):
            st.markdown("""
- `Schedule email to alice@example.com for tomorrow 9am`
- `Show my scheduled emails`
- `Reschedule email <id> to Monday 10am`
- `Cancel scheduled email <id>`
""")
        with st.expander("👥 Contacts & Newsletters"):
            st.markdown("""
- `Who do I email most frequently?`
- `Export my contacts to CSV`
- `Give me a summary for john@example.com`
- `Find newsletters in my inbox`
- `How do I unsubscribe from email <id>?`
""")
        with st.expander("📊 Analytics & Reports"):
            st.markdown("""
- `Show my email stats for the last 30 days`
- `Give me email productivity insights`
- `Generate my weekly email report`
- `Show email patterns for the last 30 days`
""")

        st.markdown(
            "<p style='font-size:0.72rem;color:#666;margin:6px 0 0 0;'>💡 Include <b>email</b> / <b>inbox</b> / <b>message</b> in queries so I know it's an email task.</p>",
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 8px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>📊 Inbox Statistics</p>",
            unsafe_allow_html=True,
        )
        try:
            inbox_info = get_inbox_count()
            if inbox_info["status"] == "success":
                total = inbox_info["total_messages"]
                unread = inbox_info["unread_messages"]
                threads = inbox_info["total_threads"]
                unread_pct = round(unread / total * 100) if total else 0
                st.markdown(
                    f"""
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px;">
                      <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#e91e8c;">{total:,}</div>
                        <div style="font-size:0.7rem;color:#888;">Total</div>
                      </div>
                      <div style="background:#1a1a2e;border:1px solid #e91e8c55;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#ff6b6b;">{unread:,}</div>
                        <div style="font-size:0.7rem;color:#888;">Unread</div>
                      </div>
                      <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#a8dadc;">{threads:,}</div>
                        <div style="font-size:0.7rem;color:#888;">Threads</div>
                      </div>
                      <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:#95e1d3;">{unread_pct}%</div>
                        <div style="font-size:0.7rem;color:#888;">Unread %</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.warning("Could not load inbox stats.")
        except Exception as e:
            st.error(f"Stats error: {str(e)}")

    # ── Session state init ────────────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm **{agent_name}**, your AI Email Agent. "
                "I can help you manage your emails with natural language commands. "
                "Try asking me to count your emails, list unread messages, or send an email!"
            ),
        })

    if "history" not in st.session_state:
        st.session_state.history = []

    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False

    if "pending_command" not in st.session_state:
        st.session_state.pending_command = None

    if "interaction_count" not in st.session_state:
        st.session_state.interaction_count = 0

    if "last_consolidation_check" not in st.session_state:
        st.session_state.last_consolidation_check = datetime.now()

        if MEMORY_AVAILABLE:
            try:
                _aid = st.session_state.get("agent_id", os.getenv(
                    "AGENT_ID", "gmail_agent_default"))
                memory = get_agent_memory(_aid)
                consolidator = memory.get_consolidator()
                if consolidator.last_consolidation:
                    hours_since = (
                        datetime.now() - consolidator.last_consolidation
                    ).total_seconds() / 3600
                    if hours_since >= 24:
                        logger.info(
                            f"Startup consolidation check: {hours_since:.1f} hours since last consolidation"
                        )
                        logger.info(
                            "Triggering consolidation after agent restart (24+ hours passed)")
                        memory.run_consolidation()
                        logger.info("Startup consolidation completed")
            except Exception as e:
                logger.error(f"Startup consolidation check error: {str(e)}")

    # ── Chat header + clear button ────────────────────────────────────────────
    _hdr_col, _clr_col = st.columns([11, 1])
    with _hdr_col:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;">
              <div style="width:4px;height:28px;background:linear-gradient(180deg,#e91e8c,#9c27b0);
                          border-radius:2px;flex-shrink:0;"></div>
              <span style="font-size:1.3rem;font-weight:700;color:#f0f0f0;letter-spacing:0.01em;">
                💬 Chat with Your Email Agent
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with _clr_col:
        _do_clear = st.button(
            "🗑", help="Clear chat history", use_container_width=False)

    # ── Display chat history ──────────────────────────────────────────────────
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_messages:
            if message["role"] == "assistant":
                _ctx = st.chat_message("assistant")
            else:
                _ctx = st.chat_message("user")
            with _ctx:
                st.markdown(message["content"])

    if _do_clear:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm **{agent_name}**, your AI Email Agent. "
                "I can help you manage your emails with natural language commands. "
                "Try asking me to count your emails, list unread messages, or send an email!"
            ),
        }]
        st.session_state.history = []
        st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    user_command = st.chat_input(
        "Type your command here... (e.g., 'count my emails' or 'list 5 unread emails')"
    )

    logger.debug(
        f"RERUN: user_command={user_command}, "
        f"is_processing={st.session_state.is_processing}, "
        f"pending={st.session_state.pending_command}"
    )

    if user_command and st.session_state.is_processing:
        st.session_state.pending_command = user_command
        st.info("⏳ Your command is queued. Processing current request...")
        st.stop()

    if st.session_state.pending_command and not st.session_state.is_processing:
        user_command = st.session_state.pending_command
        st.session_state.pending_command = None

    if user_command and not st.session_state.is_processing:
        logger.debug(f"START PROCESSING: '{user_command[:50]}'")
        st.session_state.is_processing = True
        st.session_state.chat_messages.append(
            {"role": "user", "content": user_command})

        with st.status("Processing...", expanded=False) as _status:
            try:
                _aid = st.session_state.get("agent_id", os.getenv(
                    "AGENT_ID", "gmail_agent_default"))
                logger.debug("Calling handle_conversation()")
                convo_response = handle_conversation(
                    user_command, _aid, agent_name)
                logger.debug(
                    f"handle_conversation returned: {bool(convo_response)}")

                if convo_response:
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": convo_response,
                    })
                    if MEMORY_AVAILABLE:
                        try:
                            st.session_state.interaction_count += 1
                            memory = get_agent_memory(_aid)
                            consolidator = memory.get_consolidator()
                            if consolidator.should_consolidate(st.session_state.interaction_count):
                                logger.info(
                                    f"Triggering memory consolidation after conversation "
                                    f"(interactions: {st.session_state.interaction_count})"
                                )
                                memory.run_consolidation()
                                st.session_state.interaction_count = 0
                                st.session_state.last_consolidation_check = datetime.now()
                                logger.info("Memory consolidation completed")
                        except Exception as e:
                            logger.error(
                                f"Consolidation check error: {str(e)}")
                else:
                    _max_ops = 100
                    if AGENT_MANAGER_AVAILABLE and _aid:
                        try:
                            _agent_cfg = get_agent_manager().get_agent(_aid)
                            if _agent_cfg:
                                _max_ops = int(
                                    _agent_cfg.get("config", {}).get(
                                        "max_operations", 100)
                                )
                        except Exception:
                            pass

                    result = execute_with_llm_orchestration(
                        user_command, _aid, max_operations=_max_ops
                    )

                    if result.get("status") == "error":
                        error_msg = (
                            f"❌ {result.get('message', 'Unknown error')}\n\n"
                            "💡 **Try commands like:**\n"
                            "- `count emails I received today`\n"
                            "- `list 5 unread emails`\n"
                            "- `show emails from john@example.com`\n"
                            "- `send email to someone@example.com`\n"
                            "- `delete emails from newsletter@example.com`"
                        )
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": error_msg}
                        )
                    else:
                        action = result.get("action", "unknown")
                        final_response = _compose_email_response(result, action, user_command)
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": final_response}
                        )

                        if MEMORY_AVAILABLE:
                            try:
                                memory = get_agent_memory(_aid)
                                memory.add_interaction(
                                    command=user_command,
                                    action=action,
                                    result={"count": result.get(
                                        "count", 0), "status": "success"},
                                    metadata={"reasoning": result.get(
                                        "reasoning", "")},
                                    importance="High",
                                )
                                st.session_state.interaction_count += 1
                                consolidator = memory.get_consolidator()
                                if consolidator.should_consolidate(st.session_state.interaction_count):
                                    logger.info(
                                        f"Triggering memory consolidation "
                                        f"(interactions: {st.session_state.interaction_count})"
                                    )
                                    memory.run_consolidation()
                                    st.session_state.interaction_count = 0
                                    st.session_state.last_consolidation_check = datetime.now()
                                    logger.info(
                                        "Memory consolidation completed")
                            except Exception as e:
                                logger.error(
                                    f"Memory storage/consolidation error: {str(e)}")

                        st.session_state.history.append({
                            "command": user_command,
                            "action": action,
                            "result": result,
                            "timestamp": datetime.now().isoformat(),
                        })

            except Exception as e:
                _status.update(label="Something went wrong",
                               state="error", expanded=False)
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"❌ Error executing command: {str(e)}",
                })
            finally:
                st.session_state.is_processing = False
                logger.debug("RESET is_processing = False")

        logger.debug("Calling st.rerun()")
        st.rerun()

    # ── Detailed history (sidebar) ────────────────────────────────────────────
    if st.session_state.history:
        with st.sidebar:
            st.divider()
            st.header("📜 Detailed History")
            with st.expander("View Command Details", expanded=False):
                for i, item in enumerate(reversed(st.session_state.history), 1):
                    st.markdown(f"**#{i}:** {item['command'][:40]}...")
                    st.caption(
                        f"Action: `{item['action']}` | Time: {item.get('timestamp', 'N/A')[:19]}"
                    )
                    st.divider()


if __name__ == "__main__":
    main()
