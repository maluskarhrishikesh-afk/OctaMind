"""
Drive Agent UI — main Streamlit entry point.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from .conversation import handle_conversation
from .helpers import _logo_b64, _logo_icon, _logo_path, _logo_pinkraven, _start_browser_watchdog
from .orchestrator import execute_with_llm_orchestration
from ..dashboard.styles import inject_agent_css

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("drive_agent")
logger.setLevel(logging.DEBUG)

_log_dir = Path(__file__).parent.parent.parent.parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "drive_agent.log"
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

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
))


@st.dialog("📖 Full Drive Usage Guide", width="large")
def _show_drive_guide() -> None:
    st.markdown("""
## 📂 Browse & Search
| Command | Description |
|---------|-------------|
| `List my recent files` | Show the 10 most recently modified files |
| `Search for 'budget report'` | Find files whose name contains the phrase |
| `Show files in My Drive` | List root-level files |
| `Find files shared with me` | List all files others have shared with you |
| `List files in folder 'Projects'` | List contents of a named folder |
| `Find files not modified in a year` | Stale-file audit |
| `Find duplicate files` | Detect files with the same name |
| `List large files (> 50 MB)` | Storage audit — large items |

## 📊 Storage & Analytics
| Command | Description |
|---------|-------------|
| `Show storage usage` | Display used / available quota |
| `Generate Drive health report` | Full summary of storage and sharing state |
| `Get Drive analytics` | Activity and file-type breakdown |

## 🔗 Sharing & Permissions
| Command | Description |
|---------|-------------|
| `Sharing report` | Overview of all files you have shared |
| `List publicly shared files` | Files accessible to anyone with the link |
| `Show files shared with john@example.com` | Files shared with a specific person |
| `List files I've shared` | All files you have shared outward |

## 📁 Organise
| Command | Description |
|---------|-------------|
| `Create folder 'Archive 2025'` | Make a new folder |
| `Move file 'report.pdf' to 'Archive'` | Move a file into a folder |
| `Rename file 'old_name' to 'new_name'` | Rename a file or folder |
| `List my starred files` | Show items you have starred |
| `Show files in Trash` | List trashed items |

## ⬆️ Upload & ⬇️ Download
| Command | Description |
|---------|-------------|
| `Download file 'report.pdf'` | Download a file to the local machine |
| `Show download link for 'presentation.pptx'` | Get a shareable download URL |

## 💡 Tips
- Always include words like **file**, **drive**, or **folder** so the agent recognises Drive tasks.
- For files with spaces in the name, wrap the name in quotes: `'My Budget 2025.xlsx'`.
- Storage commands (usage, quota, trash) are fully supported — just ask naturally.
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


def _compose_drive_response(result: dict, action: str, original_command: str) -> str:
    """Pass raw Drive result directly to LLM for friendly composition."""
    import json as _json
    from src.agent.llm.llm_parser import get_llm_client

    if action == "react_response":
        return result.get("message", "Done.")  # Already LLM-composed by ReAct loop

    composition_prompt = f"""The user asked: \"{original_command}\"

A Google Drive operation was executed. Here is the raw result:

{_json.dumps(result, indent=2, default=str)}

Compose a response following these formatting rules:
- Write in a friendly, conversational tone like a helpful assistant
- Use **bold** for important names, counts, and key values
- Use bullet points or numbered lists to present multiple items (e.g. list of files)
- Use tables (markdown) when listing structured data like files with names, sizes, types
- Use relevant emojis to make the response visually engaging (e.g. 📁 folders, 📄 files, 📊 spreadsheets, 💾 downloads, ☁️ uploads, 🔗 links)
- Add a brief summary sentence at the start so the user knows what happened
- If there are many files, show the most important ones and mention the total count
- Include file IDs only when the user might need to reference them for follow-up actions
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
        logger.warning("Drive response composition failed: %s", exc)
        return f"✅ Drive operation `{action}` completed."


def main() -> None:
    logger.debug("=== DRIVE AGENT MAIN() CALLED ===")
    agent_id = os.getenv("AGENT_ID", "drive_agent_default")
    agent_name = os.getenv("AGENT_NAME", "Drive Assistant")

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex="#0078d4", accent_rgb="0,120,212")

    # ── Session state init ────────────────────────────────────────────────────
    if "agent_id" not in st.session_state:
        st.session_state.agent_id = agent_id

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{
            "role": "assistant",
            "content": (
                f"👋 Hello! I'm **{agent_name}**, your AI Google Drive Agent. "
                "I can help you manage your files with natural language commands. "
                "Try asking me to list recent files, search for a document, or check your storage usage!"
            ),
        }]

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
                    "AGENT_ID", "drive_agent_default"))
                memory = get_agent_memory(_aid)
                consolidator = memory.get_consolidator()
                if consolidator.last_consolidation:
                    hours_since = (
                        datetime.now() - consolidator.last_consolidation
                    ).total_seconds() / 3600
                    if hours_since >= 24:
                        logger.info(
                            f"Startup consolidation: {hours_since:.1f}h since last run")
                        memory.run_consolidation()
                        logger.info("Startup consolidation completed")
            except Exception as e:
                logger.error(f"Startup consolidation check error: {str(e)}")

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(0,120,212,0.18) 0%, rgba(233,30,140,0.12) 100%);
                   border:1.5px solid rgba(0,120,212,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(0,120,212,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(0,120,212,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;color:#e91e8c;line-height:1.1;background:linear-gradient(135deg, #e91e8c 0%, #0078d4 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">OctaMind</div>
              <div style="font-size:1.05rem;color:#a8dadc;margin-top:6px;font-weight:600;">
                📁 {agent_name} &nbsp;•&nbsp; Google Drive Agent
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#a8dadc;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(0,120,212,0.3);">
            Give me commands in natural language, and I'll manage your Drive files! ✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        if st.button("📖 Full Usage Guide", use_container_width=True, type="secondary"):
            _show_drive_guide()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:8px 0 4px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>⚡ Quick Commands</p>",
            unsafe_allow_html=True,
        )

        with st.expander("📂 Browse & Search"):
            st.markdown("""
