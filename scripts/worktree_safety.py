"""CLI entry point for the fail-closed Git worktree safety tool."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sawopt.orchestration.worktree_safety import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
