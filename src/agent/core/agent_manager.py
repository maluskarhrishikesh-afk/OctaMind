"""
Agent Manager - Handles creation, storage, and management of agents

This module manages the multi-agent system, allowing users to create,
configure, and manage specialized agents for different services.
"""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import uuid
import shutil

# ── Personality helpers ────────────────────────────────────────────────────────

# Default trait values (0–10 scale)
DEFAULT_PERSONALITY_TRAITS: Dict[str, int] = {
    "tone": 3,           # 0 = Very Formal … 10 = Very Casual
    "verbosity": 5,      # 0 = Very Brief  … 10 = Very Detailed
    "humor": 2,          # 0 = Very Serious … 10 = Very Witty
    "empathy": 6,        # 0 = Neutral      … 10 = Very Warm
    "proactiveness": 5,  # 0 = Reactive     … 10 = Very Proactive
}

_TRAIT_LABELS = {
    "tone":          ("Very Formal",    "Very Casual"),
    "verbosity":     ("Very Brief",     "Very Detailed"),
    "humor":         ("Very Serious",   "Very Witty"),
    "empathy":       ("Neutral / Professional", "Very Warm & Empathetic"),
    "proactiveness": ("Reactive",       "Highly Proactive"),
}


def _score_label(trait: str, value: int) -> str:
    """Return a human-readable label for a 0-10 trait score."""
    lo, hi = _TRAIT_LABELS.get(trait, ("Low", "High"))
    if value <= 2:
        return f"leaning {lo}"
    if value <= 4:
        return f"slightly {lo}"
    if value == 5:
        return "balanced / neutral"
    if value <= 7:
        return f"slightly {hi}"
    return f"leaning {hi}"


def _build_personality_md(
    name: str,
    role: str,
    traits: Dict[str, int],
) -> str:
    """Render a personality.md from structured traits."""
    t = traits

    tone_desc = _score_label("tone",          t.get("tone", 5))
    verbose_desc = _score_label("verbosity",     t.get("verbosity", 5))
    humor_desc = _score_label("humor",         t.get("humor", 5))
    empathy_desc = _score_label("empathy",       t.get("empathy", 5))
    proactive_desc = _score_label("proactiveness", t.get("proactiveness", 5))

    return f"""# Personality Profile — {name}

## Identity
- **Name:** {name}
- **Primary Role:** {role}
- **Created:** {datetime.now().strftime('%Y-%m-%d')}

## Communication Style

| Trait           | Score (0–10) | Description                |
| --------------- | :----------: | -------------------------- |
| Tone            |      {t.get('tone', 5):2d}    | {tone_desc}         |
| Verbosity       |      {t.get('verbosity', 5):2d}    | {verbose_desc}      |
| Humor           |      {t.get('humor', 5):2d}    | {humor_desc}        |
| Empathy         |      {t.get('empathy', 5):2d}    | {empathy_desc}      |
| Proactiveness   |      {t.get('proactiveness', 5):2d}    | {proactive_desc}    |

## Behavioural Guidelines

- Greet the user by name when possible.
- Refer to yourself as **{name}**.
- Match communication style to the trait scores above — do not break character.
- Always be honest about what you can and cannot do.
- Prioritise clarity and helpfulness in every response.

## Notes
*(This section is updated automatically during memory consolidation.)*
"""


