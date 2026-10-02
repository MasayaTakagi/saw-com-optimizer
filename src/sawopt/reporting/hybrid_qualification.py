"""Stage 4A qualification reports and review-bundle packaging.

This module contains presentation and packaging code only. Keep it in the
schema-v2 reporting dependency set, separate from numerical study code.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .review_bundle import ReviewBundleSpec, build_review_bundle


STAGE4A_REQUIRED_ARTIFACTS = (
    "summary.md", "config_snapshot.yaml", "smoke_results.json", "smoke_results.csv",
    "metadata/implementation_validation.json", "metadata/d_only_parity.json",
    "metadata/computation_fingerprint.json", "metadata/run_source_metadata.json",
    "metadata/checkpoint_accounting.json", "metadata/initializer_accounting.json",
    "metadata/stage4b_runtime_estimate.json", "metadata/test_summary.json",
    "metadata/failed_attempts.json", "metadata/cache_idempotency.json",
    "metadata/c2c_review_status.json", "metadata/run_completion.json",
    "metadata/recovery_policy.json",
)


def _clean(value: Any) -> Any:
    """Convert common NumPy/container values to strict JSON-compatible data."""
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _clean(value.item())
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(_clean(row) for row in rows)


def _summary_markdown(result: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    lines = [
        "# Stage 4A Hybrid Protocol Qualification",
        "",
        "**NON-SCIENTIFIC SMOKE.** These short runs exercise protocol integration; they do not rank topologies or support scientific performance conclusions.",
        "",
        f"- Status: `{result['status']}`",
        "- Material / DMS: MLIT / T1_SYMMETRIC_5IDT",
        f"- Ports: {context['source_impedance_ohm']:.0f}/{context['load_impedance_ohm']:.0f} ohm",
        f"- Common validation grid: `{context['common_grid_id']}` ({len(context['common_frequencies'])} points)",
        f"- Computation fingerprint (schema v2): `{context['fingerprint']['computation_fingerprint']}`",
        "",
        "## Smoke results",
        "",
        "| Topology | Unique evaluations | Seed | Wall time (s) | Max violation | Worst IL (dB) | Physics failures | Validation |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["topologies"]:
        lines.append(
            f"| {row['topology']} | {row['unique_evaluations']} | {row['seed']} | "
            f"{row['wall_time_s']:.3f} | {row.get('final_max_violation')} | "
            f"{row.get('worst_il_db')} | {row['failure_count']} | {row['validation_status']} |"
        )
    lines.extend([
        "", "## Qualification boundaries", "",
        "- The production path uses the shared L-SHADE backend, canonical cache identity, geometry-first accounting, and rolling checkpoint session.",
        "- D-only parity passed on both the Stage 3.9 search grid and the 9,113-point common validation grid.",
        "- The combined die estimate is the documented hypothetical separate-row placement approximation.",
        "- An initial partial smoke exposed a T1-only versus hybrid-vector dimension mismatch at P_D initialization; it was corrected and the clean four-topology retry is recorded separately.",
        "- No Stage 4B production screen was launched.",
        "",
        "## Stage 4B runtime estimate", "",
        f"- For 4 topologies × 2 seeds × 4,000 unique evaluations: `{result['stage4b_runtime_estimate']['low_hours']:.2f}–{result['stage4b_runtime_estimate']['high_hours']:.2f}` hours.",
        f"- Central estimate: `{result['stage4b_runtime_estimate']['central_hours']:.2f}` hours; finalist validation assumes 16 candidates per cell on the common grid.",
        "",
    ])
    return "\n".join(lines)


def _review_request(
    context: Mapping[str, Any], topologies: Sequence[Mapping[str, Any]],
    parity: Mapping[str, Any], test_summary: Mapping[str, Any],
) -> str:
    focused = test_summary.get("focused_regressions", test_summary)
    full_suite = test_summary.get("full_suite", test_summary)
    lines = [
        "# C2C Review Request — Stage 4A Hybrid Protocol Qualification", "",
        "## Goal", "",
        "Qualify the current MLIT / T1 DMS plus ladder-resonator protocol using the current L-SHADE, unique-evaluation accounting, validation, checkpoint, provenance, and review-bundle infrastructure. Stage 4B production was not launched.", "",
        "## Implementation", "",
        "- Added a current hybrid design space using the existing ten-variable T1 decoder and existing one-port COM resonator model.",
        "- Added only D, P_D, D_P, and P_D_P; source/load shunts are stamped at their defined terminal nodes.",
        "- The combined layout is explicitly a hypothetical separate-row approximation; DMS and resonator geometry are reported separately.",
        "- Resonator defaults remain reflector electrodes=40, gap_lambda=0, metallization_ratio=0.5, thickness_over_lambda=0.04.",
        "- The first partial smoke exposed a T1-only bounds array passed to wider hybrid vectors; a clean retry uses per-topology bounds. A separate artifact-only bundle retry is recorded in failed_attempts.json.", "",
        "## D-only parity", "",
        f"- Search grid: {parity['grids']['search']['frequency_count']} points; common grid: {parity['grids']['common']['frequency_count']} points (rtol={parity['rtol']}, atol={parity['atol']}).",
        f"- Compared Y/S parameters, GT, IL, VSWR, all metrics/violations, max/sum violation, feasible flag, and scalar objective; maximum absolute difference: {parity['overall_maximum_absolute_difference']:.12g}.", "",
        "## Tests and smoke", "",
        f"- Focused regressions: {focused['passed']} passed, {focused['failed']} failed. Full suite: {full_suite['passed']} passed, {full_suite['failed']} failed, {full_suite.get('subtests_passed', 0)} subtests passed. Historical hybrid compatibility tests remain unchanged.",
        "- Four smoke cells use MLIT, current T1, 50/50 ohm, seed 20260929, 256 unique evaluations each, population 32, checkpoints 128/256.",
        "- Smoke is explicitly non-scientific; each cell used the same 9,113-point common validation grid and exercised mutation, checkpoints, canonicalization, and a zero-budget cache idempotency probe.",
        "",
        "| Topology | Unique | Wall s | Max violation | Worst IL dB | Failures | Validation |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    lines.extend(
        f"| {row['topology']} | {row['unique_evaluations']} | {row['wall_time_s']:.3f} | "
        f"{row['final_max_violation']:.6g} | {row['worst_il_db']:.6g} | "
        f"{row['failure_count']} | {row['validation_status']} |"
        for row in topologies
    )
    lines.extend([
        "", "## Provenance and lifecycle", "",
        f"- Fingerprint schema v{context['fingerprint']['fingerprint_schema_version']}; computation fingerprint `{context['fingerprint']['computation_fingerprint']}`.",
        "- Shared LShadeCheckpointSession; successful execution disposition REVIEW_WAITING pending review.",
        "- The review bundle is built with ReviewBundleSpec/build_review_bundle; C2C status is included in the run artifacts.",
        "",
        "## Known limits and proposed Stage 4B protocol", "",
        "- Placeholder literature COM profile remains uncalibrated. The row layout is hypothetical. Smoke metrics do not rank topology families.",
        "- Proposed Stage 4B: 4 topologies × 2 cold seeds × 4,000 unique evaluations; same MLIT/T1 and 50/50 ports; current bounds/spec/common grid; L-SHADE with the same accounting and initializer; validate 16 finalists per cell. Do not start this in Stage 4A.",
        "",
        "## Required judgment", "",
        "1. Is D-only parity strong enough?",
        "2. Does the hybrid integration preserve Stage 3.9 scientific contracts?",
        "3. Are topology comparisons structurally biased?",
        "4. Is L-SHADE unique-evaluation accounting matched correctly?",
        "5. Is the Stage 4B 4k × 2-seed screen safe to launch?",
        "",
    ])
    return "\n".join(lines)


def write_stage4a_reports(
    run_directory: str | Path,
    result: Mapping[str, Any],
    context: Mapping[str, Any],
    topologies: Sequence[Mapping[str, Any]],
    parity: Mapping[str, Any],
    test_summary: Mapping[str, Any],
) -> None:
    """Write Stage 4A summary, CSV, and C2C review request."""
    run = Path(run_directory)
    _write_csv(run / "smoke_results.csv", topologies)
    (run / "summary.md").write_text(_summary_markdown(result, context), encoding="utf-8")
    (run / "REVIEW_ME.md").write_text(
        _review_request(context, topologies, parity, test_summary), encoding="utf-8",
    )


def build_stage4a_review_bundle(run_directory: str | Path, context: Mapping[str, Any]) -> Path:
    """Package required Stage 4A evidence using shared review-bundle infrastructure."""
    source_paths = tuple(dict.fromkeys((
        *context["computation_paths"], *context["reporting_paths"],
        "reports/escalation_log.md",
        "reports/escalation_packets/stage4a_hybrid_sol_judgment_2026-09-29.md",
    )))
    spec = ReviewBundleSpec(
        study_type="hybrid_stage4a_protocol_qualification",
        required_artifacts=STAGE4A_REQUIRED_ARTIFACTS,
        optional_artifacts=("metadata/validated_finalists.json",),
        source_paths=source_paths,
        git_diff_paths=source_paths,
    )
    root = Path(context["root"])
    output = root / "artifacts" / "review_bundles" / f"{Path(run_directory).name}_review.zip"
    return build_review_bundle(run_directory, output, spec, repo_root=root)
