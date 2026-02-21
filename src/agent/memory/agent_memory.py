"""
Agent Memory System - Multi-layer memory for intelligent agents

Implements short-term, long-term, personality, habits, and context memory
for each agent to enable truly autonomous and personalized behavior.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path


class AgentMemory:
    """Manages multi-layer memory system for an agent"""

    def __init__(self, agent_id: str, memory_base_dir: str = "memory"):
        """
        Initialize agent memory system following memory_architecture.md

        Args:
            agent_id: Unique agent identifier
            memory_base_dir: Base directory for all agent memories
        """
        self.agent_id = agent_id
        self.memory_dir = Path(memory_base_dir) / agent_id
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir = self.memory_dir / "archive"
        self.archive_dir.mkdir(exist_ok=True)

        # Memory file paths (following memory_architecture.md)
        self.working_memory_path = self.memory_dir / "working_memory.md"
        self.episodic_memory_path = self.memory_dir / "episodic_memory.md"
        self.semantic_memory_path = self.memory_dir / "semantic_memory.md"
        self.personality_path = self.memory_dir / "personality.md"
        self.habits_path = self.memory_dir / "habits.md"
        self.consciousness_path = self.memory_dir / "consciousness.md"

        # Legacy paths for backward compatibility
        self.short_term_path = self.working_memory_path
        self.long_term_path = self.semantic_memory_path
        self.context_path = self.working_memory_path

        # Maximum interactions to keep in working memory (RAM-like)
        self.max_working_memory = 10
        self.decay_days = 90  # For episodic memory forgetting

        self._ensure_memory_files_exist()

    def _ensure_memory_files_exist(self):
        """Create memory files following memory_architecture.md structure"""

        # Working Memory (Short-Term, RAM-like)
        if not self.working_memory_path.exists():
            self.working_memory_path.write_text("""# Working Memory

> Current context and active focus. Auto-trimmed frequently (max 10 recent items).

## Active Focus
- Ready to assist

## Current Questions
- (None)

## Current Context
- Agent initialized and ready
- Last interaction: None

---

*No recent interactions recorded*
""", encoding='utf-8')

        # Episodic Memory (Events with importance scoring)
        if not self.episodic_memory_path.exists():
            self.episodic_memory_path.write_text("""# Episodic Memory

> Time-based experiences and important conversations.
> Each entry has importance (High/Medium/Low) and decay (90 days).

---

*No events recorded yet*
""", encoding='utf-8')

        # Semantic Memory (Distilled knowledge about user)
        if not self.semantic_memory_path.exists():
            self.semantic_memory_path.write_text("""# Semantic Memory

> Distilled knowledge about the user. Not raw logs - synthesized information.

## User Preferences
- (Learning preferences...)

## User Interests
- (Observing interests...)

