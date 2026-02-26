"""
Root conftest.py — ensures the project root is on sys.path for all tests,
and wires up the unified log manager so all test output goes to
logs/tests/pytest.log with correlation/request ID fields.
"""
import sys
from pathlib import Path

# Add project root so `from src.agent...` imports work in every test file
sys.path.insert(0, str(Path(__file__).parent))

# Unified logging setup — all loggers (whatsapp_agent, email_agent, etc.)
# funnel into logs/tests/pytest.log with the same corr/req format.
try:
    from src.agent.logging.log_manager import setup_test_logging
    setup_test_logging()
except Exception:
    pass  # Never fail test collection due to logging setup
