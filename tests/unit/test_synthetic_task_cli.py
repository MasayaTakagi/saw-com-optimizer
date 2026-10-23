from __future__ import annotations

import json
from pathlib import Path

import sawopt.cli as cli
from sawopt.io.synthetic_task_ledger import SyntheticTaskLedger


def _launch_args(root: Path) -> list[str]:
    return [
        "synthetic-task", "launch", "--root", str(root), "--idempotency-key", "cli-test",
        "--steps", "5", "--interval-ms", "10",
    ]


def test_spawn_return_without_worker_claim_is_ambiguous_and_not_retried(tmp_path, monkeypatch, capsys):
    root = tmp_path / "tasks"
    root.mkdir(mode=0o700)
    spawn_calls = []

    def fake_spawn(argv, **kwargs):
        spawn_calls.append((argv, kwargs))
        return object()  # fault injection: Popen returned, but no worker claims the attempt

    monkeypatch.setattr(cli.subprocess, "Popen", fake_spawn)
    assert cli.main(_launch_args(root)) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["state"] == "LAUNCH_AMBIGUOUS"
    assert first["ledger_state"] == "STARTING"
    argv, kwargs = spawn_calls[0]
    assert argv[1:3] == ["-m", "sawopt.synthetic_worker"]
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True

    assert cli.main(_launch_args(root)) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["run_id"] == first["run_id"]
    assert second["created"] is False
    assert second["state"] == "LAUNCH_AMBIGUOUS"
    assert len(spawn_calls) == 1
    assert SyntheticTaskLedger(root).get_status(first["run_id"]).owner_pid is None


def test_spawn_error_is_persisted_as_launch_ambiguous_without_relaunch(tmp_path, monkeypatch, capsys):
    root = tmp_path / "tasks"
    root.mkdir(mode=0o700)
    spawn_calls = []

    def failed_spawn(*_args, **_kwargs):
        spawn_calls.append(True)
        raise OSError("injected process creation failure")

    monkeypatch.setattr(cli.subprocess, "Popen", failed_spawn)
    assert cli.main(_launch_args(root)) == 2
    failure = json.loads(capsys.readouterr().err)
    assert failure["error"]["code"] == "LAUNCH_AMBIGUOUS"

    assert cli.main(_launch_args(root)) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["state"] == "LAUNCH_AMBIGUOUS"
    assert repeated["created"] is False
    assert len(spawn_calls) == 1
