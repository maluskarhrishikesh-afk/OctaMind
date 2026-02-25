"""
Personal Assistant UI shim.

Launched by process_manager when a user starts a Personal Assistant from the
main dashboard.  process_manager sets AGENT_ID to the PA's id; this shim
forwards that as PA_ID so personal_assistant/app.py renders only that single PA.
"""
import os

# Forward AGENT_ID → PA_ID before importing the personal-assistant app
os.environ["PA_ID"] = os.environ.get("AGENT_ID", "")

from src.agent.ui.personal_assistant.app import main  # noqa: E402

if __name__ == "__main__":
    main()
