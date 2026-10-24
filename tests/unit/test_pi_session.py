from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from sawopt.pi_session import (
    PiSessionAdapter,
    PiSessionError,
    SessionReferenceStore,
    SessionState,
    classify_dispatch_outcome,
)

SESSION_ID = "fake-session-84"
PI_VERSION = "1.4.0"
BRANCH_LEAF = "leaf-b"
ENTRY_CURSOR = "entry-a"


class FakeTransport:
    """Test-owned deterministic fake; it never starts Pi or reads session data."""

    test_only = True

    def __init__(
        self,
        session_file: Path,
        *,
        session_id: str = SESSION_ID,
        switch_session_id: str | None = None,
        version: str = PI_VERSION,
        remote_session_file: str | None = None,
        state_overrides: dict[str, Any] | None = None,
        entries_overrides: dict[str, Any] | None = None,
        branch_leaf: str = BRANCH_LEAF,
        entries_branch_leaf: str | None = None,
        entry_ids: list[str] | None = None,
        agent_state: str = "idle",
        events: list[dict[str, Any]] | None = None,
        wrong_response_id: bool = False,
        timeout_command: str | None = None,
        duplicate_response: bool = False,
    ):
        self.session_file = session_file
        self.session_id = session_id
        self.switch_session_id = switch_session_id if switch_session_id is not None else session_id
        self.version = version
        self.state_overrides = state_overrides or {}
        self.entries_overrides = entries_overrides or {}
        self.remote_session_file = remote_session_file if remote_session_file is not None else str(session_file)
        self.branch_leaf = branch_leaf
        self.entries_branch_leaf = entries_branch_leaf if entries_branch_leaf is not None else branch_leaf
        self.entry_ids = entry_ids if entry_ids is not None else [ENTRY_CURSOR, BRANCH_LEAF]
        self.agent_state = agent_state
        self.events = events or []
        self._events_delivered = False
        self.wrong_response_id = wrong_response_id
        self.timeout_command = timeout_command
        self.duplicate_response = duplicate_response
        self.requests: list[dict[str, Any]] = []

    def exchange(self, request: dict[str, Any]):
        self.requests.append(request)
        command = request["command"]
        if command == self.timeout_command:
            raise TimeoutError("fake timeout must not leak")
        if command == "switch_session":
            params = request["params"]
            if params.get("sessionFile") != str(self.session_file):
                raise RuntimeError("fake exact-session reference mismatch")
            data = {"sessionId": self.switch_session_id}
        elif command == "get_state":
            data = {
                "sessionId": self.session_id,
                "sessionFile": self.remote_session_file,
                "piVersion": self.version,
                "branchLeafId": self.branch_leaf,
                "agentState": self.agent_state,
            }
            data.update(self.state_overrides)
        elif command == "get_entries":
            data = {"entryIds": list(self.entry_ids), "branchLeafId": self.entries_branch_leaf}
            data.update(self.entries_overrides)
        else:
            raise AssertionError(f"unexpected fake RPC command: {command}")
        response_id = request["id"] + int(self.wrong_response_id)
        messages = [] if self._events_delivered else list(self.events)
        self._events_delivered = True
        response = {"type": "response", "id": response_id, "success": True, "data": data}
        messages.append(response)
        if self.duplicate_response:
            messages.append(response)
        return messages


def _fixture(tmp_path: Path, **transport_options):
    root = tmp_path / "private-session-test"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    session_file = root / "session.jsonl"
    session_file.write_text('{"synthetic":"fixture only"}\n', encoding="utf-8")
    os.chmod(session_file, 0o600)
    store = SessionReferenceStore(root)
    reference = store.register(
        local_association_key="review-task-84",
        pi_session_id=SESSION_ID,
        session_file=session_file,
        expected_pi_version=PI_VERSION,
        branch_leaf_id=BRANCH_LEAF,
        entry_cursor=ENTRY_CURSOR,
    )
    transport = FakeTransport(session_file, **transport_options)
    return root, session_file, store, reference, transport


