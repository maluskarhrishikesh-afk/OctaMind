"""
Per-PA Telegram Poller Process.

Launched by pa_poller_manager for each Personal Assistant that has a
Telegram bot token configured.  Sets TELEGRAM_BOT_TOKEN and
TELEGRAM_DATA_FILE before starting the existing poller so every PA
gets its own isolated bot and message store.

Environment vars (set by pa_poller_manager.start_pa_poller):
    PA_ID               — the Personal Assistant id
    TELEGRAM_BOT_TOKEN  — the PA-specific bot token (overrides global)
    TELEGRAM_DATA_FILE  — path to PA-specific messages JSON
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────
_log_dir = _ROOT / "logs"
_log_dir.mkdir(exist_ok=True)

pa_id = os.environ.get("PA_ID", "")
_log_file = _log_dir / f"tg_pa_{pa_id or 'unknown'}.log"

# This process runs headless (stdout/stderr → DEVNULL from the parent).
# Log only to the file; a StreamHandler on a DEVNULL/NoneType stdout causes
# silent crashes on Windows when there is no attached console.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("pa_telegram_poller")


def main() -> None:
    if not pa_id:
        logger.error("PA_ID env var not set — cannot start.")
        sys.exit(1)

    # ── Load PA and validate token ────────────────────────────────────────────
    try:
        from src.agent.hub.pa_manager import get_assistant
        pa = get_assistant(pa_id)
    except Exception as exc:
        logger.error("Could not load PA %s: %s", pa_id, exc)
        sys.exit(1)

    if not pa:
        logger.error("PA '%s' not found in assistants.json", pa_id)
        sys.exit(1)

    token = (pa.get("config") or {}).get("telegram", {}).get("bot_token", "").strip()
    if not token or token.startswith("<"):
        logger.error(
            "No telegram bot_token configured for PA '%s'. "
            "Set it in the Configure tab.", pa["name"],
        )
        sys.exit(1)

    # ── Set env vars — mirrors config/settings.json telegram structure ─────────
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    tg_cfg = (pa.get("config") or {}).get("telegram", {})
    os.environ["TELEGRAM_AUTO_REPLY"] = str(tg_cfg.get("auto_reply", True)).lower()
    persona = tg_cfg.get("auto_reply_persona", "").strip()
    if persona:
        os.environ["TELEGRAM_AUTO_REPLY_PERSONA"] = persona
    # Per-PA message store so chats don't mix across assistants
    data_file = str(_ROOT / "data" / f"tg_{pa_id}.json")
    os.environ["TELEGRAM_DATA_FILE"] = data_file

    logger.info("=== Telegram Poller for PA: %s (%s) ===", pa["name"], pa_id)
    logger.info("Data file: %s", data_file)

    # ── Release any existing getUpdates session for this token ───────────────
    # Telegram only allows ONE concurrent getUpdates connection per bot.
    # Calling /close terminates the server-side long-poll, evicting any
    # stale global poller that may still be running with the same token.
    try:
        import urllib.request as _ureq
        _ureq.urlopen(
            f"https://api.telegram.org/bot{token}/close",
            timeout=5,
        )
        logger.info("Released existing Telegram session via /close.")
        time.sleep(5)   # give Telegram time to evict the old listener
    except Exception as _ce:
        logger.debug("Telegram /close: %s (safe to ignore)", _ce)

    # ── Start poller ──────────────────────────────────────────────────────────
    try:
        from src.telegram.polling.poller import start_poller_in_background
        thread = start_poller_in_background()
        logger.info("Poller thread started (id=%s). Bot is live.", thread.ident)
    except Exception as exc:
        logger.error("Failed to start poller: %s", exc)
        sys.exit(1)

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    def _shutdown(sig, frame):
        logger.info("Shutdown signal received — stopping poller.")
        try:
            from src.telegram.polling.poller import stop_poller
            stop_poller()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
