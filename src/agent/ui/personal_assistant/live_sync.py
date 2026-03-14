from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from src.agent.runtime_paths import get_runtime_state_path, migrate_legacy_runtime_state_file

_SERVERS: dict[int, ThreadingHTTPServer] = {}
_SERVER_LOCK = threading.Lock()


def _load_pa_telegram_chat_ids(pa_id: str) -> set[str]:
    tg_path = get_runtime_state_path(f"tg_{pa_id}.json")
    if not tg_path.exists():
        return set()

    try:
        data = json.loads(tg_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    chat_ids: set[str] = set()
    for entry in data.get("messages") or []:
        chat_id = entry.get("chat_id")
        if chat_id is not None:
            chat_ids.add(str(chat_id))
    return chat_ids


def _signature_for_pa(pa_id: str) -> str:
    conv_path = migrate_legacy_runtime_state_file("hub_conversations.json")
    if not conv_path.exists():
        return ""

    try:
        data = json.loads(conv_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    telegram_chat_ids = _load_pa_telegram_chat_ids(pa_id)
    dashboard_session_id = f"dashboard_{pa_id}"
    signatures: list[tuple[str, str, int]] = []

    for session_id, session in (data.get("sessions") or {}).items():
        session = session or {}
        session_source = str(session.get("source") or "")
        session_agent_id = str(session.get("agent_id") or "").strip()

        include_session = session_id == dashboard_session_id or session_agent_id == pa_id
        if not include_session and session_source == "telegram" and session_id.startswith("telegram_"):
            include_session = session_id.removeprefix("telegram_") in telegram_chat_ids

        if include_session:
            signatures.append(
                (
                    str(session_id),
                    str(session.get("last_updated") or ""),
                    len(session.get("messages") or []),
                )
            )

    signatures.sort()
    return json.dumps(signatures, ensure_ascii=False)


class _LiveSyncHandler(BaseHTTPRequestHandler):
    server_version = "OctaLiveSync/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/events":
            self.send_error(404)
            return

        pa_id = parse_qs(parsed.query).get("pa_id", [""])[0].strip()
        if not pa_id:
            self.send_error(400, "pa_id is required")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        last_signature = _signature_for_pa(pa_id)
        keepalive_at = time.monotonic()
        try:
            while True:
                current_signature = _signature_for_pa(pa_id)
                if current_signature != last_signature:
                    payload = json.dumps({"type": "chat-update", "pa_id": pa_id})
                    self.wfile.write(f"event: chat-update\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_signature = current_signature
                    keepalive_at = time.monotonic()
                elif time.monotonic() - keepalive_at >= 15:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    keepalive_at = time.monotonic()
                time.sleep(0.75)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            return

    def log_message(self, format: str, *args) -> None:
        return


def ensure_live_sync_server(port: int) -> None:
    with _SERVER_LOCK:
        if port in _SERVERS:
            return

        server = ThreadingHTTPServer(("127.0.0.1", port), _LiveSyncHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _SERVERS[port] = server