def test_private_reference_and_exact_attach_are_observational_and_redacted(tmp_path):
    root, session_file, store, reference, transport = _fixture(tmp_path)
    root_is_private = (root.stat().st_mode & 0o777) == 0o700
    metadata_file = root / "session-reference.json"
    metadata_is_private = (metadata_file.stat().st_mode & 0o777) == 0o600
    assert root_is_private and metadata_is_private
    metadata_text = metadata_file.read_text(encoding="utf-8")
    metadata_path_is_redacted = str(root) not in metadata_text and str(session_file) not in metadata_text
    assert metadata_path_is_redacted
    path_is_redacted = str(session_file) not in repr(reference)
    assert path_is_redacted
    public_path_absent = not hasattr(reference, "session_file_reference")
    assert public_path_absent
    before_files = sorted(item.name for item in root.iterdir())

    attached = PiSessionAdapter(store, transport).attach_exact()

    assert attached.state is SessionState.ATTACHED
    assert attached.pi_session_id == SESSION_ID
    assert attached.branch_leaf_id == BRANCH_LEAF
    assert attached.entry_cursor == ENTRY_CURSOR
    path_is_redacted = str(session_file) not in repr(attached)
    assert path_is_redacted
    assert [request["command"] for request in transport.requests] == [
        "switch_session", "get_state", "get_entries",
    ]
    assert [request["id"] for request in transport.requests] == [1, 2, 3]
    selected_exact_file = transport.requests[0]["params"] == {"sessionFile": str(session_file)}
    assert selected_exact_file
    assert all(request["command"] != "prompt" for request in transport.requests)
    assert session_file.read_text(encoding="utf-8") == '{"synthetic":"fixture only"}\n'
    after_files = sorted(item.name for item in root.iterdir())
    synthetic_ledger_absent = not any(name.startswith("synthetic-tasks.sqlite3") for name in after_files)
    assert before_files == after_files and synthetic_ledger_absent


def test_status_observes_exact_context_without_switch_or_dispatch(tmp_path):
    _root, _session_file, store, _reference, transport = _fixture(tmp_path)

    status = PiSessionAdapter(store, transport).status()

    assert status.state is SessionState.ATTACHED
    assert [request["command"] for request in transport.requests] == ["get_state", "get_entries"]


def test_agent_settled_event_interleaved_before_correlated_response(tmp_path):
    events = [{
        "type": "event", "seq": 1, "event": "agent_settled", "data": {"sessionId": SESSION_ID},
    }]
    _root, _session_file, store, _reference, transport = _fixture(tmp_path, events=events)

    status = PiSessionAdapter(store, transport).status()

    assert status.state is SessionState.SETTLED


@pytest.mark.parametrize(
    "events",
    [
        [
            {"type": "event", "seq": 1, "event": "agent_settled", "data": {}},
            {"type": "event", "seq": 1, "event": "agent_settled", "data": {}},
        ],
        [
            {"type": "event", "seq": 2, "event": "agent_settled", "data": {}},
            {"type": "event", "seq": 1, "event": "agent_settled", "data": {}},
        ],
    ],
)
def test_duplicate_or_out_of_order_fake_events_fail_closed(tmp_path, events):
    _root, _session_file, store, _reference, transport = _fixture(tmp_path, events=events)

    with pytest.raises(PiSessionError) as error:
        PiSessionAdapter(store, transport).status()

    assert error.value.code == "RPC_EVENT_ORDER_INVALID"


def test_response_id_mismatch_fails_closed_without_disclosing_path(tmp_path):
    _root, session_file, store, _reference, transport = _fixture(tmp_path, wrong_response_id=True)

    with pytest.raises(PiSessionError) as error:
        PiSessionAdapter(store, transport).status()

    assert error.value.code == "RPC_RESPONSE_ID_MISMATCH"
    path_is_redacted = str(session_file) not in str(error.value)
    assert path_is_redacted


def test_fake_rpc_timeout_is_disconnected_and_does_not_leak_transport_error(tmp_path):
    _root, session_file, store, _reference, transport = _fixture(tmp_path, timeout_command="get_state")

    status = PiSessionAdapter(store, transport).status()

    assert status.state is SessionState.DISCONNECTED
    path_is_redacted = str(session_file) not in repr(status)
    assert path_is_redacted


def test_fake_rpc_process_crash_and_missing_response_are_disconnected(tmp_path):
    _root, _session_file, store, _reference, _transport = _fixture(tmp_path)

    class CrashedTransport:
        test_only = True

        def exchange(self, _request):
            raise RuntimeError("fake crash with private path omitted")

    class EmptyTransport:
        test_only = True

        def exchange(self, _request):
            return []

    crashed = PiSessionAdapter(store, CrashedTransport()).status()
    missing_response = PiSessionAdapter(store, EmptyTransport()).status()

    assert crashed.state is SessionState.DISCONNECTED
    assert missing_response.state is SessionState.DISCONNECTED


