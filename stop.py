"""
Octa Bot — Stop Launcher
Gracefully shuts down all Octa Bot processes (dashboard + all agent windows).
Bundled to stop.exe via PyInstaller.
"""
import os
import sys
import json
import subprocess
import socket
from pathlib import Path


def _project_root() -> str:
    """Return the project root regardless of whether running as script or .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _kill_pid(pid: int):
    """Force-kill a process tree on Windows."""
    try:
        subprocess.call(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  Killed PID {pid}")
    except Exception as e:
        print(f"  Could not kill PID {pid}: {e}")


def _kill_port(port: int):
    """Kill whatever process is listening on the given TCP port."""
    try:
        result = subprocess.check_output(
            f'netstat -ano | findstr :{port}',
            shell=True, text=True, stderr=subprocess.DEVNULL
        )
        for line in result.strip().splitlines():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pid = int(parts[-1])
                if pid > 0:
                    _kill_pid(pid)
    except Exception:
        pass  # Nothing listening on that port — fine


def _stop_keep_awake(root: str) -> None:
    state_file = Path(root) / 'your_data' / 'runtime_state' / 'keep_awake.json'
    if not state_file.exists():
        return

    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
    except Exception:
        state = {}

    pid = state.get('pid')
    if isinstance(pid, int) and pid > 0:
        print(f"Stopping keep-awake helper (PID={pid})...")
        _kill_pid(pid)

    try:
        state_file.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    root = _project_root()
    state_file = Path(root) / 'your_data' / 'runtime_state' / 'running_agents.json'
    legacy_state_file = Path(root) / 'running_agents.json'
    if not state_file.exists() and legacy_state_file.exists():
        state_file = legacy_state_file

    print("Stopping Octa Bot...")

    # 1. Kill all tracked agent processes from running_agents.json
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding='utf-8'))
            if state:
                print(f"Stopping {len(state)} agent(s)...")
                for agent_id, info in state.items():
                    pid = info.get('pid')
                    port = info.get('port')
                    print(f"  Agent '{agent_id}' (PID={pid}, port={port})")
                    if pid:
                        _kill_pid(pid)
                    if port:
                        _kill_port(port)
            # Clear state file
            state_file.write_text(json.dumps({}, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"Warning: could not read running_agents.json: {e}")

    # 2. Kill the dashboard on port 8501
    print("Stopping dashboard (port 8501)...")
    _kill_port(8501)

    # 3. Belt-and-suspenders: sweep ports 8501–8599
    for port in range(8502, 8600):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) == 0:
                _kill_port(port)

    _stop_keep_awake(root)

    print("Octa Bot stopped. You can close this window.")


if __name__ == '__main__':
    main()
