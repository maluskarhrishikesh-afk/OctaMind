"""Unified logging for OctaMind Personal Assistant."""
from .log_manager import (
    setup_pa_logging,
    setup_test_logging,
    new_correlation_id,
    new_request_id,
    bind_correlation,
    bind_request,
    get_correlation_id,
    get_request_id,
    log_llm_call,
    log_llm_response,
)

__all__ = [
    "setup_pa_logging",
    "setup_test_logging",
    "new_correlation_id",
    "new_request_id",
    "bind_correlation",
    "bind_request",
    "get_correlation_id",
    "get_request_id",
    "log_llm_call",
    "log_llm_response",
]
