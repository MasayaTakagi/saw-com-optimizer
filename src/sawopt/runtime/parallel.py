"""Shared process-environment helpers for numerical worker pools."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import ctypes
from datetime import datetime, timezone
from contextlib import contextmanager


@contextmanager
def single_blas_thread_environment(threads=1):
    """Temporarily cap the BLAS/OpenMP thread count for one worker."""
    names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ[name] = str(int(threads))
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _powershell_value(expression):
    """Read one Windows runtime value without making it a hard dependency."""
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", expression],
            capture_output=True, text=True, check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _memory_gib():
    """Return total and available physical memory where the host exposes it."""
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                gib = float(1024 ** 3)
                return status.ullTotalPhys / gib, status.ullAvailPhys / gib
        except (AttributeError, OSError):
            pass
    return None, None


def local_runtime_metadata(*, production_workers=None, blas_threads_per_worker=1,
                           run_start=None, run_end=None, wall_time_sec=None):
    """Capture host metadata for a reproducible local benchmark/run bundle."""
    cpu_model = _powershell_value(
        "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"
    ) or platform.processor() or platform.uname().processor or None
    physical = _powershell_value(
        "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum"
    )
    logical = os.cpu_count()
    total_ram, available_ram = _memory_gib()
    try:
        physical = int(physical) if physical is not None else None
    except (TypeError, ValueError):
        physical = None
    result = {
        "cpu_model": cpu_model,
        "physical_cores": physical,
        "logical_cores": int(logical) if logical is not None else None,
        "ram_total_gib": total_ram,
        "ram_available_start_gib": available_ram,
        "production_workers": None if production_workers is None else int(production_workers),
        "blas_threads_per_worker": int(blas_threads_per_worker),
        "platform": platform.system() or None,
        "platform_release": platform.release() or None,
        "python_version": sys.version,
        "run_start": run_start or datetime.now(timezone.utc).isoformat(),
        "run_end": run_end,
        "wall_time_sec": wall_time_sec,
    }
    return result


__all__ = ["local_runtime_metadata", "single_blas_thread_environment"]
