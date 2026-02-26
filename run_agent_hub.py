"""
Launch Agent Hub Dashboard

Run this script to start the multi-agent management interface.
"""

import subprocess
import sys
import os
from pathlib import Path


def main():
    """Launch the agent dashboard"""
    project_root = Path(__file__).parent
    dashboard_path = project_root / "src" / "agent" / "ui" / "dashboard" / "app.py"

    # Use virtual environment python if available
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    python_cmd = str(venv_python) if venv_python.exists() else "python"

    print("🚀 Launching Agent Hub...")
    print(f"📍 Dashboard: {dashboard_path}")
    print("🌐 URL: http://localhost:8501")
    print("-" * 50)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    subprocess.run([
        python_cmd,
        "-m", "streamlit", "run",
        str(dashboard_path),
        "--server.port", "8501"
    ], env=env)


if __name__ == "__main__":
    main()
