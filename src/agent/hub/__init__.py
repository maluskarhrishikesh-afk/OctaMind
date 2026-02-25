"""
OctaMind Agent Hub — channel-agnostic brain.

Any bot (Telegram, WhatsApp, WeChat …) can send a message to HubProcessor
and get a response back without knowing anything about agents, workflows, or LLMs.
"""
from .processor import HubProcessor

__all__ = ["HubProcessor"]
