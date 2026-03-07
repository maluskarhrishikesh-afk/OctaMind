"""
Skill Loader — parse skills.md and select relevant tools via cosine similarity.

Each agent has a ``skills.md`` file next to its orchestrator that lists every
tool with its signature, description, and semantic tags.  This module:

1. **Parses** a skills.md into a list of ``ToolSkill`` entries.
2. **Selects** the top-K most relevant tools for a given user query using
   SentenceTransformer embeddings + FAISS cosine-similarity search
   (the same stack used by the memory vector index).
3. **Formats** the selected tools into the ``_TOOL_DOCS`` string expected by
   the DAG planner and ReAct engine.

If FAISS or sentence_transformers are unavailable the loader falls back to
returning **all** tools (the pre-skills.md behaviour), so nothing breaks.

Usage
-----
    from src.agent.core.skill_loader import load_tool_docs

    # Returns a filtered _TOOL_DOCS string with the top-K relevant tools
    tool_docs = load_tool_docs("files", user_query, top_k=15)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("skill_loader")

# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class ToolSkill:
    """A single tool parsed from skills.md."""
    name: str
    signature: str
    description: str
    category: str
    tags: List[str] = field(default_factory=list)

    @property
    def search_text(self) -> str:
        """Concatenation of description + tags for embedding."""
        tag_str = " ".join(self.tags)
        return f"{self.name} {self.description} {tag_str}"

    @property
    def doc_line(self) -> str:
        """Format as a single-line tool doc string matching _TOOL_DOCS format."""
        return f"{self.signature} – {self.description}"


# ── Parser ──────────────────────────────────────────────────────────────────

_TOOL_HEADER_RE = re.compile(r"^###\s+(.+)$")
_CATEGORY_RE = re.compile(r"^##\s+Category:\s*(.+)$")
_FIELD_RE = re.compile(r"^-\s+\*\*(\w+)\*\*:\s*(.+)$")

_cache: Dict[str, List[ToolSkill]] = {}


def _parse_skills_md(path: Path) -> List[ToolSkill]:
    """Parse a skills.md file into a list of ToolSkill entries."""
    if not path.exists():
        logger.warning("skills.md not found at %s", path)
        return []

    text = path.read_text(encoding="utf-8")
    tools: List[ToolSkill] = []
    current_category = ""
    current_tool: Optional[Dict] = None

    for line in text.splitlines():
        line = line.rstrip()

        cat_m = _CATEGORY_RE.match(line)
        if cat_m:
            current_category = cat_m.group(1).strip()
            continue

        tool_m = _TOOL_HEADER_RE.match(line)
        if tool_m:
            # Save previous tool
            if current_tool:
                tools.append(_make_tool(current_tool, current_category))
            current_tool = {"name": tool_m.group(1).strip()}
            continue

        field_m = _FIELD_RE.match(line)
        if field_m and current_tool is not None:
            key = field_m.group(1).strip().lower()
            val = field_m.group(2).strip()
            if key == "signature":
                current_tool["signature"] = val.strip("`")
            elif key == "description":
                current_tool["description"] = val
            elif key == "tags":
                current_tool["tags"] = [t.strip() for t in val.split(",")]

    # Don't forget the last tool
    if current_tool:
        tools.append(_make_tool(current_tool, current_category))

    return tools


def _make_tool(data: Dict, category: str) -> ToolSkill:
    return ToolSkill(
        name=data.get("name", ""),
        signature=data.get("signature", data.get("name", "")),
        description=data.get("description", ""),
        category=category,
        tags=data.get("tags", []),
    )


def _get_skills(agent_name: str) -> List[ToolSkill]:
    """Load and cache skills for an agent."""
    if agent_name in _cache:
        return _cache[agent_name]

    # Resolve the skills.md path relative to the agent's UI directory
    agent_dir = Path(__file__).resolve().parents[1] / "ui" / f"{agent_name}_agent"
    path = agent_dir / "skills.md"
    skills = _parse_skills_md(path)

    if skills:
        logger.info("Loaded %d tool skills from %s", len(skills), path)
    _cache[agent_name] = skills
    return skills


# ── Cosine similarity selection ─────────────────────────────────────────────

def _select_top_k(
    query: str,
    skills: List[ToolSkill],
    top_k: int,
    agent_name: str = "?",
    min_score: float = 0.20,
) -> List[ToolSkill]:
    """Return the top-K most relevant tools for the query using cosine similarity.

    Tools scoring below *min_score* (cosine similarity) are discarded even if
    they fall within the top-K.  This keeps irrelevant tools out of the LLM
    prompt and sharply reduces hallucination of non-applicable tool calls.

    Falls back to returning all tools if FAISS/SentenceTransformers unavailable.
    """
    if not skills or top_k >= len(skills):
        return skills

    try:
        from src.agent.memory.memory_vector_index import semantic_search
    except ImportError:
        logger.debug("memory_vector_index unavailable — returning all tools")
        return skills

    texts = [skill.search_text for skill in skills]
    results = semantic_search(query=query, texts=texts, top_k=top_k)

    if not results:
        # FAISS/model not available — return all
        logger.debug("semantic_search returned empty — returning all tools")
        return skills

    # Log the full ranked list with scores before applying threshold
    logger.info(
        "┌─ [skill-loader] FAISS top-%d for agent=%s  query=%r",
        top_k, agent_name, query[:60],
    )
    selected: List[ToolSkill] = []
    skipped: List[tuple] = []
    for rank, (idx, score) in enumerate(results, 1):
        if idx < len(skills):
            accepted = score >= min_score
            marker = "✓" if accepted else "✗"
            logger.info(
                "│  #%d  score=%.4f  %s  tool=%s",
                rank, float(score), marker, skills[idx].name,
            )
            if accepted:
                selected.append(skills[idx])
            else:
                skipped.append((skills[idx].name, float(score)))

    if skipped:
        logger.info(
            "│  [skill-loader] dropped %d tool(s) below min_score=%.2f: %s",
            len(skipped), min_score,
            ", ".join(f"{n}({s:.3f})" for n, s in skipped),
        )

    # Safety: if threshold filtered everything, fall back to top-3 regardless
    if not selected:
        logger.warning(
            "│  [skill-loader] all tools below threshold — using top-3 as safety fallback",
        )
        selected = [skills[idx] for idx, _s in results[:3] if idx < len(skills)]

    logger.info(
        "└─ [skill-loader] using %d/%d tools (min_score=%.2f)",
        len(selected), len(skills), min_score,
    )
    return selected


# ── Public API ──────────────────────────────────────────────────────────────

def load_tool_docs(
    agent_name: str,
    user_query: str = "",
    top_k: int = 15,
    always_include: Optional[List[str]] = None,
    min_score: float = 0.20,
) -> str:
    """Load and filter tool docs for an agent.

    Parameters
    ----------
    agent_name:
        Agent identifier (e.g. "files", "drive", "email").
    user_query:
        The user's query — used for cosine-similarity tool selection.
        If empty, all tools are returned (useful for DAG planner which
        needs to see the full tool set).
    top_k:
        Maximum number of tools to return via similarity.
    always_include:
        Tool names that should ALWAYS be included regardless of similarity
        (e.g. "save_context", "deliver_file").
    min_score:
        Minimum cosine-similarity score [0–1] a tool must reach to be
        included.  Tools below this threshold are logged and dropped.
        Reducing this keeps the LLM focused and cuts hallucination of
        irrelevant tool calls.  Default 0.20.

    Returns
    -------
    A newline-joined string of tool documentation lines, suitable for
    injection into the DAG planner or ReAct engine system prompt.
    Returns empty string if skills.md is not found.
    """
    skills = _get_skills(agent_name)
    if not skills:
        return ""

    always_include = set(always_include or [])

    if user_query:
        selected = _select_top_k(user_query, skills, top_k, agent_name=agent_name, min_score=min_score)
        # Merge in always_include tools that weren't selected
        selected_names = {s.name for s in selected}
        for skill in skills:
            if skill.name in always_include and skill.name not in selected_names:
                selected.append(skill)
    else:
        selected = skills

    return "\n".join(skill.doc_line for skill in selected)


def get_all_tool_docs(agent_name: str) -> str:
    """Return ALL tool docs for an agent (no filtering).

    Use this for the DAG planner which needs the complete tool list.
    """
    skills = _get_skills(agent_name)
    if not skills:
        return ""
    return "\n".join(skill.doc_line for skill in skills)


def clear_cache() -> None:
    """Clear the skills cache (for testing or hot-reload)."""
    _cache.clear()
