"""
dashboard package — modular sub-components for the OctaMind Agent Hub.
"""
from .create_form import show_create_agent_form
from .agent_card import show_agent_card
from .configure_panel import show_configure_panel
from .app import main

__all__ = [
    "show_create_agent_form",
    "show_agent_card",
    "show_configure_panel",
    "main",
]