- `List my recent files`
- `Search for 'budget report'`
- `Show files in My Drive`
- `Find files shared with me`
- `List files in folder 'Projects'`
""")
        with st.expander("📊 Storage & Analytics"):
            st.markdown("""
- `Show storage usage`
- `List large files (> 50 MB)`
- `Find files not modified in a year`
- `Generate Drive health report`
- `Find duplicate files`
""")
        with st.expander("🔗 Sharing & Permissions"):
            st.markdown("""
- `Sharing report`
- `List publicly shared files`
- `Show files shared with john@example.com`
- `List files I've shared`
""")
        with st.expander("📁 Organize"):
            st.markdown("""
- `Create folder 'Archive 2025'`
- `Move file 'report.pdf' to 'Archive'`
- `Rename file 'old_name' to 'new_name'`
- `List my starred files`
- `Show files in Trash`
""")
        with st.expander("⬆️ Upload & ⬇️ Download"):
            st.markdown("""
- `Download file 'report.pdf'`
- `Show download link for 'presentation.pptx'`
""")

        st.markdown(
            "<p style='font-size:0.72rem;color:#666;margin:6px 0 0 0;'>💡 Include <b>file</b> / <b>drive</b> / <b>folder</b> in queries so I know it's a Drive task.</p>",
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown("### ⚙️ Settings")
        _max_ops_from_cfg = 100
        if AGENT_MANAGER_AVAILABLE:
            try:
                _aid_cfg = st.session_state.get(
                    "agent_id", os.getenv("AGENT_ID", "drive_agent_default"))
                _agent_cfg = get_agent_manager().get_agent(_aid_cfg)
                if _agent_cfg:
                    _max_ops_from_cfg = int(_agent_cfg.get(
                        "config", {}).get("max_operations", 100))
            except Exception:
                pass

        if "max_operations" not in st.session_state:
            st.session_state.max_operations = _max_ops_from_cfg

        st.session_state.max_operations = st.slider(
            "Max operations",
            min_value=10,
            max_value=1000,
            value=st.session_state.max_operations,
            step=10,
            help="Limit on bulk Drive API calls per command.",
        )

    # ── Chat header + clear button ────────────────────────────────────────────
    _hdr_col, _clr_col = st.columns([11, 1])
    with _hdr_col:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;">
              <div style="width:4px;height:28px;background:linear-gradient(180deg,#0078d4,#e91e8c);
                          border-radius:2px;flex-shrink:0;"></div>
              <span style="font-size:1.3rem;font-weight:700;color:#f0f0f0;letter-spacing:0.01em;">
                💬 Chat with Your Drive Agent
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
                f"👋 Hello! I'm **{agent_name}**, your AI Google Drive Agent. "
                "I can help you manage your files with natural language commands. "
                "Try asking me to list recent files, search for a document, or check your storage usage!"
            ),
        }]
        st.session_state.history = []
        st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    user_command = st.chat_input(
        "Type your command here… (e.g., 'list my recent files' or 'search for budget report')"
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

        with st.status("Processing…", expanded=False) as _status:
            try:
                _aid = st.session_state.get("agent_id", os.getenv(
                    "AGENT_ID", "drive_agent_default"))
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
                                    "Triggering memory consolidation (conversation)")
                                memory.run_consolidation()
                                st.session_state.interaction_count = 0
                                st.session_state.last_consolidation_check = datetime.now()
                                logger.info("Memory consolidation completed")
                        except Exception as e:
                            logger.error(
                                f"Consolidation check error: {str(e)}")
                else:
                    _max_ops = st.session_state.get("max_operations", 100)
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
                            "- `list my recent files`\n"
                            "- `search for 'budget report'`\n"
                            "- `show storage usage`\n"
                            "- `find large files`\n"
                            "- `sharing report`"
                        )
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": error_msg}
                        )
                    else:
                        action = result.get("action", "unknown")
                        final_response = _compose_drive_response(result, action, user_command)
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
                                )
                                st.session_state.interaction_count += 1
                                consolidator = memory.get_consolidator()
                                if consolidator.should_consolidate(st.session_state.interaction_count):
                                    logger.info(
                                        "Triggering memory consolidation after Drive op")
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