@pytest.mark.parametrize(
    ("options", "expected_state"),
    [
        ({"session_id": "another-session"}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"version": "9.9.9"}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"remote_session_file": "/different/test/session.jsonl"}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"branch_leaf": "different-leaf"}, SessionState.SESSION_CURSOR_UNKNOWN),
        ({"entry_ids": ["other-entry", BRANCH_LEAF]}, SessionState.SESSION_CURSOR_UNKNOWN),
        ({"entries_branch_leaf": "other-leaf"}, SessionState.SESSION_CURSOR_UNKNOWN),
    ],
)
def test_remote_session_version_and_cursor_mismatches_fail_closed(tmp_path, options, expected_state):
    _root, _session_file, store, _reference, transport = _fixture(tmp_path, **options)

    status = PiSessionAdapter(store, transport).status()

    assert status.state is expected_state


def test_non_test_transport_is_rejected_without_invocation(tmp_path):
    _root, _session_file, store, _reference, _transport = _fixture(tmp_path)

    class UnmarkedTransport:
        def exchange(self, _request):
            raise AssertionError("unmarked transport must not be invoked")

    with pytest.raises(PiSessionError) as error:
        PiSessionAdapter(store, UnmarkedTransport())

    assert error.value.code == "FAKE_TRANSPORT_REQUIRED"


@pytest.mark.parametrize(
    ("transport_options", "expected"),
    [
        ({"state_overrides": {"sessionId": None}}, SessionState.SESSION_MISSING),
        ({"state_overrides": {"piVersion": None}}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"state_overrides": {"sessionFile": None}}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"state_overrides": {"branchLeafId": None}}, SessionState.SESSION_CURSOR_UNKNOWN),
        ({"state_overrides": {"agentState": "unknown"}}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"entries_overrides": {"entryIds": None}}, SessionState.SESSION_CURSOR_UNKNOWN),
        ({"switch_session_id": "wrong-session"}, SessionState.SESSION_IDENTITY_MISMATCH),
        ({"agent_state": "streaming"}, SessionState.PROMPT_PENDING),
    ],
)
def test_missing_or_malformed_rpc_identity_fields_fail_closed(tmp_path, transport_options, expected):
    _root, _session_file, store, _reference, transport = _fixture(tmp_path, **transport_options)

    status = PiSessionAdapter(store, transport).attach_exact()

    assert status.state is expected


def test_duplicate_rpc_response_fails_closed(tmp_path):
    _root, _session_file, store, _reference, transport = _fixture(tmp_path, duplicate_response=True)

    with pytest.raises(PiSessionError) as error:
        PiSessionAdapter(store, transport).status()

    assert error.value.code == "RPC_PROTOCOL_INVALID"


def test_settled_event_for_foreign_session_is_not_completion(tmp_path):
    events = [{
        "type": "event", "seq": 1, "event": "agent_settled", "data": {"sessionId": "foreign"},
    }]
    _root, _session_file, store, _reference, transport = _fixture(tmp_path, events=events)

    status = PiSessionAdapter(store, transport).status()

    assert status.state is SessionState.ATTACHED


def test_missing_mapping_or_test_session_is_not_replaced(tmp_path):
    root = tmp_path / "empty-private-root"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    store = SessionReferenceStore(root)

    status = PiSessionAdapter(store, FakeTransport(root / "absent.jsonl")).status()

    assert status.state is SessionState.SESSION_MISSING
    no_reference_written = not (root / "session-reference.json").exists()
    no_replacement_session_written = not (root / "absent.jsonl").exists()
    assert no_reference_written and no_replacement_session_written


def test_missing_local_session_after_registration_is_missing_not_created(tmp_path):
    _root, session_file, store, _reference, transport = _fixture(tmp_path)
    session_file.unlink()

    status = PiSessionAdapter(store, transport).status()

    assert status.state is SessionState.SESSION_MISSING
    assert [request["command"] for request in transport.requests] == []
    missing_file_remains_absent = not session_file.exists()
    assert missing_file_remains_absent


