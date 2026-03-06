"""
Octa Bot Multi-Agent Workflow Engine.

Enables multiple agents (Email, Drive, …) to collaborate on a single
natural-language command typed in the dedicated Multi-Agent chat window.
"""
from .router import detect_agents_needed, classify_and_route, IntentResult
from .master_orchestrator import run_workflow
from .workflow_context import WorkflowContext, WorkflowStep, WorkflowPlan, NLWorkflowStep, NLWorkflowPlan
from .agent_registry import AGENT_REGISTRY, get_capabilities_text, get_executor, registered_agents

__all__ = [
    "detect_agents_needed",
    "classify_and_route",
    "IntentResult",
    "run_workflow",
    "WorkflowContext",
    "WorkflowStep",
    "WorkflowPlan",
    "NLWorkflowStep",
    "NLWorkflowPlan",
    "AGENT_REGISTRY",
    "get_capabilities_text",
    "get_executor",
    "registered_agents",
]
