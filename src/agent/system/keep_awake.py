"""
Windows keep-awake helper for OctaMind.

Runs as a lightweight background process and periodically asserts a system
execution state so Windows does not put the machine to sleep while OctaMind
is expected to remain reachable over Telegram or other external channels.
"""
from __future__ import annotations

import ctypes
import signal
import sys
import time


_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_AWAYMODE_REQUIRED = 0x00000040
_KEEP_AWAKE_FLAGS = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_AWAYMODE_REQUIRED

_STATE = {"running": True}


def _set_execution_state(flags: int) -> None:
    if sys.platform != "win32":
        return
    result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    if result == 0:
        raise OSError("SetThreadExecutionState failed")


def _shutdown(_sig=None, _frame=None) -> None:
    _STATE["running"] = False
    try:
        _set_execution_state(_ES_CONTINUOUS)
    except OSError:
        pass


def main() -> None:
    if sys.platform != "win32":
        return

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while _STATE["running"]:
        _set_execution_state(_KEEP_AWAKE_FLAGS)
        time.sleep(30)


if __name__ == "__main__":
    main()