"""
Gmail Contacts Sync — Google People API integration.

Syncs Gmail contacts to data/contacts.json so the assistant can resolve
names to email addresses without scanning the inbox for every message.

Industry standard approach used here:
  1. Primary:  Google People API (people.connections.list) — fetches the
               user's actual Google Contacts book (~all saved contacts).
  2. Fallback: Interaction mining — scan the last N emails to surface
               frequently co-emailed addresses even if not in Contacts book.
  3. Storage:  data/contacts.json — flat list, keyed for fast name lookup.

Re-running sync merges results so manually added contacts are not lost.

Requires OAuth scope: contacts.readonly  (add via setup_google_auth.py then
re-run python setup_google_auth.py to refresh the token).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("email.contacts_sync")

_CONTACTS_FILE = Path(__file__).parent.parent.parent.parent / "data" / "contacts.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_local() -> Dict[str, Any]:
    """Load existing contacts from disk.  Returns dict keyed by lower-case email."""
    if _CONTACTS_FILE.exists():
        try:
            raw = json.loads(_CONTACTS_FILE.read_text(encoding="utf-8"))
            return {c["email"].lower(): c for c in raw.get("contacts", []) if c.get("email")}
        except Exception as exc:
            logger.debug("Could not read local contacts cache: %s", exc)
    return {}


def _save_local(contacts_by_email: Dict[str, Any]) -> None:
    """Persist merged contacts to disk."""
    _CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "synced_at": datetime.now().isoformat(),
        "total": len(contacts_by_email),
        "contacts": list(contacts_by_email.values()),
    }
    _CONTACTS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_google_creds():
    """Load OAuth credentials from the Gmail token file for use with People API."""
    try:
        from src.email.gmail_auth import CREDENTIALS_PATH, TOKEN_PATH
        from google.oauth2.credentials import Credentials as _Creds
        from google.auth.transport.requests import Request as _Request
        from pathlib import Path as _Path

        token_path = _Path(TOKEN_PATH)
        if not token_path.exists():
            return None
        creds = _Creds.from_authorized_user_file(str(token_path))
        if creds.expired and creds.refresh_token:
            creds.refresh(_Request())
        return creds
    except Exception as exc:
        logger.debug("Could not load Google creds: %s", exc)
        return None


def _people_api_contacts(creds) -> List[Dict[str, Any]]:
    """
    Fetch contacts from Google People API.  Returns list of dicts
    {email, name, source: 'people_api'}.
    """
    try:
        from googleapiclient.discovery import build as _build
        service = _build("people", "v1", credentials=creds, cache_discovery=False)
        contacts: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            kwargs: Dict[str, Any] = {
                "resourceName": "people/me",
                "pageSize": 200,
                "personFields": "names,emailAddresses",
            }
            if page_token:
                kwargs["pageToken"] = page_token
            resp = service.people().connections().list(**kwargs).execute()
            for person in resp.get("connections", []):
                emails_raw = person.get("emailAddresses", [])
                names_raw  = person.get("names", [])
                name = names_raw[0].get("displayName", "") if names_raw else ""
                for ea in emails_raw:
                    email_addr = (ea.get("value") or "").strip().lower()
                    if email_addr:
                        contacts.append({"email": email_addr, "name": name, "source": "people_api"})
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return contacts
    except Exception as exc:
        logger.warning("People API contacts fetch failed: %s", exc)
        return []


def _interaction_contacts(gmail_service, max_scan: int = 500) -> List[Dict[str, Any]]:
    """
    Mine sent/received emails to surface addresses not in Contacts book.
    Returns list of {email, name, source: 'interaction', count}.
    """
    try:
        from collections import Counter
        import re as _re
        addr_re = _re.compile(r"([^<]+)<([^>]+)>|([^\s,;]+@[^\s,;]+)")

        messages = gmail_service.list_emails("in:sent OR in:inbox", max_results=max_scan)
        if not isinstance(messages, (list, dict)):
            return []
        if isinstance(messages, dict):
            messages = messages.get("emails", [])

        counter: Counter = Counter()
        name_map: Dict[str, str] = {}

        for msg in messages:
            for field in ("sender", "to", "from", "recipients"):
                val = msg.get(field, "")
                if not val:
                    continue
                for part in str(val).split(","):
                    part = part.strip()
                    m = addr_re.search(part)
                    if m:
                        if m.group(2):
                            email_addr = m.group(2).strip().lower()
                            name = m.group(1).strip().strip('"')
                        else:
                            email_addr = m.group(3).strip().lower()
                            name = ""
                        if email_addr and "@" in email_addr:
                            counter[email_addr] += 1
                            if name and email_addr not in name_map:
                                name_map[email_addr] = name

        return [
            {
                "email": email,
                "name": name_map.get(email, ""),
                "source": "interaction",
                "interaction_count": count,
            }
            for email, count in counter.most_common(300)
        ]
    except Exception as exc:
        logger.warning("Interaction contact mining failed: %s", exc)
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def sync_contacts(max_interaction_scan: int = 500) -> Dict[str, Any]:
    """
    Sync Gmail contacts to data/contacts.json.

    Merges Google People API contacts (primary) with interaction-mined
    contacts (fallback) and the existing local cache.

    Returns a result dict compatible with the skill engine.
    """
    try:
        from src.email.gmail_service import _get_client as _get_gmail

        gmail_svc = _get_gmail()
        existing  = _load_local()

        # ── 1. Google People API ───────────────────────────────────────────
        new_people_api: int = 0
        try:
            creds = _get_google_creds()
            if creds:
                api_contacts = _people_api_contacts(creds)
                for c in api_contacts:
                    email_lc = c["email"].lower()
                    if email_lc not in existing:
                        existing[email_lc] = c
                        new_people_api += 1
                    elif not existing[email_lc].get("name") and c.get("name"):
                        existing[email_lc]["name"] = c["name"]
        except Exception as exc:
            logger.info("People API step skipped: %s", exc)

        # ── 2. Interaction mining ──────────────────────────────────────────
        new_interaction: int = 0
        interact_contacts = _interaction_contacts(gmail_svc, max_interaction_scan)
        for c in interact_contacts:
            email_lc = c["email"].lower()
            if email_lc not in existing:
                existing[email_lc] = c
                new_interaction += 1
            else:
                # Update interaction count but keep People API as primary source
                existing[email_lc]["interaction_count"] = c.get("interaction_count", 0)

        # ── 3. Persist ────────────────────────────────────────────────────
        _save_local(existing)
        total = len(existing)

        return {
            "status": "success",
            "total_contacts": total,
            "new_from_people_api": new_people_api,
            "new_from_interaction": new_interaction,
            "saved_to": str(_CONTACTS_FILE),
            "message": (
                f"✅ Contacts synced — {total} total "
                f"({new_people_api} from Google Contacts, "
                f"{new_interaction} from email history). "
                f"Saved to data/contacts.json."
            ),
        }
    except Exception as exc:
        logger.error("sync_contacts failed: %s", exc)
        return {"status": "error", "message": f"Contact sync failed: {exc}"}


def search_contacts(query: str) -> Dict[str, Any]:
    """
    Search the local contacts cache by name or email.
    Returns up to 10 matches.
    """
    try:
        contacts_by_email = _load_local()
        query_lc = query.lower().strip()
        matches = [
            c for c in contacts_by_email.values()
            if query_lc in c.get("email", "").lower()
            or query_lc in c.get("name", "").lower()
        ]
        return {
            "status": "success",
            "query": query,
            "matches": matches[:10],
            "total_matches": len(matches),
            "message": (
                f"Found {len(matches)} contact(s) matching '{query}'."
                if matches else
                f"No contacts found matching '{query}'. Try sync_contacts() to refresh."
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": f"Contact search failed: {exc}"}


def list_contacts(limit: int = 50) -> Dict[str, Any]:
    """Return the top *limit* contacts sorted by interaction count."""
    try:
        contacts_by_email = _load_local()
        sorted_contacts = sorted(
            contacts_by_email.values(),
            key=lambda c: c.get("interaction_count", 0),
            reverse=True,
        )[:limit]
        return {
            "status": "success",
            "total_in_cache": len(contacts_by_email),
            "contacts": sorted_contacts,
            "message": f"{len(sorted_contacts)} contacts returned (of {len(contacts_by_email)} total).",
        }
    except Exception as exc:
        return {"status": "error", "message": f"list_contacts failed: {exc}"}
