"""Allowlisted internal worker for bounded synthetic countdown tasks only."""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence

from .io.synthetic_task_ledger import SyntheticTaskError, SyntheticTaskLedger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sawopt-synthetic-worker", add_help=False)
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ledger = SyntheticTaskLedger(args.root)
    claimed = False
    try:
        claimed = ledger.claim_attempt(args.run_id, args.attempt_id)
        if not claimed:
            return 0
        ledger.append_log(f"{args.run_id} claimed synthetic attempt {args.attempt_id}")
        while True:
            task = ledger.get_status(args.run_id)
            if task.state == "STOP_REQUESTED":
                # record_step commits STOPPED at the cooperative boundary.
                delay = task.interval_ms / 1000.0
            elif task.state == "RUNNING":
                delay = task.interval_ms / 1000.0
            else:
                raise SyntheticTaskError(
                    "RECOVERY_REQUIRED", f"worker observed fail-closed state {task.state}",
                )
            time.sleep(delay)
            state, progress = ledger.record_step(args.run_id, args.attempt_id)
            ledger.append_log(f"{args.run_id} synthetic progress {progress}/{task.progress_total}: {state}")
            if state in ("STOPPED", "COMPLETED"):
                return 0
    except Exception as exc:
        if claimed:
            try:
                code = exc.code if isinstance(exc, SyntheticTaskError) else "WORKER_FAILED"
                ledger.fail_attempt(args.run_id, args.attempt_id, code, str(exc))
            except Exception:
                pass
        try:
            ledger.append_log(f"{args.run_id} synthetic worker error: {type(exc).__name__}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
