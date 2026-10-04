"""Tiny non-scientific lifecycle fixture for queue-to-GitHub E2E qualification."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def run_qualification_fixture(config_path: str | Path, run_directory: str | Path) -> dict:
    """Write one explicitly ranking-ineligible synthetic cell and return immediately."""
    config = Path(config_path).resolve()
    run = Path(run_directory).resolve()
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    study = payload.get("study", {})
    if study.get("type") != "postrun_workflow_qualification":
        raise ValueError("qualification fixture config has an unexpected study type")
    if study.get("comparison_arms") != ["fixture"] or study.get("seeds") != ["qualification"]:
        raise ValueError("qualification fixture only accepts its single declared non-scientific cell")

    metadata = run / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "config_snapshot.yaml").write_bytes(config.read_bytes())
    _write_json(metadata / "protocol_snapshot.json", {
        "study_type": "postrun_workflow_qualification",
        "ranking_eligible": False,
        "scientific_evaluations": 0,
        "purpose": "detached queue and review-publication lifecycle qualification",
    })
    _write_json(metadata / "integrity_check.json", {
        "status": "PASS", "complete": True, "cells_expected": 1,
        "cells_present": 1, "cells_completed": 1,
        "arms_present": ["fixture"], "seeds_present": ["qualification"],
        "scientific_result": False,
    })
    summary = run / "summary"
    summary.mkdir(parents=True, exist_ok=True)
    with (summary / "primary_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["arm", "seed", "status", "ranking_eligible"])
        writer.writerow(["fixture", "qualification", "COMPLETED", "false"])
    (summary / "scientific_limitations.md").write_text(
        "This synthetic fixture has zero scientific evaluations and is not eligible for scientific ranking.\n",
        encoding="utf-8", newline="\n",
    )
    cell = run / "cells" / "fixture"
    _write_json(cell / "qualification_result.json", {
        "arm": "fixture", "seed": "qualification", "status": "COMPLETED",
        "ranking_eligible": False, "scientific_evaluations": 0,
    })
    _write_json(cell / "qualification_status.json", {
        "arm": "fixture", "seed": "qualification", "status": "COMPLETED",
        "cold_start": True, "terminal": True,
    })
    return {"status": "COMPLETED", "ranking_eligible": False, "scientific_evaluations": 0}


__all__ = ["run_qualification_fixture"]
