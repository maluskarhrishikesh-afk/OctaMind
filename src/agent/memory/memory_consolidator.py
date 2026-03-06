"""
Memory Consolidation Engine

Implements automatic memory consolidation following memory_architecture.md:
- Working memory → Semantic memory (pattern extraction)
- Episodic memory → Semantic memory (repeated themes)
- Habit detection (3+ confirmations required)
- 90-day decay mechanism
- Self reflection updates (periodic meta-summaries)

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
    4. Update self reflection layer with meta-summaries
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
        self.last_self_reflection_update = None
        # Backward-compat alias so external code reading this attribute still works
        self.last_consciousness_update: datetime | None = None
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

        # Every 8 hours (changed from 24 h — more responsive memory updates)
        if self.last_consolidation:
            hours_since = (datetime.now() -
                           self.last_consolidation).total_seconds() / 3600
            if hours_since >= 8:
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

                if state.get('last_self_reflection_update') or state.get('last_consciousness_update'):
                    raw = state.get('last_self_reflection_update') or state.get('last_consciousness_update')
                    self.last_self_reflection_update = datetime.fromisoformat(raw)
                    self.last_consciousness_update = self.last_self_reflection_update  # compat alias
                    logger.info(
                        f"Loaded last self_reflection update: {self.last_self_reflection_update}")

            except Exception as e:
                logger.error(f"Failed to load consolidation state: {e}")
                # Start fresh if state file is corrupted
                self.last_consolidation = None
                self.last_self_reflection_update = None
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
                'last_self_reflection_update': self.last_self_reflection_update.isoformat() if self.last_self_reflection_update else None,
                # kept for backward compat with older state files
                'last_consciousness_update': self.last_self_reflection_update.isoformat() if self.last_self_reflection_update else None,
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

        # Step 5 + 6: Update self reflection & adapt personality (same cadence: ~2 weeks)
        # Evaluate the gate ONCE — _update_self_reflection_layer() advances the
        # timestamp inside, so a second call to _should_update_self_reflection()
        # would incorrectly return False for the personality step.
        _run_reflection_update = self._should_update_self_reflection()
        if _run_reflection_update:
            self._update_self_reflection_layer()
            self._update_user_personality_observations()

        # Step 7 (multi-agent only): Synthesise collective consciousness
        from src.agent.memory.agent_memory import MULTI_AGENT_ID
        if self.memory.agent_id == MULTI_AGENT_ID:
            self._update_collective_consciousness()

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

        # ── Scheduled / Day-of-week behaviour detection ────────────────────────
        # Core insight: "user deletes spam every Friday", "sends OOO on Fridays"
        # We look for (day-of-week, action_keyword) pairs that appear 3+ times.
        _DAYS = ['monday', 'tuesday', 'wednesday',
                 'thursday', 'friday', 'saturday', 'sunday']
        _ACTION_KEYWORDS = {
            'delete': ['delete', 'remove', 'clear', 'trash', 'spam'],
            'send': ['send', 'compose', 'reply', 'forward', 'draft'],
            'schedule': ['schedule', 'calendar', 'invite', 'meeting', 'event'],
            'ooo': ['out of office', 'ooo', 'vacation', 'away'],
            'archive': ['archive', 'file', 'folder', 'organiz'],
            'review': ['read', 'check', 'review', 'open', 'list'],
        }

        day_action_combos: dict[str, int] = defaultdict(int)

        for interaction in interactions:
            ts = interaction.get('timestamp', '')
            cmd = (interaction.get('command', '') + ' ' +
                   interaction.get('action', '')).lower()
            if not ts or not cmd:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                day_name = _DAYS[dt.weekday()]
                hour = dt.hour
            except Exception:
                continue

            for action_label, keywords in _ACTION_KEYWORDS.items():
                if any(kw in cmd for kw in keywords):
                    day_action_combos[f"{day_name}|{action_label}"] += 1
                    # Also track hour-of-day habits (e.g. "sends emails at 9am")
                    hour_bucket = f"{hour:02d}:00"
                    day_action_combos[f"{hour_bucket}|{action_label}"] += 1

        for combo_key, occurrences in day_action_combos.items():
            if occurrences >= 3:
                parts = combo_key.split('|')
                if len(parts) != 2:
                    continue
                time_part, action_part = parts
                # Prettify
                if ':' in time_part:
                    label = f"around {time_part}"
                else:
                    label = f"on {time_part.capitalize()}s"
                new_habits.append({
                    'type': 'Scheduled Behaviour',
                    'description': (
                        f"Tends to {action_part} {label} "
                        f"(seen {occurrences}\u00d7)"
                    ),
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

    # ============ Self Reflection Layer Updates ============

    def _should_update_self_reflection(self) -> bool:
        """
        Check if self reflection layer should be updated

        Update frequency: Every 2-4 weeks

        Returns:
            True if update is needed
        """
        if not self.last_self_reflection_update:
            # First time — update if we have at least a handful of interactions.
            # Threshold is intentionally low (5) so that even a freshly set-up
            # system generates a self_reflection file after the very first session.
            interactions = self.memory.get_recent_interactions(count=50)
            return len(interactions) >= 5

        # Check if 2 weeks have passed
        days_since = (datetime.now() - self.last_self_reflection_update).days
        return days_since >= 14

    # Backward-compat alias
    def _should_update_consciousness(self) -> bool:
        """Alias for _should_update_self_reflection() — kept for backward compatibility."""
        return self._should_update_self_reflection()

    def _update_self_reflection_layer(self):
        """
        Update self reflection meta-summary layer.

        Synthesises a manager-level mental model of the user by reading
        ALL memory layers: working, episodic, semantic, and habits.
        This gives the richest possible picture of the user.
        """
        logger.info("Updating self reflection layer...")

        now_str = datetime.now().strftime("%Y-%m-%d")

        # ── Gather all memory layers ─────────────────────────────────────────
        semantic = self.memory.get_semantic_memory()
        habits   = self.memory.get_habits()
        recent_events = self.memory.get_recent_events(count=30)
        recent_interactions = self.memory.get_recent_interactions(count=50)

        # ── Who Is This Person? ——————————————————————————————————————---------
        profile_lines = [l.strip() for l in semantic.split('\n')
                         if l.strip().startswith('-') and len(l.strip()) > 5]
        profile_section = (
            f"**Last updated:** {now_str}\n\n"
            + ("\n".join(profile_lines[:8]) if profile_lines
               else "*(Still building understanding — more interactions needed)*")
        )
        self.memory.update_consciousness("Who Is This Person?", profile_section)

        # ── Current Life / Work Chapter ——————————————————————————————---------
        # Use the most recent high-importance episodic events as chapter signals
        high_events = [e for e in recent_events if e.get('importance') == 'High']
        if high_events:
            chapter_lines = []
            for ev in high_events[-5:]:
                chapter_lines.append(
                    f"- [{ev.get('date', '?')}] {ev.get('insight') or ev.get('event', '')}")
            chapter_section = (
                f"**Last updated:** {now_str}\n\n"
                "Recent high-signal events suggesting current context:\n\n"
                + "\n".join(chapter_lines)
            )
            self.memory.update_consciousness(
                "Current Life / Work Chapter", chapter_section)

        # ── How They Think & Communicate ——————————————————————————————--------
        interaction_styles: list[str] = []
        for i in recent_interactions:
            cmd = i.get('command', '').lower()
            if any(w in cmd for w in ['can you', 'could you', 'please', 'would you']):
                interaction_styles.append('polite-request')
            elif cmd.endswith('?'):
                interaction_styles.append('question')
            else:
                interaction_styles.append('direct-command')

        style_counter = Counter(interaction_styles)
        dominant_style = style_counter.most_common(1)[0][0] if style_counter else 'unknown'
        style_section = (
            f"**Last updated:** {now_str}\n\n"
            f"Dominant interaction style: **{dominant_style}** "
            f"({style_counter.get(dominant_style, 0)} of {len(interaction_styles)} recent interactions)\n"
        )
        self.memory.update_consciousness(
            "How They Think & Communicate", style_section)

        # ── Where They Need the Most Help ——————————————————————————————-------
        # Look at failed/error interactions and recurring commands
        error_interactions = [i for i in recent_interactions
                              if i.get('status') == 'error']
        command_freq = Counter(
            i.get('action', '') for i in recent_interactions if i.get('action')
        )
        freq_summary = ", ".join(
            f"{action} ({cnt}x)"
            for action, cnt in command_freq.most_common(5)
        )
        help_section = (
            f"**Last updated:** {now_str}\n\n"
            f"Most-used actions: {freq_summary or 'N/A'}\n"
            f"Errors encountered: {len(error_interactions)}\n"
        )
        self.memory.update_consciousness(
            "Where They Need the Most Help", help_section)

        # ── Trust & Safety Profile ——————————————————————————————--------------
        # Build a lightweight baseline from confirmed habits and timing patterns
        habit_content = habits
        timing_habits = [l for l in habit_content.split('\n')
                         if 'timing' in l.lower() or 'pattern' in l.lower()
                         or 'routine' in l.lower()]
        safety_section = (
            f"**Last updated:** {now_str}\n\n"
            "Established normal patterns (deviations may signal anomalies):\n\n"
            + ("\n".join(timing_habits[:5]) if timing_habits
               else "*(Building baseline — more interactions needed)*")
        )
        self.memory.update_consciousness(
            "Trust & Safety Profile", safety_section)

        self.last_self_reflection_update = datetime.now()
        self.last_consciousness_update = self.last_self_reflection_update  # compat alias
        self._save_state()
        logger.info("Self reflection layer updated (all memory layers used)")

    # Backward-compat alias
    def _update_consciousness_layer(self):
        """Alias for _update_self_reflection_layer() — kept for backward compatibility."""
        self._update_self_reflection_layer()

    # ============ User Personality Observations → Personality.md ============

    def _update_user_personality_observations(self) -> None:
        """
        Observe how this user communicates and adapt the agent's personality
        to mirror it. Rewrites the "Observed User Personality" and
        "Adapted Communication Style" sections in personality.md so the
        agent's tone gradually mirrors the user's preferred style.

        Design intent:
          - personality.md is the agent's stable *identity* (rarely changed).
          - The two auto-managed sections added here capture user-calibrated
            behavioural adaptations that evolve over time.
          - Both sections are REWRITTEN each cycle — the file doesn't grow.

        Observations extracted (all from local interaction data, 0 LLM calls):
          • Formality  → imperative / polite / casual mix ratio
          • Verbosity  → average command word count
          • Question style → inquisitive vs directive
          • Emoji usage → whether user uses emoji
          • Time-of-day → when the user is most active
        """
        interactions = self.memory.get_recent_interactions(count=100)
        if len(interactions) < 5:
            logger.debug("Not enough interactions to build user personality observations.")
            return

        now_str = datetime.now().strftime("%Y-%m-%d")

        # ── Communication formality ───────────────────────────────────────────
        polite_count, direct_count, casual_count = 0, 0, 0
        word_counts: list[int] = []
        emoji_count = 0
        question_count = 0

        for i in interactions:
            cmd = str(i.get("command", "")).strip()
            if not cmd:
                continue
            words = cmd.split()
            word_counts.append(len(words))

            cmd_lower = cmd.lower()
            if any(w in cmd_lower for w in ("please", "could you", "can you", "would you", "kindly")):
                polite_count += 1
            elif any(w in cmd_lower for w in ("hey", "yo", "hmm", "lol", "haha", "ok ", "ok,", "nah", "yep")):
                casual_count += 1
            else:
                direct_count += 1

            if "?" in cmd:
                question_count += 1
            # Rough emoji heuristic: non-ASCII chars in common emoji range
            if any(ord(c) > 127 for c in cmd):
                emoji_count += 1

        total = len(interactions)
        avg_words = sum(word_counts) / max(len(word_counts), 1)

        # Determine dominant style
        if polite_count >= max(direct_count, casual_count):
            style_label = "polite and courteous"
            style_guidance = ("Use a warm, respectful tone. Include 'please' and appreciation. "
                              "Avoid being blunt or terse.")
        elif casual_count >= direct_count:
            style_label = "casual and conversational"
            style_guidance = ("Use a relaxed, friendly tone. Short sentences are fine. "
                              "Match the user's informal energy — emojis are welcome if the user uses them.")
        else:
            style_label = "direct and task-oriented"
            style_guidance = ("Be concise and to-the-point. Lead with the answer or result. "
                              "Avoid filler phrases. The user values efficiency.")

        verbosity = (
            "brief (avg <8 words/message)"  if avg_words < 8  else
            "medium-length"                 if avg_words < 20 else
            "detailed and descriptive"
        )

        question_ratio = question_count / max(total, 1)
        interaction_type = (
            "asks many questions — be thorough in answers"
            if question_ratio > 0.5
            else "gives directives — execute clearly without over-explaining"
        )

        uses_emoji = emoji_count / max(total, 1) > 0.2

        # ── Time-of-day preference ────────────────────────────────────────────
        hour_buckets: dict[str, int] = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
        for i in interactions:
            ts = i.get("timestamp", "")
            try:
                h = datetime.fromisoformat(ts).hour
                if 5 <= h < 12:   hour_buckets["morning"]   += 1
                elif 12 <= h < 17: hour_buckets["afternoon"] += 1
                elif 17 <= h < 21: hour_buckets["evening"]   += 1
                else:              hour_buckets["night"]      += 1
            except Exception:
                pass
        peak_time = max(hour_buckets, key=hour_buckets.get)  # type: ignore[arg-type]

        # ── Write "Observed User Personality" section ─────────────────────────
        obs_section = (
            f"**Last updated:** {now_str}  \n"
            f"**Interactions analysed:** {total}  \n\n"
            f"| Attribute | Observed value |\n"
            f"|---|---|\n"
            f"| Communication style | {style_label} |\n"
            f"| Message verbosity | {verbosity} |\n"
            f"| Interaction type | {interaction_type} |\n"
            f"| Uses emoji | {'Yes' if uses_emoji else 'No'} |\n"
            f"| Most active time | {peak_time} |\n"
        )
        self.memory.update_personality_section("Observed User Personality", obs_section)

        # ── Write "Adapted Communication Style" section ───────────────────────
        # This section is read by the LLM on every request via get_full_context_for_llm.
        # It directly shapes how the agent speaks to this user.
        adapted_section = (
            f"**Auto-calibrated from {total} interactions — last updated {now_str}**\n\n"
            f"Based on how this user communicates, adapt your style as follows:\n\n"
            f"- **Tone:** {style_guidance}\n"
            f"- **Length:** Messages tend to be {verbosity}; match that depth.\n"
            f"- **Approach:** User {interaction_type}.\n"
            f"- **Emoji use:** {'Feel free to use relevant emojis sparingly.' if uses_emoji else 'Avoid emoji unless the user uses them first.'}\n"
            f"- **Best time:** User is most active in the **{peak_time}**; greet accordingly when relevant.\n\n"
            f"> This section is automatically rewritten every consolidation cycle. "
            f"Do not treat it as permanent — it reflects recent patterns only.\n"
        )
        self.memory.update_personality_section("Adapted Communication Style", adapted_section)

        logger.info(
            "User personality observations updated: style=%s, verbosity=%s, interactions=%d",
            style_label, verbosity, total,
        )

    def _update_collective_consciousness(self) -> None:
        """
        Synthesise collective_consciousness.md for the multi-agent hub.

        Reads consciousness.md from every registered agent and combines
        them into a unified cross-agent mental model of the user.
        Only runs for the _collective_memory_ agent.
        """
        from src.agent.memory.agent_memory import get_agent_memory

        if self.memory.collective_consciousness_path is None:
            return

        logger.info("Updating collective consciousness...")

        agents_json = Path(__file__).parent.parent.parent.parent / "agents.json"

        agent_ids: list[str] = []
        try:
            if agents_json.exists():
                data = json.loads(agents_json.read_text(encoding="utf-8"))
                agent_ids = [a.get("id", "") for a in data.get("agents", []) if a.get("id")]
        except Exception as exc:
            logger.error(f"Could not read agents.json for collective consciousness: {exc}")
            return

        if not agent_ids:
            logger.debug("No registered agents — skipping collective consciousness update")
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        sections: list[str] = [
            "# Collective Consciousness\n",
            f"> Last synthesised: {now_str}\n",
            "> Cross-agent synthesis: a unified picture of the user assembled from",
            "> every specialised agent's individual consciousness layer.\n",
            "---\n",
        ]

        per_agent_insights: list[str] = []
        trust_signals: list[str] = []

        for agent_id in agent_ids:
            try:
                agent_mem = get_agent_memory(agent_id)
                consciousness_path = agent_mem.consciousness_path

                if not consciousness_path.exists():
                    continue

                content = consciousness_path.read_text(encoding="utf-8")

                # Extract non-empty bullet points as insights
                bullets = [
                    line.strip() for line in content.split("\n")
                    if line.strip().startswith("-")
                    and "(" not in line  # skip placeholder text
                    and len(line.strip()) > 10
                ]

                if bullets:
                    per_agent_insights.append(
                        f"### {agent_id}\n" + "\n".join(bullets[:8])
                    )

                # Trust & Safety section extraction
                if "Trust & Safety Profile" in content:
                    idx = content.find("Trust & Safety Profile")
                    snippet = content[idx: idx + 400].split("##")[0].strip()
                    trust_signals.append(f"**{agent_id}:** {snippet[:200]}")

            except Exception as exc:
                logger.warning(f"Could not read consciousness for {agent_id}: {exc}")

        # ── Build the collective document ────────────────────────────────────
        sections.append("## Agent-Specific Insights\n")
        if per_agent_insights:
            sections.extend(per_agent_insights)
        else:
            sections.append("*(No agent has accumulated enough data yet)*")

        sections.append("\n## Composite Trust Baseline\n")
        if trust_signals:
            sections.extend(trust_signals)
        else:
            sections.append("*(Building baseline — more interactions needed)*")

        sections.append("\n## Cross-Domain Patterns\n")
        sections.append("*(Automatically populated as agents accumulate memory)*")

        sections.append("\n## Conflict / Inconsistency Log\n")
        sections.append("*(Populated when agent models conflict on the same observation)*")

        final_content = "\n".join(sections)
        self.memory.collective_consciousness_path.write_text(
            final_content, encoding="utf-8"
        )
        logger.info(
            f"Collective consciousness updated from {len(agent_ids)} agent(s)."
        )
