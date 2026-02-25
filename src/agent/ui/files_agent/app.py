"""
Files Agent UI — main Streamlit entry point.
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
logger = logging.getLogger("files_agent")
logger.setLevel(logging.DEBUG)

_log_dir = Path(__file__).parent.parent.parent.parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "files_agent.log"
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

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

# ── Optional integrations ─────────────────────────────────────────────────────
# Skills are stateless executors — memory belongs to Personal Assistants only.
try:
    from src.agent.core.agent_manager import get_agent_manager
    AGENT_MANAGER_AVAILABLE = True
except Exception:
    AGENT_MANAGER_AVAILABLE = False

ACCENT_HEX = "#4a90d9"
ACCENT_RGB = "74,144,217"


@st.dialog("📖 Full Files Agent Usage Guide", width="large")
def _show_files_guide() -> None:
    st.markdown("""
## 📁 File & Folder Operations
| Command | Description |
|---------|-------------|
| `List my Downloads folder` | Show contents of a folder |
| `Get info on C:/Users/me/report.pdf` | File metadata |
| `Copy report.pdf to D:/Backup` | Copy a file |
| `Move notes.txt to D:/Archive` | Move a file |
| `Rename old_name.txt to new_name.txt` | Rename |
| `Create folder D:/Projects/new_project` | Create a directory |
| `Delete temp.txt` | Move to Recycle Bin (safe) |
| `Open D:/Documents/readme.txt` | Open file in default app |

## 🔍 Search & Find
| Command | Description |
|---------|-------------|
| `Find files named report in C:/Users` | Search by name |
| `Find all PDF files in D:/Documents` | Search by extension |
| `Files modified in the last 7 days` | Search by date |
| `Find files larger than 100 MB` | Search by size |
| `Find duplicate files in D:/Photos` | Duplicate finder |
| `Find empty folders in C:/Users/me` | Empty folder finder |

## 🗜️ Archives
| Command | Description |
|---------|-------------|
| `Zip my Documents folder` | Compress a folder |
| `Zip report.pdf and notes.txt to archive.zip` | Zip specific files |
| `Unzip archive.zip to D:/Extracted` | Extract archive |
| `List contents of archive.zip` | Preview zip contents |
| `Archive info for backup.zip` | Compression stats |

## 🗂️ Organise & Bulk
| Command | Description |
|---------|-------------|
| `Organise D:/Downloads by file type` | Sort into Images/Docs/Video etc. |
| `Organise D:/Photos by date` | Sort into YYYY/MM folders |
| `Bulk rename files in D:/Reports with prefix Report_` | Mass rename |
| `Move all PDFs from Downloads to D:/PDF_Archive` | Bulk move |
| `Clean empty folders in D:/Projects` | Remove empty dirs |
| `Deduplicate files in D:/Photos (dry run)` | Safe duplicate removal |

## 💽 Disk & Space
| Command | Description |
|---------|-------------|
| `Show all drives` | List available drives |
| `Disk usage on C:` | Used / free / total |
| `How big is my Documents folder?` | Folder size |
| `Find large files on C: drive` | Files over threshold |
| `Files modified recently in D:/Projects` | Recent activity |

## 📖 Read & Analyse
| Command | Description |
|---------|-------------|
| `Read D:/notes.txt` | Display file contents |
| `Preview D:/data.csv` | First rows of CSV |
| `Read JSON file config.json` | Pretty-print JSON |
| `Tail D:/logs/app.log last 50 lines` | Log tail |
| `MD5 hash of report.pdf` | File integrity check |
| `Stats for D:/Documents` | Inode, permissions, etc. |

## 🧠 AI Features
| Command | Description |
|---------|-------------|
| `Summarize D:/Finance/budget.xlsx` | AI file summary |
| `Analyse my Downloads folder` | AI folder report |
| `Suggest how to organise D:/Desktop` | AI organisation advice |
| `Suggest better names for files in D:/Reports` | AI rename suggestions |
| `Find files related to project_alpha.docx` | Semantic file finder |
| `Describe D:/unknown_file.bin` | AI file description |

## 🔗 Cross-Agent (requires Gmail / Drive setup)
| Command | Description |
|---------|-------------|
| `Email D:/report.pdf to alice@example.com` | Attach file to email |
| `Upload D:/report.pdf to Google Drive` | Upload to Drive |
| `Zip and email D:/Projects/alpha to bob@example.com` | Zip then email |
| `Zip D:/Projects/alpha and upload to Drive` | Zip then upload |

