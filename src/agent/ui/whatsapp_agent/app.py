"""
WhatsApp Agent UI — main Streamlit entry point.

Sets up the logger, imports the modular sub-components, and runs the
Streamlit rendering loop.
"""
from __future__ import annotations
from .orchestrator import execute_with_llm_orchestration
from .conversation import handle_conversation
from .helpers import _logo_b64, _logo_icon, _logo_path, _logo_pinkraven, _start_browser_watchdog
from src.whatsapp.webhook.message_store import get_message_count
from src.whatsapp.whatsapp_auth import credentials_configured
import streamlit as st
from ..dashboard.styles import inject_agent_css

# ── Logging ───────────────────────────────────────────────────────────────────
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("whatsapp_agent")
logger.setLevel(logging.DEBUG)

_log_dir = Path(__file__).parent.parent.parent.parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "whatsapp_agent.log"
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

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..")))


@st.dialog("📖 Full WhatsApp Usage Guide", width="large")
def _show_whatsapp_guide() -> None:
    st.markdown("""
## 📨 Send Messages
| Command | Description |
|---------|-------------|
| `Send hi to 919876543210` | Send a text message |
| `Message 14155552671 saying I'll be late` | Natural language sending |
| `Send image to 919876543210 url https://example.com/photo.jpg` | Send media |
| `Reply to message wamid.xxx saying Thanks!` | Quoted reply |
| `Send template hello_world to 919876543210` | Business template |

## 📥 Read & Check
| Command | Description |
|---------|-------------|
| `Show unread messages` | List unread inbound messages |
| `Show recent messages` | Last 20 messages |
| `Get my conversation with 919876543210` | Full chat thread |
| `Mark message wamid.xxx as read` | Send read receipt |
| `Show media messages` | Images, videos, documents |

## 🔍 Search
| Command | Description |
|---------|-------------|
| `Search messages for meeting` | Full-text search |
| `Messages from last week` | Messages by date range |
| `Find messages containing invoice` | Keyword search |

## 👥 Contacts & Groups
| Command | Description |
|---------|-------------|
| `List my contacts` | All known contacts |
| `Who do I message most?` | Top contacts by message count |
| `Contact info for 919876543210` | Contact details |
| `Name 919876543210 as Alice` | Set display name |
| `Show my groups` | All known groups |
| `Messages in group <group_id>` | Group message history |

## 🧠 AI Smart Features
| Command | Description |
|---------|-------------|
| `Summarize my chat with 919876543210` | AI conversation summary |
| `Action items from chat with 919876543210` | Extract tasks |
| `Draft a message to 919876543210 about project update` | AI-drafted message |
| `How should I reply to message wamid.xxx?` | 3 reply suggestions |
| `Detect urgent messages` | AI urgency scan |
| `Translate message wamid.xxx to Hindi` | Language translation |
| `Sentiment of chat with 919876543210` | Mood analysis |
| `Key info in message wamid.xxx` | Extract names, dates, links |

## ⏰ Scheduling
| Command | Description |
|---------|-------------|
| `Schedule message to 919876543210 for tomorrow 9am saying Good morning` | Schedule a message |
| `Show scheduled messages` | List pending sends |
| `Cancel scheduled message abc12345` | Cancel a queued message |
| `Enable auto-reply with message "I'm busy, will reply later"` | Auto-reply |
| `Disable auto-reply` | Turn off auto-reply |

## 📊 Analytics
| Command | Description |
|---------|-------------|
| `Show my WhatsApp stats for the last 30 days` | Volume metrics |
| `Activity report for last week` | Hourly/daily patterns |
| `Who messages me most?` | Top senders |
| `Response time for 919876543210` | How fast you reply |

## 🔗 Cross-Agent
| Command | Description |
|---------|-------------|
| `Forward message wamid.xxx to alice@example.com` | WhatsApp → Email |
| `Share Drive file <file_id> with 919876543210` | Drive → WhatsApp |

## 💡 Tips
- Phone numbers must be in **E.164** format: country code + number, **no + sign or spaces**
  - India: `919876543210` (91 + 10-digit number)
  - US: `14155552671` (1 + 10-digit number)
- Use message IDs from list results to act on specific messages
- The webhook server must be running to receive inbound messages
- Run `python -m uvicorn src.whatsapp.webhook.receiver:app --port 9001` for the webhook
    """)


# ── Optional integrations ─────────────────────────────────────────────────────
# Skills are stateless executors — memory belongs to Personal Assistants only.
try:
    from src.agent.core.agent_manager import get_agent_manager
    AGENT_MANAGER_AVAILABLE = True
