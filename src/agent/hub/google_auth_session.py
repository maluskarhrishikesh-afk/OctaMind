from __future__ import annotations

import html as _html_mod
import json
import logging
import os
import secrets
import socket as _socket
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer as _HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from google.oauth2.credentials import Credentials

from src.agent.runtime_paths import get_runtime_state_path

logger = logging.getLogger("google_auth_session")

_SESSION_TTL_SECONDS = 1800
_SESSION_LOCK = threading.Lock()
_SESSIONS_PATH = get_runtime_state_path("runtime_state", "google_auth_pending.json", create_parent=True)
_PUBLIC_CALLBACK_PATH = "/oauth/google/callback"

# Registry of active local-callback server threads, keyed by OAuth state token.
_LOCAL_CALLBACK_SERVERS: dict[str, threading.Thread] = {}
_LOCAL_CALLBACK_LOCK = threading.Lock()


@dataclass
class GoogleAuthSession:
    service_key: str
    label: str
    auth_url: str
    redirect_uri: str
    token_path: Path
    state: str
    created_at: float
    expires_at: float
    session_id: str | None = None
    uses_public_callback: bool = False
    uses_local_callback: bool = False


@dataclass(frozen=True)
class _ServiceConfig:
    service_key: str
    label: str
    credentials_path: Path
    token_path: Path
    scopes: list[str]


def _normalize_service_key(service_key: str) -> str:
    aliases = {
        "gmail": "email",
        "mail": "email",
        "google_drive": "drive",
        "gdrive": "drive",
        "scheduler": "calendar",
        "google_calendar": "calendar",
    }
    normalized = str(service_key or "").strip().lower().replace("-", "_").replace(" ", "_")
    return aliases.get(normalized, normalized)


def _gmail_config() -> _ServiceConfig:
    from src.email.gmail_auth import SCOPES, _resolve_google_paths

    credentials_path, token_path = _resolve_google_paths()
    return _ServiceConfig(
        service_key="email",
        label="Gmail",
        credentials_path=Path(credentials_path),
        token_path=Path(token_path),
        scopes=list(SCOPES),
    )


def _drive_config() -> _ServiceConfig:
    from src.drive.drive_auth import SCOPES, _resolve_drive_paths

    credentials_path, token_path = _resolve_drive_paths()
    return _ServiceConfig(
        service_key="drive",
        label="Google Drive",
        credentials_path=Path(credentials_path),
        token_path=Path(token_path),
        scopes=list(SCOPES),
    )


def _calendar_config() -> _ServiceConfig:
    from src.calendar.calendar_auth import SCOPES, _resolve_paths

    credentials_path, token_path = _resolve_paths()
    return _ServiceConfig(
        service_key="calendar",
        label="Google Calendar",
        credentials_path=Path(credentials_path),
        token_path=Path(token_path),
        scopes=list(SCOPES),
    )


def _get_service_config(service_key: str) -> _ServiceConfig:
    normalized = _normalize_service_key(service_key)
    if normalized == "email":
        return _gmail_config()
    if normalized == "drive":
        return _drive_config()
    if normalized == "calendar":
        return _calendar_config()
    raise ValueError(f"Unsupported Google auth service: {service_key}")


def is_google_service_authorized(service_key: str) -> bool:
    config = _get_service_config(service_key)
    return config.token_path.exists()


def _get_public_callback_base_url() -> str:
    direct = os.getenv("HUB_PUBLIC_BASE_URL", "").strip() or os.getenv("OAUTH_PUBLIC_BASE_URL", "").strip()
    if direct:
        return direct.rstrip("/")
    try:
        from src.agent.llm.provider_registry import load_credentials

        creds = load_credentials()
        google = creds.get("google", {}) if isinstance(creds, dict) else {}
        raw = str(
            google.get("oauth_callback_base_url")
            or google.get("public_hub_base_url")
            or ""
        ).strip()
        return raw.rstrip("/")
    except (ImportError, AttributeError, OSError, ValueError, TypeError):
        return ""


def get_google_oauth_redirect_uri() -> str:
    base_url = _get_public_callback_base_url()
    if base_url:
        return f"{base_url}{_PUBLIC_CALLBACK_PATH}"
    return "http://localhost"


def has_public_google_oauth_callback() -> bool:
    return bool(_get_public_callback_base_url())


