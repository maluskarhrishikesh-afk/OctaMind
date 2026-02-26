"""
OctaMind Unified Log Manager
============================
All components — skills, LLM calls, workflows — write to a single log file
per personal assistant instance.  Two correlation identifiers are threaded
through every log record:

    correlation_id  The same value for the entire lifetime of a single
                    user-message turn (set once when the message arrives;
                    identical across every skill/tool invoked that turn).

    request_id      A fresh value for each logical sub-operation within a
                    turn (e.g. each tool call, each LLM call, each agent
                    dispatch).  Great for grouping lines of one tool call.

Both are stored in ``contextvars.ContextVar`` so they work correctly with
asyncio and threaded Streamlit sessions.

Usage
-----
At PA startup (once per process)::

    from src.agent.logging import setup_pa_logging
    setup_pa_logging("pa_alice")   # writes to  logs/pa_alice.log

At the start of each user message turn::

    from src.agent.logging import bind_correlation, new_correlation_id
    bind_correlation(new_correlation_id())

Before an LLM call or a tool dispatch::

    from src.agent.logging import bind_request, new_request_id, log_llm_call, log_llm_response
    rid = new_request_id()
    bind_request(rid)
    log_llm_call(logger, provider="github_models", model="gpt-4o", tokens_in=312)
    response = llm.chat(...)
    log_llm_response(logger, tokens_out=88, latency_ms=1240)

All existing ``logging.getLogger("whatsapp_agent")`` etc. calls continue to
work unchanged — the handlers are attached to the root logger so every named
logger in every module funnels through here automatically.

Log format (one line per record)::

    [2026-02-26 14:32:11.123] INFO  | corr=x9y8z7 req=a1b2c3 | whatsapp_agent         | Sent message to +91...
    [2026-02-26 14:32:12.001] INFO  | corr=x9y8z7 req=a1b2c3 | llm.call               | provider=github_models model=gpt-4o tokens_in=312
    [2026-02-26 14:32:13.244] INFO  | corr=x9y8z7 req=a1b2c3 | llm.response           | tokens_out=88 latency_ms=1243

Count LLM calls::

    grep "llm.call" logs/pa_alice.log | wc -l
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Context variables — async & thread safe
# ---------------------------------------------------------------------------
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# ---------------------------------------------------------------------------
# Project root (two levels up from src/agent/logging/)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # c:\…\OctaMind
_LOGS_DIR = _ROOT / "logs"


# ---------------------------------------------------------------------------
# Custom log filter — injects corr/req ids into every LogRecord
# ---------------------------------------------------------------------------
class _CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()   # type: ignore[attr-defined]
        record.request_id = _request_id.get()           # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------
_FMT = (
    "[%(asctime)s.%(msecs)03d] %(levelname)-5s | "
    "corr=%(correlation_id)-8s req=%(request_id)-8s | "
    "%(name)-30s | %(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(_FMT, datefmt=_DATE_FMT)


# ---------------------------------------------------------------------------
# Handler registry — prevents duplicate handlers on repeated imports
# ---------------------------------------------------------------------------
_active_pa_handler: Optional[logging.FileHandler] = None


# ---------------------------------------------------------------------------
# Public setup functions
# ---------------------------------------------------------------------------

def setup_pa_logging(pa_name: str, level: int = logging.DEBUG, console: bool = True) -> None:
    """
    Configure the root logger to write **all** log output to
    ``logs/<pa_name>.log``.

    Call this **once** at PA process startup before any other imports that
    use logging.  Subsequent calls replace the previous PA file handler so
    you can (in theory) hot-swap PAs, but in practice this is called once.

    Args:
        pa_name:  PA name used as the log filename (sanitised).
        level:    Root logging level (default DEBUG).
        console:  Whether to attach a StreamHandler for console output.
                  Set to False for headless background processes where stdout
                  is redirected to DEVNULL (avoids silent Windows crashes).
    """
    global _active_pa_handler

    _LOGS_DIR.mkdir(exist_ok=True)

    # Sanitise name for use as filename
    safe_name = re.sub(r"[^\w\-.]", "_", pa_name)
    log_file = _LOGS_DIR / f"{safe_name}.log"

    root = logging.getLogger()
    root.setLevel(level)

    filt = _CorrelationFilter()
    fmt = _make_formatter()

    # Remove previous PA file handler if present
    if _active_pa_handler is not None:
        root.removeHandler(_active_pa_handler)
        _active_pa_handler.close()

    # File handler — rotates nothing; kept simple to inspect with a text editor
    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    fh.addFilter(filt)
    root.addHandler(fh)
    _active_pa_handler = fh

    # Console handler (INFO only, useful during dev/startup)
    # Only add if explicitly requested and not already present (avoids duplicates
    # and prevents crashes in headless processes where stdout is DEVNULL).
    if console:
        has_stream = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in root.handlers
        )
        if not has_stream:
            sh = logging.StreamHandler()
            sh.setLevel(logging.INFO)
            sh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
            root.addHandler(sh)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "watchdog", "fsevents"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger("log_manager")
    logger.info("PA logging initialised → %s", log_file)


def setup_test_logging(level: int = logging.DEBUG) -> None:
    """
    Configure logging for test runs.  Output goes to ``logs/tests/pytest.log``.
    Intended to be called from ``conftest.py`` or a pytest plugin.
    """
    tests_dir = _LOGS_DIR / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    log_file = tests_dir / "pytest.log"

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid double-adding if already configured
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and str(log_file) in str(h.baseFilename):
            return

    filt = _CorrelationFilter()
    fmt = _make_formatter()

    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    fh.addFilter(filt)
    root.addHandler(fh)

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("log_manager").info("Test logging initialised → %s", log_file)


# ---------------------------------------------------------------------------
# Correlation / Request ID helpers
# ---------------------------------------------------------------------------

def new_correlation_id() -> str:
    """Return a fresh 8-character correlation ID (hex)."""
    return uuid.uuid4().hex[:8]


def new_request_id() -> str:
    """Return a fresh 8-character request ID (hex)."""
    return uuid.uuid4().hex[:8]


def bind_correlation(cid: str) -> str:
    """
    Set the correlation ID for the current async context / thread.
    Returns the id for convenience.

    Call once at the start of each user-message turn::

        bind_correlation(new_correlation_id())
    """
    _correlation_id.set(cid)
    return cid


def bind_request(rid: str) -> str:
    """
    Set the request ID for the current async context / thread.
    Returns the id for convenience.

    Call before each sub-operation (tool call, LLM call, agent dispatch)::

        bind_request(new_request_id())
    """
    _request_id.set(rid)
    return rid


def get_correlation_id() -> str:
    """Return the current correlation ID (or '-' if not set)."""
    return _correlation_id.get()


def get_request_id() -> str:
    """Return the current request ID (or '-' if not set)."""
    return _request_id.get()


# ---------------------------------------------------------------------------
# LLM call convenience helpers
# ---------------------------------------------------------------------------
_llm_call_start: ContextVar[float] = ContextVar("llm_call_start", default=0.0)
_llm_logger = logging.getLogger("llm.call")


def log_llm_call(
    logger: logging.Logger | None = None,
    *,
    provider: str = "unknown",
    model: str = "unknown",
    tokens_in: int = 0,
    **extra: object,
) -> None:
    """
    Log an outgoing LLM call and record the start timestamp so that
    ``log_llm_response`` can compute latency automatically.

    Example::

        log_llm_call(logger, provider="github_models", model="gpt-4o", tokens_in=400)
    """
    _llm_call_start.set(time.perf_counter())
    lg = logger or _llm_logger
    extras = " ".join(f"{k}={v}" for k, v in extra.items())
    lg.info(
        "LLM_CALL provider=%s model=%s tokens_in=%s %s",
        provider, model, tokens_in, extras,
    )


def log_llm_response(
    logger: logging.Logger | None = None,
    *,
    tokens_out: int = 0,
    error: str | None = None,
    **extra: object,
) -> float:
    """
    Log an LLM response and return the measured latency in milliseconds.

    Example::

        latency_ms = log_llm_response(logger, tokens_out=88)
    """
    start = _llm_call_start.get()
    latency_ms = round((time.perf_counter() - start) * 1000) if start else 0
    lg = logger or _llm_logger
    extras = " ".join(f"{k}={v}" for k, v in extra.items())
    if error:
        lg.warning(
            "LLM_RESPONSE error=%s latency_ms=%s %s", error, latency_ms, extras
        )
    else:
        lg.info(
            "LLM_RESPONSE tokens_out=%s latency_ms=%s %s", tokens_out, latency_ms, extras
        )
    return float(latency_ms)
