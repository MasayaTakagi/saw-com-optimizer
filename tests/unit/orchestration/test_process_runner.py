import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sawopt.orchestration.process_runner import build_worker_command, launch_detached


class ProcessRunnerTests(unittest.TestCase):
    def test_worker_command_is_explicit(self):
        command = build_worker_command(Path("run"), python_executable="python-test")
        self.assertEqual(command[:4], ["python-test", "-m", "sawopt.orchestration.cli", "worker"])
        self.assertNotIn("--last", command)

    def test_detached_probe_completes_after_launcher_returns(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "marker.txt"
            command = [
                sys.executable,
                "-c",
                (
                    "import pathlib, sys, time; time.sleep(.25); "
                    "pathlib.Path(sys.argv[1]).write_text('done', encoding='utf-8')"
                ),
                str(marker),
            ]
            pid = launch_detached(root / "run", project_root=root, command=command)
            self.assertGreater(pid, 0)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not marker.exists():
                time.sleep(.05)
            self.assertEqual(marker.read_text(encoding="utf-8"), "done")
            # The marker is written immediately before process exit; give the
            # detached process time to close inherited log handles on Windows.
            time.sleep(.25)


if __name__ == "__main__":
    unittest.main()
