"""Platform-specific detached process launching."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .pid_utils import pid_exists


def build_worker_command(
    run_dir: Path,
    python_executable: str | None = None,
    *,
    resume: bool = False,
) -> list[str]:
    command = [
        python_executable or sys.executable,
        "-m",
        "sawopt.orchestration.cli",
        "worker",
        "--run-dir",
        str(Path(run_dir).resolve()),
    ]
    if resume:
        command.append("--resume")
    return command


def launch_detached(run_dir: Path, *, project_root: Path,
                    command: Sequence[str] | None = None,
                    env: dict[str, str] | None = None) -> int:
    """Start a worker that is independent of the launcher terminal.

    Windows uses a new process group plus ``DETACHED_PROCESS``.  Unix uses a
    new session.  The optimizer itself never sees these platform details.
    """
    run_dir = Path(run_dir)
    project_root = Path(project_root).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    child_env = dict(os.environ)
    child_env.update(env or {})
    source_path = str(project_root / "src")
    child_env["PYTHONPATH"] = os.pathsep.join(
        [source_path, child_env["PYTHONPATH"]] if child_env.get("PYTHONPATH") else [source_path]
    )
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    child_command = list(command or build_worker_command(run_dir))

    with stdout_path.open("a", encoding="utf-8") as stdout, \
            stderr_path.open("a", encoding="utf-8") as stderr:
        kwargs = dict(
            args=child_command,
            cwd=str(project_root),
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
        )
        if os.name == "nt":
            kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            )
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(**kwargs)
    pid = int(process.pid)
    # The launcher intentionally does not wait for this child.  Marking the
    # local Popen wrapper as detached prevents its destructor from emitting a
    # false ResourceWarning while the OS process continues independently.
    process.returncode = 0
    return pid

__all__ = ["build_worker_command", "launch_detached", "pid_exists"]
