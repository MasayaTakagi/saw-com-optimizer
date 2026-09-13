"""Platform-safe local process liveness checks."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102


if os.name == "nt":
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _KERNEL32.WaitForSingleObject.restype = wintypes.DWORD
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL


def _normalize_pid(pid: int | None) -> int | None:
    try:
        numeric_pid = int(pid)
    except (TypeError, ValueError):
        return None
    return numeric_pid if numeric_pid > 0 else None


def _windows_pid_exists(pid: int) -> bool:
    handle = _KERNEL32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE,
        False,
        pid,
    )
    if not handle:
        return False
    try:
        return _KERNEL32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _KERNEL32.CloseHandle(handle)


def _posix_pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False
    return True


def pid_exists(pid: int | None) -> bool:
    """Return whether a local PID currently refers to a running process.

    Windows uses ``OpenProcess`` plus a zero-timeout wait, avoiding the
    signal-oriented ``os.kill(pid, 0)`` probe. POSIX keeps the conventional
    non-destructive signal probe and treats permission denial as liveness.
    """
    numeric_pid = _normalize_pid(pid)
    if numeric_pid is None:
        return False
    if os.name == "nt":
        return _windows_pid_exists(numeric_pid)
    return _posix_pid_exists(numeric_pid)


__all__ = ["pid_exists"]
