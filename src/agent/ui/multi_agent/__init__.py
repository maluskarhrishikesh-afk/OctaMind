"""
Multi-Agent UI package — dedicated chat window for cross-agent workflows.

Multi-agent commands are routed here when 2+ agents are running.
Accent colour: purple (#7c3aed / #8b5cf6) to distinguish from
Email (pink) and Drive (blue) agents.
"""
from .app import main

__all__ = ["main"]