@pytest.mark.parametrize("path_kind", ["outside", "traversal", "symlink"])
def test_registration_rejects_external_traversal_and_symlink_session_files(tmp_path, path_kind):
    root = tmp_path / f"root-{path_kind}"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("not a real session", encoding="utf-8")
    os.chmod(outside, 0o600)
    if path_kind == "outside":
        candidate = outside
    elif path_kind == "traversal":
        candidate = root / ".." / outside.name
    else:
        candidate = root / "linked-session.jsonl"
        candidate.symlink_to(outside)
    store = SessionReferenceStore(root)

    with pytest.raises(PiSessionError) as error:
        store.register(
            local_association_key="local-key",
            pi_session_id=SESSION_ID,
            session_file=candidate,
            expected_pi_version=PI_VERSION,
        )

    assert error.value.code == "SESSION_IDENTITY_MISMATCH"
    path_is_redacted = str(outside) not in str(error.value)
    assert path_is_redacted
    mapping_absent = not (root / "session-reference.json").exists()
    assert mapping_absent


def test_symlinked_private_root_is_rejected_without_writing_metadata(tmp_path):
    real_root = tmp_path / "real-private-root"
    real_root.mkdir(mode=0o700)
    os.chmod(real_root, 0o700)
    alias = tmp_path / "root-alias"
    alias.symlink_to(real_root, target_is_directory=True)
    session_file = real_root / "session.jsonl"
    session_file.write_text("fake only", encoding="utf-8")
    os.chmod(session_file, 0o600)
    store = SessionReferenceStore(alias)

    with pytest.raises(PiSessionError) as error:
        store.register(
            local_association_key="local-key",
            pi_session_id=SESSION_ID,
            session_file=session_file,
            expected_pi_version=PI_VERSION,
        )

    assert error.value.code == "SESSION_STORE_UNSAFE"
    metadata_absent = not (real_root / "session-reference.json").exists()
    assert metadata_absent