## 💡 Tips
- Use full absolute paths for best results: `C:/Users/YourName/Documents`
- Destructive operations (delete, bulk remove) default to **dry run** — confirm before applying
- AI features require a configured LLM provider in `config/settings.json`
- Cross-agent tools require Gmail OAuth or Drive credentials
""")


def _compose_files_response(result: dict, user_command: str) -> str:
    """Pass raw Files result to LLM for friendly formatting."""
    import json as _json
    from src.agent.llm.llm_parser import get_llm_client

    action = result.get("action", "unknown")
    if action == "react_response":
        return result.get("message", "Done.")

    composition_prompt = f"""The user asked: "{user_command}"

A local file system operation was executed. Here is the raw result:

{_json.dumps(result, indent=2, default=str)}

Compose a friendly, conversational response using markdown:
- **Bold** file and folder names
- Use bullet lists or tables when listing files or search results
- Use relevant emojis (📁 folder, 📄 file, 🗜️ archive, 💽 disk, 🔍 search, ✅ done, ⚠️ warning)
- Brief summary sentence at the start
- Format sizes in human-readable form (KB, MB, GB)
- Do NOT show raw JSON keys or internal fields unless the user needs them"""

    llm = get_llm_client()
    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Compose clear, friendly markdown responses from raw file system tool results.",
                },
                {"role": "user", "content": composition_prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
            timeout=40,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Files response composition failed: %s", exc)
        return f"✅ File operation `{action}` completed."


# ── Streamlit app ─────────────────────────────────────────────────────────────

def main() -> None:  # noqa: C901
    logger.debug("=== FILES AGENT MAIN() ===")
    agent_id = os.getenv("AGENT_ID", "files_agent_default")
    agent_name = os.getenv("AGENT_NAME", "Files Assistant")

    st.set_page_config(
        page_title=f"{agent_name} — OctaMind",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex=ACCENT_HEX, accent_rgb=ACCENT_RGB)

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
        <div style="background:linear-gradient(135deg, rgba(74,144,217,0.18) 0%, rgba(100,170,240,0.12) 100%);
                   border:1.5px solid rgba(74,144,217,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(74,144,217,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(74,144,217,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;color:{ACCENT_HEX};line-height:1.1;background:linear-gradient(135deg, #4a90d9 0%, #2c6faf 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">OctaMind</div>
              <div style="font-size:1.05rem;color:#a8dadc;margin-top:6px;font-weight:600;">
                🗂️ {agent_name} &nbsp;•&nbsp; Files Agent
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#a8dadc;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(74,144,217,0.3);">
            I can help you manage, search, organise, and analyse your local files and drives. ✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        if st.button("📖 Full Usage Guide", use_container_width=True, type="secondary"):
            _show_files_guide()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 4px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>⚡ Quick Commands</p>",
            unsafe_allow_html=True,
        )

        with st.expander("📁 File Operations"):
            st.markdown("""
- `List my Downloads folder`
- `Get info on C:/Users/me/report.pdf`
- `Copy report.pdf to D:/Backup`
- `Create folder D:/Projects/new`
""")
        with st.expander("🔍 Search"):
            st.markdown("""
- `Find all PDF files in D:/Documents`
- `Files modified in the last 7 days`
- `Find files larger than 100 MB on C:`
- `Find duplicate files in D:/Photos`
""")
        with st.expander("🗜️ Archives"):
            st.markdown("""
- `Zip my Documents folder`
- `Unzip archive.zip to D:/Extracted`
- `List contents of backup.zip`
""")
        with st.expander("🗂️ Organise"):
            st.markdown("""
- `Organise D:/Downloads by file type`
- `Organise D:/Photos by date`
- `Bulk rename files in D:/Reports`
- `Clean empty folders in D:/Projects`
""")
        with st.expander("💽 Disk & Space"):
            st.markdown("""
- `Show all drives`
- `Disk usage on C:`
- `How big is my Documents folder?`
- `Find large files on C: drive`
""")
        with st.expander("🧠 AI Features"):
            st.markdown("""