except Exception:
    AGENT_MANAGER_AVAILABLE = False


def _compose_whatsapp_response(result: dict, action: str, original_command: str) -> str:
    """Pass raw WhatsApp result to LLM for friendly composition."""
    import json as _json
    from src.agent.llm.llm_parser import get_llm_client

    if action == "react_response":
        return result.get("message", "Done.")

    composition_prompt = f"""The user asked: "{original_command}"

A WhatsApp operation was executed. Here is the raw result:

{_json.dumps(result, indent=2, default=str)}

Compose a friendly, conversational response using markdown:
- **Bold** names and phone numbers
- Use bullet points or tables when listing messages or contacts
- Use relevant emojis (💬 messages, ✅ sent, 📱 WhatsApp, 📞 call, 🔔 urgent)
- Brief summary sentence at the start
- Include message IDs only when the user needs them to act
- Do NOT show raw JSON keys or internal fields"""

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
        logger.warning("WhatsApp response composition failed: %s", exc)
        return f"✅ WhatsApp operation `{action}` completed."


# ── Streamlit app ─────────────────────────────────────────────────────────────

def main() -> None:  # noqa: C901
    logger.debug("=== WHATSAPP AGENT MAIN() ===")
    agent_id = os.getenv("AGENT_ID", "whatsapp_agent_default")
    agent_name = os.getenv("AGENT_NAME", "WhatsApp Assistant")

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex="#25d366", accent_rgb="37,211,102")

    # Start automation scheduler (once per process)
    try:
        from src.agent.core.automation_scheduler import start_scheduler
        _sched = start_scheduler(agent_id)  # noqa: F841
    except Exception as _sched_err:
        logger.warning("Automation scheduler could not start: %s", _sched_err)

    if "agent_id" not in st.session_state:
        st.session_state.agent_id = agent_id

    # ── Credentials warning ───────────────────────────────────────────────────
    if not credentials_configured():
        st.warning(
            "⚠️ **WhatsApp credentials not configured.**  \n"
            "Add `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` to "
            "`config/settings.json` under the `whatsapp` key.  \n"
            "See the [WHATSAPP_SETUP.md](documentation/WHATSAPP_SETUP.md) guide.",
            icon="⚠️",
        )

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(18,140,126,0.18) 0%, rgba(37,211,102,0.12) 100%);
                   border:1.5px solid rgba(37,211,102,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(37,211,102,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(37,211,102,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;color:#25d366;line-height:1.1;background:linear-gradient(135deg, #25d366 0%, #128c7e 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">OctaMind</div>
              <div style="font-size:1.05rem;color:#a8dadc;margin-top:6px;font-weight:600;">
                💬 {agent_name} &nbsp;•&nbsp; WhatsApp Agent
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#a8dadc;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(37,211,102,0.3);">
            Give me commands in natural language, and I'll handle your WhatsApp messages! ✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        if st.button("📖 Full Usage Guide", use_container_width=True, type="secondary"):
            _show_whatsapp_guide()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 4px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>⚡ Quick Commands</p>",
            unsafe_allow_html=True,
        )

        with st.expander("📨 Send Messages"):
            st.markdown("""
- `Send hi to 919876543210`
- `Reply to message wamid.xxx saying Yes`
- `Schedule message for tomorrow 9am`
""")
        with st.expander("📥 Read Messages"):
            st.markdown("""
- `Show unread messages`
- `Show recent messages`
- `Conversation with 919876543210`
- `Show media messages`
""")
        with st.expander("🔍 Search"):
            st.markdown("""
- `Search for meeting`
- `Messages from last week`
""")
        with st.expander("👥 Contacts & Groups"):
            st.markdown("""
- `List my contacts`
- `Who do I message most?`
- `Show my groups`
""")
        with st.expander("🧠 AI Features"):
            st.markdown("""
- `Summarize chat with 919876543210`
- `Action items from conversation`
- `Draft message to 919876543210 about update`
- `Detect urgent messages`
- `Translate message wamid.xxx to Hindi`
""")
        with st.expander("⏰ Schedule"):
            st.markdown("""
- `Schedule message for tomorrow 9am`
- `Show scheduled messages`
- `Enable auto-reply with ...`
""")
        with st.expander("📊 Analytics"):
            st.markdown("""
- `WhatsApp stats last 30 days`
- `Activity report this week`
- `Who messages me most?`
""")

        st.markdown(
            "<p style='font-size:0.72rem;color:#666;margin:6px 0 0 0;'>💡 Phone numbers in E.164 format: <b>919876543210</b> (no + or spaces)</p>",
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 8px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>📊 Message Stats</p>",
            unsafe_allow_html=True,
        )
        try:
            counts = get_message_count()
            total = counts.get("total", 0)
            inbound = counts.get("inbound", 0)
            outbound = counts.get("outbound", 0)
            unread = counts.get("unread", 0)
            st.markdown(
                f"""
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px;">
                  <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:1.5rem;font-weight:700;color:#25d366;">{total:,}</div>
                    <div style="font-size:0.7rem;color:#888;">Total</div>
                  </div>
                  <div style="background:#1a1a2e;border:1px solid #25d36655;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:1.5rem;font-weight:700;color:#ff6b6b;">{unread:,}</div>
                    <div style="font-size:0.7rem;color:#888;">Unread</div>
                  </div>
                  <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:1.5rem;font-weight:700;color:#a8dadc;">{inbound:,}</div>
                    <div style="font-size:0.7rem;color:#888;">Received</div>
                  </div>
                  <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:1.5rem;font-weight:700;color:#95e1d3;">{outbound:,}</div>
                    <div style="font-size:0.7rem;color:#888;">Sent</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.error(f"Stats error: {str(e)}")

    # ── Session state init ────────────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm **{agent_name}**, your AI WhatsApp Assistant. "
                "I can help you send messages, read your inbox, search conversations, "
                "and much more using natural language. "
                "Try saying: *Show unread messages* or *Send hi to 919876543210*"
            ),
        }]

    if "history" not in st.session_state:
        st.session_state.history = []

    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False

    if "pending_command" not in st.session_state:
        st.session_state.pending_command = None

    # ── Chat header + clear button ────────────────────────────────────────────
    _hdr_col, _clr_col = st.columns([11, 1])
    with _hdr_col:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;">
              <div style="width:4px;height:28px;background:linear-gradient(180deg,#25d366,#128c7e);
                          border-radius:2px;flex-shrink:0;"></div>
              <span style="font-size:1.3rem;font-weight:700;color:#f0f0f0;letter-spacing:0.01em;">
                💬 Chat with Your WhatsApp Agent
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with _clr_col:
        _do_clear = st.button("🗑", help="Clear chat history", use_container_width=False)

    # ── Display chat history ──────────────────────────────────────────────────
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_messages:
            role = "assistant" if message["role"] == "assistant" else "user"
            with st.chat_message(role):
                st.markdown(message["content"])

    if _do_clear:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm **{agent_name}**, your AI WhatsApp Assistant. "
                "How can I help you today?"
            ),
        }]
        st.session_state.history = []
        st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    user_command = st.chat_input(
        "Type your command... (e.g., 'show unread messages' or 'send hi to 919876543210')"
    )

    if user_command and st.session_state.is_processing:
        st.session_state.pending_command = user_command
        st.info("⏳ Your command is queued. Processing current request...")
        st.stop()

    if st.session_state.pending_command and not st.session_state.is_processing:
        user_command = st.session_state.pending_command
        st.session_state.pending_command = None

    if user_command and not st.session_state.is_processing:
        logger.debug("START PROCESSING: '%s'", user_command[:50])
        st.session_state.is_processing = True
        st.session_state.chat_messages.append({"role": "user", "content": user_command})

        with st.status("Processing...", expanded=False) as _status:
            try:
                _aid = st.session_state.get("agent_id", os.getenv(
                    "AGENT_ID", "whatsapp_agent_default"))

                convo_response = handle_conversation(user_command, _aid, agent_name)

                if convo_response:
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": convo_response,
                    })
                else:
                    _max_ops = 100
                    if AGENT_MANAGER_AVAILABLE and _aid:
                        try:
                            _agent_cfg = get_agent_manager().get_agent(_aid)
                            if _agent_cfg:
                                _max_ops = int(
                                    _agent_cfg.get("config", {}).get("max_operations", 100)
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
                            "- `show unread messages`\n"
                            "- `send hi to 919876543210`\n"
                            "- `summarize chat with 919876543210`\n"
                            "- `schedule message for tomorrow 9am`"
                        )
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": error_msg}
                        )
                    else:
                        action = result.get("action", "unknown")
                        final_response = _compose_whatsapp_response(result, action, user_command)
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": final_response}
                        )

                        st.session_state.history.append({
                            "command": user_command,
                            "action": action,
                            "result": result,
                            "timestamp": datetime.now().isoformat(),
                        })

            except Exception as e:
                _status.update(label="Something went wrong", state="error", expanded=False)
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"❌ Error executing command: {str(e)}",
                })
            finally:
                st.session_state.is_processing = False

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
