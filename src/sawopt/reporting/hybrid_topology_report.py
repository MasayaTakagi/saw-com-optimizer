"""Reports and shared review-bundle packaging for hybrid topology screens."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .review_bundle import ReviewBundleSpec, build_review_bundle


def _summary(result: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    lines = [
        "# Hybrid Topology Screening",
        "",
        "Production comparison outputs are stratified by the predeclared unique-evaluation budget.",
        "The B4000 rows are the equal-budget primary comparison. Dimension-normalized rows are a separate sensitivity stratum.",
        "",
        f"- Mode: `{context['mode']}`",
        f"- Material / DMS: MLIT / `{context['contract']['dms_topology']}`",
        f"- Ports: 50 / 50 ohm",
        f"- Seeds: `{list(context['seeds'])}`",
        f"- Common validation grid: `{context['common_grid_id']}` ({len(context['common_frequencies'])} points)",
        f"- Computation fingerprint (schema v2): `{context['fingerprint']['computation_fingerprint']}`",
        f"- Lifecycle: `{result['run_disposition']}`",
        f"- Stage 4B launched: `{str(result['stage4b_launched']).lower()}`",
        "",
        "## Equal-budget primary stratum",
        "",
        "| Topology | Dimension | Population | Seed | Unique evaluations | Eval/dimension | Max violation | Worst IL (dB) | Failures | Validation |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["topologies"]:
        metrics = row["common_grid_result"]
        lines.append(
            f"| {row['topology']} | {context['dimensions'][row['topology']]} | "
            f"{context['initial_populations'][row['topology']]} | {row['seed']} | "
            f"{row['absolute_unique_evaluations']} | {row['evaluations_per_dimension']:.3f} | "
            f"{metrics['max_violation']:.6g} | {metrics['worst_il_db']} | "
            f"{row['runtime']['failure_count']} | {metrics['validation_status']} |"
        )
    lines.extend([
        "", "## Dimension-normalized sensitivity stratum", "",
        "| Topology | Seed | Target | Eval/dimension | Max violation | Worst IL (dB) | Validation |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in result["normalized_sensitivity"]:
        metrics = row["common_grid_result"]
        lines.append(
            f"| {row['topology']} | {row['seed']} | {row['absolute_unique_evaluations']} | "
            f"{row['evaluations_per_dimension']:.3f} | {metrics['max_violation']:.6g} | "
            f"{metrics['worst_il_db']} | {metrics['validation_status']} |"
        )
    fairness = result["fairness_contract"]
    lines.extend([
        "", "## Interpretation and controls", "",
        f"- Equal-budget primary work: {fairness['primary_total_unique_evaluations']} unique evaluations.",
        f"- Complete dimension-normalized stratum: {fairness['sensitivity_total_unique_evaluations']} unique evaluations.",
        "- Structural continuation is unconditional for d > 10; B4000 outcomes do not decide continuation.",
        "- The schedule horizon remains B4000, and each cell's hard maximum is fixed before cold start.",
        "- Two seeds support screening only, not a definitive topology ranking.",
        "- No topology is automatically promoted or eliminated from Stage 4B; all four remain candidates for a separately predeclared selection gate.",
        "- The B4000 equal-budget stratum is authoritative; normalized sensitivity results cannot replace it.",
        "- No impedance sweep, T2, M0 comparison, or model calibration is included.",
        "",
    ])
    return "\n".join(lines)


def _review_request(result: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    lines = [
        "# C2C Review Request — Hybrid Topology Screening", "",
        "Review the current Stage 4B implementation and its run evidence. Stage 4B production remains gated by a separate launch authorization.",
        "", "## Fixed contract", "",
        "- MLIT / current T1, 50/50 ohm, current Stage 3.9 bounds/specification and common 9,113-point validation grid.",
        "- Exactly D, P_D, D_P, and P_D_P; all Stage 4B D controls are cold runs under the same contract.",
        f"- Seeds: {list(context['seeds'])}; L-SHADE; geometry-first comparator; initial population is 18 × dimension.",
        f"- Primary: {context['primary_budget']} unique evaluations per topology/seed.",
        f"- Normalized sensitivity: max({context['primary_budget']}, {context['evaluations_per_dimension']} × dimension), predeclared for every d > 10 cell.",
        "- Keep B4000 as the primary endpoint; use the B4000 L-SHADE schedule horizon while continuing the same checkpoint/RNG state.",
        "- Decision policy: no automatic promotion/elimination from Stage 4B. All four remain candidates until a separately predeclared selection gate; normalized sensitivity cannot replace B4000.",
        "", "## Execution evidence", "",
        f"- Study status: {result['status']}; disposition: {result['run_disposition']}; stage4b_launched={result['stage4b_launched']}.",
        f"- Computation fingerprint: `{context['fingerprint']['computation_fingerprint']}` (schema v2).",
        f"- Common-grid identity: `{context['common_grid_id']}` ({len(context['common_frequencies'])} points).",
        "- Machine-readable cells and separate comparison strata are in topology_results.json/.csv.",
        "- Runtime checkpoints use the shared LShadeCheckpointSession and remain REVIEW_WAITING pending review.",
        "",
        "## Required questions", "",
        "1. Is the equal B4000 primary comparison correctly isolated from the normalized sensitivity stratum?",
        "2. Are unconditional dimension-based continuation and 18 × dimension initialization unbiased by observed performance?",
        "3. Does exact B4000 checkpoint continuation preserve the fixed L-SHADE horizon and RNG stream?",
        "4. Are the lifecycle, provenance, common-grid validation, and machine-readable outputs sufficient?",
        "5. Is a future managed Stage 4B launch ready under the project's long-running policy?",
        "",
    ]
    return "\n".join(lines)


def write_hybrid_topology_reports(
    run_directory: str | Path, result: Mapping[str, Any], context: Mapping[str, Any],
) -> None:
    run = Path(run_directory)
    (run / "summary.md").write_text(_summary(result, context), encoding="utf-8")
    (run / "REVIEW_ME.md").write_text(_review_request(result, context), encoding="utf-8")


def build_hybrid_topology_review_bundle(
    run_directory: str | Path, context: Mapping[str, Any],
) -> Path:
    run = Path(run_directory)
    source_paths = tuple(dict.fromkeys((
        *context["computation_paths"], *context["reporting_paths"],
        "reports/escalation_log.md",
        "reports/escalation_packets/stage4b_fairness_sol_judgment_2026-09-29.md",
    )))
    spec = ReviewBundleSpec(
        study_type="hybrid_topology_screening",
        required_artifacts=(
            "summary.md", "REVIEW_ME.md", "config_snapshot.yaml",
            "topology_results.json", "topology_results.csv",
            "metadata/resolved_contract.json", "metadata/computation_fingerprint.json",
            "metadata/run_source_metadata.json", "metadata/implementation_validation.json",
            "metadata/fairness_contract.json", "metadata/initializer_accounting.json",
            "metadata/checkpoint_accounting.json", "metadata/c2c_review_status.json",
            "metadata/run_completion.json", "metadata/recovery_policy.json",
            "metadata/trajectory.csv",
            "metadata/review_bundle.json",
        ),
        source_paths=source_paths,
        git_diff_paths=source_paths,
    )
    stem = run.parent.name if run.name == "optimizer" else run.name
    output = context["root"] / "artifacts" / "review_bundles" / f"{stem}_review.zip"
    return build_review_bundle(run, output, spec, repo_root=context["root"])


__all__ = [
    "build_hybrid_topology_review_bundle", "write_hybrid_topology_reports",
]
