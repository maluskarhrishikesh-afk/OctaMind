"""
Octa Bot Agent Hub — main Streamlit entry point.
"""
from __future__ import annotations

import logging
import json
from copy import deepcopy

import streamlit as st
import streamlit.components.v1 as components

from src.agent.core.agent_manager import get_agent_manager
from src.agent.core.process_manager import cleanup_stale, get_agent_status
from src.agent.runtime_paths import get_runtime_state_path
from src.agent.ui.dashboard.configure_panel import show_configure_panel
from src.agent.ui.dashboard.create_form import show_create_agent_form
from src.agent.ui.dashboard.helpers import _logo_b64, _logo_icon
from src.agent.ui.dashboard.log_viewer import show_log_viewer
from src.agent.ui.dashboard.styles import inject_css

logger = logging.getLogger("Octa Bot.dashboard")

_PA_SKILL_EXCLUDED_TYPES = {"telegram", "whatsapp", "custom"}
_APP_INITIALIZED = False
_NAV_STATE_KEYS = (
    "show_create_form",
    "configure_agent_id",
    "configure_pa_id",
    "show_log_viewer",
    "show_create_pa_panel",
    "active_pa_id",
    "active_pa_url",
    "dashboard_scroll_target",
)


def _startup() -> None:
    """Run one-time process startup hooks for the dashboard."""
    global _APP_INITIALIZED
    if _APP_INITIALIZED:
        return
    _APP_INITIALIZED = True

    try:
        from src.agent.memory.agent_memory import MULTI_AGENT_ID, get_agent_memory

        get_agent_memory(MULTI_AGENT_ID)
        logger.info("[startup] Multi-agent memory initialised.")
    except Exception as exc:
        logger.error("[startup] Failed to init multi-agent memory: %s", exc)

    try:
        from src.agent.memory.consolidation_runner import get_consolidation_runner

        runner = get_consolidation_runner()
        runner.start()
        logger.info("[startup] ConsolidationRunner started.")
    except Exception as exc:
        logger.error("[startup] Failed to start ConsolidationRunner: %s", exc)


_startup()


def _get_available_pa_skill_keys() -> list[str]:
    """Return all PA-attachable skills from the shared skill registry."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
    except Exception:
        AGENT_REGISTRY = {}

    return [
        key
        for key in AGENT_REGISTRY.keys()
        if key not in _PA_SKILL_EXCLUDED_TYPES
    ]


def _build_skill_catalog(manager, assistants: list[dict]) -> list[dict]:
    """Build the dashboard skill catalog from the shared skill registry."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
    except Exception:
        AGENT_REGISTRY = {}
    try:
        from src.agent.hub.skill_help import get_skill_help_doc, get_skill_help_preview
    except Exception:
        get_skill_help_doc = None
        get_skill_help_preview = None

    agent_types = manager.get_agent_types()
    usage_counts: dict[str, int] = {}
    enabled_by_skill: dict[str, list[str]] = {}
    for assistant in assistants:
        for skill in assistant.get("skills", []) or []:
            normalized = str(skill).strip()
            if normalized:
                usage_counts[normalized] = usage_counts.get(normalized, 0) + 1
                enabled_by_skill.setdefault(normalized, []).append(str(assistant.get("id", "")).strip())

    catalog = []
    for key in _get_available_pa_skill_keys():
        meta = agent_types.get(key, {})
        help_doc = get_skill_help_doc(key) if get_skill_help_doc else None
        description = get_skill_help_preview(key) if get_skill_help_preview else ""
        if not description:
            description = str(AGENT_REGISTRY.get(key, {}).get("description", "")).strip()
        if not description:
            description = str(meta.get("description", "")).strip()
        catalog.append(
            {
                "key": key,
                "name": str(help_doc.title if help_doc else meta.get("name", key.replace("_", " ").title())),
                "icon": str(meta.get("icon", "🔧")),
                "description": description,
                "help_markdown": help_doc.body if help_doc else "",
                "enabled_assistant_ids": enabled_by_skill.get(key, []),
                "assistant_count": usage_counts.get(key, 0),
            }
        )
    return catalog


def _update_skill_assignments(skill_key: str, selected_pa_ids: list[str], assistants: list[dict]) -> bool:
    """Enable or disable one skill across assistants from the dashboard."""
    from src.agent.hub.pa_manager import update_assistant

    selected = {str(pa_id).strip() for pa_id in selected_pa_ids if str(pa_id).strip()}
    changed = False
    for assistant in assistants:
        pa_id = str(assistant.get("id", "")).strip()
        if not pa_id:
            continue
        current_skills = [str(skill).strip() for skill in assistant.get("skills", []) if str(skill).strip()]
        has_skill = skill_key in current_skills
        should_have_skill = pa_id in selected
        if should_have_skill and not has_skill:
            update_assistant(pa_id, skills=current_skills + [skill_key])
            changed = True
        elif has_skill and not should_have_skill:
            update_assistant(pa_id, skills=[skill for skill in current_skills if skill != skill_key])
            changed = True
    return changed


def _current_nav_state() -> dict:
    """Capture the current dashboard navigation state for back-navigation."""
    return {key: deepcopy(st.session_state.get(key)) for key in _NAV_STATE_KEYS}


def _restore_nav_state(state: dict) -> None:
    """Restore a previously captured dashboard navigation state."""
    defaults = {
        "show_create_form": False,
        "configure_agent_id": None,
        "configure_pa_id": None,
        "show_log_viewer": False,
        "show_create_pa_panel": False,
        "active_pa_id": None,
        "active_pa_url": None,
        "dashboard_scroll_target": None,
    }
    merged = {**defaults, **(state or {})}
    for key, value in merged.items():
        st.session_state[key] = value


def _push_nav_state() -> None:
    """Push current dashboard view onto the back stack if it changed."""
    current = _current_nav_state()
    history = st.session_state.setdefault("nav_history", [])
    if not history or history[-1] != current:
        history.append(current)