def _find_free_port() -> int:
    """Bind to port 0 (OS assigns a free ephemeral port) and return it."""
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_local_callback_server(port: int, expected_state: str) -> None:
    """Background thread: one-shot HTTP server that captures the OAuth redirect.

    Binds to ``127.0.0.1:{port}``, waits for Google's redirect, exchanges the
    code via ``_complete_google_auth_parts``, sends a Telegram notification, and
    then exits. The thread is daemon so it never blocks interpreter shutdown.
    """
    completed = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            code = (params.get("code") or [""])[0]
            error = (params.get("error") or [""])[0]
            error_description = (params.get("error_description") or [""])[0]
            recv_state = (params.get("state") or [expected_state])[0]

            # Ignore requests that are not the OAuth callback (e.g. favicon).
            if not (code or error):
                self.send_response(204)
                self.end_headers()
                return

            ok, message = _complete_google_auth_parts(
                state=recv_state,
                code=code,
                error=error,
                error_description=error_description,
                notify_telegram=True,
            )

            if ok:
                body_html = (
                    "<!doctype html><html><head><meta charset=utf-8>"
                    "<title>Authorization Complete</title></head>"
                    "<body style='font-family:sans-serif;text-align:center;padding:60px 20px'>"
                    "<h2 style='color:#22a06b'>&#10003; Authorization complete!</h2>"
                    "<p>You can close this tab and return to Telegram.</p>"
                    "</body></html>"
                )
            else:
                body_html = (
                    "<!doctype html><html><head><meta charset=utf-8>"
                    "<title>Authorization Failed</title></head>"
                    "<body style='font-family:sans-serif;text-align:center;padding:60px 20px'>"
                    "<h2 style='color:#e5330a'>&#10007; Authorization failed</h2>"
                    f"<p>{_html_mod.escape(message)}</p>"
                    "</body></html>"
                )

            body = body_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            completed.set()

        def log_message(self, *args, **kwargs) -> None:  # silence HTTP access logs
            pass

    server = _HTTPServer(("127.0.0.1", port), _Handler)
    server.timeout = 2  # poll interval so we can check deadline
    deadline = time.time() + _SESSION_TTL_SECONDS + 120
    try:
        while not completed.is_set() and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
        with _LOCAL_CALLBACK_LOCK:
            _LOCAL_CALLBACK_SERVERS.pop(expected_state, None)


def _load_oauth_client(credentials_path: Path) -> tuple[str, dict[str, Any]]:
    raw = json.loads(credentials_path.read_text(encoding="utf-8"))
    if "installed" in raw:
        return "installed", raw["installed"]
    if "web" in raw:
        return "web", raw["web"]
    raise ValueError(f"Unsupported Google OAuth credentials format in {credentials_path}")


def _load_client_config(credentials_path: Path) -> dict[str, Any]:
    _, config = _load_oauth_client(credentials_path)
    return config


def _load_pending_sessions() -> dict[str, dict[str, Any]]:
    if not _SESSIONS_PATH.exists():
        return {}
    try:
        payload = json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sessions = payload.get("sessions", {})
    return sessions if isinstance(sessions, dict) else {}