- `Summarize D:/Finance/budget.xlsx`
- `Analyse my Downloads folder`
- `Suggest how to organise D:/Desktop`
- `Suggest better names for D:/Reports`
""")

        st.divider()
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:0 0 8px 0;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'>💽 Drive Space</p>",
            unsafe_allow_html=True,
        )
        try:
            from src.files.features.disk import list_drives
            drives = list_drives()
            if drives.get("drives"):
                for d in drives["drives"][:4]:
                    label = d.get("drive") or d.get("mountpoint", "?")
                    total_b = d.get("total_bytes", 0)
                    used_b = d.get("used_bytes", 0)
                    free_b = d.get("free_bytes", 0)
                    pct = d.get("percent_used", 0)
                    def _fmt(b):
                        if b >= 1 << 30:
                            return f"{b / (1<<30):.1f} GB"
                        elif b >= 1 << 20:
                            return f"{b / (1<<20):.1f} MB"
                        return f"{b / (1<<10):.1f} KB"
                    bar_color = "#ff6b6b" if pct > 85 else "#4a90d9"
                    st.markdown(
                        f"""
                        <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;padding:10px;margin-bottom:6px;">
                          <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                            <span style="font-size:0.82rem;font-weight:600;color:#ddd;">💽 {label}</span>
                            <span style="font-size:0.75rem;color:#888;">{_fmt(free_b)} free</span>
                          </div>
                          <div style="background:#333;height:6px;border-radius:3px;overflow:hidden;">
                            <div style="background:{bar_color};width:{min(pct,100):.0f}%;height:100%;border-radius:3px;"></div>
                          </div>
                          <div style="font-size:0.7rem;color:#666;margin-top:3px;">{_fmt(used_b)} / {_fmt(total_b)} ({pct:.0f}%)</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No drive info available")
        except Exception as _de:
            st.caption(f"Drive info unavailable: {_de}")

    # ── Session state init ────────────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    f"👋 Hello! I'm **{agent_name}**, your AI Files Assistant.  \n"
                    "I can help you manage, search, organise, and analyse your local files and drives.  \n"
                    "Try: *list my Downloads folder*, *find large files on C:*, *find duplicate files in D:/Photos*, "
                    "or *organise D:/Downloads by file type*."
                ),
            }
        ]

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
            f"""
            <div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;">
              <div style="width:4px;height:28px;background:linear-gradient(180deg,{ACCENT_HEX},#2c6faf);
                          border-radius:2px;flex-shrink:0;"></div>
              <span style="font-size:1.3rem;font-weight:700;color:#f0f0f0;letter-spacing:0.01em;">
                🗂️ Chat with Your Files Agent
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
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    f"👋 Hello! I'm **{agent_name}**, your AI Files Assistant.  \n"
                    "How can I help you today?"
                ),
            }
        ]
        st.session_state.history = []
        st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    user_command = st.chat_input(
        "Type your command… (e.g., 'list my Downloads folder' or 'find large files on C:')"
    )

    if user_command and st.session_state.is_processing:
        st.session_state.pending_command = user_command
        st.info("⏳ Your command is queued. Processing current request…")
        st.stop()

    if st.session_state.pending_command and not st.session_state.is_processing:
        user_command = st.session_state.pending_command
        st.session_state.pending_command = None

    if user_command and not st.session_state.is_processing:
        logger.debug("START PROCESSING: '%s'", user_command[:50])
        st.session_state.is_processing = True
        st.session_state.chat_messages.append({"role": "user", "content": user_command})

        with st.status("Processing…", expanded=False) as _status:
            try:
                _aid = st.session_state.get(
                    "agent_id", os.getenv("AGENT_ID", "files_agent_default")
                )

                convo_response = handle_conversation(user_command, _aid, agent_name)

                if convo_response:
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": convo_response}
                    )
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
                            "- `list my Downloads folder`\n"
                            "- `find large files on C:`\n"
                            "- `find duplicate files in D:/Photos`\n"
                            "- `organise D:/Downloads by file type`"
                        )
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": error_msg}
                        )
                    else:
                        final_response = _compose_files_response(result, user_command)
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": final_response}
                        )

                        action = result.get("action", "unknown")
                        st.session_state.history.append(
                            {
                                "command": user_command,
                                "action": action,
                                "result": result,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            except Exception as e:
                _status.update(label="Something went wrong", state="error", expanded=False)
                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": f"❌ Error executing command: {str(e)}",
                    }
                )
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
                    st.markdown(f"**#{i}:** {item['command'][:40]}…")
                    st.caption(
                        f"Action: `{item['action']}` | Time: {item.get('timestamp', 'N/A')[:19]}"
                    )
                    st.divider()


if __name__ == "__main__":
    main()