## Technical Background
- (Understanding user's domain...)

## Communication Style
- (Adapting to user's style...)

## Key Patterns
- (Identifying patterns over time...)
""", encoding='utf-8')

        # Personality (Assistant behavior)
        if not self.personality_path.exists():
            self.personality_path.write_text("""# Personality Profile

> Defines assistant behavior, not user behavior. Rarely changes.

## Core Traits
- **Tone:** Clear, structured, intellectually serious
- **Response Style:** Direct and informative, no fluff
- **Approach:** Technical depth with practical examples

## Goals
- Help with task automation and management
- Provide intelligent assistance
- Learn and adapt to user preferences

## Interaction Guidelines
- Always explain the "why" behind actions
- Confirm before destructive operations
- Provide summaries after complex operations
- Be proactive with suggestions when appropriate
""", encoding='utf-8')

        # Habits (Behavioral patterns - update only after 3+ confirmations)
        if not self.habits_path.exists():
            self.habits_path.write_text("""# Habits & Behavioral Learning

> Patterns that repeat consistently. Updated only after 3+ confirmations.

## Communication Pattern
- (Observing communication patterns...)

## Learning Pattern
- (Identifying learning style...)

## Work Pattern
- (Understanding work approach...)

## Trigger-Based Behaviors
- Confirm before bulk operations
- Provide summaries after actions
- Suggest optimizations when appropriate

## Time-Based Routines
- (No scheduled routines yet)
""", encoding='utf-8')

        # Consciousness (Meta summary layer - highest abstraction)
        if not self.consciousness_path.exists():
            self.consciousness_path.write_text("""# Consciousness

> Meta summary layer - distilled identity evolution. Not raw memory.
> Updated periodically (every 2-4 weeks) via summarization.

## User Profile Evolution
New user - building understanding over time.

## Primary Goals (User)
- (Observing user's long-term goals...)

## Core Pattern Recognition
- (Identifying user's thinking patterns...)

## Strategic Direction
- (Understanding user's trajectory...)

## Key Insights
- User is exploring AI agent systems
- Focus on practical implementation
- Values structured approaches
""", encoding='utf-8')

    def _save_json(self, path: Path, data: Dict[str, Any]):
        """Save JSON data to file (kept for compatibility)"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_json(self, path: Path) -> Dict[str, Any]:
        """Load JSON data from file (kept for compatibility)"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _parse_working_memory_markdown(self) -> List[Dict[str, Any]]:
        """Parse working memory from Markdown format"""
        content = self.working_memory_path.read_text(encoding='utf-8')
        interactions = []

        # Split by interaction separator
        sections = content.split('## Interaction ')

        for section in sections[1:]:  # Skip header
            lines = section.strip().split('\n')
            if len(lines) < 4:
                continue

            interaction = {}
            for line in lines:
                line = line.strip()
                if line.startswith('**Timestamp:**'):
                    interaction['timestamp'] = line.replace(
                        '**Timestamp:**', '').strip()
                elif line.startswith('**Command:**'):
                    interaction['command'] = line.replace(
                        '**Command:**', '').strip()
                elif line.startswith('**Action:**'):
                    interaction['action'] = line.replace(
                        '**Action:**', '').strip()
                elif line.startswith('**Status:**'):
                    interaction['status'] = line.replace(
                        '**Status:**', '').strip()
                elif line.startswith('**Result:**'):
                    interaction['result'] = line.replace(
                        '**Result:**', '').strip()
                elif line.startswith('**Metadata:**'):
                    metadata_str = line.replace('**Metadata:**', '').strip()
                    if metadata_str and metadata_str != 'None':
                        interaction['metadata'] = metadata_str

            if 'command' in interaction:
                interactions.append(interaction)

        return interactions

    def _parse_episodic_memory_markdown(self) -> List[Dict[str, Any]]:
        """Parse episodic memory events"""
        content = self.episodic_memory_path.read_text(encoding='utf-8')
        events = []

        # Split by date headers
        sections = content.split('## ')

        for section in sections[1:]:  # Skip header
            lines = section.strip().split('\n')
            if len(lines) < 2:
                continue

            # First line is the date
            date = lines[0].strip()
            event = {'date': date}

            for line in lines[1:]:
                line = line.strip()
                if line.startswith('**Event:**'):
                    event['event'] = line.replace('**Event:**', '').strip()
                elif line.startswith('**Insight:**'):
                    event['insight'] = line.replace('**Insight:**', '').strip()
                elif line.startswith('**Importance:**'):
                    event['importance'] = line.replace(
                        '**Importance:**', '').strip()
                elif line.startswith('**Context:**'):
                    event['context'] = line.replace('**Context:**', '').strip()

            if 'event' in event:
                events.append(event)

        return events

    # ============ Working Memory (Short-Term, RAM-like) ============

    def add_interaction(
        self,
        command: str,
        action: str,
        result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        importance: str = "Medium"
    ):
        """
        Add interaction to working memory and episodic memory

        Args:
            command: User's command
            action: Action taken
            result: Result of the action
            metadata: Additional context
            importance: High/Medium/Low (for episodic memory)
        """
        timestamp = datetime.now().isoformat()
        status = result.get('status', 'unknown')

        # Format result for display
        result_str = status
        if 'deleted_count' in result:
            result_str = f"{status} ({result['deleted_count']} deleted)"
        elif 'count' in result:
            result_str = f"{status} ({result['count']} emails)"
        elif 'total' in result:
            result_str = f"{status} (total: {result['total']}, unread: {result.get('unread', 0)})"
        elif 'message' in result:
            result_str = f"{status} - {result['message']}"

        # Format metadata
        metadata_str = 'None'
        if metadata:
            metadata_str = ', '.join(
                [f"{k}: {v}" for k, v in metadata.items()])

        # Add to working memory (RAM-like, limited size)
        working_entry = f"""## Interaction at {timestamp}

**Timestamp:** {timestamp}
**Command:** {command}
**Action:** {action}
**Status:** {status}
**Result:** {result_str}
**Metadata:** {metadata_str}

---

"""

        # Read existing working memory
        current = self.working_memory_path.read_text(encoding='utf-8')

        # Remove "No interactions" message if present
        if '*No recent interactions recorded*' in current:
            current = current.replace('*No recent interactions recorded*', '')

        # Split into header and interactions
        parts = current.split('---', 1)
        if len(parts) > 1 and '## Active Focus' in parts[0]:
            header = parts[0] + '---\n\n'
        else:
            header = """# Working Memory

> Current context and active focus. Auto-trimmed frequently (max 10 recent items).

## Active Focus
- Processing user requests

## Current Questions
- (None)

## Current Context
- Active session in progress

---

"""

        # Add new entry at the top
        new_content = header + working_entry

        # Keep only recent interactions (limited to max_working_memory)
        if len(parts) > 1:
            existing_interactions = parts[1].split('## Interaction ')
            kept_interactions = existing_interactions[1:self.max_working_memory]
            for interaction in kept_interactions:
                new_content += '## Interaction ' + interaction

        self.working_memory_path.write_text(new_content, encoding='utf-8')

        # Also add to episodic memory (with importance scoring)
        self.add_episodic_event(
            event=f"{action}: {command}",
            insight=f"User performed {action}",
            importance=importance,
            context=result_str
        )

    def add_episodic_event(
        self,
        event: str,
        insight: str = "",
        importance: str = "Medium",
        context: str = ""
    ):
        """
        Add event to episodic memory with importance scoring

        Args:
            event: Description of what happened
            insight: What we learned
            importance: High/Medium/Low
            context: Additional details
        """
        date = datetime.now().strftime("%Y-%m-%d")

        entry = f"""## {date}
**Event:** {event}
**Insight:** {insight}
**Importance:** {importance}
**Context:** {context}

---

"""

        # Read existing episodic memory
        current = self.episodic_memory_path.read_text(encoding='utf-8')

        # Remove "No events" message if present
        if '*No events recorded yet*' in current:
            current = current.replace('*No events recorded yet*', '')

        # Split into header and entries
        parts = current.split('---', 1)
        header = parts[0] + '---\n\n'

        # Add new entry at top (most recent first)
        new_content = header + entry

        # Keep existing entries
        if len(parts) > 1:
            new_content += parts[1]

        self.episodic_memory_path.write_text(new_content, encoding='utf-8')

    def get_recent_interactions(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent interactions from working memory"""
        interactions = self._parse_working_memory_markdown()
        return interactions[:count]

    def get_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent episodic events"""
        events = self._parse_episodic_memory_markdown()
        return events[:count]

    def search_interactions(self, query: str) -> List[Dict[str, Any]]:
        """Search interactions by command or action"""
        interactions = self._parse_working_memory_markdown()
        query_lower = query.lower()

        return [
            interaction for interaction in interactions
            if query_lower in interaction.get('command', '').lower()
            or query_lower in interaction.get('action', '').lower()
        ]

    def search_episodic_memory(self, query: str) -> List[Dict[str, Any]]:
        """Search episodic memory for events matching query"""
        events = self._parse_episodic_memory_markdown()
        query_lower = query.lower()

        return [
            event for event in events
            if query_lower in event.get('event', '').lower()
            or query_lower in event.get('insight', '').lower()
            or query_lower in event.get('context', '').lower()
        ]

    # ============ Semantic Memory (Distilled Knowledge) ============

    def update_semantic_memory(self, section: str, content: str):
        """
        Update a section of semantic memory

        Args:
            section: Section name (e.g., "User Preferences", "Key Patterns")
            content: Content to add/update
        """
        current = self.semantic_memory_path.read_text(encoding='utf-8')

        # Simple append for now - can be made smarter
        timestamp = datetime.now().strftime("%Y-%m-%d")
        update = f"\n### {timestamp} - {section}\n{content}\n"

        self.semantic_memory_path.write_text(
            current + update, encoding='utf-8')

    def get_semantic_memory(self) -> str:
        """Get full semantic memory as text"""
        return self.semantic_memory_path.read_text(encoding='utf-8')

    # Legacy method name for compatibility
    def update_long_term_memory(self, section: str, content: str):
        """Update semantic memory (legacy name)"""
        self.update_semantic_memory(section, content)

    def get_long_term_memory(self) -> str:
        """Get semantic memory (legacy name)"""
        return self.get_semantic_memory()

    # ============ Personality ============

    def get_personality(self) -> str:
        """Get personality profile"""
        return self.personality_path.read_text(encoding='utf-8')

    def update_personality(self, trait: str, description: str):
        """Add or update personality trait"""
        current = self.personality_path.read_text(encoding='utf-8')
        update = f"\n## {trait}\n{description}\n"
        self.personality_path.write_text(current + update, encoding='utf-8')

    # ============ Habits ============

    def get_habits(self) -> str:
        """Get habits and automated behaviors"""
        return self.habits_path.read_text(encoding='utf-8')

    def add_habit(self, habit_type: str, description: str):
        """
        Add a new habit (only after 3+ confirmations)

        Args:
            habit_type: Type of habit (Communication, Learning, Work Pattern)
            description: What the habit is
        """
        current = self.habits_path.read_text(encoding='utf-8')

        # Find the section and add
        timestamp = datetime.now().strftime("%Y-%m-%d")
        update = f"\n### {habit_type} - {timestamp}\n- {description}\n"

        self.habits_path.write_text(current + update, encoding='utf-8')

    # ============ Consciousness (Meta Summary Layer) ============

    def get_consciousness(self) -> str:
        """Get consciousness meta summary"""
        return self.consciousness_path.read_text(encoding='utf-8')

    def update_consciousness(self, section: str, content: str):
        """
        Update consciousness layer (should be done periodically, not frequently)

        Args:
            section: Section to update (User Profile Evolution, Core Pattern Recognition, etc.)
            content: New distilled insight
        """
        current = self.consciousness_path.read_text(encoding='utf-8')

        # Find and replace section or append
        lines = current.split('\n')
        new_lines = []
        in_section = False
        section_header = f"## {section}"
        section_found = False

        for line in lines:
            if line.startswith('## '):
                if line == section_header:
                    in_section = True
                    section_found = True
                    new_lines.append(line)
                    new_lines.append(content)
                else:
                    in_section = False
                    new_lines.append(line)
            elif not in_section:
                new_lines.append(line)

        # If section not found, append it
        if not section_found:
            new_lines.append(f"\n## {section}")
            new_lines.append(content)

        self.consciousness_path.write_text(
            '\n'.join(new_lines), encoding='utf-8')

    # ============ Full Memory Context (for LLM) ============

    # Character caps for LLM context — keeps token usage predictable
    _LLM_PERSONALITY_CAP = 1500   # ~375 tokens  — stable, rarely changes
    _LLM_CONSCIOUSNESS_CAP = 1000  # ~250 tokens  — high-level summary only
    _LLM_SEMANTIC_CAP = 3000      # ~750 tokens  — most-recent sections only
    _LLM_HABITS_CAP = 1500        # ~375 tokens  — most-recent habits only

    @staticmethod
    def _tail(text: str, max_chars: int) -> str:
        """Return the last `max_chars` characters of text (keeps most-recent content)."""
        if len(text) <= max_chars:
            return text
        truncated = text[-max_chars:]
        # Walk forward to the next newline so we don't start mid-sentence
        nl = truncated.find('\n')
        return ("...[earlier content trimmed]...\n" + truncated[nl + 1:]) if nl != -1 else truncated

    def get_full_context_for_llm(self, include_episodic: bool = False) -> str:
        """
        Get memory context formatted for LLM.

        What is included and why:
          - personality      : Who the agent is (capped, stable)
          - consciousness    : Big-picture understanding (capped, infrequent)
          - working_memory   : Last 5 interactions (always small)
          - semantic_memory  : Learned user knowledge — TAIL only (capped, grows over time)
          - habits           : Repeated patterns — TAIL only (capped, grows over time)
          - episodic_memory  : NOT included by default (too large; use include_episodic=True)
          - archive/         : Never included

        Returns formatted string kept under ~2 000 tokens total.
        """
        recent_interactions = self.get_recent_interactions(5)

        personality = self._tail(
            self.get_personality(), self._LLM_PERSONALITY_CAP)
        consciousness = self._tail(
            self.get_consciousness(), self._LLM_CONSCIOUSNESS_CAP)
        semantic = self._tail(self.get_semantic_memory(),
                              self._LLM_SEMANTIC_CAP)
        habits = self._tail(self.get_habits(), self._LLM_HABITS_CAP)

        context = f"""
# Agent Memory Context

## Personality
{personality}

## Consciousness (Meta Understanding)
{consciousness}

## Working Memory (Last 5 interactions)
"""
        for i, interaction in enumerate(recent_interactions, 1):
            timestamp = interaction.get('timestamp', 'Unknown')
            command = interaction.get('command', 'Unknown')
            action = interaction.get('action', 'Unknown')
            status = interaction.get('status', 'Unknown')
            result = interaction.get('result', status)

            context += f"\n{i}. [{timestamp}]\n"
            context += f"   Command: {command}\n"
            context += f"   Action: {action}\n"
            context += f"   Result: {result}\n"

        context += f"\n## Semantic Memory (User Knowledge — recent)\n{semantic}\n"
        context += f"\n## Habits & Patterns (recent)\n{habits}\n"

        if include_episodic:
            recent_events = self.get_recent_events(5)
            context += "\n## Recent Important Events\n"
            for i, event in enumerate(recent_events, 1):
                context += f"\n{i}. [{event.get('date', 'Unknown')}]\n"
                context += f"   Event: {event.get('event', 'N/A')}\n"
                context += f"   Insight: {event.get('insight', 'N/A')}\n"
                context += f"   Importance: {event.get('importance', 'Medium')}\n"

        return context

    def remember(self, query: str) -> str:
        """
        Search all memory layers for relevant information when user asks "Do you remember...?"

        Args:
            query: What the user is asking about

        Returns:
            Formatted string with relevant memories
        """
        results = []
        query_lower = query.lower()

        # Check if this is a general recall request (no specific search terms)
        general_recall_keywords = ["earlier", "before", "past", "previous", "we did", "have we",
                                   "did we", "do you know", "recall", "remember what", "what happened"]
        is_general_recall = any(
            keyword in query_lower for keyword in general_recall_keywords)

        # Extract meaningful search terms (remove common words)
        stop_words = ["can", "you", "recall", "what", "we", "did", "earlier", "before",
                      "do", "know", "have", "the", "a", "an", "about", "tell", "me"]
        search_terms = [word for word in query_lower.split()
                        if word not in stop_words and len(word) > 2]

        # If it's a general recall with no specific terms, show recent activity
        if is_general_recall and len(search_terms) == 0:
            recent_interactions = self.get_recent_interactions(10)
            if recent_interactions:
                results.append("## Recent Activity (From Working Memory):")
                for i, interaction in enumerate(recent_interactions, 1):
                    cmd = interaction.get('command', 'N/A')
                    action = interaction.get('action', 'N/A')
                    result = interaction.get('result', 'N/A')
                    timestamp = interaction.get('timestamp', 'Unknown')
                    results.append(f"\n{i}. **{cmd}**")
                    results.append(f"   Action: {action}")
                    results.append(f"   Result: {result}")
                    results.append(f"   When: {timestamp}")

            # Also show recent episodic events
            recent_events = self.get_recent_events(5)
            if recent_events:
                results.append("\n## Recent Important Events:")
                for i, event in enumerate(recent_events, 1):
                    results.append(
                        f"\n{i}. [{event.get('date', 'N/A')}] {event.get('event', 'N/A')}")
                    results.append(
                        f"   Insight: {event.get('insight', 'N/A')}")
        else:
            # Specific search - look for matching terms
            # Search working memory
            working_matches = self.search_interactions(query)
            if working_matches:
                results.append("## From Working Memory (Recent Interactions):")
                for i, interaction in enumerate(working_matches[:3], 1):
                    results.append(
                        f"{i}. {interaction.get('command', 'N/A')} - {interaction.get('action', 'N/A')}")
                    results.append(
                        f"   Result: {interaction.get('result', 'N/A')}")
                    results.append(
                        f"   When: {interaction.get('timestamp', 'Unknown')}\n")

            # Search episodic memory
            episodic_matches = self.search_episodic_memory(query)
            if episodic_matches:
                results.append("\n## From Episodic Memory (Past Events):")
                for i, event in enumerate(episodic_matches[:5], 1):
                    results.append(
                        f"{i}. [{event.get('date', 'N/A')}] {event.get('event', 'N/A')}")
                    results.append(
                        f"   Insight: {event.get('insight', 'N/A')}")
                    results.append(
                        f"   Importance: {event.get('importance', 'Medium')}\n")

            # Check semantic memory
            semantic = self.get_semantic_memory()
            if query.lower() in semantic.lower():
                results.append(
                    "\n## From Semantic Memory (Learned Knowledge):")
                # Extract relevant sections
                lines = semantic.split('\n')
                for i, line in enumerate(lines):
                    if query.lower() in line.lower():
                        # Include context (3 lines before and after)
                        start = max(0, i - 3)
                        end = min(len(lines), i + 4)
                        context_lines = lines[start:end]
                        results.append('\n'.join(context_lines))
                        results.append("")
                        break

        if not results:
            return "I don't have any specific memories matching that query in my current memory layers. Could you provide more context?"

        return '\n'.join(results)

    # ============ On-demand Recall for LLM context ============

    # Words that signal the user is trying to recall something from the past.
    # When detected, episodic + working memory is searched and the results are
    # injected into the LLM context for that single turn — exactly how a human
    # pauses to search their memory before answering.
    _RECALL_SIGNALS = {
        "remember", "recall", "did we", "have we", "last time", "earlier",
        "before", "previous", "when did", "what was", "told you", "mentioned",
        "said", "talked about", "discussed", "do you know", "you know that",
    }

    # Words to strip when extracting the actual search topic from the query.
    _RECALL_STOP_WORDS = {
        "can", "you", "recall", "what", "we", "did", "earlier", "before",
        "do", "know", "have", "the", "a", "an", "about", "tell", "me",
        "remember", "i", "my", "your", "that", "this", "and", "or", "is",
        "was", "are", "were", "when", "how", "why", "which", "who",
    }

    def recall_for_llm(self, query: str, max_episodic: int = 5, max_working: int = 3) -> str:
        """
        On-demand episodic recall: searches all memory layers for content matching
        `query` and returns a compact, LLM-ready string to be appended to the
        normal context before the LLM is called.

        Design rationale
        ----------------
        The standard context (get_full_context_for_llm) only carries the most
        recent / most common memory.  When the user asks "do you remember X?"
        or "what did I say about Y?" the relevant episode may be older than what
        is in working memory.  This method searches episodic memory on demand and
        injects only the matching hits — keeping the normal context small while
        still giving the LLM what it needs to answer the recall query.

        No indexing is used: keyword search over the structured episodic file is
        fast enough at current scale (<1 ms for thousands of entries).  Vector
        indexing should only be considered once individual files exceed ~20 KB.

        Returns
        -------
        str  Formatted multi-section string, or "" if the query is not a recall
             query or nothing relevant was found.
        """
        query_lower = query.lower()

        # Only run if this looks like a recall-seeking query
        if not any(signal in query_lower for signal in self._RECALL_SIGNALS):
            return ""

        # Extract meaningful search terms from the query
        terms = [
            w for w in query_lower.split()
            if w not in self._RECALL_STOP_WORDS and len(w) > 2
        ]

        sections: list[str] = []

        # --- 1. Working memory (recent interactions) ---
        if terms:
            seen_ts: set[str] = set()
            hits: list[dict] = []
            for term in terms:
                for h in self.search_interactions(term):
                    ts = h.get('timestamp', '')
                    if ts not in seen_ts:
                        seen_ts.add(ts)
                        hits.append(h)
            if hits:
                lines = ["### Recalled from Recent Interactions:"]
                for h in hits[:max_working]:
                    lines.append(
                        f"- [{h.get('timestamp', '?')}] "
                        f"{h.get('command', '?')} → {h.get('result', '?')}"
                    )
                sections.append('\n'.join(lines))

        # --- 2. Episodic memory ---
        if terms:
            seen_events: list[dict] = []
            seen_keys: set[str] = set()
            for term in terms:
                for e in self.search_episodic_memory(term):
                    key = e.get('event', '') + e.get('date', '')
                    if key not in seen_keys:
                        seen_keys.add(key)
                        seen_events.append(e)
        else:
            seen_events = self.get_recent_events(max_episodic)

        if seen_events:
            lines = ["### Recalled from Episodic Memory (past events):"]
            for e in seen_events[:max_episodic]:
                ctx = f" | context: {e['context']}" if e.get('context') else ""
                lines.append(
                    f"- [{e.get('date', '?')}] {e.get('event', '?')}{ctx}"
                )
            sections.append('\n'.join(lines))

        # --- 3. Semantic memory (section-level keyword match) ---
        if terms:
            sem_lines = self.get_semantic_memory().split('\n')
            matched_blocks: list[str] = []
            for i, line in enumerate(sem_lines):
                if any(t in line.lower() for t in terms):
                    start = max(0, i - 2)
                    end = min(len(sem_lines), i + 5)
                    block = '\n'.join(sem_lines[start:end]).strip()
                    if block and block not in matched_blocks:
                        matched_blocks.append(block)
            if matched_blocks:
                sections.append(
                    "### Recalled from Semantic Memory (learned knowledge):\n"
                    + '\n---\n'.join(matched_blocks[:3])
                )

        if not sections:
            return ""

        header = "## On-Demand Memory Recall (retrieved for this query only)"
        return header + '\n\n' + '\n\n'.join(sections)

    # ============ Memory Consolidation ============

    def get_consolidator(self):
        """
        Get memory consolidator for this agent

        Returns:
            MemoryConsolidator instance
        """
        from .memory_consolidator import MemoryConsolidator
        return MemoryConsolidator(self)

    def run_consolidation(self):
        """
        Run memory consolidation cycle

        This should be called periodically (every 20 interactions or 24 hours) to:
        - Extract patterns from working memory → semantic memory
        - Detect habits (3+ confirmations)
        - Apply 90-day decay to episodic memory
        - Update consciousness layer
        """
        consolidator = self.get_consolidator()
        consolidator.consolidate()

    def clear_working_memory(self):
        """Clear working memory (keep structure)"""
        self.working_memory_path.write_text("""# Working Memory

> Current context and active focus. Auto-trimmed frequently (max 10 recent items).

## Active Focus
- Ready to assist

## Current Questions
- (None)

## Current Context
- Agent initialized and ready
- Last interaction: None

---

*No recent interactions recorded*
""", encoding='utf-8')

    # Legacy method name for compatibility
    def clear_short_term_memory(self):
        """Clear working memory (legacy name)"""
        self.clear_working_memory()

    def get_context(self) -> str:
        """Get current context (compatibility method)"""
        return self.working_memory_path.read_text(encoding='utf-8')

    def update_context(self, section: str, content: str):
        """Update working memory context (compatibility method)"""
        current = self.working_memory_path.read_text(encoding='utf-8')

        lines = current.split('\n')
        new_lines = []
        in_section = False
        section_header = f"## {section}"

        for line in lines:
            if line.startswith('## '):
                in_section = line == section_header
                new_lines.append(line)
                if in_section:
                    new_lines.append(content)
            elif not in_section:
                new_lines.append(line)

        self.working_memory_path.write_text(
            '\n'.join(new_lines), encoding='utf-8')


# Factory function
def get_agent_memory(agent_id: str) -> AgentMemory:
    """Get or create agent memory instance"""
    return AgentMemory(agent_id)