def test_test_session_reference_under_pi_home_is_rejected_without_access(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_pi_root = fake_home / ".pi"
    fake_pi_root.mkdir(parents=True, mode=0o700)
    os.chmod(fake_pi_root, 0o700)
    session_file = fake_pi_root / "session.jsonl"
    session_file.write_text("do not read", encoding="utf-8")
    os.chmod(session_file, 0o600)
    monkeypatch.setenv("HOME", str(fake_home))
    store = SessionReferenceStore(fake_pi_root)

    with pytest.raises(PiSessionError) as error:
        store.register(
            local_association_key="local-key",
            pi_session_id=SESSION_ID,
            session_file=session_file,
            expected_pi_version=PI_VERSION,
        )

    assert error.value.code == "SESSION_STORE_UNSAFE"
    metadata_absent = not (fake_pi_root / "session-reference.json").exists()
    assert metadata_absent


@pytest.mark.parametrize("use_symlink_alias", [False, True])
def test_configured_raw_root_and_symlink_alias_are_excluded_before_register_or_load(
    tmp_path, monkeypatch, use_symlink_alias,
):
    raw_root = tmp_path / "protected-raw"
    raw_root.mkdir(mode=0o700)
    os.chmod(raw_root, 0o700)
    sentinel = raw_root / "sentinel.txt"
    sentinel.write_text("synthetic preservation sentinel", encoding="utf-8")
    os.chmod(sentinel, 0o600)
    configured_root = raw_root
    if use_symlink_alias:
        configured_root = tmp_path / "raw-alias"
        configured_root.symlink_to(raw_root, target_is_directory=True)
    session_root = raw_root / "test-session-root"
    session_root.mkdir(mode=0o700)
    os.chmod(session_root, 0o700)
    session_file = session_root / "session.jsonl"
    session_file.write_text("test fixture only", encoding="utf-8")
    os.chmod(session_file, 0o600)
    session_file_identity = session_file.stat()
    monkeypatch.setenv("SAWOPT_DATA_ROOT", str(configured_root))
    store = SessionReferenceStore(session_root)

    outcomes = []
    try:
        store.register(
            local_association_key="local-key",
            pi_session_id=SESSION_ID,
            session_file=session_file,
            expected_pi_version=PI_VERSION,
        )
    except PiSessionError as error:
        outcomes.append(error.code)
    else:
        outcomes.append("ALLOWED")
    try:
        store.load()
    except PiSessionError as error:
        outcomes.append(error.code)
    else:
        outcomes.append("ALLOWED")

    metadata_absent = not (session_root / "session-reference.json").exists()
    assert outcomes == ["SESSION_STORE_UNSAFE", "SESSION_STORE_UNSAFE"]
    assert metadata_absent
    assert sentinel.read_text(encoding="utf-8") == "synthetic preservation sentinel"
    assert session_file.stat() == session_file_identity


@pytest.mark.parametrize("invalid_kind", ["empty", "relative", "missing", "broken-alias", "non-directory", "unreadable"])
def test_invalid_configured_raw_root_fails_closed_before_session_metadata(
    tmp_path, monkeypatch, invalid_kind,
):
    session_root = tmp_path / "separate-private-session"
    session_root.mkdir(mode=0o700)
    os.chmod(session_root, 0o700)
    session_file = session_root / "session.jsonl"
    session_file.write_text("test fixture only", encoding="utf-8")
    os.chmod(session_file, 0o600)
    session_file_identity = session_file.stat()
    restore_mode = None
    if invalid_kind == "empty":
        configured_raw = ""
    elif invalid_kind == "relative":
        configured_raw = "relative/raw-root"
    elif invalid_kind == "missing":
        configured_raw = str(tmp_path / "missing-raw-root")
    elif invalid_kind == "broken-alias":
        broken_target = tmp_path / "missing-target"
        configured_alias = tmp_path / "broken-raw-alias"
        configured_alias.symlink_to(broken_target, target_is_directory=True)
        configured_raw = str(configured_alias)
    elif invalid_kind == "non-directory":
        configured_file = tmp_path / "raw-root-file"
        configured_file.write_text("not a directory", encoding="utf-8")
        configured_raw = str(configured_file)
    else:
        unreadable = tmp_path / "unreadable-raw-root"
        unreadable.mkdir(mode=0o700)
        os.chmod(unreadable, 0o000)
        configured_raw = str(unreadable)
        restore_mode = unreadable
    monkeypatch.setenv("SAWOPT_DATA_ROOT", configured_raw)
    store = SessionReferenceStore(session_root)

    outcomes = []
    try:
        try:
            store.register(
                local_association_key="local-key",
                pi_session_id=SESSION_ID,
                session_file=session_file,
                expected_pi_version=PI_VERSION,
            )
        except PiSessionError as error:
            outcomes.append(error.code)
        else:
            outcomes.append("ALLOWED")
        try:
            store.load()
        except PiSessionError as error:
            outcomes.append(error.code)
        else:
            outcomes.append("ALLOWED")
    finally:
        if restore_mode is not None:
            os.chmod(restore_mode, 0o700)

    metadata_absent = not (session_root / "session-reference.json").exists()
    assert outcomes == ["SESSION_STORE_UNSAFE", "SESSION_STORE_UNSAFE"]
    assert metadata_absent
    assert session_file.stat() == session_file_identity


def test_unrelated_private_session_fixture_still_works_with_configured_raw_root(tmp_path, monkeypatch):
    raw_root = tmp_path / "configured-raw"
    raw_root.mkdir(mode=0o700)
    os.chmod(raw_root, 0o700)
    monkeypatch.setenv("SAWOPT_DATA_ROOT", str(raw_root))

    root, _session_file, store, _reference, transport = _fixture(tmp_path)

    assert root != raw_root and root not in raw_root.parents and raw_root not in root.parents
    assert PiSessionAdapter(store, transport).attach_exact().state is SessionState.ATTACHED


@pytest.mark.parametrize("unsafe_part", ["root", "nested-directory", "session-file"])
def test_insecure_directory_or_session_file_permissions_fail_closed(tmp_path, unsafe_part):
    root = tmp_path / "mode-root"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    if unsafe_part == "root":
        os.chmod(root, 0o750)
        session_file = root / "session.jsonl"
    elif unsafe_part == "nested-directory":
        nested = root / "nested"
        nested.mkdir(mode=0o700)
        os.chmod(nested, 0o750)
        session_file = nested / "session.jsonl"
    else:
        session_file = root / "session.jsonl"
    session_file.write_text("fake only", encoding="utf-8")
    os.chmod(session_file, 0o640 if unsafe_part == "session-file" else 0o600)
    store = SessionReferenceStore(root)

    with pytest.raises(PiSessionError) as error:
        store.register(
            local_association_key="local-key",
            pi_session_id=SESSION_ID,
            session_file=session_file,
            expected_pi_version=PI_VERSION,
        )

    assert error.value.code in {"SESSION_STORE_UNSAFE", "SESSION_IDENTITY_MISMATCH"}
    mapping_absent = not (root / "session-reference.json").exists()
    assert mapping_absent


def test_metadata_symlink_or_permissive_mode_is_rejected(tmp_path):
    _root, _session_file, store, _reference, _transport = _fixture(tmp_path)
    metadata_file = _root / "session-reference.json"
    os.chmod(metadata_file, 0o640)
    with pytest.raises(PiSessionError) as insecure_mode:
        store.load()
    assert insecure_mode.value.code == "SESSION_IDENTITY_MISMATCH"

    os.chmod(metadata_file, 0o600)
    retained_metadata = _root / "retained-metadata.json"
    metadata_file.rename(retained_metadata)
    metadata_file.symlink_to(retained_metadata)
    with pytest.raises(PiSessionError) as symlink:
        store.load()
    assert symlink.value.code == "SESSION_IDENTITY_MISMATCH"


def test_replaced_fixture_file_inode_does_not_resume_same_exact_identity(tmp_path):
    _root, session_file, store, _reference, _transport = _fixture(tmp_path)
    retained_original = session_file.with_name("retained-original.jsonl")
    session_file.rename(retained_original)
    session_file.write_text("replacement fixture", encoding="utf-8")
    os.chmod(session_file, 0o600)

    with pytest.raises(PiSessionError) as error:
        store.load()

    assert error.value.code == "SESSION_IDENTITY_MISMATCH"


def test_boolean_metadata_schema_version_is_rejected(tmp_path):
    root, _session_file, store, _reference, _transport = _fixture(tmp_path)
    metadata_file = root / "session-reference.json"
    document = json.loads(metadata_file.read_text(encoding="utf-8"))
    document["schema_version"] = True
    metadata_file.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(metadata_file, 0o600)

    with pytest.raises(PiSessionError) as error:
        store.load()

    assert error.value.code == "SESSION_IDENTITY_MISMATCH"


def test_corrupt_mapping_with_traversal_is_rejected_without_path_disclosure(tmp_path):
    _root, _session_file, store, _reference, _transport = _fixture(tmp_path)
    metadata_file = _root / "session-reference.json"
    document = json.loads(metadata_file.read_text(encoding="utf-8"))
    document["session_file_reference"] = "../private/session.jsonl"
    metadata_file.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(metadata_file, 0o600)

    with pytest.raises(PiSessionError) as error:
        store.load()

    assert error.value.code == "SESSION_IDENTITY_MISMATCH"
    error_is_redacted = "../private/session.jsonl" not in str(error.value)
    assert error_is_redacted


def test_repeated_attach_uses_only_the_same_reference_and_never_dispatches(tmp_path):
    _root, _session_file, store, _reference, transport = _fixture(tmp_path)
    adapter = PiSessionAdapter(store, transport)

    first = adapter.attach_exact()
    second = adapter.attach_exact()

    assert first.state is second.state is SessionState.ATTACHED
    assert [request["command"] for request in transport.requests] == [
        "switch_session", "get_state", "get_entries",
        "switch_session", "get_state", "get_entries",
    ]
    assert all(request["command"] in {"switch_session", "get_state", "get_entries"} for request in transport.requests)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"acknowledged": True}, SessionState.PROMPT_PENDING),
        ({"acknowledged": False}, SessionState.DISPATCH_AMBIGUOUS),
        ({"acknowledged": True, "connected": False}, SessionState.DISPATCH_AMBIGUOUS),
        ({"acknowledged": True, "client_restarted": True}, SessionState.DISPATCH_AMBIGUOUS),
        ({"acknowledged": True, "connected": False, "agent_settled": True}, SessionState.DISPATCH_AMBIGUOUS),
        ({"acknowledged": True, "client_restarted": True, "agent_settled": True}, SessionState.DISPATCH_AMBIGUOUS),
        ({"acknowledged": True, "agent_settled": True}, SessionState.SETTLED),
        ({"acknowledged": False, "agent_settled": True}, SessionState.DISPATCH_AMBIGUOUS),
    ],
)
def test_dispatch_observation_classifier_requires_ack_settlement_and_live_context(kwargs, expected):
    assert classify_dispatch_outcome(**kwargs) is expected


