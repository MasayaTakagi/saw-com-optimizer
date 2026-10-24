"""Opt-in, mock-only exact Pi-session identity boundary.

No Pi executable, RPC process, provider, session transcript, or credential is
used here. Callers must inject a deterministic fake transport explicitly.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Protocol


_METADATA_NAME = "session-reference.json"
_SCHEMA_VERSION = 1
_MAX_METADATA_BYTES = 8192
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_IDENTITY_FIELDS = {
    "schema_version", "local_association_key", "pi_session_id", "session_file_reference",
    "expected_pi_version", "branch_leaf_id", "entry_cursor", "file_device", "file_inode",
}
_ERROR_MESSAGES = {
    "SESSION_MISSING": "the exact test session reference or file is missing",
    "SESSION_IDENTITY_MISMATCH": "the exact test session identity does not match",
    "SESSION_CURSOR_UNKNOWN": "the recorded session branch cursor cannot be verified",
    "SESSION_STORE_UNSAFE": "the explicit private test-session directory is unsafe",
    "SESSION_REFERENCE_EXISTS": "a test-session reference already exists; it will not be replaced",
    "FAKE_TRANSPORT_REQUIRED": "this adapter accepts only an explicitly marked test fake transport",
    "RPC_DISCONNECTED": "the fake RPC transport disconnected or returned no response",
    "RPC_RESPONSE_ID_MISMATCH": "the fake RPC response ID did not match its request",
    "RPC_EVENT_ORDER_INVALID": "the fake RPC event sequence was duplicated or out of order",
    "RPC_PROTOCOL_INVALID": "the fake RPC response stream was invalid",
    "RPC_REJECTED": "the fake RPC request was rejected",
}


class SessionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    SESSION_MISSING = "SESSION_MISSING"
    SESSION_IDENTITY_MISMATCH = "SESSION_IDENTITY_MISMATCH"
    SESSION_CURSOR_UNKNOWN = "SESSION_CURSOR_UNKNOWN"
    ATTACHED = "ATTACHED"
    PROMPT_PENDING = "PROMPT_PENDING"
    SETTLED = "SETTLED"
    DISPATCH_AMBIGUOUS = "DISPATCH_AMBIGUOUS"


class PiSessionError(Exception):
    """Typed error whose public text never contains a session path or payload."""

    def __init__(self, code: str):
        self.code = code if code in _ERROR_MESSAGES else "SESSION_IDENTITY_MISMATCH"
        super().__init__(_ERROR_MESSAGES[self.code])


@dataclass(frozen=True, repr=False)
class SessionReference:
    """Protected test-only mapping; path and local file identity stay out of repr."""

    local_association_key: str
    pi_session_id: str
    _session_file_reference: str = field(repr=False)
    expected_pi_version: str
    branch_leaf_id: str | None
    entry_cursor: str | None
    file_device: int = field(repr=False)
    file_inode: int = field(repr=False)

    def __repr__(self) -> str:
        return "SessionReference(<redacted test-only identity>)"


@dataclass(frozen=True)
class SessionStatus:
    state: SessionState
    pi_session_id: str | None = None
    branch_leaf_id: str | None = None
    entry_cursor: str | None = None


class FakeRpcTransport(Protocol):
    """Injected test seam; no production subprocess/RPC implementation exists."""

    test_only: bool

    def exchange(self, request: dict[str, Any]) -> Iterable[Mapping[str, Any]]: ...


def _safe_token(value: object, *, optional: bool = False) -> bool:
    if value is None:
        return optional
    return isinstance(value, str) and bool(_KEY_RE.fullmatch(value))


def _raise(code: str) -> None:
    raise PiSessionError(code) from None


def _configured_raw_root() -> Path | None:
    if "SAWOPT_DATA_ROOT" not in os.environ:
        return None
    raw = os.environ["SAWOPT_DATA_ROOT"]
    if not raw or not os.path.isabs(raw) or ".." in Path(raw).parts:
        _raise("SESSION_STORE_UNSAFE")
    descriptor: int | None = None
    try:
        configured = Path(raw).resolve(strict=True)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(configured, flags)
        info = os.fstat(descriptor)
        linked = os.stat(configured, follow_symlinks=False)
        mode = stat.S_IMODE(info.st_mode)
        if (
            not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
            or not (mode & 0o444) or not (mode & 0o111)
            or not os.access(configured, os.R_OK | os.X_OK)
        ):
            _raise("SESSION_STORE_UNSAFE")
        return configured
    except PiSessionError:
        raise
    except (OSError, RuntimeError, ValueError):
        _raise("SESSION_STORE_UNSAFE")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                _raise("SESSION_STORE_UNSAFE")


class SessionReferenceStore:
    """One explicit test-only mapping under a private disposable temp directory."""

    def __init__(self, root: str | os.PathLike[str]):
        self._root = Path(os.fspath(root))

    def __repr__(self) -> str:
        return "SessionReferenceStore(<redacted explicit root>)"

    def _open_root(self) -> int:
        raw = os.fspath(self._root)
        if not raw or not os.path.isabs(raw) or ".." in Path(raw).parts or sys.platform != "linux":
            _raise("SESSION_STORE_UNSAFE")
        candidate = Path(os.path.abspath(raw))
        configured_raw_root = _configured_raw_root()
        if configured_raw_root is not None and candidate.is_relative_to(configured_raw_root):
            _raise("SESSION_STORE_UNSAFE")
        try:
            temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
            if not candidate.is_relative_to(temp_root):
                _raise("SESSION_STORE_UNSAFE")
            pi_root = Path.home() / ".pi"
            if candidate == pi_root or pi_root in candidate.parents:
                _raise("SESSION_STORE_UNSAFE")
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            root_fd = os.open(candidate.anchor, flags)
            try:
                for component in candidate.parts[1:]:
                    child_fd = os.open(component, flags, dir_fd=root_fd)
                    os.close(root_fd)
                    root_fd = child_fd
                info = os.fstat(root_fd)
                if (
                    not stat.S_ISDIR(info.st_mode) or not hasattr(os, "getuid")
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    _raise("SESSION_STORE_UNSAFE")
                return root_fd
            except Exception:
                os.close(root_fd)
                raise
        except PiSessionError:
            raise
        except (OSError, RuntimeError, ValueError):
            _raise("SESSION_STORE_UNSAFE")

    @staticmethod
    def _relative_file(session_file: str | os.PathLike[str], root: Path) -> PurePosixPath:
        raw = os.fspath(session_file)
        if not raw or not os.path.isabs(raw) or ".." in Path(raw).parts or "\\" in raw:
            _raise("SESSION_IDENTITY_MISMATCH")
        candidate = Path(raw)
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            _raise("SESSION_IDENTITY_MISMATCH")
        parts = relative.parts
        if not parts or any(part in ("", ".", "..") for part in parts):
            _raise("SESSION_IDENTITY_MISMATCH")
        return PurePosixPath(*parts)

    @staticmethod
    def _open_session_file(root_fd: int, reference: PurePosixPath) -> tuple[int, os.stat_result]:
        if reference.is_absolute() or not reference.parts or any(part in ("", ".", "..") for part in reference.parts):
            _raise("SESSION_IDENTITY_MISMATCH")
        parent_fd = os.dup(root_fd)
        file_fd: int | None = None
        try:
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            for component in reference.parts[:-1]:
                child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                info = os.fstat(child_fd)
                if (
                    not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    os.close(child_fd)
                    _raise("SESSION_IDENTITY_MISMATCH")
                os.close(parent_fd)
                parent_fd = child_fd
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            file_fd = os.open(reference.parts[-1], flags, dir_fd=parent_fd)
            info = os.fstat(file_fd)
            linked = os.stat(reference.parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or stat.S_ISLNK(linked.st_mode)
                or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
            ):
                _raise("SESSION_IDENTITY_MISMATCH")
            result_fd, file_fd = file_fd, None
            return result_fd, info
        except PiSessionError:
            raise
        except FileNotFoundError:
            _raise("SESSION_MISSING")
        except (OSError, ValueError):
            _raise("SESSION_IDENTITY_MISMATCH")
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(parent_fd)

    def register(
        self,
        *,
        local_association_key: str,
        pi_session_id: str,
        session_file: str | os.PathLike[str],
        expected_pi_version: str,
        branch_leaf_id: str | None = None,
        entry_cursor: str | None = None,
    ) -> SessionReference:
        if (
            not _safe_token(local_association_key) or not _safe_token(pi_session_id)
            or local_association_key == pi_session_id or not _safe_token(expected_pi_version)
            or not _safe_token(branch_leaf_id, optional=True) or not _safe_token(entry_cursor, optional=True)
        ):
            _raise("SESSION_IDENTITY_MISMATCH")
        root_fd = self._open_root()
        file_fd: int | None = None
        try:
            relative = self._relative_file(session_file, self._root)
            file_fd, file_info = self._open_session_file(root_fd, relative)
            identity = SessionReference(
                local_association_key=local_association_key,
                pi_session_id=pi_session_id,
                _session_file_reference=relative.as_posix(),
                expected_pi_version=expected_pi_version,
                branch_leaf_id=branch_leaf_id,
                entry_cursor=entry_cursor,
                file_device=file_info.st_dev,
                file_inode=file_info.st_ino,
            )
            encoded = json.dumps({
                "schema_version": _SCHEMA_VERSION,
                "local_association_key": identity.local_association_key,
                "pi_session_id": identity.pi_session_id,
                "session_file_reference": identity._session_file_reference,
                "expected_pi_version": identity.expected_pi_version,
                "branch_leaf_id": identity.branch_leaf_id,
                "entry_cursor": identity.entry_cursor,
                "file_device": identity.file_device,
                "file_inode": identity.file_inode,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                metadata_fd = os.open(_METADATA_NAME, flags, 0o600, dir_fd=root_fd)
            except FileExistsError:
                _raise("SESSION_REFERENCE_EXISTS")
            try:
                os.fchmod(metadata_fd, 0o600)
                remaining = memoryview(encoded)
                while remaining:
                    written = os.write(metadata_fd, remaining)
                    if written <= 0:
                        _raise("SESSION_STORE_UNSAFE")
                    remaining = remaining[written:]
                os.fsync(metadata_fd)
            finally:
                os.close(metadata_fd)
            os.fsync(root_fd)
            return identity
        except PiSessionError:
            raise
        except (OSError, TypeError, ValueError):
            _raise("SESSION_STORE_UNSAFE")
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(root_fd)

    def load(self) -> SessionReference:
        root_fd = self._open_root()
        metadata_fd: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            try:
                metadata_fd = os.open(_METADATA_NAME, flags, dir_fd=root_fd)
            except FileNotFoundError:
                _raise("SESSION_MISSING")
            info = os.fstat(metadata_fd)
            linked = os.stat(_METADATA_NAME, dir_fd=root_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or stat.S_ISLNK(linked.st_mode)
                or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
                or info.st_size > _MAX_METADATA_BYTES
            ):
                _raise("SESSION_IDENTITY_MISMATCH")
            raw = os.read(metadata_fd, _MAX_METADATA_BYTES + 1)
            if len(raw) > _MAX_METADATA_BYTES:
                _raise("SESSION_IDENTITY_MISMATCH")
            document = json.loads(raw.decode("utf-8"))
            if not isinstance(document, dict) or set(document) != _IDENTITY_FIELDS:
                _raise("SESSION_IDENTITY_MISMATCH")
            if type(document["schema_version"]) is not int or document["schema_version"] != _SCHEMA_VERSION:
                _raise("SESSION_IDENTITY_MISMATCH")
            relative = document["session_file_reference"]
            if (
                not isinstance(relative, str) or "\\" in relative or PurePosixPath(relative).is_absolute()
                or any(part in ("", ".", "..") for part in PurePosixPath(relative).parts)
            ):
                _raise("SESSION_IDENTITY_MISMATCH")
            if (
                not _safe_token(document["local_association_key"])
                or not _safe_token(document["pi_session_id"])
                or document["local_association_key"] == document["pi_session_id"]
                or not _safe_token(document["expected_pi_version"])
                or not _safe_token(document["branch_leaf_id"], optional=True)
                or not _safe_token(document["entry_cursor"], optional=True)
                or not isinstance(document["file_device"], int)
                or isinstance(document["file_device"], bool)
                or not isinstance(document["file_inode"], int)
                or isinstance(document["file_inode"], bool)
            ):
                _raise("SESSION_IDENTITY_MISMATCH")
            expected = (document["file_device"], document["file_inode"])
            session_fd, session_info = self._open_session_file(root_fd, PurePosixPath(relative))
            os.close(session_fd)
            if expected != (session_info.st_dev, session_info.st_ino):
                _raise("SESSION_IDENTITY_MISMATCH")
            return SessionReference(
                local_association_key=document["local_association_key"],
                pi_session_id=document["pi_session_id"],
                _session_file_reference=relative,
                expected_pi_version=document["expected_pi_version"],
                branch_leaf_id=document["branch_leaf_id"],
                entry_cursor=document["entry_cursor"],
                file_device=document["file_device"],
                file_inode=document["file_inode"],
            )
        except PiSessionError:
            raise
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
            _raise("SESSION_IDENTITY_MISMATCH")
        finally:
            if metadata_fd is not None:
                os.close(metadata_fd)
            os.close(root_fd)

    def _session_file_path(self, reference: SessionReference) -> Path:
        return self._root / PurePosixPath(reference._session_file_reference)


class _RpcClient:
    def __init__(self, transport: FakeRpcTransport, session_id: str):
        self.transport = transport
        self.session_id = session_id
        self.next_request_id = 1
        self.last_event_sequence = 0
        self.agent_settled = False

    def request(self, command: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        request_id = self.next_request_id
        self.next_request_id += 1
        request = {
            "type": "request", "id": request_id, "command": command, "params": dict(params or {}),
        }
        try:
            messages = iter(self.transport.exchange(request))
            response: Mapping[str, Any] | None = None
            for message in messages:
                if not isinstance(message, Mapping):
                    _raise("RPC_PROTOCOL_INVALID")
                message_type = message.get("type")
                if message_type == "event":
                    self._event(message)
                    continue
                if message_type != "response":
                    _raise("RPC_PROTOCOL_INVALID")
                response_id = message.get("id")
                if isinstance(response_id, bool) or not isinstance(response_id, int) or response_id != request_id:
                    _raise("RPC_RESPONSE_ID_MISMATCH")
                if response is not None:
                    _raise("RPC_PROTOCOL_INVALID")
                response = message
        except PiSessionError:
            raise
        except Exception:
            _raise("RPC_DISCONNECTED")
        if response is None:
            _raise("RPC_DISCONNECTED")
        if response.get("success") is not True:
            error = response.get("error")
            remote_code = error.get("code") if isinstance(error, Mapping) else None
            if remote_code in ("SESSION_MISSING", "SESSION_IDENTITY_MISMATCH"):
                _raise(str(remote_code))
            _raise("RPC_REJECTED")
        data = response.get("data")
        if not isinstance(data, Mapping):
            _raise("RPC_PROTOCOL_INVALID")
        return data

    def _event(self, event: Mapping[str, Any]) -> None:
        sequence = event.get("seq")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence != self.last_event_sequence + 1:
            _raise("RPC_EVENT_ORDER_INVALID")
        if not isinstance(event.get("event"), str) or not isinstance(event.get("data"), Mapping):
            _raise("RPC_PROTOCOL_INVALID")
        self.last_event_sequence = sequence
        if (
            event["event"] == "agent_settled"
            and event["data"].get("sessionId") == self.session_id
        ):
            self.agent_settled = True


def _status_for_error(error: PiSessionError) -> SessionStatus | None:
    try:
        state = SessionState(error.code)
    except ValueError:
        if error.code == "RPC_DISCONNECTED":
            state = SessionState.DISCONNECTED
        else:
            return None
    return SessionStatus(state)


class PiSessionAdapter:
    """Explicit exact-session status/attach boundary using only an injected fake."""

    def __init__(self, store: SessionReferenceStore, transport: FakeRpcTransport):
        if getattr(transport, "test_only", False) is not True:
            _raise("FAKE_TRANSPORT_REQUIRED")
        self.store = store
        self.transport = transport

    def status(self) -> SessionStatus:
        try:
            reference = self.store.load()
            client = _RpcClient(self.transport, reference.pi_session_id)
            state = client.request("get_state")
            return self._verify_state(reference, state, client)
        except PiSessionError as error:
            status = _status_for_error(error)
            if status is not None:
                return status
            raise

    def attach_exact(self) -> SessionStatus:
        try:
            reference = self.store.load()
            session_file = self.store._session_file_path(reference)
            client = _RpcClient(self.transport, reference.pi_session_id)
            selected = client.request("switch_session", {"sessionFile": str(session_file)})
            if selected.get("sessionId") != reference.pi_session_id:
                return SessionStatus(SessionState.SESSION_IDENTITY_MISMATCH)
            state = client.request("get_state")
            return self._verify_state(reference, state, client)
        except PiSessionError as error:
            status = _status_for_error(error)
            if status is not None:
                return status
            raise

    def _verify_state(
        self,
        reference: SessionReference,
        state: Mapping[str, Any],
        client: _RpcClient,
    ) -> SessionStatus:
        if state.get("sessionId") is None:
            return SessionStatus(SessionState.SESSION_MISSING)
        if (
            state.get("sessionId") != reference.pi_session_id
            or state.get("sessionFile") != str(self.store._session_file_path(reference))
            or state.get("piVersion") != reference.expected_pi_version
        ):
            return SessionStatus(SessionState.SESSION_IDENTITY_MISMATCH)
        if (
            reference.branch_leaf_id is not None
            and state.get("branchLeafId") != reference.branch_leaf_id
        ):
            return SessionStatus(SessionState.SESSION_CURSOR_UNKNOWN)
        if reference.branch_leaf_id is not None or reference.entry_cursor is not None:
            entries = client.request("get_entries", {
                "sessionId": reference.pi_session_id,
                "entryId": reference.entry_cursor,
            })
            entry_ids = entries.get("entryIds")
            if not isinstance(entry_ids, list) or any(not isinstance(value, str) for value in entry_ids):
                _raise("SESSION_CURSOR_UNKNOWN")
            if reference.branch_leaf_id is not None and entries.get("branchLeafId") != reference.branch_leaf_id:
                return SessionStatus(SessionState.SESSION_CURSOR_UNKNOWN)
            if reference.entry_cursor is not None and reference.entry_cursor not in entry_ids:
                return SessionStatus(SessionState.SESSION_CURSOR_UNKNOWN)
        if state.get("agentState") not in ("idle", "streaming"):
            return SessionStatus(SessionState.SESSION_IDENTITY_MISMATCH)
        if state.get("agentState") == "streaming":
            result_state = SessionState.PROMPT_PENDING
        elif client.agent_settled:
            result_state = SessionState.SETTLED
        else:
            result_state = SessionState.ATTACHED
        return SessionStatus(
            result_state,
            pi_session_id=reference.pi_session_id,
            branch_leaf_id=reference.branch_leaf_id,
            entry_cursor=reference.entry_cursor,
        )


def classify_dispatch_outcome(
    *,
    acknowledged: bool,
    agent_settled: bool = False,
    connected: bool = True,
    client_restarted: bool = False,
) -> SessionState:
    """Classify a fake/observed dispatch outcome; this function never dispatches."""
    if any(type(value) is not bool for value in (acknowledged, agent_settled, connected, client_restarted)):
        _raise("RPC_PROTOCOL_INVALID")
    if not acknowledged or not connected or client_restarted:
        return SessionState.DISPATCH_AMBIGUOUS
    if agent_settled:
        return SessionState.SETTLED
    return SessionState.PROMPT_PENDING


__all__ = [
    "FakeRpcTransport", "PiSessionAdapter", "PiSessionError", "SessionReference",
    "SessionReferenceStore", "SessionState", "SessionStatus", "classify_dispatch_outcome",
]