def _go_home(section: str | None = None, push_history: bool = True) -> None:
    """Return to the dashboard home and optionally scroll to a section."""
    if push_history:
        _push_nav_state()
    _restore_nav_state({"dashboard_scroll_target": section})


def _go_back() -> None:
    """Go back to the previous dashboard view if one exists."""
    history = st.session_state.setdefault("nav_history", [])
    if history:
        previous = history.pop()
        _restore_nav_state(previous)


def _set_dashboard_scroll_target(section: str) -> None:
    """Navigate home and scroll to a dashboard section."""
    _go_home(section=section, push_history=True)


def _open_pa_workspace(pa_id: str, url: str | None = None, push_history: bool = True) -> None:
    """Open a Personal Assistant inside the dashboard workspace."""
    if push_history:
        _push_nav_state()
    st.session_state.active_pa_id = pa_id
    st.session_state.active_pa_url = url
    st.session_state.show_create_form = False
    st.session_state.show_create_pa_panel = False
    st.session_state.show_log_viewer = False
    st.session_state.configure_agent_id = None
    st.session_state.dashboard_scroll_target = None


def _workspace_composer_queue_path(pa_id: str):
    return get_runtime_state_path("runtime_state", "dashboard_composer", f"{pa_id}.json", create_parent=True)


def _enqueue_workspace_command(pa_id: str, command: str) -> None:
    payload = {
        "pa_id": pa_id,
        "command": command,
    }
    queue_path = _workspace_composer_queue_path(pa_id)
    queue_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _close_pa_workspace() -> None:
    """Return from the embedded assistant workspace back to the dashboard home."""
    _go_home(push_history=False)


