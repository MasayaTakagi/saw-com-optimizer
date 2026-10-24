from pathlib import Path
from unittest import mock

import pytest

from sawopt import __main__ as legacy_cli
from sawopt.io import config
from sawopt.orchestration import active_runs, run_manager


@pytest.mark.parametrize(
    "command",
    ["simulate", "optimize", "sweep", "report", "run-study", "stage4b-shakedown"],
)
def test_retired_legacy_commands_are_unavailable_without_run_output(command, tmp_path):
    output = tmp_path / "must-not-be-created"
    with mock.patch.object(config, "load_experiment_config") as load_config, \
            mock.patch.object(active_runs, "register_active_run") as register_run, \
            mock.patch("subprocess.Popen") as popen, \
            mock.patch.object(Path, "read_text", side_effect=AssertionError("unexpected file read")):
        with pytest.raises(SystemExit) as error:
            legacy_cli.main([
                command, "--config", str(tmp_path / "missing.yaml"), "--run", str(output),
            ])
    assert error.value.code == 2
    load_config.assert_not_called()
    register_run.assert_not_called()
    popen.assert_not_called()
    assert not output.exists()
