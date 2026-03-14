from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
YOUR_DATA_DIR = ROOT / "your_data"
BACKUP_DIR = YOUR_DATA_DIR / "_legacy_data_backup_20260311"


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _backup_legacy_tree() -> int:
    if not DATA_DIR.exists():
        return 0
    copied = 0
    for source in DATA_DIR.rglob("*"):
        if not source.is_file():
            continue
        target = BACKUP_DIR / source.relative_to(DATA_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied


def _copy_if_missing(relative_path: str) -> bool:
    source = DATA_DIR / relative_path
    target = YOUR_DATA_DIR / relative_path
    if not source.exists() or target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _dedupe_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for message in messages:
        message_id = str(message.get("id", "")).strip()
        if not message_id:
            continue
        previous = by_id.get(message_id)
        if previous is None:
            by_id[message_id] = dict(message)
            continue
        prev_ts = _parse_dt(previous.get("timestamp"))
        curr_ts = _parse_dt(message.get("timestamp"))
        if curr_ts >= prev_ts:
            by_id[message_id] = dict(message)
    return sorted(by_id.values(), key=lambda item: (_parse_dt(item.get("timestamp")), str(item.get("id", ""))))


def _rebuild_telegram_chats(messages: list[dict[str, Any]], base_chats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    existing: dict[str, dict[str, Any]] = {}
    for chat_blob in base_chats:
        for chat_id, chat in chat_blob.items():
            existing[str(chat_id)] = dict(chat)

    counts: Counter[str] = Counter()
    first_seen: dict[str, datetime] = {}
    last_seen: dict[str, datetime] = {}
    titles: dict[str, str] = {}
    usernames: dict[str, str] = {}
    chat_types: dict[str, str] = {}

    for message in messages:
        chat_id = str(message.get("chat_id", "")).strip()
        if not chat_id:
            continue
        counts[chat_id] += 1
        ts = _parse_dt(message.get("timestamp"))
        first_seen[chat_id] = min(ts, first_seen.get(chat_id, ts))
        last_seen[chat_id] = max(ts, last_seen.get(chat_id, ts))
        chat_types[chat_id] = str(message.get("chat_type") or chat_types.get(chat_id) or "private")
        if message.get("from_user"):
            titles[chat_id] = str(message.get("from_user"))
        if message.get("username"):
            usernames[chat_id] = "@" + str(message.get("username")).lstrip("@")

    rebuilt: dict[str, dict[str, Any]] = {}
    for chat_id in set(existing) | set(counts):
        old = existing.get(chat_id, {})
        rebuilt[chat_id] = {
            "id": old.get("id", int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id),
            "type": chat_types.get(chat_id, old.get("type", "private")),
            "title": titles.get(chat_id, old.get("title", chat_id)),
            "username": usernames.get(chat_id, old.get("username", "")),
            "first_seen": min(first_seen.get(chat_id, _parse_dt(old.get("first_seen"))), _parse_dt(old.get("first_seen"))).isoformat() if old.get("first_seen") else first_seen.get(chat_id, datetime.min.replace(tzinfo=timezone.utc)).isoformat(),
            "last_seen": max(last_seen.get(chat_id, _parse_dt(old.get("last_seen"))), _parse_dt(old.get("last_seen"))).isoformat() if old.get("last_seen") else last_seen.get(chat_id, datetime.min.replace(tzinfo=timezone.utc)).isoformat(),
            "message_count": counts.get(chat_id, old.get("message_count", 0)),
        }
        if rebuilt[chat_id]["first_seen"].startswith("0001-"):
            rebuilt[chat_id]["first_seen"] = old.get("first_seen", "")
        if rebuilt[chat_id]["last_seen"].startswith("0001-"):
            rebuilt[chat_id]["last_seen"] = old.get("last_seen", "")
    return rebuilt


def _merge_telegram_store(relative_path: str) -> bool:
    data_path = DATA_DIR / relative_path
    your_path = YOUR_DATA_DIR / relative_path
    if not data_path.exists() and not your_path.exists():
        return False

    data_blob = _read_json(data_path, {"offset": 0, "messages": [], "chats": {}})
    your_blob = _read_json(your_path, {"offset": 0, "messages": [], "chats": {}})
    messages = _dedupe_messages(list(data_blob.get("messages", [])) + list(your_blob.get("messages", [])))
    chats = _rebuild_telegram_chats(messages, [data_blob.get("chats", {}), your_blob.get("chats", {})])
    merged = {
        "offset": max(int(data_blob.get("offset", 0) or 0), int(your_blob.get("offset", 0) or 0)),
        "messages": messages,
        "chats": chats,
    }
    before = your_path.read_text(encoding="utf-8") if your_path.exists() else None
    _write_json(your_path, merged)
    after = your_path.read_text(encoding="utf-8")
    return before != after


def _merge_hub_conversations() -> bool:
    data_blob = _read_json(DATA_DIR / "hub_conversations.json", {"sessions": {}})
    your_blob = _read_json(YOUR_DATA_DIR / "hub_conversations.json", {"sessions": {}})
    merged_sessions: dict[str, dict[str, Any]] = {}
    changed = False

    for session_id in set(data_blob.get("sessions", {})) | set(your_blob.get("sessions", {})):
        left = data_blob.get("sessions", {}).get(session_id, {})
        right = your_blob.get("sessions", {}).get(session_id, {})
        messages: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for item in list(left.get("messages", [])) + list(right.get("messages", [])):
            key = (str(item.get("role", "")), str(item.get("content", "")))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            messages.append(item)
        left_updated = _parse_dt(left.get("last_updated"))
        right_updated = _parse_dt(right.get("last_updated"))
        latest = right if right_updated >= left_updated else left
        merged_sessions[session_id] = {
            "source": latest.get("source") or right.get("source") or left.get("source") or "unknown",
            "session_id": session_id,
            "last_updated": max(left_updated, right_updated).isoformat(),
            "messages": messages,
        }

    current = _read_json(YOUR_DATA_DIR / "hub_conversations.json", {"sessions": {}})
    target = {"sessions": merged_sessions}
    if current != target:
        _write_json(YOUR_DATA_DIR / "hub_conversations.json", target)
        changed = True
    return changed


def _merge_octa_context() -> bool:
    data_blob = _read_json(DATA_DIR / "octa_context.json", {})
    your_blob = _read_json(YOUR_DATA_DIR / "octa_context.json", {})
    merged: dict[str, Any] = {}
    for key in set(data_blob) | set(your_blob):
        if key == "diary":
            entries = list(data_blob.get("diary", [])) + list(your_blob.get("diary", []))
            deduped: dict[str, dict[str, Any]] = {}
            for entry in entries:
                identity = json.dumps(entry, sort_keys=True, ensure_ascii=False)
                deduped[identity] = entry
            merged[key] = sorted(
                deduped.values(),
                key=lambda item: _parse_dt(item.get("written_at") or item.get("timestamp")),
            )[-20:]
            continue

        left = data_blob.get(key)
        right = your_blob.get(key)
        if isinstance(left, dict) and isinstance(right, dict):
            left_written = _parse_dt(left.get("written_at"))
            right_written = _parse_dt(right.get("written_at"))
            merged[key] = right if right_written >= left_written else left
        else:
            merged[key] = right if right is not None else left

    current = _read_json(YOUR_DATA_DIR / "octa_context.json", {})
    if current != merged:
        _write_json(YOUR_DATA_DIR / "octa_context.json", merged)
        return True
    return False


def _merge_context_history() -> bool:
    lines: list[str] = []
    seen: set[str] = set()
    for source in (DATA_DIR / "octa_context_history.jsonl", YOUR_DATA_DIR / "octa_context_history.jsonl"):
        if not source.exists():
            continue
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line or line in seen:
                continue
            seen.add(line)
            lines.append(line)
    target = YOUR_DATA_DIR / "octa_context_history.jsonl"
    content = "\n".join(lines) + ("\n" if lines else "")
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    if before != content:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True
    return False


def _merge_jobs() -> bool:
    data_blob = _read_json(DATA_DIR / "octa_jobs.json", {"schema_version": 1, "jobs": []})
    your_blob = _read_json(YOUR_DATA_DIR / "octa_jobs.json", {"schema_version": 1, "jobs": []})
    merged_jobs: dict[str, dict[str, Any]] = {}
    fallback_index = 0
    for source in (data_blob.get("jobs", []), your_blob.get("jobs", [])):
        for job in source:
            job_id = str(job.get("job_id") or f"fallback_{fallback_index}")
            fallback_index += 1
            previous = merged_jobs.get(job_id)
            if previous is None:
                merged_jobs[job_id] = job
                continue
            prev_dt = _parse_dt(previous.get("updated_at") or previous.get("created_at"))
            curr_dt = _parse_dt(job.get("updated_at") or job.get("created_at"))
            if curr_dt >= prev_dt:
                merged_jobs[job_id] = job
    jobs = sorted(
        merged_jobs.values(),
        key=lambda item: _parse_dt(item.get("updated_at") or item.get("created_at")),
        reverse=True,
    )
    target_blob = {
        "schema_version": max(int(data_blob.get("schema_version", 1)), int(your_blob.get("schema_version", 1))),
        "jobs": jobs,
    }
    current = _read_json(YOUR_DATA_DIR / "octa_jobs.json", {"schema_version": 1, "jobs": []})
    if current != target_blob:
        _write_json(YOUR_DATA_DIR / "octa_jobs.json", target_blob)
        return True
    return False


def _merge_list_by_id(relative_path: str, id_key: str = "id") -> bool:
    data_items = _read_json(DATA_DIR / relative_path, [])
    your_items = _read_json(YOUR_DATA_DIR / relative_path, [])
    merged: dict[str, dict[str, Any]] = {}
    fallback_index = 0
    for source in (data_items, your_items):
        for item in source:
            item_id = str(item.get(id_key) or f"fallback_{fallback_index}")
            fallback_index += 1
            previous = merged.get(item_id)
            if previous is None:
                merged[item_id] = item
                continue
            prev_dt = _parse_dt(previous.get("updated_at") or previous.get("created_at") or previous.get("send_time"))
            curr_dt = _parse_dt(item.get("updated_at") or item.get("created_at") or item.get("send_time"))
            if curr_dt >= prev_dt:
                merged[item_id] = item
    merged_list = sorted(
        merged.values(),
        key=lambda item: _parse_dt(item.get("updated_at") or item.get("created_at") or item.get("send_time")),
    )
    current = _read_json(YOUR_DATA_DIR / relative_path, [])
    if current != merged_list:
        _write_json(YOUR_DATA_DIR / relative_path, merged_list)
        return True
    return False


def _prefer_existing_your_data(relative_path: str) -> bool:
    data_path = DATA_DIR / relative_path
    your_path = YOUR_DATA_DIR / relative_path
    if not data_path.exists():
        return False
    if not your_path.exists():
        your_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(data_path, your_path)
        return True
    return False


def main() -> None:
    if not DATA_DIR.exists():
        print("Legacy data directory not found; nothing to migrate.")
        return

    YOUR_DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup_count = _backup_legacy_tree()
    changed: dict[str, bool] = {}

    for rel in (
        "action_items.json",
        "operation_history.json",
        "organizer_archival_policies.json",
        "organizer_pending_plans.json",
        ".last_context_prune",
        "octa_manifest.txt",
    ):
        changed[rel] = _copy_if_missing(rel) or _prefer_existing_your_data(rel)

    changed["hub_conversations.json"] = _merge_hub_conversations()
    changed["octa_context.json"] = _merge_octa_context()
    changed["octa_context_history.jsonl"] = _merge_context_history()
    changed["octa_jobs.json"] = _merge_jobs()
    changed["telegram_messages.json"] = _merge_telegram_store("telegram_messages.json")
    changed["whatsapp_scheduled.json"] = _merge_list_by_id("whatsapp_scheduled.json")

    for tg_file in sorted(DATA_DIR.glob("tg_pa_*.json")):
        changed[tg_file.name] = _merge_telegram_store(tg_file.name)

    for rel in ("assistants.json", "habits.json", "habit_logs.json", "octa_job_notifications.json", "telegram_scheduled.json"):
        changed[rel] = _prefer_existing_your_data(rel)

    shutil.rmtree(DATA_DIR)

    summary = {
        "backup_dir": str(BACKUP_DIR),
        "backed_up_files": backup_count,
        "updated_files": sorted([name for name, did_change in changed.items() if did_change]),
        "removed_legacy_dir": str(DATA_DIR),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()