def _render_pa_workspace(pa: dict, manager) -> None:
    """Render the assistant chat UI embedded inside the dashboard."""
    status = get_agent_status(pa["id"])
    workspace_url = st.session_state.get("active_pa_url") or (status or {}).get("url")
    st.session_state.active_pa_url = workspace_url

    st.markdown(
        f"""
        <style>
        .main .block-container {{
            padding-bottom: 0.75rem !important;
        }}
        </style>
        <div id="workspace-toolbar-{pa['id']}" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
                    background:rgba(15,23,42,0.78);border:1px solid rgba(99,102,241,0.18);border-radius:16px;
                    padding:10px 14px;margin-bottom:12px;backdrop-filter:blur(10px);box-shadow:0 14px 36px rgba(15,23,42,0.22);">
            <div style="display:flex;align-items:center;gap:10px;min-width:0;">
                <div style="font-size:1rem;font-weight:800;color:#f8fafc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🤖 {pa['name']}</div>
                <span style="background:{'#16a34a' if status else '#475569'};color:#fff;padding:4px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;">{'Running' if status else 'Stopped'}</span>
            </div>
            <div style="font-size:0.78rem;color:#64748b;">Dashboard workspace</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_col1, action_col2, action_col3 = st.columns([1.1, 1.2, 1.2])
    with action_col1:
        if st.button("🏠 Home", key=f"home_pa_{pa['id']}", use_container_width=True):
            _close_pa_workspace()
            st.rerun()
    with action_col2:
        cfg_open = st.session_state.get("configure_pa_id") == pa["id"]
        cfg_label = "✖ Close Config" if cfg_open else "⚙️ Configure"
        if st.button(cfg_label, key=f"workspace_cfg_{pa['id']}", use_container_width=True):
            _push_nav_state()
            st.session_state.configure_pa_id = None if cfg_open else pa["id"]
            st.session_state.dashboard_scroll_target = None
            st.rerun()
    with action_col3:
        if status:
            if st.button("🔄 Refresh Chat", key=f"refresh_pa_{pa['id']}", use_container_width=True):
                st.rerun()
        else:
            if st.button("▶️ Start Assistant", key=f"workspace_start_{pa['id']}", use_container_width=True, type="primary"):
                from src.agent.core.process_manager import start_agent

                started = start_agent(pa["id"], pa["name"], "personal_assistant")
                st.session_state.active_pa_url = started.get("url")
                st.rerun()

    if st.session_state.get("configure_pa_id") == pa["id"]:
        _render_pa_configure_panel(pa)

    if not workspace_url:
        st.markdown(
            "<div style='background:rgba(15,23,42,0.78);border:1px solid rgba(99,102,241,0.22);padding:28px;border-radius:18px;text-align:center;'>"
            "<div style='font-size:1.05rem;font-weight:800;color:#e2e8f0;'>Assistant is not running yet</div>"
            "<div style='color:#64748b;font-size:0.9rem;margin-top:8px;'>Start the assistant to load chat inside this dashboard workspace.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    if "?" in workspace_url:
        embedded_url = f"{workspace_url}&embedded=1&external_composer=1"
    else:
        embedded_url = f"{workspace_url}?embedded=1&external_composer=1"

    st.markdown(
        f"<div id='workspace-frame-wrap-{pa['id']}' style='background:rgba(15,23,42,0.75);border:1px solid rgba(99,102,241,0.18);border-radius:20px;padding:8px;box-shadow:0 18px 48px rgba(15,23,42,0.28);overflow:hidden;box-sizing:border-box;'></div>",
        unsafe_allow_html=True,
    )
    components.iframe(embedded_url, height=780, scrolling=False)
    components.html(
        f"""
        <script>
        (function() {{
            var resizeObserver = null;
            var contentWindow = null;

            function measureContentHeight(frame) {{
                try {{
                    var doc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
                    if (!doc) {{
                        return null;
                    }}
                    var body = doc.body;
                    var html = doc.documentElement;
                    return Math.max(
                        body ? body.scrollHeight : 0,
                        body ? body.offsetHeight : 0,
                        html ? html.scrollHeight : 0,
                        html ? html.offsetHeight : 0,
                        html ? html.clientHeight : 0
                    );
                }} catch (error) {{
                    return null;
                }}
            }}

            function applyWorkspaceLayout() {{
                var parentDoc = window.parent.document;
                var frame = Array.from(parentDoc.querySelectorAll('iframe')).find(function(node) {{
                    return (node.src || '').indexOf('{embedded_url}') !== -1;
                }});
                var wrap = parentDoc.getElementById('workspace-frame-wrap-{pa['id']}');
                var toolbar = parentDoc.getElementById('workspace-toolbar-{pa['id']}');
                if (!frame || !wrap) {{
                    return;
                }}
                if (frame.parentElement !== wrap) {{
                    wrap.appendChild(frame);
                }}
                var frameHeight = measureContentHeight(frame) || 780;
                frame.style.width = '100%';
                frame.style.height = frameHeight + 'px';
                frame.style.border = '0';
                frame.style.borderRadius = '16px';
                frame.style.display = 'block';
                frame.setAttribute('height', String(frameHeight));
                wrap.style.height = 'auto';
                wrap.style.maxHeight = 'none';
                wrap.style.overflow = 'hidden';
                wrap.style.boxSizing = 'border-box';
                if (toolbar) {{
                    toolbar.style.position = 'sticky';
                    toolbar.style.top = '0';
                    toolbar.style.zIndex = '20';
                }}
                if (contentWindow !== frame.contentWindow) {{
                    contentWindow = frame.contentWindow;
                    if (resizeObserver) {{
                        resizeObserver.disconnect();
                        resizeObserver = null;
                    }}
                    try {{
                        var observedDoc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
                        if (observedDoc && observedDoc.body && window.parent.ResizeObserver) {{
                            resizeObserver = new window.parent.ResizeObserver(function() {{
                                applyWorkspaceLayout();
                            }});
                            resizeObserver.observe(observedDoc.body);
                        }}
                    }} catch (error) {{
                    }}
                }}
            }}
            window.addEventListener('load', applyWorkspaceLayout);
            applyWorkspaceLayout();
            setTimeout(applyWorkspaceLayout, 120);
            setTimeout(applyWorkspaceLayout, 450);
            window.parent.addEventListener('resize', applyWorkspaceLayout);
        }})();
        </script>
        """,
        height=0,
    )

    st.markdown(
        f"""
        <style>
        .st-key-workspace_composer_shell_{pa['id']} {{
            position: sticky;
            bottom: 0;
            z-index: 30;
            padding-top: 0.6rem;
            padding-bottom: 0.35rem;
            background: linear-gradient(180deg, rgba(2,6,23,0) 0%, rgba(2,6,23,0.92) 20%, rgba(2,6,23,0.98) 100%);
        }}
        .st-key-workspace_composer_shell_{pa['id']} [data-testid="stHorizontalBlock"] {{
            align-items: end;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key=f"workspace_composer_shell_{pa['id']}"):
        with st.form(f"workspace_composer_form_{pa['id']}", clear_on_submit=True):
            input_col, send_col = st.columns([8.6, 1.4])
            with input_col:
                workspace_input = st.text_input(
                    "Message",
                    placeholder=f"Ask {pa['name']}…",
                    key=f"workspace_composer_input_{pa['id']}",
                    label_visibility="collapsed",
                    disabled=not bool(status),
                )
            with send_col:
                submitted = st.form_submit_button(
                    "Send",
                    use_container_width=True,
                    type="primary",
                    disabled=not bool(status),
                )

        if submitted:
            workspace_input = (workspace_input or "").strip()
            if workspace_input:
                _enqueue_workspace_command(pa["id"], workspace_input)
                st.rerun()


def _render_pa_configure_panel(pa: dict) -> None:
    """Inline dashboard configure panel for a Personal Assistant."""
    from src.agent.hub.pa_manager import load_assistants, update_assistant

    fresh = next((item for item in load_assistants() if item["id"] == pa["id"]), pa)

    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
    except Exception as exc:
        st.error(f"Could not load channel registry: {exc}")
        return

    available_skills = _get_available_pa_skill_keys()
    current_skills = [skill for skill in fresh.get("skills", []) if skill not in _PA_SKILL_EXCLUDED_TYPES]
    skill_options = list(dict.fromkeys(current_skills + available_skills))
    channel_options = ["dashboard", "telegram"]
    telegram_cfg = (fresh.get("config") or {}).get("telegram", {})

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(124,58,237,0.12) 0%,rgba(99,102,241,0.08) 100%);
                    border:1px solid rgba(124,58,237,0.28);border-radius:16px;padding:18px 20px;margin:16px 0 20px 0;">
            <div style="font-size:1.2rem;font-weight:800;color:#e2e8f0;">⚙️ Configure Personal Assistant</div>
            <div style="color:#a5b4fc;font-size:0.9rem;margin-top:4px;">{fresh['name']}</div>
            <div style="color:#64748b;font-size:0.82rem;margin-top:8px;">Enable or disable attached skills and update Telegram settings directly from the Dashboard.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not skill_options:
        st.warning("No assignable skills are available right now.")

    with st.form(f"dashboard_configure_pa_{fresh['id']}"):
        new_name = st.text_input("Assistant Name", value=fresh["name"])
        new_skills = st.multiselect(
            "Skills",
            options=skill_options,
            default=[skill for skill in current_skills if skill in skill_options],
            help="These are the shared skills available to this Personal Assistant.",
        )
        new_channels = st.multiselect(
            "Channels",
            options=channel_options,
            default=[channel for channel in fresh.get("channels", []) if channel in channel_options] or ["dashboard", "telegram"],
            format_func=lambda channel: f"{CHANNEL_REGISTRY[channel].icon} {CHANNEL_REGISTRY[channel].display_name}" if channel in CHANNEL_REGISTRY else channel.title(),
        )
        new_token = st.text_input(
            "Telegram Bot Token",
            value=telegram_cfg.get("bot_token", ""),
            placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            type="password",
        )
        new_auto_reply = st.checkbox("Telegram auto-reply enabled", value=telegram_cfg.get("auto_reply", True))

        save_col, cancel_col = st.columns([3, 1])
        with save_col:
            save_clicked = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
        with cancel_col:
            cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)

        if cancel_clicked:
            st.session_state.configure_pa_id = None
            st.rerun()

        if save_clicked:
            if not new_name.strip():
                st.error("Assistant name cannot be empty.")
            elif not new_skills:
                st.error("Attach at least one skill.")
            elif "telegram" in new_channels and not new_token.strip():
                st.error("Telegram requires a bot token.")
            else:
                config = dict(fresh.get("config") or {})
                telegram = dict(config.get("telegram") or {})
                if new_token.strip():
                    telegram["bot_token"] = new_token.strip()
                    telegram["auto_reply"] = new_auto_reply
                    config["telegram"] = telegram
                elif "telegram" in config:
                    del config["telegram"]

                update_assistant(
                    fresh["id"],
                    name=new_name.strip(),
                    skills=new_skills,
                    channels=new_channels,
                    config=config,
                )
                st.session_state.configure_pa_id = None
                st.toast(f"Updated {new_name.strip()}.", icon="✅")
                st.rerun()


