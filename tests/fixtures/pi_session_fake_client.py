"""Test-owned fake Pi-session client used only to verify process restart."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sawopt.pi_session import PiSessionAdapter, PiSessionError, SessionReferenceStore


class FakeTransport:
    test_only = True

    def __init__(self, store: SessionReferenceStore):
        self.store = store
        self.reference = store.load()

    def exchange(self, request):
        reference = self.reference
        session_file = self.store._session_file_path(reference)
        command = request["command"]
        if command == "switch_session":
            if request["params"].get("sessionFile") != str(session_file):
                raise RuntimeError("fake exact-session reference mismatch")
            data = {"sessionId": reference.pi_session_id}
        elif command == "get_state":
            data = {
                "sessionId": reference.pi_session_id,
                "sessionFile": str(session_file),
                "piVersion": reference.expected_pi_version,
                "branchLeafId": reference.branch_leaf_id,
                "agentState": "idle",
            }
        elif command == "get_entries":
            data = {
                "entryIds": [reference.entry_cursor, reference.branch_leaf_id],
                "branchLeafId": reference.branch_leaf_id,
            }
        else:
            raise AssertionError("unexpected fake RPC command")
        return [{"type": "response", "id": request["id"], "success": True, "data": data}]


def main() -> int:
    try:
        store = SessionReferenceStore(Path(sys.argv[1]))
        status = PiSessionAdapter(store, FakeTransport(store)).attach_exact()
        print(json.dumps({
            "state": status.state.value,
            "session_id": status.pi_session_id,
            "branch_leaf_id": status.branch_leaf_id,
            "entry_cursor": status.entry_cursor,
        }, sort_keys=True))
        return 0
    except PiSessionError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
