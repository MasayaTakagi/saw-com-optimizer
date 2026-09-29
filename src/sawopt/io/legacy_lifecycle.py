"""Compatibility adapter for historical marker-based run lifecycle signals.

New study entry points should supply :class:`RunDisposition` directly. This
adapter translates only the historical markers previously consulted by the
checkpoint lifecycle core.
"""
from __future__ import annotations

import json
from pathlib import Path

from .lifecycle import RunDisposition


LEGACY_REVIEW_WAITING_MARKERS = (
    "PHASE_C_SUPPLEMENT_COMPLETE_WAITING_FOR_REVIEW.txt",
    "PHASE_C_FINAL_CONFIRMATION_COMPLETE_WAITING_FOR_REVIEW.txt",
    "STAGE3_6_GATE2B_A_COMPLETE_WAITING_FOR_REVIEW.txt",
    # Historical core behavior treated this stop marker as review waiting.
    "STAGE3_6_GATE2B_B_COMPLETE_STOP.txt",
)


def legacy_process_disposition(
    run_directory: str | Path, *, return_code: int | None,
) -> RunDisposition:
    """Translate a legacy process result and its historical markers.

    A clean return establishes execution completion, independent of a study's
    scientific gate result. The historical review markers override that state.
    A missing or failed process return maps to FAILED; callers that have no
    lifecycle evidence should use UNKNOWN explicitly instead.
    """
    if return_code is None or int(return_code) != 0:
        return RunDisposition.FAILED
    root = Path(run_directory)
    if any((root / marker).is_file() for marker in LEGACY_REVIEW_WAITING_MARKERS):
        return RunDisposition.REVIEW_WAITING
    return RunDisposition.COMPLETED


def resolve_process_disposition(
    run_directory: str | Path, *, return_code: int | None,
) -> RunDisposition:
    """Resolve current explicit study state before the legacy marker fallback.

    A failed child process always remains a lifecycle failure. On a clean exit,
    a well-formed explicit completion record is authoritative. An unreadable or
    unknown explicit record fails safe to ``REVIEW_WAITING`` so a missing
    interpretation cannot trigger checkpoint finalization. Only runs without
    an explicit record use the historical marker adapter.
    """
    if return_code is None or int(return_code) != 0:
        return RunDisposition.FAILED

    marker = Path(run_directory) / "metadata" / "run_completion.json"
    if marker.exists():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("completion marker must be an object")
            raw = value.get("disposition", value.get("status"))
            disposition = RunDisposition(str(raw))
            if disposition is RunDisposition.UNKNOWN:
                return RunDisposition.REVIEW_WAITING
            return disposition
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return RunDisposition.REVIEW_WAITING

    return legacy_process_disposition(run_directory, return_code=return_code)


__all__ = [
    "LEGACY_REVIEW_WAITING_MARKERS", "legacy_process_disposition",
    "resolve_process_disposition",
]