def _render_create_pa_panel() -> None:
    """Inline panel to create a Personal Assistant."""
    skill_meta = {
        "email": {
            "icon": "📧",
            "title": "Email",
            "description": "Read, send, search, and organize Gmail.",
        },
        "drive": {
            "icon": "📁",
            "title": "Google Drive",
            "description": "Browse, upload, and manage Drive files.",
        },
        "files": {
            "icon": "🗂️",
            "title": "Local Files",
            "description": "Search, organize, and inspect local files.",
        },
        "calendar": {
            "icon": "📅",
            "title": "Calendar",
            "description": "View agendas, create events, and manage reminders.",
        },
        "scheduler": {
            "icon": "🧠",
            "title": "Smart Scheduler",
            "description": "Find slots, protect focus time, and resolve conflicts.",
        },
        "file_organizer": {
            "icon": "🗃️",
            "title": "File Organizer",
            "description": "Propose and apply tidy file organization plans.",
        },
        "habit_tracker": {
            "icon": "✅",
            "title": "Habit Tracker",
            "description": "Track habits, streaks, and progress reports.",
        },
        "browser": {
            "icon": "🌐",
            "title": "Web Browser",
            "description": "Browse websites, search, and summarize pages.",
        },
        "stock_market": {
            "icon": "📈",
            "title": "Stock Market Analysis",
            "description": "Quotes, indicators, sentiment, and portfolio insights.",
        },
        "linkedin": {
            "icon": "💼",
            "title": "LinkedIn",
            "description": "Create posts, schedule content, and track analytics.",
        },
    }

    available_skill_keys = _get_available_pa_skill_keys()
    if "create_pa_skills" not in st.session_state:
        st.session_state.create_pa_skills = set()
    else:
        st.session_state.create_pa_skills &= set(available_skill_keys)

    st.markdown(
        """
        <div style="background:linear-gradient(135deg,rgba(99,102,241,0.12) 0%,rgba(139,92,246,0.08) 100%);
                    border:1px solid rgba(99,102,241,0.25);border-radius:16px;padding:18px 20px;margin:18px 0 20px 0;">
            <div style="font-size:1.2rem;font-weight:800;color:#e2e8f0;">🤖 Create Personal Assistant</div>
            <div style="color:#94a3b8;font-size:0.84rem;margin-top:4px;">Choose from the shared skill catalog available to Personal Assistants.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;'>ASSISTANT NAME</p>",
        unsafe_allow_html=True,
    )
    pa_name = st.text_input(
        "Assistant Name",
        placeholder="e.g. My Work Assistant",
        label_visibility="collapsed",
    )

    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin:18px 0 10px 0;'>SKILLS</p>"
        "<div style='color:#64748b;font-size:0.82rem;margin-bottom:12px;'>Start with zero selected skills and enable only what this assistant should use.</div>",
        unsafe_allow_html=True,
    )

    if not available_skill_keys:
        st.warning("No assignable skills are available right now.")
    else:
        cols = st.columns(2)
        for idx, key in enumerate(available_skill_keys):
            meta = skill_meta.get(key, {"icon": "🔧", "title": key.capitalize(), "description": f"Use the {key} skill."})
            enabled = key in st.session_state.create_pa_skills
            border = "rgba(99,102,241,0.6)" if enabled else "rgba(255,255,255,0.08)"
            bg = "rgba(99,102,241,0.10)" if enabled else "rgba(255,255,255,0.03)"
            title_color = "#a5b4fc" if enabled else "#cbd5e1"
            with cols[idx % 2]:
                st.markdown(
                    f"""
                    <div style="background:{bg};border:1.5px solid {border};border-radius:12px;padding:12px 14px;margin-bottom:6px;min-height:104px;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                            <span style="font-size:1.3rem;">{meta['icon']}</span>
                            <span style="font-weight:700;color:{title_color};font-size:0.9rem;">{meta['title']}</span>
                        </div>
                        <div style="color:#64748b;font-size:0.78rem;line-height:1.45;">{meta['description']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                label = "✓ Enabled" if enabled else "Enable"
                btn_type = "primary" if enabled else "secondary"
                if st.button(label, key=f"pa_skill_{key}", type=btn_type, use_container_width=True):
                    if enabled:
                        st.session_state.create_pa_skills.discard(key)
                    else:
                        st.session_state.create_pa_skills.add(key)
                    st.rerun()

    selected_skills = list(st.session_state.create_pa_skills)

    st.divider()
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;'>TELEGRAM BOT <span style='color:#f87171;font-size:0.82rem;'>★ required</span></p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#64748b;font-size:0.82rem;margin-bottom:10px;'>Create a bot with <b style='color:#94a3b8;'>@BotFather</b>, then paste the token below so you can chat with this assistant from Telegram.</div>",
        unsafe_allow_html=True,
    )
    tg_token = st.text_input(
        "Telegram Bot Token",
        placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        type="password",
        label_visibility="collapsed",
    )

    col_save, col_cancel = st.columns([3, 1])
    with col_save:
        if st.button("✨ Create Assistant", type="primary", use_container_width=True):
            if not pa_name.strip():
                st.error("Please give your assistant a name.")
            elif not available_skill_keys:
                st.error("No assignable skills are available yet.")
            elif not selected_skills:
                st.error("Enable at least one skill so your assistant can help you.")
            elif not tg_token.strip():
                st.error("A Telegram Bot Token is required. Get one from @BotFather.")
            else:
                from src.agent.core.process_manager import start_agent
                from src.agent.hub.pa_manager import create_assistant

                config = {"telegram": {"bot_token": tg_token.strip(), "auto_reply": True}}
                new_pa = create_assistant(pa_name.strip(), selected_skills, ["dashboard", "telegram"], config=config)
                try:
                    start_agent(new_pa["id"], new_pa["name"], "personal_assistant")
                except Exception:
                    pass
                try:
                    from src.telegram.pa_poller_manager import start_pa_poller

                    start_pa_poller(new_pa["id"])
                except Exception as exc:
                    st.warning(f"Assistant created but Telegram bot failed to start: {exc}")

                st.session_state.pop("create_pa_skills", None)
                st.session_state.show_create_pa_panel = False
                st.toast(f"{new_pa['name']} is ready.", icon="✅")
                st.rerun()
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop("create_pa_skills", None)
            st.session_state.show_create_pa_panel = False
            st.rerun()


def _show_pa_card(pa: dict) -> None:
    """Render a single Personal Assistant card on the dashboard."""
    from src.agent.core.process_manager import start_agent, stop_agent
    from src.agent.hub.pa_manager import delete_assistant, update_assistant

    pa_id = pa["id"]
    pa_name = pa["name"]
    skills = pa.get("skills", [])
    status = get_agent_status(pa_id)
    is_running = status is not None

    tg_token = (pa.get("config") or {}).get("telegram", {}).get("bot_token", "").strip()
    try:
        from src.telegram.pa_poller_manager import get_pa_poller_status, start_pa_poller, stop_pa_poller

        tg_running = get_pa_poller_status(pa_id) is not None
    except Exception:
        start_pa_poller = None
        stop_pa_poller = None
        tg_running = False

    status_badge = "● Running" if is_running else "● Stopped"
    status_color = "#16a34a" if is_running else "#6b7280"
    tg_badge = "✈️ Bot Running" if tg_running else "✈️ Bot Stopped"
    tg_color = "#229ED9" if tg_running else "#6b7280"
    skill_tags = " ".join(
        f"<span style='background:rgba(124,58,237,0.18);color:#c4b5fd;padding:2px 8px;border-radius:10px;font-size:0.73rem;font-weight:600;margin:2px;display:inline-block;'>{skill}</span>"
        for skill in skills[:6]
    )

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#111827 0%,#1f2937 100%);padding:18px 20px 14px;border-radius:14px;border:1px solid rgba(124,58,237,0.28);margin-bottom:10px;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
                <div style="font-size:1.1rem;font-weight:800;color:#f8fafc;">🤖 {pa_name}</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <span style="background:{status_color};color:#fff;padding:3px 10px;border-radius:999px;font-size:0.74rem;font-weight:700;">{status_badge}</span>
                    <span style="background:{tg_color};color:#fff;padding:3px 10px;border-radius:999px;font-size:0.74rem;font-weight:700;">{tg_badge}</span>
                </div>
            </div>
            <div style="font-size:0.76rem;color:#64748b;font-weight:700;letter-spacing:0.06em;margin-bottom:6px;">SKILLS</div>
            <div style="margin-bottom:6px;">{skill_tags or "<span style='color:#64748b;font-size:0.8rem;'>No skills</span>"}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not tg_token:
        with st.expander("Add Telegram token", expanded=False):
            quick_token = st.text_input(
                "Paste your Bot Token from @BotFather",
                placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                type="password",
                key=f"quick_token_{pa_id}",
                label_visibility="collapsed",
            )
            if st.button("Save Token", key=f"save_token_{pa_id}", type="primary"):
                if quick_token.strip():
                    config = dict(pa.get("config") or {})
                    telegram = dict(config.get("telegram") or {})
                    telegram["bot_token"] = quick_token.strip()
                    telegram.setdefault("auto_reply", True)
                    config["telegram"] = telegram
                    update_assistant(pa_id, config=config)
                    st.rerun()
                else:
                    st.warning("Token cannot be empty.")

    col1, col2, col3, col4, col5 = st.columns([1.2, 1.05, 1.05, 0.52, 0.52])
    with col1:
        if is_running:
            if st.button("⏹️ Stop Assistant", key=f"stop_pa_{pa_id}", use_container_width=True):
                stop_agent(pa_id)
                if st.session_state.get("active_pa_id") == pa_id:
                    st.session_state.active_pa_url = None
                st.rerun()
        else:
            if st.button("▶️ Start Assistant", key=f"start_pa_{pa_id}", use_container_width=True, type="primary"):
                started = start_agent(pa_id, pa_name, "personal_assistant")
                _open_pa_workspace(pa_id, started.get("url"))
                st.rerun()
    with col2:
        if is_running and status and status.get("url"):
            if st.button("💬 Open Chat", key=f"open_chat_{pa_id}", use_container_width=True):
                _open_pa_workspace(pa_id, status["url"])
                st.rerun()
        else:
            st.button("💬 Open Chat", key=f"disabled_chat_{pa_id}", use_container_width=True, disabled=True)
    with col3:
        if tg_token and start_pa_poller and stop_pa_poller:
            if tg_running:
                if st.button("✈️ Stop Bot", key=f"stop_tg_{pa_id}", use_container_width=True):
                    stop_pa_poller(pa_id)
                    st.rerun()
            else:
                if st.button("✈️ Start Bot", key=f"start_tg_{pa_id}", use_container_width=True):
                    start_pa_poller(pa_id)
                    st.rerun()
        else:
            st.button("✈️ Start Bot", key=f"disabled_tg_{pa_id}", use_container_width=True, disabled=True)
    with col4:
        is_configuring = st.session_state.get("configure_pa_id") == pa_id
        cfg_label = "✖" if is_configuring else "⚙️"
        cfg_help = "Close configure" if is_configuring else "Configure assistant"
        if st.button(cfg_label, key=f"configure_pa_{pa_id}", use_container_width=True, help=cfg_help):
            _push_nav_state()
            st.session_state.configure_pa_id = None if is_configuring else pa_id
            st.session_state.configure_agent_id = None
            st.session_state.dashboard_scroll_target = None
            st.rerun()
    with col5:
        confirm_key = f"confirm_delete_pa_{pa_id}"
        if not st.session_state.get(confirm_key, False):
            if st.button("🗑️", key=f"delete_pa_{pa_id}", use_container_width=True, help="Delete assistant"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            if st.button("⚠️ Confirm", key=f"confirm_pa_{pa_id}", use_container_width=True, type="primary"):
                try:
                    stop_agent(pa_id)
                except Exception:
                    pass
                if stop_pa_poller:
                    try:
                        stop_pa_poller(pa_id)
                    except Exception:
                        pass
                delete_assistant(pa_id)
                st.session_state[confirm_key] = False
                st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Octa Bot — Agent Hub",
        page_icon=_logo_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_css()
    cleanup_stale()

    if "show_create_form" not in st.session_state:
        st.session_state.show_create_form = False
    if "configure_agent_id" not in st.session_state:
        st.session_state.configure_agent_id = None
    if "configure_pa_id" not in st.session_state:
        st.session_state.configure_pa_id = None
    if "show_log_viewer" not in st.session_state:
        st.session_state.show_log_viewer = False
    if "show_create_pa_panel" not in st.session_state:
        st.session_state.show_create_pa_panel = False
    if "active_pa_id" not in st.session_state:
        st.session_state.active_pa_id = None
    if "active_pa_url" not in st.session_state:
        st.session_state.active_pa_url = None
    if "nav_history" not in st.session_state:
        st.session_state.nav_history = []
    if "dashboard_scroll_target" not in st.session_state:
        st.session_state.dashboard_scroll_target = None

    manager = get_agent_manager()
    agents = manager.list_agents()

    from src.agent.hub.pa_manager import load_assistants

    assistants = load_assistants()
    skill_catalog = _build_skill_catalog(manager, assistants)
    skill_count = len(skill_catalog)

    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;padding:8px 0 16px 0;border-bottom:1px solid rgba(99,102,241,0.2);margin-bottom:16px;">
                <img src="{_logo_b64()}" style="width:34px;height:34px;border-radius:8px;object-fit:cover;">
                <div>
                    <div style="font-size:1.05rem;font-weight:800;background:linear-gradient(135deg,#e91e8c 0%,#a5b4fc 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1.1;">Octa Bot</div>
                    <div style="font-size:0.68rem;color:#475569;font-weight:500;letter-spacing:0.05em;">AGENT HUB</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        nav_col1, nav_col2 = st.columns(2)
        with nav_col1:
            if st.button("⌂", key="sidebar_home", use_container_width=True, help="Go to Dashboard home"):
                _go_home(section=None, push_history=True)
                st.rerun()
        with nav_col2:
            back_disabled = not bool(st.session_state.get("nav_history"))
            if st.button("←", key="sidebar_back", use_container_width=True, help="Go back", disabled=back_disabled):
                _go_back()
                st.rerun()

        st.markdown(
            "<p style='font-size:0.72rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;margin:14px 0 8px 0;'>Jump To</p>",
            unsafe_allow_html=True,
        )
        if st.button("Personal Assistants", key="jump_assistants", use_container_width=True):
            _set_dashboard_scroll_target("assistants-section")
            st.rerun()
        if st.button("Skills", key="jump_skills", use_container_width=True):
            _set_dashboard_scroll_target("skills-section")
            st.rerun()
        if st.button("Channels", key="jump_channels", use_container_width=True):
            _set_dashboard_scroll_target("channels-section")
            st.rerun()

        st.divider()

        if st.button("🤖  Create Personal Assistant", use_container_width=True, type="primary"):
            _push_nav_state()
            st.session_state.show_create_pa_panel = True
            st.session_state.show_create_form = False
            st.session_state.show_log_viewer = False
            st.session_state.configure_agent_id = None
            st.session_state.configure_pa_id = None
            st.session_state.active_pa_id = None
            st.session_state.active_pa_url = None
            st.session_state.dashboard_scroll_target = None
            st.rerun()

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        if st.button("➕  Add Agent / Skill", use_container_width=True):
            _push_nav_state()
            st.session_state.show_create_form = True
            st.session_state.show_create_pa_panel = False
            st.session_state.show_log_viewer = False
            st.session_state.configure_agent_id = None
            st.session_state.configure_pa_id = None
            st.session_state.active_pa_id = None
            st.session_state.active_pa_url = None
            st.session_state.dashboard_scroll_target = None
            st.rerun()

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        logs_btn_type = "primary" if st.session_state.show_log_viewer else "secondary"
        if st.button("📊  Log Analyser", use_container_width=True, type=logs_btn_type):
            _push_nav_state()
            st.session_state.show_log_viewer = not st.session_state.show_log_viewer
            st.session_state.show_create_form = False
            st.session_state.show_create_pa_panel = False
            st.session_state.configure_agent_id = None
            st.session_state.configure_pa_id = None
            st.session_state.active_pa_id = None
            st.session_state.active_pa_url = None
            st.session_state.dashboard_scroll_target = None
            st.rerun()

        st.divider()
        st.markdown(
            "<p style='font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 10px 0;'>YOUR ASSISTANTS</p>",
            unsafe_allow_html=True,
        )
        if assistants:
            for assistant in assistants:
                status = get_agent_status(assistant["id"])
                running = status is not None
                dot_color = "#22c55e" if running else "#6b7280"
                state_label = "Running" if running else "Stopped"
                st.markdown(
                    f"<div style='display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:rgba(255,255,255,0.03);border-radius:8px;border:1px solid rgba(255,255,255,0.06);margin-bottom:6px;'><div style='overflow:hidden;flex:1;min-width:0;'><div style='font-size:0.84rem;font-weight:600;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{assistant['name']}</div><div style='font-size:0.72rem;color:#475569;'>{', '.join(assistant.get('skills', []))[:28]}</div></div><span style='background:{dot_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.68rem;font-weight:700;white-space:nowrap;margin-left:6px;'>{state_label}</span></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div style='color:#475569;font-size:0.82rem;text-align:center;padding:12px 8px;background:rgba(255,255,255,0.02);border-radius:8px;border:1px dashed rgba(255,255,255,0.08);'>No assistants yet.<br>Create one above ↑</div>",
                unsafe_allow_html=True,
            )

        st.divider()
        running_pas = sum(1 for assistant in assistants if get_agent_status(assistant["id"]) is not None)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;background:rgba(233,30,140,0.06);border:1px solid rgba(233,30,140,0.2);border-radius:10px;'><div style='font-size:1.5rem;font-weight:800;color:#e91e8c;line-height:1;'>{skill_count}</div><div style='font-size:0.7rem;color:#475569;margin-top:2px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;'>Skills</div></div>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.2);border-radius:10px;'><div style='font-size:1.5rem;font-weight:800;color:#22c55e;line-height:1;'>{running_pas}/{len(assistants)}</div><div style='font-size:0.7rem;color:#475569;margin-top:2px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;'>Active</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.08) 50%, rgba(233,30,140,0.06) 100%);border:1px solid rgba(99,102,241,0.25);padding:28px 28px 22px;border-radius:20px;margin-bottom:28px;backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(99,102,241,0.12);">
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:10px;">
                <img src="{_logo_b64()}" style="width:60px;height:60px;border-radius:14px;object-fit:cover;box-shadow:0 4px 16px rgba(99,102,241,0.35);">
                <div>
                    <div style="font-size:2.2rem;font-weight:900;background:linear-gradient(135deg,#e91e8c 0%,#a5b4fc 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1.1;">Octa Bot</div>
                    <div style="font-size:0.95rem;color:#64748b;margin-top:4px;font-weight:500;">Your AI-powered hub — one place to manage all your digital life</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.show_log_viewer:
        show_log_viewer()
        return

    active_pa = next((assistant for assistant in assistants if assistant["id"] == st.session_state.active_pa_id), None)
    if st.session_state.active_pa_id and not active_pa:
        _close_pa_workspace()
        st.rerun()

    if active_pa:
        _render_pa_workspace(active_pa, manager)
        return

    if st.session_state.show_create_pa_panel:
        _render_create_pa_panel()

    if st.session_state.show_create_form:
        show_create_agent_form()

    cfg_agent = next((agent for agent in agents if agent["id"] == st.session_state.configure_agent_id), None)
    if cfg_agent:
        show_configure_panel(cfg_agent)

    cfg_pa = next((assistant for assistant in assistants if assistant["id"] == st.session_state.configure_pa_id), None)
    if cfg_pa:
        _render_pa_configure_panel(cfg_pa)

    st.markdown("<div id='skills-section'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.1rem;font-weight:700;color:#94a3b8;margin:16px 0 8px 0;text-transform:uppercase;letter-spacing:0.06em;'>🧩 Skills</div>"
        "<div style='color:#64748b;font-size:0.82rem;margin-bottom:12px;'>These skills are available to assign to Personal Assistants.</div>",
        unsafe_allow_html=True,
    )

    search_col, filter_col = st.columns([2, 1])
    with search_col:
        search = st.text_input("Search skills", placeholder="Search by name or type", label_visibility="collapsed")
    with filter_col:
        filter_types = [skill["key"] for skill in skill_catalog]
        filter_type = st.selectbox("Filter by type", ["All"] + filter_types, label_visibility="collapsed")

    visible_skills = list(skill_catalog)
    if search:
        query = search.lower()
        visible_skills = [
            skill
            for skill in visible_skills
            if query in skill["name"].lower()
            or query in skill["key"].lower()
            or query in skill["description"].lower()
        ]
    if filter_type != "All":
        visible_skills = [skill for skill in visible_skills if skill["key"] == filter_type]

    st.markdown(
        f"<div style='color:#64748b;font-size:0.85rem;margin:16px 0 20px 0;'>Showing {len(visible_skills)} of {skill_count} skill(s)</div>",
        unsafe_allow_html=True,
    )

    if visible_skills:
        cols = st.columns(5)
        for idx, skill in enumerate(visible_skills):
            with cols[idx % 5]:
                usage_count = skill["assistant_count"]
                usage_badge = (
                    f"<span style='background:rgba(34,197,94,0.16);color:#86efac;padding:2px 8px;border-radius:999px;font-size:0.68rem;font-weight:700;'>Enabled on {usage_count} assistant{'s' if usage_count != 1 else ''}</span>"
                    if usage_count
                    else "<span style='background:rgba(148,163,184,0.12);color:#94a3b8;padding:2px 8px;border-radius:999px;font-size:0.68rem;font-weight:700;'>Not enabled yet</span>"
                )
                with st.container(border=True):
                    st.markdown(
                        f"""
                        <div style="border:1px solid rgba(99,102,241,0.22);border-radius:12px;padding:10px 10px 8px;background:rgba(15,23,42,0.28);margin-bottom:8px;">
                        <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px;">
                            <span style="font-size:1.1rem;line-height:1;margin-top:1px;">{skill['icon']}</span>
                            <div>
                                <div style="font-size:0.84rem;font-weight:800;color:#e2e8f0;line-height:1.15;">{skill['key']}-agent-skill</div>
                                <div style="font-size:0.7rem;color:#94a3b8;line-height:1.2;">{skill['name']}</div>
                            </div>
                        </div>
                        <div style="font-size:0.76rem;color:#94a3b8;line-height:1.4;margin-bottom:8px;min-height:52px;">
                            {skill['description']}
                        </div>
                        <div style="margin-bottom:2px;">{usage_badge}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    with st.expander("View Help"):
                        st.markdown(skill["help_markdown"] or "Help content is not available for this skill yet.")
                        st.caption("Assistant Access")
                        pa_options = [assistant["id"] for assistant in assistants]
                        selected_pa_ids = st.multiselect(
                            "Enabled for assistants",
                            options=pa_options,
                            default=[pa_id for pa_id in skill["enabled_assistant_ids"] if pa_id in pa_options],
                            format_func=lambda pa_id: next((assistant["name"] for assistant in assistants if assistant["id"] == pa_id), pa_id),
                            key=f"skill_assign_{skill['key']}",
                            help="Choose which Personal Assistants can use this skill.",
                        )
                        if st.button("Save Access", key=f"save_skill_assign_{skill['key']}", use_container_width=True):
                            if _update_skill_assignments(skill["key"], selected_pa_ids, assistants):
                                st.toast(f"Updated {skill['name']} access.", icon="✅")
                                st.rerun()
                            st.info("No changes to save.")
    else:
        st.markdown(
            "<div style='background:rgba(255,107,107,0.1);border:1px solid rgba(255,107,107,0.2);padding:20px;border-radius:12px;text-align:center;'><div style='color:#ff6b6b;font-weight:600;'>No skills match your filters</div><div style='color:#888;font-size:0.9rem;margin-top:6px;'>Try adjusting your search terms or filters.</div></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("<div id='channels-section'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.1rem;font-weight:700;color:#94a3b8;margin:16px 0 8px 0;text-transform:uppercase;letter-spacing:0.06em;'>📡 Channels</div>"
        "<div style='color:#64748b;font-size:0.82rem;margin-bottom:12px;'>Dashboard is always on. Telegram bots are managed per assistant.</div>",
        unsafe_allow_html=True,
    )

    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        from src.telegram.pa_poller_manager import get_pa_poller_status

        dashboard_col, telegram_col = st.columns(2)
        dashboard_channel = CHANNEL_REGISTRY.get("dashboard")
        telegram_channel = CHANNEL_REGISTRY.get("telegram")
        bot_count = sum(1 for assistant in assistants if get_pa_poller_status(assistant["id"]) is not None)

        with dashboard_col:
            if dashboard_channel is not None:
                try:
                    dashboard_status = dashboard_channel.status()
                    detail = f"Port {dashboard_status.port}" if dashboard_status.port else (dashboard_status.detail or "Always available")
                except Exception:
                    detail = "Always available"
                st.markdown(
                    f"<div style='background:rgba(22,163,74,0.08);border:1px solid rgba(22,163,74,0.28);padding:14px 16px;border-radius:12px;'><div style='display:flex;align-items:center;justify-content:space-between;gap:12px;'><div><div style='font-size:1rem;font-weight:700;color:#e2e8f0;'>{dashboard_channel.icon} {dashboard_channel.display_name}</div><div style='font-size:0.8rem;color:#94a3b8;margin-top:4px;'>Streamlit web dashboard</div></div><span style='background:#16a34a;color:#fff;padding:3px 10px;border-radius:999px;font-size:0.74rem;font-weight:700;'>● {detail}</span></div></div>",
                    unsafe_allow_html=True,
                )

        with telegram_col:
            if telegram_channel is not None:
                badge_color = "#229ED9" if bot_count else "#4b5563"
                state = f"{bot_count} bot{'s' if bot_count != 1 else ''} running" if bot_count else "No bots running"
                st.markdown(
                    f"<div style='background:rgba(34,158,217,0.08);border:1px solid rgba(34,158,217,0.24);padding:14px 16px;border-radius:12px;'><div style='display:flex;align-items:center;justify-content:space-between;gap:12px;'><div><div style='font-size:1rem;font-weight:700;color:#e2e8f0;'>{telegram_channel.icon} {telegram_channel.display_name}</div><div style='font-size:0.8rem;color:#94a3b8;margin-top:4px;'>Managed from each PA card</div></div><span style='background:{badge_color};color:#fff;padding:3px 10px;border-radius:999px;font-size:0.74rem;font-weight:700;'>✈️ {state}</span></div></div>",
                    unsafe_allow_html=True,
                )
    except Exception as exc:
        st.warning(f"Could not load channel registry: {exc}")

    st.divider()
    st.markdown("<div id='assistants-section'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:1.1rem;font-weight:700;color:#94a3b8;margin:16px 0 10px 0;text-transform:uppercase;letter-spacing:0.06em;'>🤖 Personal Assistants</div>"
        "<div style='color:#475569;font-size:0.84rem;margin-bottom:16px;'>Your AI assistants, each with their own memory, skills, and Telegram bot.</div>",
        unsafe_allow_html=True,
    )
    if assistants:
        cols = st.columns(2)
        for idx, assistant in enumerate(assistants):
            with cols[idx % 2]:
                _show_pa_card(assistant)
    else:
        st.markdown(
            "<div style='background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2);padding:20px;border-radius:12px;text-align:center;color:#a78bfa;'>No personal assistants yet. Click <b>🤖 Create Personal Assistant</b> in the sidebar to get started.</div>",
            unsafe_allow_html=True,
        )

    scroll_target = st.session_state.get("dashboard_scroll_target")
    if scroll_target:
        components.html(
            f"""
            <script>
            (function() {{
                var docs = [window.parent.document, document];
                for (var i = 0; i < docs.length; i++) {{
                    var el = docs[i].getElementById("{scroll_target}");
                    if (el) {{
                        el.scrollIntoView({{behavior: "smooth", block: "start"}});
                        break;
                    }}
                }}
            }})();
            </script>
            """,
            height=0,
        )
        st.session_state.dashboard_scroll_target = None


if __name__ == "__main__":
    main()
