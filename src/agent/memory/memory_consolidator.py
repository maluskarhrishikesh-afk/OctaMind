"""
Memory Consolidation Engine

Implements automatic memory consolidation following memory_architecture.md:
- Working memory → Semantic memory (pattern extraction)
- Episodic memory → Semantic memory (repeated themes)
- Habit detection (3+ confirmations required)
- 90-day decay mechanism
- Consciousness updates (periodic meta-summaries)

This mimics human sleep consolidation where short-term memories
are consolidated into long-term storage.
"""

import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
import re

logger = logging.getLogger("email_agent.memory_consolidator")


class MemoryConsolidator:
    """
    Automatic memory consolidation system

    Runs periodically to:
    1. Extract patterns from working memory → semantic memory
    2. Detect habits from repeated behaviors (3+ confirmations)
    3. Apply 90-day decay to episodic memory
    4. Update consciousness layer with meta-summaries
    5. Archive old low-importance memories
    """

    def __init__(self, agent_memory):
        """
        Initialize consolidator

        Args:
            agent_memory: AgentMemory instance to operate on
        """
        self.memory = agent_memory
        self.habit_tracker = defaultdict(int)  # Track behavior frequencies
        self.state_file = self.memory.memory_dir / "consolidation_state.json"

        # Load persisted state (survives restarts)
        self.last_consolidation = None
        self.last_consciousness_update = None
        self._load_state()

    # ============ Main Consolidation Entry Point ============

    def should_consolidate(self, interaction_count: int) -> bool:
        """
        Check if consolidation should run

        Triggers:
        - Every 20 interactions
        - Every 24 hours
        - Manual trigger

        Args:
            interaction_count: Number of interactions since last consolidation

        Returns:
            True if consolidation should run
        """
        # Every 20 interactions
        if interaction_count >= 20:
            return True

        # Every 24 hours
        if self.last_consolidation:
            hours_since = (datetime.now() -
                           self.last_consolidation).total_seconds() / 3600
            if hours_since >= 24:
                return True

        return False

    def _load_state(self):
        """
        Load consolidation state from disk

        Persists:
        - last_consolidation timestamp
        - last_consciousness_update timestamp

        This ensures 24-hour triggers work across agent restarts.
        """
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                # Parse timestamps
                if state.get('last_consolidation'):
                    self.last_consolidation = datetime.fromisoformat(
                        state['last_consolidation'])
                    logger.info(
                        f"Loaded last consolidation: {self.last_consolidation}")

                if state.get('last_consciousness_update'):
                    self.last_consciousness_update = datetime.fromisoformat(
                        state['last_consciousness_update'])
                    logger.info(
                        f"Loaded last consciousness update: {self.last_consciousness_update}")

            except Exception as e:
                logger.error(f"Failed to load consolidation state: {e}")
                # Start fresh if state file is corrupted
                self.last_consolidation = None
                self.last_consciousness_update = None
        else:
            logger.debug("No consolidation state file found, starting fresh")

    def _save_state(self):
        """
        Save consolidation state to disk

        Called after each consolidation to persist state across restarts.
        """
        try:
            state = {
                'last_consolidation': self.last_consolidation.isoformat() if self.last_consolidation else None,
                'last_consciousness_update': self.last_consciousness_update.isoformat() if self.last_consciousness_update else None
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)

            logger.debug(f"Saved consolidation state to {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to save consolidation state: {e}")

    def consolidate(self):
        """
        Run full memory consolidation cycle

        Order:
        1. Extract patterns from working memory
        2. Consolidate episodic events
        3. Detect and update habits
        4. Apply 90-day decay
        5. Update consciousness (if needed)
        """
        logger.info("=== Starting Memory Consolidation ===")

        # Step 1: Extract patterns from working memory
        patterns = self._extract_patterns_from_working_memory()
        if patterns:
            self._update_semantic_with_patterns(patterns)

        # Step 2: Consolidate episodic events
        themes = self._extract_themes_from_episodic()
        if themes:
            self._update_semantic_with_themes(themes)

        # Step 3: Detect habits (3+ confirmations)
        new_habits = self._detect_habits()
        if new_habits:
            self._add_confirmed_habits(new_habits)

        # Step 4: Apply 90-day decay
        self._apply_decay_mechanism()

        # Step 5: Update consciousness (every 2-4 weeks)
        if self._should_update_consciousness():
            self._update_consciousness_layer()

        self.last_consolidation = datetime.now()

        # Persist state to survive restarts
        self._save_state()

        logger.info("=== Memory Consolidation Complete ===")

    # ============ Pattern Extraction from Working Memory ============

    def _extract_patterns_from_working_memory(self) -> Dict[str, List[str]]:
        """
        Analyze working memory for recurring patterns

        Patterns detected:
        - Repeated commands (email preferences)
        - Common timeframes (today, yesterday, this week)
        - Frequent actions (count, search, delete)

        Returns:
            Dict of pattern_type → [examples]
        """
        interactions = self.memory.get_recent_interactions(count=50)

        patterns = {
            'frequent_commands': [],
            'timeframe_preferences': [],
            'action_preferences': [],
            'error_patterns': []
        }

        if not interactions:
            return patterns

        # Count command frequencies
        commands = [i.get('command', '').lower()
                    for i in interactions if i.get('command')]
        command_freq = Counter(commands)

        # Frequent commands (appeared 3+ times)
        for cmd, count in command_freq.items():
            if count >= 3:
                patterns['frequent_commands'].append(
                    f"{cmd} (used {count} times)")

        # Detect timeframe preferences
        timeframes = []
        for cmd in commands:
            if 'today' in cmd:
                timeframes.append('today')
            elif 'yesterday' in cmd:
                timeframes.append('yesterday')
            elif 'week' in cmd:
                timeframes.append('this week')
            elif 'month' in cmd:
                timeframes.append('this month')

        timeframe_freq = Counter(timeframes)
        for tf, count in timeframe_freq.items():
            if count >= 2:
                patterns['timeframe_preferences'].append(
                    f"{tf} ({count} times)")

        # Detect action preferences
        actions = [i.get('action', '').lower()
                   for i in interactions if i.get('action')]
        action_freq = Counter(actions)

        for action, count in action_freq.items():
            if count >= 3:
                patterns['action_preferences'].append(
                    f"{action} (performed {count} times)")

        # Detect error patterns
        errors = [i for i in interactions if i.get('status') == 'error']
        if len(errors) >= 2:
            error_types = [e.get('result', '') for e in errors]
            patterns['error_patterns'] = error_types

        return patterns

    def _update_semantic_with_patterns(self, patterns: Dict[str, List[str]]):
        """
        Update semantic memory with extracted patterns

        Args:
            patterns: Detected patterns from working memory
        """
        content_parts = []

        if patterns['frequent_commands']:
            content_parts.append(
                "**Frequent Commands:**\n- " + "\n- ".join(patterns['frequent_commands']))

        if patterns['timeframe_preferences']:
            content_parts.append("**Timeframe Preferences:**\n- " +
                                 "\n- ".join(patterns['timeframe_preferences']))

        if patterns['action_preferences']:
            content_parts.append(
                "**Action Preferences:**\n- " + "\n- ".join(patterns['action_preferences']))

        if content_parts:
            content = "\n\n".join(content_parts)
            self.memory.update_semantic_memory("Usage Patterns", content)
            logger.info(
                f"Updated semantic memory with {len(content_parts)} pattern types")

    # ============ Theme Extraction from Episodic Memory ============

    def _extract_themes_from_episodic(self) -> Dict[str, List[str]]:
        """
        Analyze episodic memory for recurring themes

        Themes detected:
        - Repeated events
        - Common contexts
        - Important insights

        Returns:
            Dict of theme_type → [examples]
        """
        events = self.memory.get_recent_events(count=50)

        themes = {
            'recurring_events': [],
            'important_insights': [],
            'user_context': []
        }

        if not events:
            return themes

        # Extract high-importance insights
        high_importance = [e for e in events if e.get('importance') == 'High']
        themes['important_insights'] = [
            e.get('insight', '') for e in high_importance if e.get('insight')]

        # Extract recurring event types
        event_texts = [e.get('event', '').lower()
                       for e in events if e.get('event')]
        event_freq = Counter(event_texts)

        for event, count in event_freq.items():
            if count >= 2:
                themes['recurring_events'].append(
                    f"{event} (occurred {count} times)")

        # Extract context patterns
        contexts = [e.get('context', '') for e in events if e.get('context')]
        if contexts:
            themes['user_context'] = list(set(contexts))[
                :5]  # Top 5 unique contexts

        return themes

    def _update_semantic_with_themes(self, themes: Dict[str, List[str]]):
        """
        Update semantic memory with episodic themes

        Args:
            themes: Extracted themes from episodic memory
        """
        content_parts = []

        if themes['important_insights']:
            content_parts.append("**Key Insights:**\n- " +
                                 "\n- ".join(themes['important_insights'][:5]))

        if themes['recurring_events']:
            content_parts.append(
                "**Recurring Events:**\n- " + "\n- ".join(themes['recurring_events']))

        if themes['user_context']:
            content_parts.append("**User Context:**\n- " +
                                 "\n- ".join(themes['user_context']))

        if content_parts:
            content = "\n\n".join(content_parts)
            self.memory.update_semantic_memory("Episodic Themes", content)
            logger.info(
                f"Updated semantic memory with {len(content_parts)} theme types")

    # ============ Habit Detection (3+ Confirmations) ============

    def _detect_habits(self) -> List[Dict[str, str]]:
        """
        Detect habits from repeated behaviors (requires 3+ confirmations)

        Habit types:
        - Communication patterns (how user asks questions)
        - Work patterns (time of day, frequency)
        - Learning patterns (types of questions asked)

        Returns:
            List of detected habits with type and description
        """
        interactions = self.memory.get_recent_interactions(count=100)
        new_habits = []

        if len(interactions) < 10:
            return new_habits  # Need sufficient data

        # Track behavior patterns
        behaviors = defaultdict(int)

        # Communication pattern: Question style
        question_styles = []
        for i in interactions:
            cmd = i.get('command', '').lower()
            if '?' in cmd:
                if cmd.startswith('what') or cmd.startswith('how') or cmd.startswith('why'):
                    question_styles.append('inquisitive')
                else:
                    question_styles.append('direct')
            else:
                question_styles.append('imperative')

        style_freq = Counter(question_styles)
        most_common_style, count = style_freq.most_common(1)[0]

        if count >= 7:  # 7+ instances = habit
            percentage = (count / len(question_styles)) * 100
            new_habits.append({
                'type': 'Communication Pattern',
                'description': f"Prefers {most_common_style} communication style ({percentage:.0f}% of interactions)"
            })

        # Work pattern: Time of day analysis
        timestamps = []
        for i in interactions:
            ts = i.get('timestamp', '')
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    hour = dt.hour
                    if 5 <= hour < 12:
                        timestamps.append('morning')
                    elif 12 <= hour < 17:
                        timestamps.append('afternoon')
                    elif 17 <= hour < 21:
                        timestamps.append('evening')
                    else:
                        timestamps.append('night')
                except:
                    pass

        if timestamps:
            time_freq = Counter(timestamps)
            most_common_time, count = time_freq.most_common(1)[0]

            if count >= 5:  # 5+ sessions in same time = habit
                percentage = (count / len(timestamps)) * 100
                new_habits.append({
                    'type': 'Work Pattern',
                    'description': f"Most active during {most_common_time} ({percentage:.0f}% of sessions)"
                })

        # Learning pattern: Task complexity
        task_complexity = []
        for i in interactions:
            cmd = i.get('command', '').lower()
            # Simple tasks: count, list
            if any(word in cmd for word in ['count', 'list', 'show']):
                task_complexity.append('simple_queries')
            # Complex tasks: search, filter, analyze
            elif any(word in cmd for word in ['search', 'filter', 'analyze', 'find']):
                task_complexity.append('complex_queries')
            # Conversational
            else:
                task_complexity.append('conversational')

        complexity_freq = Counter(task_complexity)
        most_common_complexity, count = complexity_freq.most_common(1)[0]

        if count >= 5:
            percentage = (count / len(task_complexity)) * 100
            new_habits.append({
                'type': 'Learning Pattern',
                'description': f"Prefers {most_common_complexity.replace('_', ' ')} ({percentage:.0f}% of tasks)"
            })

        return new_habits

    def _add_confirmed_habits(self, habits: List[Dict[str, str]]):
        """
        Add confirmed habits to habits.md

        Args:
            habits: List of detected habits
        """
        for habit in habits:
            self.memory.add_habit(habit['type'], habit['description'])
            logger.info(
                f"Added habit: {habit['type']} - {habit['description']}")

    # ============ 90-Day Decay Mechanism ============

    @staticmethod
    def _serialize_episodic_event(event: Dict[str, Any]) -> str:
        """Serialize a single episodic event dict back to markdown format."""
        date = event.get('date', datetime.now().strftime("%Y-%m-%d"))
        ev = event.get('event', '')
        insight = event.get('insight', '')
        importance = event.get('importance', 'Medium')
        context = event.get('context', '')
        return (
            f"## {date}\n"
            f"**Event:** {ev}\n"
            f"**Insight:** {insight}\n"
            f"**Importance:** {importance}\n"
            f"**Context:** {context}\n\n"
            f"---\n\n"
        )

    def _apply_decay_mechanism(self):
        """
        Apply 90-day decay to episodic memory.

        Rules:
        - Low importance + 90+ days  → Delete permanently
        - Medium importance + 90+ days → Move to archive/episodic_YYYY_MM.md
        - High importance              → Keep always
        """
        events = self.memory.get_recent_events(count=1000)  # Get all events

        cutoff_date = datetime.now() - timedelta(days=90)
        deleted_count = 0
        archived_count = 0

        events_to_keep = []
        # Medium old → archive file
        events_to_archive: List[Dict[str, Any]] = []

        for event in events:
            date_str = event.get('date', '')
            importance = event.get('importance', 'Medium')

            try:
                # Parse date
                event_date = datetime.strptime(date_str, "%Y-%m-%d")

                # Apply decay rules
                if event_date < cutoff_date:
                    if importance == 'Low':
                        # Delete — don't add anywhere
                        deleted_count += 1
                        continue
                    elif importance == 'Medium':
                        # Archive to monthly file — remove from main episodic
                        archived_count += 1
                        events_to_archive.append(event)
                    else:  # High
                        # Keep always in main file
                        events_to_keep.append(event)
                else:
                    # Not old enough for decay
                    events_to_keep.append(event)

            except Exception:
                # Invalid date — keep the event to be safe
                events_to_keep.append(event)

        if deleted_count > 0 or archived_count > 0:
            logger.info(
                f"Decay mechanism: deleted {deleted_count} low-importance events, "
                f"archived {archived_count} medium-importance events"
            )

            # ── Rewrite episodic_memory.md with only kept events ──────────────
            episodic_path = self.memory.episodic_memory_path
            header = (
                "# Episodic Memory\n\n"
                "> Time-based experiences and important conversations.\n"
                "> Each entry has importance (High/Medium/Low) and decay (90 days).\n\n"
                "---\n\n"
            )
            new_content = header
            for ev in events_to_keep:
                new_content += self._serialize_episodic_event(ev)
            if not events_to_keep:
                new_content += "*No events recorded yet*\n"

            episodic_path.write_text(new_content, encoding='utf-8')
            logger.info(
                f"Episodic memory rewritten: {len(events_to_keep)} events kept"
            )

            # ── Move archived Medium events to archive/episodic_YYYY_MM.md ──
            if events_to_archive:
                archive_dir = episodic_path.parent / "archive"
                archive_dir.mkdir(exist_ok=True)

                # Group archived events by YYYY-MM
                by_month: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for ev in events_to_archive:
                    month_key = ev.get('date', '')[:7]  # "YYYY-MM"
                    if not month_key:
                        month_key = "unknown"
                    by_month[month_key].append(ev)

                for month_key, month_events in by_month.items():
                    safe_key = month_key.replace('-', '_')
                    archive_file = archive_dir / f"episodic_{safe_key}.md"

                    if archive_file.exists():
                        existing = archive_file.read_text(encoding='utf-8')
                    else:
                        existing = (
                            f"# Episodic Archive — {month_key}\n\n"
                            f"> Archived medium-importance memories (90+ days old).\n\n"
                            f"---\n\n"
                        )

                    for ev in month_events:
                        existing += self._serialize_episodic_event(ev)

                    archive_file.write_text(existing, encoding='utf-8')

                logger.info(
                    f"Archived {archived_count} events across "
                    f"{len(by_month)} monthly archive file(s)"
                )

    # ============ Consciousness Layer Updates ============

    def _should_update_consciousness(self) -> bool:
        """
        Check if consciousness layer should be updated

        Update frequency: Every 2-4 weeks

        Returns:
            True if update is needed
        """
        if not self.last_consciousness_update:
            # First time - update if we have sufficient data
            interactions = self.memory.get_recent_interactions(count=50)
            return len(interactions) >= 30

        # Check if 2 weeks have passed
        days_since = (datetime.now() - self.last_consciousness_update).days
        return days_since >= 14

    def _update_consciousness_layer(self):
        """
        Update consciousness meta-summary layer

        Synthesizes:
        - User profile evolution
        - Core pattern recognition
        - Strategic direction insights
        """
        logger.info("Updating consciousness layer...")

        # Analyze semantic memory for meta-patterns
        semantic = self.memory.get_semantic_memory()
        habits = self.memory.get_habits()

        # Extract user profile evolution
        profile_update = self._synthesize_user_profile(semantic, habits)
        if profile_update:
            self.memory.update_consciousness(
                "User Profile Evolution", profile_update)

        # Extract core patterns
        pattern_update = self._synthesize_core_patterns(semantic, habits)
        if pattern_update:
            self.memory.update_consciousness(
                "Core Pattern Recognition", pattern_update)

        self.last_consciousness_update = datetime.now()

        # Persist updated consciousness timestamp
        self._save_state()

        logger.info("Consciousness layer updated")

    def _synthesize_user_profile(self, semantic: str, habits: str) -> str:
        """
        Synthesize user profile from semantic memory and habits

        Args:
            semantic: Semantic memory content
            habits: Habits content

        Returns:
            Synthesized profile text
        """
        # Extract key phrases from semantic memory
        lines = semantic.split('\n')
        preferences = [l for l in lines if 'prefer' in l.lower()
                       or 'like' in l.lower()]

        if preferences or habits:
            synthesis = f"**Updated:** {datetime.now().strftime('%Y-%m-%d')}\n\n"

            if preferences:
                synthesis += "User demonstrates clear preferences in email management:\n"
                synthesis += "\n".join(
                    f"- {p.strip()}" for p in preferences[:5])
                synthesis += "\n\n"

            synthesis += "Behavioral patterns have stabilized around systematic email interaction."

            return synthesis

        return ""

    def _synthesize_core_patterns(self, semantic: str, habits: str) -> str:
        """
        Synthesize core patterns from memory

        Args:
            semantic: Semantic memory content
            habits: Habits content

        Returns:
            Synthesized pattern text
        """
        # Analyze habits for patterns
        habit_lines = habits.split('\n')
        communication = [l for l in habit_lines if 'Communication' in l]
        work = [l for l in habit_lines if 'Work' in l]

        if communication or work:
            synthesis = f"**Updated:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
            synthesis += "Emerging patterns in user behavior:\n\n"

            if communication:
                synthesis += "**Communication:** Consistent interaction style established.\n"

            if work:
                synthesis += "**Work Rhythm:** Regular usage patterns detected.\n"

            synthesis += "\nUser exhibits systematic approach to email management with growing sophistication."

            return synthesis

        return ""
