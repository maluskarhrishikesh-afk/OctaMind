"""
OctaMind Agent Hub — main Streamlit entry point.
"""
from __future__ import annotations

import logging

import streamlit as st

from src.agent.core.process_manager import cleanup_stale, get_agent_status
from src.agent.core.agent_manager import get_agent_manager

from .helpers import _logo_b64, _logo_icon
from .styles import inject_css
from .create_form import show_create_agent_form
from .agent_card import show_agent_card
from .configure_panel import show_configure_panel

logger = logging.getLogger("octamind.dashboard")

# ---------------------------------------------------------------------------
# One-time application startup (runs once per Streamlit worker process).
# A module-level flag ensures this block does NOT re-execute on every
# Streamlit hot-reload / page interaction.
# ---------------------------------------------------------------------------
_APP_INITIALIZED: bool = False


def _startup() -> None:
    """
    Bootstrap tasks that must run exactly once when the app process starts:
      1. Ensure __multi_agent__ memory files exist (creates them if absent).
      2. Start the global consolidation background thread.
    """
    global _APP_INITIALIZED
    if _APP_INITIALIZED:
        return
    _APP_INITIALIZED = True

    # 1 — Ensure multi-agent memory is ready from the very first launch
    try:
        from src.agent.memory.agent_memory import get_agent_memory, MULTI_AGENT_ID
        get_agent_memory(MULTI_AGENT_ID)   # triggers _ensure_memory_files_exist()
        logger.info("[startup] Multi-agent memory initialised.")
    except Exception as exc:
        logger.error(f"[startup] Failed to init multi-agent memory: {exc}")

    # 2 — Start the 30-minute smart consolidation background thread
    #     (dirty-check gated: only runs when new interactions exist)
    try:
        from src.agent.memory.consolidation_runner import get_consolidation_runner
        runner = get_consolidation_runner()
        runner.start()
        logger.info("[startup] ConsolidationRunner (30-min smart) started.")
    except Exception as exc:
        logger.error(f"[startup] Failed to start ConsolidationRunner: {exc}")


_startup()   # execute at import time (once per process)


