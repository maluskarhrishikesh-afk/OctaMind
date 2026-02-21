"""
Agent Hub Dashboard — thin shim.

All implementation has been moved to src/agent/ui/dashboard/.
This file is kept as an entry point because the process launcher references it by path.
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..")))

from src.agent.ui.dashboard.app import main  # noqa: E402

if __name__ == "__main__":
    main()
