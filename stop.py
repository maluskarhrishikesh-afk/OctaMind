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


def main():
    root = _project_root()
    state_file = os.path.join(root, 'running_agents.json')

    print("Stopping Octa Bot...")

    # 1. Kill all tracked agent processes from running_agents.json
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
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
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)
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

    print("Octa Bot stopped. You can close this window.")


if __name__ == '__main__':
    main()
