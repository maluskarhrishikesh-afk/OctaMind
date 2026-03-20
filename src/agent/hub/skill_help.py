from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class SkillHelpDoc:
    key: str
    title: str
    aliases: tuple[str, ...]
    body: str
    enableable: bool = True


_DOC_CACHE_STATE: dict[str, object] = {
    "docs": {},
    "token": None,
}


def normalize_skill_name(raw_name: str) -> str:
    return str(raw_name or "").strip().lower().replace("-", "_").replace(" ", "_")


def _skill_help_dir() -> Path:
    return Path(__file__).with_name("skill_help_md")


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()

    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text.strip()

    metadata_text = parts[0][4:]
    body = parts[1].strip()
    metadata: dict[str, object] = {}
    current_list_key: Optional[str] = None

    for raw_line in metadata_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_list_key:
            values = metadata.setdefault(current_list_key, [])
            if isinstance(values, list):
                values.append(stripped[2:].strip())
            continue
        if ":" not in stripped:
            current_list_key = None
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            metadata[key] = value.strip('"\'')
            current_list_key = None
        else:
            metadata[key] = []
            current_list_key = key

    return metadata, body


def _load_skill_docs() -> dict[str, SkillHelpDoc]:
    files = sorted(_skill_help_dir().glob("*.md"))
    token = tuple((path.name, path.stat().st_mtime_ns) for path in files)
    cached_docs = _DOC_CACHE_STATE.get("docs")
    if _DOC_CACHE_STATE.get("token") == token and isinstance(cached_docs, dict) and cached_docs:
        return cached_docs  # type: ignore[return-value]

    docs: dict[str, SkillHelpDoc] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(text)
        key = normalize_skill_name(str(metadata.get("key", path.stem)))
        title = str(metadata.get("title", key.replace("_", " ").title()))
        aliases_raw = metadata.get("aliases", [])
        aliases = tuple(
            alias.strip().lower()
            for alias in (aliases_raw if isinstance(aliases_raw, list) else [])
            if alias.strip()
        )
        docs[key] = SkillHelpDoc(
            key=key,
            title=title,
            aliases=aliases,
            body=body,
            enableable=str(metadata.get("enableable", "true") or "true").strip().lower() not in {"false", "0", "no"},
        )
    _DOC_CACHE_STATE["docs"] = docs
    _DOC_CACHE_STATE["token"] = token
    return docs


def _get_skill_doc(skill_name: str) -> Optional[SkillHelpDoc]:
    return _load_skill_docs().get(skill_name)


def get_skill_help_doc(skill_name: str) -> Optional[SkillHelpDoc]:
    return _get_skill_doc(normalize_skill_name(skill_name))


def list_skill_help_docs() -> list[SkillHelpDoc]:
    return list(_load_skill_docs().values())


def _display_skill_name(skill_name: str) -> str:
    guide = _get_skill_doc(skill_name)
    return guide.title if guide else skill_name.replace("_", " ").title()


def _display_enable_command(skill_name: str) -> str:
    return skill_name.replace("_", " ")


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"`([^`]*)`", r"\1", text)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^[-*]\s+", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def get_skill_help_preview(skill_name: str) -> str:
    doc = get_skill_help_doc(skill_name)
    if not doc:
        return ""
    paragraphs = [segment.strip() for segment in doc.body.split("\n\n") if segment.strip()]
    for paragraph in paragraphs:
        stripped = _strip_markdown(paragraph)
        if stripped and not stripped.lower().startswith(f"{doc.title.lower()} skill"):
            return stripped
    return _strip_markdown(doc.body)


def _find_skills_in_text(text: str) -> list[str]:
    lowered = str(text or "").lower()
    matches: list[tuple[int, str]] = []
    for skill_name, doc in _load_skill_docs().items():
        for alias in doc.aliases:
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                matches.append((lowered.find(alias), skill_name))
                break
    matches.sort(key=lambda item: item[0])
    ordered: list[str] = []
    for _, skill_name in matches:
        if skill_name not in ordered:
            ordered.append(skill_name)
    return ordered


def format_enable_commands(skill_names: Iterable[str]) -> str:
    skills = [skill for skill in skill_names if _get_skill_doc(skill) is not None and _get_skill_doc(skill).enableable]  # type: ignore[union-attr]
    if not skills:
        return "Use `/skills` to view available skills, then enable one with `/enable <skill_name>`."
    commands = "\n".join(f"- `/enable {_display_enable_command(skill)}`" for skill in skills)
    return f"Use these Telegram commands:\n{commands}"


def format_missing_skills_reply(agent_name: str, missing_skills: list[str], source: str) -> str:
    missing_labels = [f"**{_display_skill_name(skill)}**" for skill in missing_skills]
    if len(missing_labels) == 1:
        missing_label = missing_labels[0]
    else:
        missing_label = ", ".join(missing_labels[:-1]) + f" and {missing_labels[-1]}"
    suffix = "s" if len(missing_skills) > 1 else ""
    verb = "are" if len(missing_skills) > 1 else "is"

    if source == "telegram":
        channel_hint = (
            "Use `/skills` to view what is enabled right now.\n\n"
            f"{format_enable_commands(missing_skills)}"
        )
    else:
        channel_hint = (
            "Open **Configure** for this assistant from the Dashboard, then enable these skills in the **Skills** list."
        )

    return (
        f"⚠️ This request needs the {missing_label} skill{suffix}, which {verb} not enabled for **{agent_name}**.\n\n"
        f"{channel_hint}"
    )


def _is_enable_guidance_query(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in (
        "how to enable",
        "how do i enable",
        "how can i enable",
        "turn on",
    ))


def _is_skill_help_query(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in (
        "help with",
        "what can",
        "what does",
        "tell me about",
        "what things does",
        "how does",
        "what is the",
        "how do i use",
        "how can i use",
        "how do i operate",
        "how does this assistant work",
        "how does octamind work",
    ))


def _is_product_help_query(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in (
        "how do i use this assistant",
        "how can i use this assistant",
        "how do i use octamind",
        "how do i operate this assistant",
        "how do i operate this product",
        "how exactly do i run this",
    ))


def format_skill_help(skill_name: str, source: str = "telegram", enabled_skills: Optional[set[str]] = None) -> str:
    guide = _get_skill_doc(skill_name)
    if not guide:
        return "I do not have built-in help for that skill yet. Use `/skills` to see the supported skills."

    title = guide.title

    enabled_note = ""
    if source == "telegram" and guide.enableable:
        if enabled_skills is not None and skill_name in enabled_skills:
            enabled_note = f"\n\n✅ **{title}** is already enabled for this assistant."
        else:
            enabled_note = f"\n\nTo enable it in Telegram, run: `/enable {_display_enable_command(skill_name)}`"

    return f"{guide.body}{enabled_note}"


def maybe_get_skill_help_reply(
    message: str,
    *,
    source: str = "telegram",
    enabled_skills: Optional[set[str]] = None,
) -> Optional[str]:
    if _is_product_help_query(message):
        return format_skill_help("assistant_guide", source=source, enabled_skills=enabled_skills)

    skills = _find_skills_in_text(message)
    if not skills:
        return None

    if _is_enable_guidance_query(message):
        labels = ", ".join(_display_skill_name(skill) for skill in skills)
        return (
            f"You can enable {labels} right here in Telegram.\n\n"
            f"{format_enable_commands(skills)}\n\n"
            "After that, you can ask me what you want to do with that skill in plain language."
        )

    if _is_skill_help_query(message):
        return "\n\n---\n\n".join(
            format_skill_help(skill, source=source, enabled_skills=enabled_skills)
            for skill in skills
        )

    return None