@st.dialog("🤖 Create Personal Assistant", width="large")
def _create_pa_dialog() -> None:
    """Dialog to create a new Personal Assistant with selected skills + channels."""
    # ── Skill catalogue with plain-language descriptions ─────────────────
    _SKILL_META = {
        "email": {
            "icon": "📧",
            "title": "Email",
            "description": "Read, send & organise your Gmail inbox. Get smart summaries, set follow-up reminders, and search emails by anything.",
        },
        "drive": {
            "icon": "📁",
            "title": "Google Drive",
            "description": "Browse and manage your Google Drive. Upload, share, organize folders, and find any file instantly.",
        },
        "files": {
            "icon": "🗂️",
            "title": "Local Files",
            "description": "Organise your computer's files. Search, sort, zip archives, and analyse what's taking up space.",
        },
        "whatsapp": {
            "icon": "💬",
            "title": "WhatsApp",
            "description": "Chat via WhatsApp. Send messages, manage contacts, schedule messages, and get conversation summaries.",
        },
        "calendar": {
            "icon": "📅",
            "title": "Calendar",
            "description": "Manage your Google Calendar. Create and update events, find free slots, get daily agendas, and set reminders.",
        },
        "scheduler": {
            "icon": "🧠",
            "title": "Smart Scheduler",
            "description": "Intelligent calendar scheduling — finds optimal meeting slots, protects focus time, and resolves calendar conflicts automatically.",
        },
        "file_organizer": {
            "icon": "🗃️",
            "title": "File Organizer",
            "description": "Approval-driven file organisation. Scans folders, proposes tidy plans by type or date, and applies them only after your confirmation.",
        },
        "habit_tracker": {
            "icon": "✅",
            "title": "Habit Tracker",
            "description": "Build better habits. Track daily completions, monitor streaks, get weekly reports, and receive motivating analytics.",
        },
        "browser": {
            "icon": "🌐",
            "title": "Web Browser",
            "description": "Browse any website, search the web, extract article text, find links, download files, and get instant page summaries — all without leaving the app.",
        },
        "stock_market": {
            "icon": "📈",
            "title": "Stock Market Analysis",
            "description": "Real-time quotes, technical indicators (RSI, MACD, Bollinger), risk scoring, pattern detection, portfolio analysis, news sentiment, and market overview. Informational only — no buy/sell.",
        },
    }

    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        all_skill_keys = list(AGENT_REGISTRY.keys())
    except Exception:
        all_skill_keys = list(_SKILL_META.keys())

    # ── Initialise selected_skills in session state ───────────────────────
    if "create_pa_skills" not in st.session_state:
        st.session_state.create_pa_skills = set(all_skill_keys)

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,rgba(99,102,241,0.12) 0%,rgba(139,92,246,0.08) 100%);
                    border:1px solid rgba(99,102,241,0.25);border-radius:14px;
                    padding:16px 20px;margin-bottom:20px;">
            <div style="color:#a5b4fc;font-size:0.875rem;line-height:1.6;">
                Your Personal Assistant will use the selected skills to help you with various tasks.
                It remembers your preferences and learns from every interaction.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Assistant Name ────────────────────────────────────────────────────
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:0.08em;margin-bottom:6px;'>ASSISTANT NAME</p>",
        unsafe_allow_html=True,
    )
    pa_name = st.text_input(
        "Assistant Name",
        placeholder="e.g. My Work Assistant",
        label_visibility="collapsed",
    )

    # ── Skills ────────────────────────────────────────────────────────────
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:0.08em;margin:18px 0 10px 0;'>SKILLS  <span style=\"color:#475569;font-weight:500;font-size:0.72rem;text-transform:none;\">"
        "— choose what your assistant can do</span></p>",
        unsafe_allow_html=True,
    )
    skill_cols = st.columns(2)
    for i, key in enumerate(all_skill_keys):
        meta = _SKILL_META.get(key, {"icon": "🔧", "title": key.capitalize(), "description": f"Use the {key} skill."})
        is_on = key in st.session_state.create_pa_skills
        with skill_cols[i % 2]:
            border_col = "rgba(99,102,241,0.6)" if is_on else "rgba(255,255,255,0.08)"
            bg_col = "rgba(99,102,241,0.10)" if is_on else "rgba(255,255,255,0.03)"
            title_col = "#a5b4fc" if is_on else "#64748b"
            check = "✓ " if is_on else ""
            st.markdown(
                f"""
                <div style="background:{bg_col};border:1.5px solid {border_col};border-radius:12px;
                            padding:12px 14px;margin-bottom:6px;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                        <span style="font-size:1.3rem;">{meta['icon']}</span>
                        <span style="font-weight:700;color:{title_col};font-size:0.9rem;">{check}{meta['title']}</span>
                    </div>
                    <div style="color:#475569;font-size:0.78rem;line-height:1.45;">{meta['description']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            btn_label = "✓ Enabled" if is_on else "Enable"
            btn_type = "primary" if is_on else "secondary"
            if st.button(btn_label, key=f"pa_skill_{key}", use_container_width=True, type=btn_type):
                if is_on:
                    st.session_state.create_pa_skills.discard(key)
                else:
                    st.session_state.create_pa_skills.add(key)
                st.rerun()

    selected_skills = list(st.session_state.create_pa_skills)

    # ── Channels (simplified — Dashboard always on, Telegram optional) ───
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    st.divider()
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:0.08em;margin-bottom:12px;'>TELEGRAM BOT  "
        "<span style='color:#f87171;font-size:0.82rem;'>★ required</span></p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='color:#64748b;font-size:0.82rem;margin-bottom:10px;'>"
        "Create a Telegram bot via <b style='color:#94a3b8;'>@BotFather</b> (free), "
        "copy the token it gives you, and paste it below. "
        "This is how you'll chat with your assistant on your phone."
        "</div>",
        unsafe_allow_html=True,
    )
    tg_token = st.text_input(
        "Telegram Bot Token",
        placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        type="password",
        label_visibility="collapsed",
    )

    # ── Action buttons ────────────────────────────────────────────────────
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    col_save, col_cancel = st.columns([3, 1])
    with col_save:
        if st.button("✨ Create Assistant", type="primary", use_container_width=True):
            if not pa_name.strip():
                st.error("⚠️ Please give your assistant a name.")
            elif not selected_skills:
                st.error("⚠️ Enable at least one skill so your assistant can help you.")
            elif not tg_token.strip():
                st.error("⚠️ A Telegram Bot Token is required — get one free from @BotFather on Telegram.")
            else:
                from src.agent.hub.pa_manager import create_assistant
                from src.agent.core.process_manager import start_agent
                selected_channels = ["dashboard", "telegram"]
                cfg = {"telegram": {"bot_token": tg_token.strip(), "auto_reply": True}}
                new_pa = create_assistant(pa_name.strip(), selected_skills, selected_channels, config=cfg)
                try:
                    start_agent(new_pa["id"], new_pa["name"], "personal_assistant")
                except Exception:
                    pass
                try:
                    from src.telegram.pa_poller_manager import start_pa_poller
                    start_pa_poller(new_pa["id"])
                except Exception as _tge:
                    st.warning(f"⚠️ Assistant created but Telegram bot failed to start: {_tge}")
                # Clean up session state
                if "create_pa_skills" in st.session_state:
                    del st.session_state["create_pa_skills"]
                st.toast(f"✅ **{new_pa['name']}** is ready! Reload the page to open its Chat window.", icon="✅")
                st.rerun()
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            if "create_pa_skills" in st.session_state:
                del st.session_state["create_pa_skills"]
            st.rerun()


def _show_pa_card(pa: dict) -> None:
    """Render a single Personal Assistant card on the dashboard."""
    from src.agent.core.process_manager import start_agent, stop_agent
    from src.agent.hub.pa_manager import delete_assistant

    pa_id   = pa["id"]
    pa_name = pa["name"]
    skills   = pa.get("skills", [])
    channels = pa.get("channels", [])

    # ── Gather status ──────────────────────────────────────────────────────
    status     = get_agent_status(pa_id)
    is_running = status is not None

    tg_token = (pa.get("config") or {}).get("telegram", {}).get("bot_token", "").strip()
    start_pa_poller = stop_pa_poller = None
    try:
        from src.telegram.pa_poller_manager import get_pa_poller_status, start_pa_poller, stop_pa_poller
        tg_running = get_pa_poller_status(pa_id) is not None
    except Exception:
        tg_running = False

    # ── Visual variables ───────────────────────────────────────────────────
    pa_badge_color  = "#16a34a" if is_running else "#6b7280"
    pa_badge_label  = "● Running" if is_running else "● Stopped"
    tg_badge_color  = "#229ED9" if tg_running else "#6b7280"
    tg_badge_label  = "✈️ Bot Running" if tg_running else "✈️ Bot Stopped"

    skill_tags = " ".join(
        f"<span style='background:rgba(124,58,237,0.18);color:#a78bfa;"
        f"padding:2px 8px;border-radius:10px;font-size:0.73rem;font-weight:600;margin:2px;'>{s}</span>"
        for s in skills[:6]
    )

    # ── Card HTML ──────────────────────────────────────────────────────────
    glow = "0 0 20px rgba(124,58,237,0.45)" if is_running else "0 4px 14px rgba(0,0,0,0.22)"
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#1a1a2e 0%,{'#1e0a3c' if is_running else '#16213e'} 100%);
                    padding:18px 20px 14px;border-radius:14px;
                    border:1.5px solid rgba(124,58,237,{'0.6' if is_running else '0.35'});
                    margin-bottom:4px;box-shadow:{glow};position:relative;overflow:hidden;">
          <!-- bg glow -->
          <div style="position:absolute;top:-20px;right:-20px;width:110px;height:110px;
                      background:radial-gradient(circle,rgba(124,58,237,0.10) 0%,transparent 70%);
                      border-radius:50%;pointer-events:none;"></div>
          <div style="position:relative;z-index:1;">
            <!-- Row 1: name + PA status badge + Telegram badge -->
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
              <span style="font-size:1.15rem;font-weight:800;
                           background:linear-gradient(135deg,#a78bfa 0%,#7c3aed 100%);
                           -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                           background-clip:text;flex:1;min-width:100px;">🤖 {pa_name}</span>
              <span style="background:{pa_badge_color};color:#fff;padding:3px 10px;
                           border-radius:20px;font-size:0.74rem;font-weight:700;white-space:nowrap;">{pa_badge_label}</span>
              <span style="background:{'rgba(34,158,217,0.25)' if tg_running else 'rgba(107,114,128,0.2)'};
                           color:{'#229ED9' if tg_running else '#9ca3af'};padding:3px 10px;
                           border-radius:20px;font-size:0.74rem;font-weight:700;white-space:nowrap;
                           border:1px solid {'rgba(34,158,217,0.4)' if tg_running else 'rgba(107,114,128,0.25)'};">{tg_badge_label}</span>
            </div>
            <!-- Row 2: skills -->
            <div style="font-size:0.78rem;color:#6b7280;font-weight:600;
                        margin-bottom:6px;letter-spacing:0.04em;">SKILLS</div>
            <div style="margin-bottom:4px;">{skill_tags if skill_tags else "<span style='color:#4b5563;font-size:0.78rem;'>none</span>"}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── No-token warning with inline quick-set ──────────────────────────────
    pa_url = (status or {}).get("url", "") if is_running else ""
    if not tg_token:
        with st.expander("⚠️ No Telegram token — click to add one", expanded=False):
            quick_token = st.text_input(
                "Paste your Bot Token from @BotFather",
                placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                type="password",
                key=f"quick_token_{pa_id}",
                label_visibility="collapsed",
            )
            if st.button("💾 Save Token", key=f"save_token_{pa_id}", type="primary"):
                if quick_token.strip():
                    from src.agent.hub.pa_manager import update_assistant
                    cfg = dict(pa.get("config") or {})
                    tg = dict(cfg.get("telegram") or {})
                    tg["bot_token"] = quick_token.strip()
                    tg.setdefault("auto_reply", True)
                    cfg["telegram"] = tg
                    update_assistant(pa_id, config=cfg)
                    st.rerun()
                else:
                    st.warning("Token cannot be empty.")

    # ── Action buttons ──────────────────────────────────────────────────────
    # When PA is running: [Open Chat] [▶️ Start Bot?] [Stop PA] [🗑️]
    # When PA is stopped: [Start PA]                            [🗑️]
    if is_running:
        show_start_bot = bool(tg_token and not tg_running and start_pa_poller)
        if show_start_bot:
            c1, c2, c3, c4 = st.columns([2, 1.6, 1.5, 0.8])
        else:
            c1, c3, c4 = st.columns([2, 1.5, 0.8])
            c2 = None

        with c1:
            if pa_url:
                st.link_button("🚀 Open Chat", url=pa_url, type="primary", use_container_width=True)
            else:
                st.button("🚀 Open", key=f"open_pa_{pa_id}", disabled=True, use_container_width=True)

        if c2 is not None:
            with c2:
                if st.button("✈️ Start Bot", key=f"start_bot_{pa_id}", use_container_width=True, type="primary"):
                    try:
                        start_pa_poller(pa_id)
                        st.rerun()
                    except Exception as _tge:
                        st.error(f"Bot failed to start: {_tge}")

        with c3:
            if st.button("⏹️ Stop PA", key=f"stop_pa_{pa_id}", use_container_width=True):
                with st.spinner(f"Stopping {pa_name}…"):
                    if tg_running and stop_pa_poller:
                        try:
                            stop_pa_poller(pa_id)
                        except Exception:
                            pass
                    stop_agent(pa_id)
                st.rerun()

    else:
        c1, c4 = st.columns([3, 0.8])
        with c1:
            if st.button("▶️ Start PA", key=f"start_pa_{pa_id}", type="primary", use_container_width=True):
                with st.spinner(f"Launching {pa_name}…"):
                    try:
                        info = start_agent(pa_id, pa_name, "personal_assistant")
                        if tg_token and start_pa_poller:
                            try:
                                start_pa_poller(pa_id)
                            except Exception as _tge:
                                st.warning(f"PA started but bot failed to launch: {_tge}")
                        st.toast(f"✅ Started on port {info['port']}", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    with c4:
        if st.button("🗑️", key=f"del_pa_{pa_id}", use_container_width=True,
                     help=f"Delete {pa_name}"):
            with st.spinner(f"Deleting {pa_name}…"):
                try:
                    if tg_running and stop_pa_poller:
                        stop_pa_poller(pa_id)
                except Exception:
                    pass
                try:
                    if is_running:
                        stop_agent(pa_id)
                except Exception:
                    pass
                delete_assistant(pa_id)
            st.rerun()

    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="OctaMind — Agent Hub",
        page_icon=_logo_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_css()

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
        # Logo / branding
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;padding:8px 0 16px 0;
                        border-bottom:1px solid rgba(99,102,241,0.2);margin-bottom:16px;">
                <img src="{_logo_b64()}" style="width:34px;height:34px;border-radius:8px;object-fit:cover;">
                <div>
                    <div style="font-size:1.05rem;font-weight:800;
                                background:linear-gradient(135deg,#e91e8c 0%,#a5b4fc 100%);
                                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                                background-clip:text;line-height:1.1;">OctaMind</div>
                    <div style="font-size:0.68rem;color:#475569;font-weight:500;letter-spacing:0.05em;">AGENT HUB</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Primary action ────────────────────────────────────────────────
        if st.button("🤖  Create Personal Assistant", use_container_width=True, type="primary"):
            _create_pa_dialog()

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        if st.button("➕  Add Agent / Skill", use_container_width=True):
            st.session_state.show_create_form = True
            st.rerun()

        st.divider()

        # ── Your Assistants — live status ─────────────────────────────────
        from src.agent.hub.pa_manager import load_assistants as _load_pa
        _all_pas = _load_pa()

        st.markdown(
            "<p style='font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;"
            "letter-spacing:0.08em;margin:0 0 10px 0;'>YOUR ASSISTANTS</p>",
            unsafe_allow_html=True,
        )
        if _all_pas:
            for _pa in _all_pas:
                _status = get_agent_status(_pa["id"])
                _running = _status is not None
                _dot_col = "#22c55e" if _running else "#6b7280"
                _state_label = "Running" if _running else "Stopped"
                try:
                    from src.telegram.pa_poller_manager import get_pa_poller_status as _gps2
                    _tg_running = _gps2(_pa["id"]) is not None
                    _tg_dot = "✈️" if _tg_running else ""
                except Exception:
                    _tg_dot = ""
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;justify-content:space-between;
                                padding:8px 10px;background:rgba(255,255,255,0.03);border-radius:8px;
                                border:1px solid rgba(255,255,255,0.06);margin-bottom:6px;">
                        <div style="overflow:hidden;flex:1;min-width:0;">
                            <div style="font-size:0.84rem;font-weight:600;color:#e2e8f0;
                                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                                {_tg_dot} {_pa['name']}
                            </div>
                            <div style="font-size:0.72rem;color:#475569;">{', '.join(_pa.get('skills',[]))[:28]}</div>
                        </div>
                        <span style="background:{_dot_col};color:#fff;padding:2px 8px;
                                     border-radius:10px;font-size:0.68rem;font-weight:700;
                                     white-space:nowrap;margin-left:6px;">{_state_label}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div style='color:#475569;font-size:0.82rem;text-align:center;padding:12px 8px;"
                "background:rgba(255,255,255,0.02);border-radius:8px;border:1px dashed rgba(255,255,255,0.08);'>"
                "No assistants yet.<br>Create one above ↑</div>",
                unsafe_allow_html=True,
            )

        st.divider()

        # ── Skills & system stats ─────────────────────────────────────────
        _CH_TYPES_SIDE = {"telegram", "whatsapp"}
        skill_count = sum(1 for a in agents if a["type"] not in _CH_TYPES_SIDE)
        pa_count = len(_all_pas)
        _running_pas = sum(1 for _pa in _all_pas if get_agent_status(_pa["id"]) is not None)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;background:rgba(233,30,140,0.06);"
                f"border:1px solid rgba(233,30,140,0.2);border-radius:10px;'>"
                f"<div style='font-size:1.5rem;font-weight:800;color:#e91e8c;line-height:1;'>{skill_count}</div>"
                f"<div style='font-size:0.7rem;color:#475569;margin-top:2px;font-weight:600;text-transform:uppercase;"
                f"letter-spacing:0.04em;'>Skills</div></div>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;background:rgba(34,197,94,0.06);"
                f"border:1px solid rgba(34,197,94,0.2);border-radius:10px;'>"
                f"<div style='font-size:1.5rem;font-weight:800;color:#22c55e;line-height:1;'>{_running_pas}/{pa_count}</div>"
                f"<div style='font-size:0.7rem;color:#475569;margin-top:2px;font-weight:600;text-transform:uppercase;"
                f"letter-spacing:0.04em;'>Active</div></div>",
                unsafe_allow_html=True,
            )

        st.divider()

        # ── How it works ──────────────────────────────────────────────────
        st.markdown(
            "<p style='font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;"
            "letter-spacing:0.08em;margin:0 0 10px 0;'>HOW IT WORKS</p>",
            unsafe_allow_html=True,
        )
        for _step_icon, _step_text in [
            ("1️⃣", "Create a **Personal Assistant** — give it a name"),
            ("2️⃣", "Enable the **Skills** it needs (email, drive, files…)"),
            ("3️⃣", "Connect **Telegram** to chat from your phone"),
            ("4️⃣", "Chat via the **Dashboard** or Telegram anytime"),
        ]:
            st.markdown(
                f"<div style='display:flex;gap:8px;align-items:flex-start;padding:5px 0;"
                f"font-size:0.8rem;color:#64748b;line-height:1.4;'>"
                f"<span style='flex-shrink:0;'>{_step_icon}</span><span>{_step_text}</span></div>",
                unsafe_allow_html=True,
            )

    # ── Main area ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.08) 50%,rgba(233,30,140,0.06) 100%);
                    border:1px solid rgba(99,102,241,0.25);padding:28px 28px 22px;border-radius:20px;
                    margin-bottom:28px;backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(99,102,241,0.12);">
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:10px;">
              <img src="{_logo_b64()}" style="width:60px;height:60px;border-radius:14px;object-fit:cover;
                                              box-shadow:0 4px 16px rgba(99,102,241,0.35);">
              <div>
                <div style="font-size:2.2rem;font-weight:900;background:linear-gradient(135deg, #e91e8c 0%, #a5b4fc 100%);
                           -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
                           line-height:1.1;">OctaMind</div>
                <div style="font-size:0.95rem;color:#64748b;margin-top:4px;font-weight:500;">
                  Your AI-powered hub — one place to manage all your digital life
                </div>
              </div>
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
        "<div style='font-size:1.1rem;font-weight:700;color:#94a3b8;margin:24px 0 14px 0;text-transform:uppercase;letter-spacing:0.06em;'>🧩 Skills</div>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input(
            "🔍 Search agents",
            placeholder="Search by name or type...",
            label_visibility="collapsed"
        )
    with col2:
        _CHANNEL_TYPES_FILTER = {"telegram", "whatsapp"}
        skill_type_keys = [k for k in manager.get_agent_types().keys() if k not in _CHANNEL_TYPES_FILTER]
        filter_type = st.selectbox(
            "Filter by type",
            ["All"] + skill_type_keys,
            label_visibility="collapsed"
        )

    # Exclude channel-type agents from the skill agents grid
    _CH_TYPES = {"telegram", "whatsapp"}
    agents_display = [a for a in agents if a["type"] not in _CH_TYPES]

    filtered = agents_display
    if search:
        filtered = [a for a in filtered
                    if search.lower() in a["name"].lower()
                    or search.lower() in a["type"].lower()]
    if filter_type != "All":
        filtered = [a for a in filtered if a["type"] == filter_type]

    st.markdown(
        f"<div style='color:#64748b;font-size:0.85rem;margin:16px 0 20px 0;'>Showing {len(filtered)} of {len(agents_display)} skill(s)</div>",
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

    cols = st.columns(4)
    for idx, agent in enumerate(filtered):
        with cols[idx % 4]:
            show_agent_card(agent)
    # ── Channels ────────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<div style='font-size:1.1rem;font-weight:700;color:#94a3b8;margin:16px 0 10px 0;text-transform:uppercase;letter-spacing:0.06em;'>📡 Channels</div>"
        "<div style='color:#475569;font-size:0.84rem;margin-bottom:16px;'>"
        "How your assistant communicates with you. Dashboard is always available. "
        "Configure Telegram via each Assistant's bot token."
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        ch_cols = st.columns(2)
        for idx, (ch_name, ch) in enumerate(CHANNEL_REGISTRY.items()):
            with ch_cols[idx % 2]:
                running = ch.is_running()

                # ── Telegram — managed per-PA, show aggregate info ──────────
                if ch_name == "telegram":
                    try:
                        from src.agent.hub.pa_manager import load_assistants as _lpas
                        from src.telegram.pa_poller_manager import get_pa_poller_status as _gps
                        all_pas = _lpas()
                        bot_count = sum(1 for _p in all_pas if _gps(_p["id"]) is not None)
                    except Exception:
                        bot_count = 0
                        all_pas = []
                    tg_bg     = "rgba(34,158,217,0.08)"  if running else "rgba(255,255,255,0.03)"
                    tg_border = "rgba(34,158,217,0.35)" if running else "rgba(255,255,255,0.1)"
                    bot_label = (
                        f"<span style='background:#229ED9;color:#fff;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.76rem;font-weight:600'>"
                        f"✈️ {bot_count} bot{'s' if bot_count != 1 else ''} running</span>"
                        if running else
                        "<span style='background:#4b5563;color:#fff;padding:3px 10px;"
                        "border-radius:12px;font-size:0.76rem;font-weight:600'>✈️ No bots running</span>"
                    )
                    st.markdown(
                        f"<div style='background:{tg_bg};border:1.5px solid {tg_border};"
                        f"padding:16px 18px;border-radius:12px;margin-bottom:4px;'>"
                        f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
                        f"<div style='font-size:1.5rem'>{ch.icon}</div>{bot_label}</div>"
                        f"<div style='font-size:1rem;font-weight:700;color:#e2e8f0;margin:8px 0 4px'>{ch.display_name}</div>"
                        f"<div style='font-size:0.82rem;color:#94a3b8;margin-bottom:8px;'>{ch.description}</div>"
                        f"<div style='font-size:0.78rem;color:#a8dadc;background:rgba(168,218,220,0.08);"
                        f"padding:6px 10px;border-radius:8px;border-left:3px solid #a8dadc;'>"
                        f"⬇️ Start / Stop individual bots via the <b>PA cards</b> below</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)
                    continue

                # ── Dashboard — always-on, show status only, no stop button ──
                if ch_name == "dashboard":
                    try:
                        s = ch.status()
                        detail = f" · Port {s.port}" if s.port else (f" · {s.detail}" if s.detail else "")
                    except Exception:
                        detail = ""
                    st.markdown(
                        f"<div style='background:rgba(22,163,74,0.08);border:1.5px solid rgba(22,163,74,0.35);"
                        f"padding:16px 18px 10px;border-radius:12px;margin-bottom:4px;'>"
                        f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
                        f"<div style='font-size:1.5rem'>{ch.icon}</div>"
                        f"<span style='background:#16a34a;color:#fff;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.76rem;font-weight:600'>● Always Running</span></div>"
                        f"<div style='font-size:1rem;font-weight:700;color:#e2e8f0;margin:8px 0 4px'>"
                        f"{ch.display_name}{detail}</div>"
                        f"<div style='font-size:0.82rem;color:#94a3b8'>{ch.description}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)
                    continue

                # ── Dashboard / API — show card + Start/Stop button ─────────
                bg    = "rgba(22,163,74,0.08)"  if running else "rgba(255,255,255,0.03)"
                border= "rgba(22,163,74,0.35)" if running else "rgba(255,255,255,0.1)"
                badge = (
                    "<span style='background:#16a34a;color:#fff;padding:3px 10px;"
                    "border-radius:12px;font-size:0.76rem;font-weight:600'>● Running</span>"
                    if running else
                    "<span style='background:#4b5563;color:#fff;padding:3px 10px;"
                    "border-radius:12px;font-size:0.76rem;font-weight:600'>● Stopped</span>"
                )
                try:
                    s = ch.status()
                    detail = f" · Port {s.port}" if s.port else (f" · {s.detail}" if s.detail else "")
                except Exception:
                    detail = ""
                st.markdown(
                    f"<div style='background:{bg};border:1.5px solid {border};"
                    f"padding:16px 18px 10px;border-radius:12px;margin-bottom:4px;'>"
                    f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
                    f"<div style='font-size:1.5rem'>{ch.icon}</div>{badge}</div>"
                    f"<div style='font-size:1rem;font-weight:700;color:#e2e8f0;margin:8px 0 4px'>"
                    f"{ch.display_name}{detail}</div>"
                    f"<div style='font-size:0.82rem;color:#94a3b8'>{ch.description}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    if not running:
                        if st.button(
                            f"▶️ Start {ch.display_name}", key=f"ch_start_{ch_name}",
                            use_container_width=True, type="primary",
                        ):
                            try:
                                ch.start()
                                st.rerun()
                            except Exception as _se:
                                st.error(str(_se))
                with btn_c2:
                    if running:
                        if st.button(
                            f"⏹️ Stop {ch.display_name}", key=f"ch_stop_{ch_name}",
                            use_container_width=True,
                        ):
                            try:
                                ch.stop()
                                st.rerun()
                            except Exception as _se:
                                st.error(str(_se))
                st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)
    except Exception as _ce:
        st.warning(f"Could not load channel registry: {_ce}")
    # ── Personal Assistants ───────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<div style='font-size:1.1rem;font-weight:700;color:#94a3b8;margin:16px 0 10px 0;text-transform:uppercase;letter-spacing:0.06em;'>🤖 Personal Assistants</div>"
        "<div style='color:#475569;font-size:0.84rem;margin-bottom:16px;'>"
        "Your AI assistants — each with their own memory, skills, and Telegram bot."
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        from src.agent.hub.pa_manager import load_assistants as _load_pas
        assistants = _load_pas()
        if assistants:
            pa_cols = st.columns(2)
            for idx, pa in enumerate(assistants):
                with pa_cols[idx % 2]:
                    _show_pa_card(pa)
        else:
            st.markdown(
                "<div style='background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2);"
                "padding:20px;border-radius:12px;text-align:center;color:#a78bfa;'>"
                "No personal assistants yet. Click <b>🤖 Create Personal Assistant</b> in the sidebar to get started."
                "</div>",
                unsafe_allow_html=True,
            )
    except Exception as _e:
        st.warning(f"Could not load personal assistants: {_e}")


if __name__ == "__main__":
    main()
