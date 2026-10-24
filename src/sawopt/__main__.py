"""Legacy review-export entry point; scientific CLI commands are retired."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != "export-review":
        parser = argparse.ArgumentParser(
            description="Export saved legacy run evidence for review",
        )
        parser.add_argument("command", choices=["export-review"])
        parser.parse_args(arguments)

    from .reporting.github_review import main as export_review_main

    return int(export_review_main(arguments[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
