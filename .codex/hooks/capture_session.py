"""Capture the active Codex session for explicit asynchronous callbacks."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _project_root() -> Path:
    """Resolve this project's root from the installed Hook location.

    The workspace can contain a parent Git repository, so using
    ``git rev-parse --show-toplevel`` would not necessarily identify the
    project that owns this Hook.
    """
    return Path(__file__).resolve().parents[2]


def capture_payload(payload: dict, destination: Path) -> dict:
    """Persist only the stable session fields needed by the launcher."""
    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        raise ValueError("Hook payload contains an empty session_id")
    session_cwd = Path(payload.get("session_cwd") or payload.get("cwd") or os.getcwd()).resolve()
    project_root = Path(payload.get("project_root") or _project_root()).resolve()
    captured = {
        "session_id": session_id,
        "session_cwd": str(session_cwd),
        "project_root": str(project_root),
        "model": payload.get("model"),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook_event_name": payload.get("hook_event_name") or "SessionStart",
        "source": payload.get("source") or payload.get("hook_event_name") or "SessionStart",
    }
    _atomic_write(Path(destination), captured)
    return captured


def build_additional_context(session_id: str) -> str:
    """Explain which continuation mode uses each runtime identity."""
    return (
        f"Current Codex session ID: {session_id}. "
        "This captured session identity is for legacy_resume continuation only. "
        "Use it with --session-id only when continuation_mode is explicitly legacy_resume. "
        "For queue mode, use the exact original Desktop thread ID with --thread-id; "
        "do not pass --session-id or --session-file. "
        "For continuation_mode=disabled, neither identity is required. "
        "The session ID and Desktop thread ID are distinct."
    )


def _record_hook_error(cwd: Path, exc: BaseException) -> None:
    try:
        root = _project_root()
        log_path = root / ".codex" / "runtime" / "hook_errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} "
                f"{type(exc).__name__}: {exc}\n"
            )
    except OSError:
        # The original Hook error is still emitted below when possible.
        pass


def main() -> int:
    cwd = Path(os.getcwd()).resolve()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise TypeError("Hook payload must be a JSON object")
        root = _project_root()
        normalized = dict(payload)
        normalized["session_cwd"] = str(Path(payload.get("cwd") or os.getcwd()).resolve())
        normalized["project_root"] = str(root)
        captured = capture_payload(normalized, root / ".codex" / "runtime" / "current_session.json")
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": build_additional_context(captured["session_id"]),
            }
        }, ensure_ascii=False))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _record_hook_error(cwd, exc)
        print(f"capture_session hook failed: {exc}", file=sys.stderr)
        # Hook failures must not prevent a Codex session from starting.  The
        # launcher performs strict validation before enabling callbacks, and
        # this log/stderr signal prevents a silent failure.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