def _save_pending_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    _SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _SESSIONS_PATH.with_name(
        f"{_SESSIONS_PATH.stem}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    tmp.write_text(json.dumps({"sessions": sessions}, indent=2), encoding="utf-8")
    tmp.replace(_SESSIONS_PATH)


def _prune_expired_sessions(sessions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    now = time.time()
    return {
        state: record
        for state, record in sessions.items()
        if float(record.get("expires_at", 0)) > now
    }


def cancel_google_auth_session(service_key: str) -> None:
    normalized = _normalize_service_key(service_key)
    with _SESSION_LOCK:
        sessions = _prune_expired_sessions(_load_pending_sessions())
        sessions = {
            state: record
            for state, record in sessions.items()
            if record.get("service_key") != normalized
        }
        _save_pending_sessions(sessions)


def _record_to_session(record: dict[str, Any]) -> GoogleAuthSession:
    return GoogleAuthSession(
        service_key=str(record["service_key"]),
        label=str(record["label"]),
        auth_url=str(record["auth_url"]),
        redirect_uri=str(record["redirect_uri"]),
        token_path=Path(str(record["token_path"])),
        state=str(record["state"]),
        created_at=float(record["created_at"]),
        expires_at=float(record["expires_at"]),
        session_id=str(record.get("session_id") or "") or None,
        uses_public_callback=bool(record.get("uses_public_callback", False)),
        uses_local_callback=bool(record.get("uses_local_callback", False)),
    )


def start_google_auth_session(
    service_key: str,
    *,
    force: bool = False,
    session_id: str | None = None,
) -> GoogleAuthSession:
    normalized = _normalize_service_key(service_key)
    config = _get_service_config(normalized)

    if not config.credentials_path.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials file not found at '{config.credentials_path}'."
        )

    client_type, client = _load_oauth_client(config.credentials_path)
    client_id = str(client.get("client_id", "")).strip()
    auth_uri = str(client.get("auth_uri") or "https://accounts.google.com/o/oauth2/auth").strip()
    if not client_id:
        raise ValueError(f"Missing client_id in {config.credentials_path}")

    new_local_port: int | None = None
    session: GoogleAuthSession

    with _SESSION_LOCK:
        sessions = _prune_expired_sessions(_load_pending_sessions())
        if not force:
            for record in sessions.values():
                if record.get("service_key") == normalized:
                    existing = _record_to_session(record)
                    if not existing.uses_local_callback:
                        return existing
                    # Local-callback session: return it only if the server thread is alive.
                    with _LOCAL_CALLBACK_LOCK:
                        thread = _LOCAL_CALLBACK_SERVERS.get(existing.state)
                        alive = thread is not None and thread.is_alive()
                    if alive:
                        return existing
                    # Server died (e.g. after OctaMind restart) — create a fresh session.
                    logger.info(
                        "Local callback server for %s is gone — creating new auth session.",
                        normalized,
                    )
                    sessions.pop(existing.state, None)
                    break

        sessions = {
            st: rec
            for st, rec in sessions.items()
            if rec.get("service_key") != normalized
        }

        redirect_uri = get_google_oauth_redirect_uri()
        uses_public_callback = redirect_uri.startswith("https://")
        uses_local_callback = False

        if uses_public_callback and client_type != "web":
            raise ValueError(
                "Public OAuth callback mode requires Google Web application credentials. "
                "Replace config/credentials.json with a Web client that includes the public callback URI."
            )

        # For installed/desktop credentials without a public callback URL, spin up a
        # local HTTP server on a random free port so Google can redirect back here
        # automatically — no URL pasteback needed.
        if not uses_public_callback and client_type == "installed":
            new_local_port = _find_free_port()
            redirect_uri = f"http://127.0.0.1:{new_local_port}/callback"
            uses_local_callback = True

        state = secrets.token_urlsafe(24)
        created_at = time.time()
        expires_at = created_at + _SESSION_TTL_SECONDS
        auth_url = auth_uri + "?" + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(config.scopes),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": state,
            }
        )

        session = GoogleAuthSession(
            service_key=normalized,
            label=config.label,
            auth_url=auth_url,
            redirect_uri=redirect_uri,
            token_path=config.token_path,
            state=state,
            created_at=created_at,
            expires_at=expires_at,
            session_id=session_id,
            uses_public_callback=uses_public_callback,
            uses_local_callback=uses_local_callback,
        )
        sessions[state] = {
            **asdict(session),
            "token_path": str(session.token_path),
            "credentials_path": str(config.credentials_path),
        }
        _save_pending_sessions(sessions)
        # session lock released here

    if new_local_port is not None:
        t = threading.Thread(
            target=_run_local_callback_server,
            args=(new_local_port, session.state),
            daemon=True,
            name=f"oauth-cb-{session.state[:8]}",
        )
        with _LOCAL_CALLBACK_LOCK:
            _LOCAL_CALLBACK_SERVERS[session.state] = t
        t.start()
        logger.info(
            "Local OAuth callback server started on http://127.0.0.1:%d for %s",
            new_local_port, normalized,
        )

    return session


def _extract_auth_response_parts(raw_text: str) -> dict[str, str]:
    text = str(raw_text or "").strip()
    if not text:
        return {}

    if "http://localhost" in text or "https://localhost" in text:
        start = text.find("http://localhost")
        if start == -1:
            start = text.find("https://localhost")
        fragment = text[start:].split()[0]
        parsed = urlparse(fragment)
        params = parse_qs(parsed.query)
    elif "code=" in text or "state=" in text or "error=" in text:
        query = text.split("?", 1)[1] if "?" in text else text
        params = parse_qs(query)
    else:
        return {}

    extracted: dict[str, str] = {}
    for key in ("code", "state", "error", "error_description"):
        value = (params.get(key) or [""])[0]
        if value:
            extracted[key] = value
    return extracted


