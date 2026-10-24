import argparse
import json
from pathlib import Path
from unittest import mock

import pytest

from sawopt.io import config
from sawopt.orchestration import active_runs, cli, run_manager


def test_parser_keeps_only_recorded_status_and_publication_commands():
    parser = cli.build_parser()
    actions = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
    assert len(actions) == 1
    assert set(actions[0].choices) == {"status", "mark-review-published"}


def test_status_remains_an_observational_command(capsys):
    with mock.patch.object(cli, "format_status", return_value="recorded status") as format_mock:
        assert cli.main(["status", "fixture-run"]) == 0
    format_mock.assert_called_once_with(cli.resolve_run_dir("fixture-run"))
    assert capsys.readouterr().out.strip() == "recorded status"


def test_review_publication_command_remains_available(capsys, tmp_path):
    expected = {
        "state": "REVIEW_WAITING",
        "review_evidence_state": "PUBLISHED",
        "review_output_dir": "reports/fixture/run-1",
        "review_publication_branch": "review-branch",
        "review_publication_commit": "a" * 40,
        "review_published_at": "2026-10-24T00:00:00+00:00",
    }
    with mock.patch.object(cli, "mark_review_published", return_value=expected) as publish_mock:
        assert cli.main([
            "mark-review-published", "--run-dir", str(tmp_path / "run"),
            "--review-path", expected["review_output_dir"],
            "--branch", expected["review_publication_branch"],
            "--commit", expected["review_publication_commit"],
        ]) == 0
    publish_mock.assert_called_once()
    assert json.loads(capsys.readouterr().out) == {
        key: expected[key] for key in (
            "state", "review_evidence_state", "review_output_dir",
            "review_publication_branch", "review_publication_commit", "review_published_at",
        )
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["launch", "--config", "missing.yaml", "--run-dir", "retired-run"],
        ["launch", "--config", "missing.yaml", "--run-dir", "retired-run", "--resume"],
        ["recover", "retired-run"],
        ["worker", "--run-dir", "retired-run"],
    ],
)
def test_retired_execution_commands_reject_before_config_io_or_side_effects(
    argv, tmp_path,
):
    run_dir = tmp_path / "retired-run"
    argv = [str(run_dir) if value == "retired-run" else value for value in argv]
    with mock.patch.object(config, "load_experiment_config") as load_config, \
            mock.patch.object(active_runs, "register_active_run") as register_run, \
            mock.patch("subprocess.Popen") as popen, \
            mock.patch.object(Path, "read_text", side_effect=AssertionError("unexpected file read")):
        with pytest.raises(SystemExit) as error:
            cli.main(argv)
    assert error.value.code == 2
    load_config.assert_not_called()
    register_run.assert_not_called()
    popen.assert_not_called()
    assert not run_dir.exists()