def test_dispatch_observation_classifier_rejects_non_boolean_flags():
    with pytest.raises(PiSessionError) as error:
        classify_dispatch_outcome(acknowledged="yes")

    assert error.value.code == "RPC_PROTOCOL_INVALID"


def test_new_adapter_instance_reloads_same_exact_mock_session_context(tmp_path):
    root, session_file, store, original, first_transport = _fixture(tmp_path)
    assert PiSessionAdapter(store, first_transport).attach_exact().state is SessionState.ATTACHED
    restarted_transport = FakeTransport(session_file)

    recovered = PiSessionAdapter(SessionReferenceStore(root), restarted_transport).attach_exact()

    assert recovered.state is SessionState.ATTACHED
    assert recovered.pi_session_id == original.pi_session_id == SESSION_ID
    assert recovered.branch_leaf_id == original.branch_leaf_id == BRANCH_LEAF
    assert recovered.entry_cursor == original.entry_cursor == ENTRY_CURSOR


def test_test_owned_client_subprocess_reloads_same_mapping_and_cursor(tmp_path):
    root, _session_file, _store, _reference, _transport = _fixture(tmp_path)
    fixture_client = Path(__file__).parents[1] / "fixtures" / "pi_session_fake_client.py"
    completed = subprocess.run(
        [sys.executable, str(fixture_client), str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        env={**os.environ, "PI_OFFLINE": "1"},
    )

    output = json.loads(completed.stdout)
    assert output == {
        "state": "ATTACHED",
        "session_id": SESSION_ID,
        "branch_leaf_id": BRANCH_LEAF,
        "entry_cursor": ENTRY_CURSOR,
    }
    output_is_redacted = str(root) not in completed.stdout
    error_is_redacted = str(root) not in completed.stderr
    assert output_is_redacted and error_is_redacted


def test_detached_synthetic_task_completes_when_pi_is_unavailable(tmp_path):
    repository_root = Path(__file__).resolve().parents[2]
    root = tmp_path / "synthetic-task-without-pi"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    no_pi_bin = tmp_path / "no-pi-executable"
    no_pi_bin.mkdir(mode=0o700)
    environment = {**os.environ, "PATH": str(no_pi_bin), "PI_OFFLINE": "1"}
    launch = subprocess.run(
        [
            sys.executable, "-m", "sawopt.cli", "synthetic-task", "launch", "--root", str(root),
            "--idempotency-key", "pi-unavailable-test", "--steps", "1", "--interval-ms", "10",
        ],
        cwd=repository_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        env=environment,
    )
    launched = json.loads(launch.stdout)
    assert launched["synthetic_only"] is True
    run_id = launched["run_id"]
    deadline = time.monotonic() + 20
    status = None
    while time.monotonic() < deadline:
        observed = subprocess.run(
            [sys.executable, "-m", "sawopt.cli", "synthetic-task", "status", "--root", str(root), "--run-id", run_id],
            cwd=repository_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            env=environment,
        )
        status = json.loads(observed.stdout)
        if status["state"] in {"COMPLETED", "FAILED", "RECOVERY_REQUIRED"}:
            break
        time.sleep(0.02)

    assert status is not None and status["state"] == "COMPLETED"
    assert status["progress_completed"] == status["progress_total"] == 1


def test_fresh_cli_and_synthetic_worker_import_without_pi_adapter(tmp_path):
    repository_root = Path(__file__).resolve().parents[2]
    no_pi_bin = tmp_path / "no-pi-bin"
    no_pi_bin.mkdir(mode=0o700)
    isolated_home = tmp_path / "no-pi-home"
    isolated_home.mkdir(mode=0o700)
    environment = {**os.environ, "PATH": str(no_pi_bin), "HOME": str(isolated_home), "PI_OFFLINE": "1"}
    completed = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; import sawopt.cli; import sawopt.synthetic_worker; "
            "assert 'sawopt.pi_session' not in sys.modules; "
            "print('synthetic-import-isolated')",
        ],
        cwd=repository_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        env=environment,
    )
    assert completed.stdout.strip() == "synthetic-import-isolated"
    assert completed.stderr == ""