def _notify_telegram_auth_completion(session_id: str | None, message: str) -> None:
    session_value = str(session_id or "").strip()
    if not session_value.startswith("telegram_"):
        return
    chat_id = session_value.split("telegram_", 1)[1].strip()
    if not chat_id:
        return
    try:
        from src.telegram.telegram_service import send_text
        from src.telegram.polling.message_store import store_outbound_message

        resp = send_text(chat_id, message)
        store_outbound_message(chat_id, message, message_id=resp.get("message_id", 0))
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("Could not send Telegram auth completion notice for %s: %s", session_id, exc)


def _build_token_credentials(token_payload: dict[str, Any], client: dict[str, Any], scopes: list[str]) -> Credentials:
    creds = Credentials(
        token=token_payload.get("access_token"),
        refresh_token=token_payload.get("refresh_token"),
        token_uri=str(client.get("token_uri") or "https://oauth2.googleapis.com/token"),
        client_id=str(client.get("client_id") or ""),
        client_secret=str(client.get("client_secret") or ""),
        scopes=scopes,
    )
    expires_in = token_payload.get("expires_in")
    if expires_in is not None:
        try:
            creds.expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError, OverflowError):
            pass
    return creds


def _complete_google_auth_parts(
    *,
    state: str,
    code: str,
    error: str,
    error_description: str,
    notify_telegram: bool,
) -> tuple[bool, str]:
    normalized_state = str(state or "")
    normalized_code = str(code or "")
    normalized_error = str(error or "")
    normalized_error_description = str(error_description or "")

    with _SESSION_LOCK:
        sessions = _prune_expired_sessions(_load_pending_sessions())
        record = sessions.get(normalized_state) if normalized_state else None
        if record is None and len(sessions) == 1 and normalized_code:
            normalized_state, record = next(iter(sessions.items()))
        if record is None:
            _save_pending_sessions(sessions)
            return False, "I couldn't match that auth response to a pending Google sign-in session. Start again with /auth calendar, /auth email, or /auth drive."

        if normalized_error:
            sessions.pop(normalized_state, None)
            _save_pending_sessions(sessions)
            detail = normalized_error_description or normalized_error
            message = f"Google sign-in was cancelled or failed: {detail}. Start again with /auth {record['service_key']}."
            if notify_telegram:
                _notify_telegram_auth_completion(record.get("session_id"), message)
            return False, message

        if not normalized_code:
            return False, "That Google redirect did not include an authorization code. Paste the full final URL from the browser address bar."

        service_key = str(record["service_key"])
        label = str(record["label"])
        redirect_uri = str(record["redirect_uri"])
        credentials_path = Path(str(record["credentials_path"]))
        token_path = Path(str(record["token_path"]))
        session_id = str(record.get("session_id") or "") or None
        sessions.pop(normalized_state, None)
        _save_pending_sessions(sessions)

    config = _get_service_config(service_key)
    client = _load_client_config(credentials_path)
    token_uri = str(client.get("token_uri") or "https://oauth2.googleapis.com/token")
    payload = {
        "client_id": str(client.get("client_id") or ""),
        "code": normalized_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    client_secret = str(client.get("client_secret") or "").strip()
    if client_secret:
        payload["client_secret"] = client_secret

    try:
        response = requests.post(token_uri, data=payload, timeout=30)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.exception("Google token exchange failed for %s: %s", service_key, exc)
        return False, f"{label} sign-in could not be completed: {exc}"

    if response.status_code >= 400 or data.get("error"):
        error_text = data.get("error_description") or data.get("error") or response.text
        message = f"{label} sign-in was not accepted by Google: {error_text}"
        if notify_telegram:
            _notify_telegram_auth_completion(session_id, message)
        return False, message

    if not data.get("refresh_token"):
        message = f"{label} sign-in finished but Google did not return a refresh token. Please run /auth {service_key} again and approve the request."
        if notify_telegram:
            _notify_telegram_auth_completion(session_id, message)
        return False, message

    creds = _build_token_credentials(data, client, config.scopes)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")

    if service_key == "email":
        try:
            from src.email.gmail_service import reset_gmail_client

            reset_gmail_client()
        except (ImportError, AttributeError):
            pass

    message = f"✅ {label} authorization is complete. You can send your request again now."
    if notify_telegram:
        _notify_telegram_auth_completion(session_id, message)
    return True, message


def complete_google_auth_callback(
    *,
    state: str,
    code: str = "",
    error: str = "",
    error_description: str = "",
) -> tuple[bool, str]:
    return _complete_google_auth_parts(
        state=state,
        code=code,
        error=error,
        error_description=error_description,
        notify_telegram=True,
    )


def complete_google_auth_session(raw_text: str) -> tuple[bool, str]:
    extracted = _extract_auth_response_parts(raw_text)
    if not extracted:
        return False, "I couldn't find a Google auth code in that message. Paste the full http://localhost/... URL that Google redirected to."

    return _complete_google_auth_parts(
        state=extracted.get("state", ""),
        code=extracted.get("code", ""),
        error=extracted.get("error", ""),
        error_description=extracted.get("error_description", ""),
        notify_telegram=False,
    )


def build_telegram_google_auth_reply(
    services: list[str],
    *,
    force: bool = False,
    session_id: str | None = None,
) -> str | None:
    unique_services: list[str] = []
    for service in services:
        normalized = _normalize_service_key(service)
        if normalized in {"calendar", "email", "drive"} and normalized not in unique_services:
            unique_services.append(normalized)

    if not unique_services:
        return None

    lines: list[str] = []
    errors: list[str] = []
    local_sessions: list[GoogleAuthSession] = []
    uses_local_callback = False
    for service in unique_services:
        if not force and is_google_service_authorized(service):
            continue
        try:
            session = start_google_auth_session(service, force=force, session_id=session_id)
            lines.append(f"• {session.label}: {session.auth_url}")
            if session.uses_local_callback:
                uses_local_callback = True
                local_sessions.append(session)
        except FileNotFoundError as exc:
            errors.append(f"• {_get_service_config(service).label}: {exc}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Could not start Google auth session for %s: %s", service, exc)
            errors.append(f"• {_get_service_config(service).label}: could not prepare the sign-in link ({exc})")

    if not lines and not errors:
        return None

    intro = (
        "🔑 Google sign-in is required before I can use that skill."
        if len(lines) == 1
        else "🔑 Google sign-in is required before I can use those skills."
    )
    if not lines:
        return f"{intro}\n\n" + "\n".join(errors)

    # For local-callback sessions open the sign-in URL in the local browser automatically
    # so the user only needs to approve the consent screen — no URL copy-paste required.
    if local_sessions:
        import webbrowser as _wb
        for _sess in local_sessions:
            try:
                _wb.open(_sess.auth_url)
            except OSError:
                pass

    if has_public_google_oauth_callback():
        return (
            f"{intro}\n\n"
            "1. Open the sign-in link on your phone or any browser.\n"
            + "\n".join(lines)
            + "\n\n"
            "2. Finish Google sign-in and consent.\n"
            "3. Google will return to OctaMind's public callback URL and complete setup automatically.\n"
            "4. When you see the success page, come back to Telegram and continue."
            + ("\n\n" + "\n".join(errors) if errors else "")
        )
    if uses_local_callback:
        browser_note = (
            "A sign-in page has been opened in your browser on the OctaMind machine. "
            "If it didn't open, use the link below."
        )
        return (
            f"{intro}\n\n"
            f"{browser_note}\n\n"
            + "\n".join(lines)
            + "\n\n"
            "Complete Google sign-in and grant the requested permissions.\n"
            "Your browser will show an \"Authorization complete!\" page.\n"
            "You will receive a notification here in Telegram once the token is saved. ✅"
            + ("\n\n" + "\n".join(errors) if errors else "")
        )
    return (
        f"{intro}\n\n"
        "1. Open the sign-in link on your phone or any browser.\n"
        + "\n".join(lines)
        + "\n\n"
        "2. Finish Google sign-in and consent.\n"
        "3. When Google redirects to a http://localhost/... page, copy the full address from the browser bar and send it back in this Telegram chat.\n"
        "4. You can paste the URL directly, or send `/authcomplete <paste-url>`.\n\n"
        "This flow does not require the laptop browser or a localhost server to be reachable."
        + ("\n\n" + "\n".join(errors) if errors else "")
    )