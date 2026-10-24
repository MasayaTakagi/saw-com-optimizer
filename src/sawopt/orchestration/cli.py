"""Read-only status and guarded publication for historical orchestration runs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .run_manager import format_status, mark_review_published


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_run_dir(value: str, root: Path | None = None) -> Path:
    root = (root or project_root()).resolve()
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    if len(candidate.parts) == 1:
        return (root / "runs" / candidate).resolve()
    return (root / candidate).resolve()


def status(args: argparse.Namespace) -> int:
    print(format_status(resolve_run_dir(args.run_id)))
    return 0


def mark_published(args: argparse.Namespace) -> int:
    result = mark_review_published(
        resolve_run_dir(args.run_dir), review_path=args.review_path,
        branch=args.branch, commit=args.commit,
    )
    print(json.dumps({
        "state": result["state"],
        "review_evidence_state": result["review_evidence_state"],
        "review_output_dir": result["review_output_dir"],
        "review_publication_branch": result["review_publication_branch"],
        "review_publication_commit": result["review_publication_commit"],
        "review_published_at": result["review_published_at"],
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read historical run status or finalize validated review publication",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="display recorded run status")
    status_parser.add_argument("run_id")
    status_parser.set_defaults(handler=status)

    published_parser = subparsers.add_parser(
        "mark-review-published", help="record validated review publication",
    )
    published_parser.add_argument("--run-dir", required=True)
    published_parser.add_argument("--review-path", required=True)
    published_parser.add_argument("--branch", required=True)
    published_parser.add_argument("--commit", required=True)
    published_parser.set_defaults(handler=mark_published)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(arguments)
    return int(args.handler(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"orchestration error: {exc}", file=sys.stderr)
        raise SystemExit(1)