class AgentManager:
    """Manages agent configurations and lifecycle"""

    AGENT_TYPES = {
        'email': {
            'name': 'Email Agent',
            'description': 'Read, send and organise your Gmail inbox with smart summaries, follow-up reminders, and search',
            'icon': '📧',
            'capabilities': ['send', 'list', 'delete', 'count', 'search', 'summarize']
        },
        'drive': {
            'name': 'Google Drive Agent',
            'description': 'Browse and manage Google Drive — upload, share, organise folders, and find any file instantly',
            'icon': '📁',
            'capabilities': ['upload', 'download', 'list', 'share', 'organize', 'search']
        },
        'calendar': {
            'name': 'Calendar Agent',
            'description': 'Manage Google Calendar — create and update events, find free slots, get daily agendas, and set reminders',
            'icon': '📅',
            'capabilities': ['create_event', 'list_events', 'delete_event', 'find_slots', 'reminders']
        },
        'whatsapp': {
            'name': 'WhatsApp Agent',
            'description': 'Send and receive WhatsApp messages, manage contacts, schedule messages, and analyse conversations',
            'icon': '💬',
            'capabilities': ['send', 'receive', 'search', 'schedule', 'analytics', 'ai_features']
        },
        'telegram': {
            'name': 'Telegram Agent',
            'description': 'Send and receive Telegram messages, manage chats, schedule messages, create polls, and analyse conversations',
            'icon': '✈️',
            'capabilities': ['send', 'receive', 'search', 'schedule', 'polls', 'media', 'ai_features']
        },
        'files': {
            'name': 'Files Agent',
            'description': 'Manage, search, organise and analyse local files and folders',
            'icon': '🗂️',
            'capabilities': ['search', 'organise', 'archive', 'read', 'analyse', 'cross_agent']
        },
        'scheduler': {
            'name': 'Scheduler Agent',
            'description': 'Smart calendar scheduling — find optimal meeting slots, protect deep-work time, and resolve conflicts',
            'icon': '🧠',
            'capabilities': ['suggest_slots', 'protect_focus', 'resolve_conflicts', 'optimize_day', 'recurring_blocks']
        },
        'file_organizer': {
            'name': 'File Organizer Agent',
            'description': 'Approval-driven file organisation — scans folders, proposes plans, and applies them only on your confirmation',
            'icon': '🗃️',
            'capabilities': ['scan_propose', 'preview_plan', 'apply_plan', 'archive_old', 'archival_policies']
        },
        'habit_tracker': {
            'name': 'Habit Tracker Agent',
            'description': 'Track daily habits, log completions, monitor streaks, and get weekly analytics reports',
            'icon': '✅',
            'capabilities': ['add_habit', 'log_completion', 'streaks', 'weekly_report', 'analytics', 'calendar_sync']
        },
        'browser': {
            'name': 'Browser Agent',
            'description': 'Browse the web, search for information, extract page text, list links, download files, and summarise any URL',
            'icon': '🌐',
            'capabilities': ['browse_url', 'search_web', 'extract_text', 'get_page_links', 'get_page_title', 'get_page_metadata', 'find_on_page', 'extract_structured_data', 'download_file', 'summarize_page']
        },
        'stock_market': {
            'name': 'Stock Market Analysis Agent',
            'description': 'Real-time quotes, technical analysis (RSI/MACD/Bollinger), risk scoring, pattern detection, portfolio analysis, sentiment — read-only, no buy/sell',
            'icon': '📈',
            'capabilities': ['get_quote', 'get_historical_data', 'technical_analysis', 'risk_score', 'pattern_detection', 'portfolio_analysis', 'portfolio_suggestions', 'sentiment_analysis', 'compare_stocks', 'market_overview']
        },
        'linkedin': {
            'name': 'LinkedIn Agent',
            'description': 'Manage a LinkedIn page — create text, image and video posts, schedule content, generate AI-written posts and AI images, and track page analytics',
            'icon': '💼',
            'capabilities': [
                'create_text_post', 'create_image_post', 'create_video_post',
                'create_article_post', 'schedule_post', 'list_scheduled_posts',
                'cancel_scheduled_post', 'generate_ai_post_content', 'generate_ai_image',
                'get_post_analytics', 'get_page_analytics', 'get_org_followers',
                'delete_post', 'list_published_posts',
            ]
        },
        'custom': {
            'name': 'Custom Agent',
            'description': 'Build your own agent with custom capabilities',
            'icon': '🔧',
            'capabilities': []
        }
    }

    def __init__(self, storage_path: str = "agents.json"):
        """Initialize agent manager with storage path"""
        self.storage_path = storage_path
        self._ensure_storage_exists()

    def _ensure_storage_exists(self):
        """Create storage file if it doesn't exist"""
        if not os.path.exists(self.storage_path):
            self._save_agents({'agents': []})

    def _load_agents(self) -> Dict[str, Any]:
        """Load agents from storage"""
        try:
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'agents': []}

    def _save_agents(self, data: Dict[str, Any]):
        """Save agents to storage"""
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def create_agent(
        self,
        name: str,
        agent_type: str,
        role: str,
        config: Optional[Dict[str, Any]] = None,
        personality_traits: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new skill agent.

        Skills are stateless executors — they do NOT get their own memory.
        Memory and personality live at the Personal Assistant (PA) level.

        Args:
            name: Skill's display name
            agent_type: Type of skill (gmail, google_drive, files, custom, …)
            role: Description of what the skill should do
            config: Additional configuration options
            personality_traits: Ignored for skills (kept for API compatibility).
                                 Personality is managed at the PA level.

        Returns:
            Created agent/skill data dict
        """
        if agent_type not in self.AGENT_TYPES:
            raise ValueError(
                f"Invalid agent type: {agent_type}. Must be one of {list(self.AGENT_TYPES.keys())}")

        agent_id = str(uuid.uuid4())[:8]

        merged_config = config or {}
        # Do NOT store personality traits on skills — they belong to the PA.

        agent = {
            'id': agent_id,
            'name': name,
            'type': agent_type,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'config': merged_config,
            'enabled': True,
            'metadata': self.AGENT_TYPES[agent_type].copy()
        }

        # Save skill record
        data = self._load_agents()
        data['agents'].append(agent)
        self._save_agents(data)

        # Skills are stateless — no memory folder is created.
        # Memory lives at the Personal Assistant level.
        return agent


    def list_agents(self) -> List[Dict[str, Any]]:
        """Get all agents"""
        data = self._load_agents()
        return data.get('agents', [])

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID"""
        agents = self.list_agents()
        for agent in agents:
            if agent['id'] == agent_id:
                return agent
        return None

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """Update agent configuration"""
        data = self._load_agents()
        agents = data.get('agents', [])

        for i, agent in enumerate(agents):
            if agent['id'] == agent_id:
                agents[i].update(updates)
                agents[i]['updated_at'] = datetime.now().isoformat()
                self._save_agents(data)
                return True

        return False

    def delete_agent(self, agent_id: str) -> bool:
        """
        Delete an agent and its associated memory

        Args:
            agent_id: Agent ID to delete

        Returns:
            True if agent was deleted, False if not found
        """
        data = self._load_agents()
        agents = data.get('agents', [])

        original_count = len(agents)
        agents = [a for a in agents if a['id'] != agent_id]

        if len(agents) < original_count:
            # Remove from agents.json
            data['agents'] = agents
            self._save_agents(data)

            # Delete agent's memory folder
            memory_dir = Path("memory") / agent_id
            if memory_dir.exists():
                try:
                    shutil.rmtree(memory_dir)
                    print(f"✅ Deleted memory for agent {agent_id}")
                except Exception as e:
                    print(f"⚠️ Warning: Could not delete memory folder: {e}")

            return True

        return False

    def get_agent_types(self) -> Dict[str, Dict[str, Any]]:
        """Get available agent types and their metadata"""
        return self.AGENT_TYPES

    def toggle_agent(self, agent_id: str) -> bool:
        """Enable/disable an agent"""
        agent = self.get_agent(agent_id)
        if agent:
            return self.update_agent(agent_id, {'enabled': not agent.get('enabled', True)})
        return False

    def update_personality_traits(
        self, agent_id: str, traits: Dict[str, int]
    ) -> bool:
        """Persist updated personality traits to agents.json and rewrite personality.md.

        Args:
            agent_id: Target agent's ID.
            traits:   Dict with keys tone/verbosity/humor/empathy/proactiveness (0–10).

        Returns:
            True if the agent was found and updated, False otherwise.
        """
        agent = self.get_agent(agent_id)
        if not agent:
            return False

        merged = {**DEFAULT_PERSONALITY_TRAITS, **traits}
        config = agent.get("config", {})
        config["personality_traits"] = merged
        ok = self.update_agent(agent_id, {"config": config})

        if ok:
            try:
                from src.agent.memory.agent_memory import get_agent_memory
                mem = get_agent_memory(agent_id)
                content = _build_personality_md(
                    agent["name"], agent["role"], merged)
                mem.personality_path.write_text(content, encoding="utf-8")
            except Exception as exc:
                print(f"⚠️ Could not rewrite personality.md: {exc}")
        return ok


_manager_instance: Optional['AgentManager'] = None


def get_agent_manager() -> AgentManager:
    """Return the shared AgentManager singleton."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = AgentManager()
    return _manager_instance
