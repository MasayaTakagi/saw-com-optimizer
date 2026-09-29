import json
import sys

import pytest

from sawopt import __main__ as cli
from sawopt.io.checkpoints import CheckpointStore


def test_run_study_dispatch_preserves_explicit_review_waiting(tmp_path, monkeypatch):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    store = CheckpointStore(tmp_path / "checkpoints", run_directory=tmp_path)
    store.write(lambda path: path.write_text('{"value":1}', encoding="utf-8"))
    store.write(lambda path: path.write_text('{"value":2}', encoding="utf-8"))
    (metadata / "run_completion.json").write_text(json.dumps({
        "status": "REVIEW_WAITING", "disposition": "REVIEW_WAITING",
    }), encoding="utf-8")
    monkeypatch.setattr(cli, "_run_study", lambda *args, **kwargs: {"status": "COMPLETE"})
    monkeypatch.setattr(sys, "argv", [
        "sawopt", "run-study", "--config", "unused.yaml", "--run", str(tmp_path),
    ])

    cli.main()

    completion = json.loads((metadata / "run_completion.json").read_text(encoding="utf-8"))
    assert completion["disposition"] == "REVIEW_WAITING"
    assert store.latest_path.is_file()
    assert store.previous_path.is_file()
    assert not store.final_path.exists()


@pytest.mark.parametrize("study_type", ["dms_topology_screening", "hybrid_topology_screening"])
def test_run_study_dispatches_by_study_type(tmp_path, monkeypatch, study_type):
    from sawopt.io.config import load_experiment_config

    monkeypatch.setattr(cli, "load_experiment_config", lambda _path: {"study": {"type": study_type}})
    calls = []

    def run(_config, run_dir, *, resume):
        calls.append((str(run_dir), resume))
        return {"status": "REVIEW_WAITING"}

    if study_type == "dms_topology_screening":
        from sawopt.studies import dms_topology_screening
        monkeypatch.setattr(dms_topology_screening, "run_dms_topology_screening", run)
    else:
        from sawopt.studies import hybrid_comparison
        monkeypatch.setattr(hybrid_comparison, "run_hybrid_topology_screening", run)

    assert cli._run_study("fixture.yaml", tmp_path, resume=True) == {"status": "REVIEW_WAITING"}
    assert calls == [(str(tmp_path), True)]


def test_run_study_rejects_unknown_study_type(monkeypatch):
    monkeypatch.setattr(cli, "load_experiment_config", lambda _path: {"study": {"type": "unknown"}})
    with pytest.raises(ValueError, match="Unknown study.type 'unknown'"):
        cli._run_study("fixture.yaml", "run")
