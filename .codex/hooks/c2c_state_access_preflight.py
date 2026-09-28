"""Check write access to the canonical C2C state root without changing C2C state."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
from pathlib import Path


EXIT_CODES = {
    "PASS": 0,
    "ACTIVE_SANDBOX_DENIED": 2,
    "STATE_PATH_MISMATCH": 3,
    "STATE_ROOT_MISSING": 4,
    "OTHER_IO_FAILURE": 5,
    "PROBE_CLEANUP_FAILED": 6,
}


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _is_reparse_point(info: os.stat_result) -> bool:
    """Inspect a path's lstat result without following Windows redirects."""
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", None)
    if attributes is not None:
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)
    if os.name == "nt":
        raise OSError("Cannot inspect Windows reparse-point attributes.")
    return False


def _state_root(environ: dict[str, str]) -> tuple[Path | None, str | None, str | None]:
    local_app_data = environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None, "STATE_ROOT_MISSING", "LOCALAPPDATA is not set."

    try:
        local_root_input = Path(local_app_data)
        if not local_root_input.is_absolute():
            try:
                relative_state = Path(os.path.abspath(str(local_root_input))) / "codex-with-chatgpt"
                relative_state.lstat()
            except FileNotFoundError:
                return None, "STATE_ROOT_MISSING", "The canonical C2C state directory does not exist."
            except OSError as exc:
                return None, "OTHER_IO_FAILURE", f"Cannot inspect the configured state path ({type(exc).__name__})."
            return None, "STATE_PATH_MISMATCH", "LOCALAPPDATA is not an absolute path."
        local_root = Path(os.path.abspath(str(local_root_input)))
        lexical_root = local_root / "codex-with-chatgpt"
        lexical_info = lexical_root.lstat()
    except FileNotFoundError:
        return None, "STATE_ROOT_MISSING", "The canonical C2C state directory does not exist."
    except RuntimeError:
        return None, "STATE_PATH_MISMATCH", "The canonical state path contains a redirect loop."
    except (OSError, ValueError) as exc:
        return None, "OTHER_IO_FAILURE", f"Cannot inspect the canonical state path ({type(exc).__name__})."

    try:
        if _is_reparse_point(lexical_info):
            return None, "STATE_PATH_MISMATCH", "The canonical C2C state directory is a symlink, junction, or other reparse point."
    except OSError as exc:
        return None, "STATE_PATH_MISMATCH", f"Cannot verify that the canonical state directory is not a reparse point ({type(exc).__name__})."
    if not stat.S_ISDIR(lexical_info.st_mode):
        return None, "STATE_ROOT_MISSING", "The canonical C2C state path is not a directory."

    configured = environ.get("C2C_STATE_DIR")
    if configured:
        override = Path(configured)
        if not override.is_absolute() or not _same_path(override, lexical_root):
            return None, "STATE_PATH_MISMATCH", "C2C_STATE_DIR must name the canonical lexical state directory."

    try:
        resolved_root = lexical_root.resolve(strict=True)
        resolved_info = resolved_root.stat()
    except FileNotFoundError:
        return None, "STATE_ROOT_MISSING", "The resolved C2C state path does not exist."
    except (OSError, RuntimeError, ValueError) as exc:
        return None, "STATE_PATH_MISMATCH", f"Cannot verify the canonical state path identity ({type(exc).__name__})."
    if not stat.S_ISDIR(resolved_info.st_mode):
        return None, "STATE_ROOT_MISSING", "The resolved C2C state path is not a directory."
    if not _same_path(resolved_root, lexical_root):
        try:
            same_object = os.path.samefile(lexical_root, resolved_root)
        except (OSError, ValueError):
            same_object = False
        if not same_object:
            return None, "STATE_PATH_MISMATCH", "The canonical state path does not resolve to the same directory object."

    return lexical_root, None, None


def probe_state_access(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Exclusively create and remove one empty canary in the existing state root."""
    environment = os.environ if environ is None else environ
    root, failure, detail = _state_root(environment)
    if failure:
        return {"status": failure, "detail": detail or "State path validation failed."}

    assert root is not None
    canary = root / f".c2c-access-probe-{secrets.token_hex(16)}.tmp"
    try:
        descriptor = os.open(canary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except PermissionError:
        return {"status": "ACTIVE_SANDBOX_DENIED", "detail": "The active process cannot create a canary in the canonical C2C state root."}
    except OSError as exc:
        return {"status": "OTHER_IO_FAILURE", "detail": f"Canary creation failed ({type(exc).__name__})."}

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        try:
            canary.unlink()
        except OSError:
            return {"status": "PROBE_CLEANUP_FAILED", "detail": f"Canary cleanup failed at {canary}."}
        if isinstance(exc, PermissionError):
            return {"status": "ACTIVE_SANDBOX_DENIED", "detail": "The active process cannot flush the canary in the canonical C2C state root."}
        return {"status": "OTHER_IO_FAILURE", "detail": f"Canary flush failed ({type(exc).__name__})."}

    try:
        canary.unlink()
    except OSError:
        return {"status": "PROBE_CLEANUP_FAILED", "detail": f"Canary cleanup failed at {canary}."}
    return {"status": "PASS", "detail": "The active process created, flushed, closed, and removed one canary."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable result.")
    parser.add_argument("--hook-output", action="store_true", help="Emit Codex SessionStart hook context.")
    args = parser.parse_args()

    result = probe_state_access()
    result["scope"] = "%LOCALAPPDATA%\\codex-with-chatgpt"
    result["meaning"] = "Informational at SessionStart; a direct same-boundary PASS is required before C2C commands."
    if args.hook_output:
        status = result["status"]
        message = (
            f"C2C state preflight: {status}. {result['detail']} "
            "This hook is informational only; run the direct preflight in the same execution boundary "
            "as C2C commands, and do not run doctor/session/record unless that direct check passes."
        )
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }}, ensure_ascii=False))
        return 0
    elif args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{result['status']}: {result['detail']}")
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
