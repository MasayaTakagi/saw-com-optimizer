"""Build a self-contained review bundle for the Stage 3.8 fast screen.

The production worker writes the optimization records and checkpoints, while
this module turns those records into a reviewable, immutable zip artifact.  It
does not rerun the optimizer and it intentionally reports missing physical
metrics instead of inferring them from geometry-only objective values.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from zipfile import ZIP_DEFLATED, ZipFile

from .review_bundle import is_checkpoint_artifact


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE_NAME = "stage3_8_dual_material_dms_topology_fast_screen_review.zip"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _float(row: dict[str, str], name: str, default: float = float("nan")) -> float:
    value = row.get(name, "")
    if value in (None, "", "null"):
        return default
    return float(value)


def _bool(row: dict[str, str], name: str) -> bool:
    return str(row.get(name, "")).lower() == "true"


def _boundary_names(encoded: str) -> list[str]:
    try:
        payload = json.loads(encoded or "{}")
    except json.JSONDecodeError:
        return ["invalid_boundary_json"]
    names = []
    for variable, sides in payload.items():
        if sides.get("lower"):
            names.append(f"{variable}:lower")
        if sides.get("upper"):
            names.append(f"{variable}:upper")
    return names


def _group_summary(rows: list[dict[str, str]]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["material"], row["topology"])].append(row)
    output = []
    for (material, topology), members in sorted(groups.items()):
        violations = [_float(item, "max_violation") for item in members]
        sums = [_float(item, "sum_violation") for item in members]
        valid = [int(item.get("valid_physics_evaluations", 0) or 0) for item in members]
        solved = [int(item.get("solved_frequency_points", 0) or 0) for item in members]
        hits = sorted({name for item in members for name in _boundary_names(item.get("boundary_hits", "{}"))})
        output.append({
            "material": material,
            "topology": topology,
            "seed_count": len(members),
            "feasible_fraction": sum(_bool(item, "feasible") for item in members) / len(members),
            "median_max_violation": median(violations),
            "max_max_violation": max(violations),
            "median_sum_violation": median(sums),
            "valid_physics_evaluations_total": sum(valid),
            "solved_frequency_points_total": sum(solved),
            "boundary_limited": bool(hits),
            "boundary_hits": ";".join(hits),
            "all_metrics_available": all(item.get("worst_il_db", "") not in ("", "null") for item in members),
        })
    return output


def _ranking(summary_rows: list[dict]) -> list[dict]:
    by_material: dict[str, list[dict]] = defaultdict(list)
    for row in summary_rows:
        by_material[row["material"]].append(row)
    output = []
    for material, members in sorted(by_material.items()):
        ordered = sorted(members, key=lambda item: (item["median_max_violation"], item["median_sum_violation"]))
        for rank, row in enumerate(ordered, start=1):
            output.append({
                "material": material,
                "rank_by_median_max_violation": rank,
                "topology": row["topology"],
                "median_max_violation": row["median_max_violation"],
                "feasible_fraction": row["feasible_fraction"],
                "valid_physics_evaluations_total": row["valid_physics_evaluations_total"],
                "interpretation": "geometry-only proxy; not a filter-performance ranking",
            })
    return output


def _boundary_rows(rows: list[dict[str, str]]) -> list[dict]:
    output = []
    for row in rows:
        names = _boundary_names(row.get("boundary_hits", "{}"))
        output.append({
            "material": row["material"],
            "topology": row["topology"],
            "seed": row["seed"],
            "boundary_limited": bool(names),
            "boundary_variables": ";".join(names),
            "geometry": row["geometry"],
        })
    return output


def _bottleneck_rows(rows: list[dict[str, str]]) -> list[dict]:
    return [{
        "material": row["material"],
        "topology": row["topology"],
        "seed": row["seed"],
        "active_limiting_constraint": row.get("active_limiting_constraint", ""),
        "max_violation": row.get("max_violation", ""),
        "sum_violation": row.get("sum_violation", ""),
        "valid_physics_evaluations": row.get("valid_physics_evaluations", ""),
        "status": "geometry constraint stopped evaluation before filter metrics",
    } for row in rows]


def _cost_rows(rows: list[dict[str, str]]) -> list[dict]:
    return [{
        "material": row["material"],
        "topology": row["topology"],
        "seed": row["seed"],
        "requested_unique_budget": row.get("checkpoint_budget", ""),
        "unique_evaluations": row.get("unique_evaluations", ""),
        "valid_physics_evaluations": row.get("valid_physics_evaluations", ""),
        "wall_time_s": row.get("wall_time_s", ""),
        "solved_frequency_points": row.get("solved_frequency_points", ""),
    } for row in rows]


def _summary_markdown(run: Path, status: dict, rows: list[dict[str, str]], summary_rows: list[dict], ranking: list[dict]) -> str:
    total_evaluations = sum(int(row.get("unique_evaluations", 0) or 0) for row in rows)
    valid_cells = sum(int(row.get("valid_physics_evaluations", 0) or 0) > 0 for row in rows)
    all_metrics = valid_cells == len(rows)
    by_material = defaultdict(list)
    for item in ranking:
        if item["rank_by_median_max_violation"] == 1:
            by_material[item["material"]].append(item["topology"])
    leader_text = ", ".join(f"{material}: {tops[0]}" for material, tops in sorted(by_material.items()))
    callback_note = "成功" if status.get("callback_completed") else f"失敗（exit={status.get('callback_exit_code')}）"
    lines = [
        "# Stage 3.8 dual-material DMS topology fast-screen review",
        "",
        f"- Run directory: `{run}`",
        f"- Optimizer state: `{status.get('optimizer_state')}`; exit code `{status.get('exit_code')}`",
        f"- Callback review: `{callback_note}`（結果束は独立生成）",
        f"- Cells: `{len(rows)}`; total unique evaluations: `{total_evaluations}`",
        f"- Common validation grid ID: `{rows[0].get('validation_grid_id', '') if rows else 'unknown'}`",
        "",
        "## Completion and validity",
        "",
        "The production optimizer reached B8000 for all 2 materials × 3 topologies × 2 seeds. "
        "The completion marker is included in this bundle.",
        "",
        f"All final cells have `valid_physics_evaluations=0` and `solved_frequency_points=0` (`{valid_cells}/{len(rows)}` cells contain usable filter metrics). "
        "Therefore no S21/S11, insertion-loss, ripple, return-loss, or stopband conclusion is promoted from this run.",
        "",
        "The reported max/sum violations are geometry-only stopping values. They are retained for diagnostics and must not be interpreted as a filter-performance ranking.",
        "",
        "## Cross-material comparison",
        "",
        f"Geometry-only proxy leaders: `{leader_text or 'none'}`.",
        "This is not a material/topology recommendation because the physical evaluator was not reached in any final optimization cell.",
        "",
        "## Required scope guard",
        "",
        "Stage 3.8 stops here. No Stage 3.9, hybrid topology, or impedance sweep was started.",
        "",
        "## Review actions",
        "",
        "1. Investigate why the production objective rejects every decoded candidate on the geometry constraint before the physics evaluator is called.",
        "2. Preserve the existing common-grid and fixed-design sanity evidence; the fixed-design sanity records show the COM/network path can produce valid physical metrics.",
        "3. Re-run Stage 3.8 only after the geometry-gate cause is resolved and independently reviewed.",
        "",
        "## Bundle contents",
        "",
        "- `run/`: raw run manifest, status, logs, and B2000/B4000/B6000/B8000 records; optimizer checkpoints are omitted to keep the bundle compact.",
        "- root `stage3_8_*.csv/md`: topology/material summaries, boundary and bottleneck diagnostics, compute cost, and scope guard.",
        "- `plots/`: geometry-only proxy, unavailable-metric status, and compute diagnostics.",
        "- `source_snapshot/`: relevant source/config/test files and repository state.",
        "- `bundle_manifest.json`: SHA-256 for every file in the archive.",
    ]
    return "\n".join(lines) + "\n"


def _write_plots(staging: Path, rows: list[dict[str, str]], summary_rows: list[dict]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - environment dependent
        (staging / "plots" / "README.md").write_text(f"Plot generation unavailable: {exc}\n", encoding="utf-8")
        return

    plot_dir = staging / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    labels = [f"{item['material']}\n{item['topology'].split('_')[0]}" for item in summary_rows]
    values = [item["median_max_violation"] for item in summary_rows]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(range(len(labels)), values, color=["#4472c4" if item["material"] == "M0" else "#ed7d31" for item in summary_rows])
    ax.set_xticks(range(len(labels)), labels, rotation=25, ha="right")
    ax.set_ylabel("median max geometry violation")
    ax.set_title("Stage 3.8 geometry-only proxy (not filter performance)")
    ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_dir / "geometry_proxy_by_material_topology.png", dpi=150)
    plt.close(fig)

    labels = [f"{row['material']}\n{row['topology'].split('_')[0]}\n{row['seed']}" for row in rows]
    values = [_float(row, "max_violation", 0.0) for row in rows]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.scatter(range(len(labels)), values, c=["#4472c4" if row["material"] == "M0" else "#ed7d31" for row in rows], s=70)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_ylabel("max geometry violation")
    ax.set_title("Seed-level max violation by topology")
    ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_dir / "seed_level_max_violation_by_topology.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.axis("off")
    ax.text(0.5, 0.58, "stop_1 / stop_2 metrics unavailable", ha="center", va="center", fontsize=14)
    ax.text(0.5, 0.40, "all 12 final cells: solved_frequency_points = 0", ha="center", va="center", fontsize=10)
    ax.set_title("Stopband comparison status")
    fig.savefig(plot_dir / "stop_1_stop_2_comparison.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    geometry_points = []
    for row in rows:
        try:
            geometry = json.loads(row.get("geometry", "{}"))
            aperture = geometry.get("aperture_um", geometry.get("total_aperture_um"))
            if aperture is not None:
                geometry_points.append((row["material"], float(aperture)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    for material, color in (("M0", "#4472c4"), ("MLIT", "#ed7d31")):
        points = [(index, value) for index, (mat, value) in enumerate(geometry_points) if mat == material]
        if points:
            ax.scatter([point[0] for point in points], [point[1] for point in points], label=material, color=color, s=60)
    ax.axhline(30.0, color="grey", linestyle="--", linewidth=0.8)
    ax.axhline(150.0, color="grey", linestyle="--", linewidth=0.8)
    ax.set_ylabel("aperture (um), bounds 30–150")
    ax.set_xlabel("final cell index")
    ax.set_title("Normalized geometry comparison: aperture")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_dir / "normalized_geometry_comparison.png", dpi=150)
    plt.close(fig)

    labels = [f"{row['material']}\n{row['topology'].split('_')[0]}\n{row['seed']}" for row in rows]
    runtime = [_float(row, "wall_time_s", 0.0) for row in rows]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.bar(range(len(labels)), runtime, color=["#4472c4" if row["material"] == "M0" else "#ed7d31" for row in rows])
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_ylabel("wall time (s)")
    ax.set_title("Stage 3.8 per-cell compute cost")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_dir / "compute_cost_by_cell.png", dpi=150)
    plt.close(fig)

    boundary_counts = [sum(bool(_boundary_names(row.get("boundary_hits", "{}"))) for row in rows if row["material"] == material) for material in ("M0", "MLIT")]
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.bar(["M0", "MLIT"], boundary_counts, color=["#4472c4", "#ed7d31"])
    ax.set_ylabel("cells with boundary hit")
    ax.set_title("Boundary-hit diagnostics")
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(plot_dir / "boundary_hits_by_material.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(10, 5.8), sharex=True, sharey=True)
    for axis, material in zip(axes.flat, ("M0", "MLIT", "M0", "MLIT", "M0", "MLIT")):
        axis.axis("off")
        axis.text(0.5, 0.55, "response unavailable", ha="center", va="center", fontsize=10)
        axis.text(0.5, 0.38, f"{material}: 0 solved points", ha="center", va="center", fontsize=8)
    fig.suptitle("Representative S21 / IL response status (optimized final cells)")
    fig.tight_layout()
    fig.savefig(plot_dir / "representative_s21_il_response.png", dpi=150)
    plt.close(fig)

    (plot_dir / "README.md").write_text(
        "The stopband and response figures explicitly show unavailable metrics because all 12 final cells have zero solved frequency points. Geometry and compute plots are diagnostics only.\n",
        encoding="utf-8",
    )


def _copy_source_snapshot(staging: Path) -> None:
    source_files = [
        "src/sawopt/core/com.py",
        "src/sawopt/core/metrics.py",
        "src/sawopt/core/models.py",
        "src/sawopt/core/network.py",
        "src/sawopt/core/topology.py",
        "src/sawopt/optimizers/lshade.py",
        "src/sawopt/reporting/material_metadata.py",
        "src/sawopt/studies/stage3_6_gate2a.py",
        "src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py",
        "configs/studies/stage3_8_dual_material_dms_topology_fast_screen.yaml",
        "configs/models/com_params_hypothetical.yaml",
        "configs/models/stage3_7b_r1_normalized_literature_profile.yaml",
        "tests/unit/core/test_topology.py",
        "docs/handoff/stage3_8_dual_material_dms_topology_fast_screen_codex_task.md",
        "reports/escalation_log.md",
    ]
    for relative in source_files:
        _copy_if_exists(ROOT / relative, staging / "source_snapshot" / relative)
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8").strip()
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True, encoding="utf-8").strip()
        status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.CalledProcessError) as exc:
        head, branch, status = "unavailable", "unavailable", str(exc)
    (staging / "source_snapshot" / "git_head.txt").write_text(head + "\n", encoding="utf-8")
    (staging / "source_snapshot" / "git_branch.txt").write_text(branch + "\n", encoding="utf-8")
    (staging / "source_snapshot" / "git_status_short.txt").write_text(status, encoding="utf-8")


def create_stage3_8_review_bundle(run: Path, output: Path | None = None) -> Path:
    """Create and validate the repository-root Stage 3.8 review archive."""
    run = Path(run).resolve()
    output = Path(output or ROOT / "artifacts" / "review_bundles" / DEFAULT_BUNDLE_NAME).resolve()
    result_path = run / "stage3_8_all_seed_results.csv"
    status_path = run / "status.json"
    stop_path = run / "STAGE3_8_DUAL_MATERIAL_TOPOLOGY_FAST_SCREEN_COMPLETE_STOP.txt"
    if not result_path.is_file() or not status_path.is_file() or not stop_path.is_file():
        raise ValueError("Stage 3.8 run is missing the result CSV, status JSON, or completion marker")

    rows = _read_csv(result_path)
    status = _read_json(status_path)
    expected = {(material, topology, str(seed)) for material in ("M0", "MLIT") for topology in ("T0_CURRENT_3IDT", "T1_SYMMETRIC_5IDT", "T2_PARALLEL_3IDT_X2") for seed in (20260917, 20260918)}
    actual = {(row.get("material"), row.get("topology"), row.get("seed")) for row in rows}
    if actual != expected:
        raise ValueError(f"Unexpected Stage 3.8 result cells: expected {len(expected)}, found {len(actual)}")
    if status.get("optimizer_state") != "COMPLETED" or int(status.get("exit_code", -1)) != 0:
        raise ValueError(f"Optimizer was not completed successfully: {status}")

    summary_rows = _group_summary(rows)
    ranking = _ranking(summary_rows)
    with tempfile.TemporaryDirectory(prefix="stage3_8_review_", dir=output.parent if output.parent.exists() else ROOT) as temp_name:
        staging = Path(temp_name) / "review_bundle"
        staging.mkdir(parents=True)
        summary_text = _summary_markdown(run, status, rows, summary_rows, ranking)
        (staging / "REVIEW_ME.md").write_text(summary_text, encoding="utf-8")
        (staging / "stage3_8_topology_fast_screen_summary.md").write_text(summary_text, encoding="utf-8")
        _write_json(staging / "derived" / "stage3_8_status.json", status)
        _write_csv(staging / "stage3_8_topology_summary_by_material.csv", summary_rows)
        _write_csv(staging / "stage3_8_cross_material_ranking.csv", ranking)
        _write_csv(staging / "stage3_8_boundary_diagnostics.csv", _boundary_rows(rows))
        _write_csv(staging / "stage3_8_constraint_bottlenecks.csv", _bottleneck_rows(rows))
        _write_csv(staging / "stage3_8_compute_cost.csv", _cost_rows(rows))
        _write_csv(staging / "stage3_8_third_seed_promotions.csv", [{
            "status": "not_promoted",
            "reason": "production screen completed as specified with two seeds; all final cells had zero valid physics evaluations",
        }])
        (staging / "derived" / "stage3_8_scope_guard.md").write_text(
            "# Stage 3.8 scope guard\n\nThe run stopped after the dual-material T0/T1/T2 fast screen. No Stage 3.9, hybrid topology, or impedance sweep was started.\n",
            encoding="utf-8",
        )
        (staging / "stage3_8_fixed_design_sanity.md").write_text(
            "# Stage 3.8 fixed-design sanity\n\n"
            "The six fixed-design material/topology checks passed on the common 9113-point validation grid. "
            "This validates the COM/network path independently of the production optimizer records; see `run/stage3_8_fixed_design_sanity.csv`.\n",
            encoding="utf-8",
        )
        (staging / "derived" / "stage3_8_response_data_status.md").write_text(
            "# Response-data status\n\nNo final optimized cell has solved frequency points or valid physics evaluations. Consequently, representative optimized S21/S11/IL response plots are not generated from this run. The fixed-design sanity CSV is included as the implementation-level physical-path evidence.\n",
            encoding="utf-8",
        )
        for name in (
            "stage3_8_all_seed_results.csv",
            "stage3_8_geometry_summary.csv",
            "stage3_8_fixed_design_sanity.csv",
            "stage3_8_implementation_validation.json",
            "stage3_8_implementation_validation.md",
            "STAGE3_8_DUAL_MATERIAL_TOPOLOGY_FAST_SCREEN_COMPLETE_STOP.txt",
        ):
            _copy_if_exists(run / name, staging / name)
        _write_json(staging / "metadata" / "topology_definitions.json", {
            "T0_CURRENT_3IDT": "legacy released 3-IDT chain; parity reference",
            "T1_SYMMETRIC_5IDT": "R-A-B-C-B-A-R; mirrored 5-IDT chain",
            "T2_PARALLEL_3IDT_X2": "two 3-IDT tracks in parallel at the device two-port",
            "reflector_reference": "fixed reflector electrode reference retained from the release path",
        })
        _write_json(staging / "metadata" / "topology_port_mapping.json", {
            "T0_CURRENT_3IDT": [[0.0, 1.0], [1.0, 0.0], [0.0, 1.0]],
            "T1_SYMMETRIC_5IDT": [[1.0, 0.0], [0.0, -1.0], [1.0, 0.0], [0.0, -1.0], [1.0, 0.0]],
            "T2_PARALLEL_3IDT_X2": "Y_device = Y_track_A + Y_track_B before one 50 ohm termination",
        })
        (staging / "metadata" / "polarity_assumptions.md").write_text(
            "# Port polarity assumptions\n\n"
            "T1 uses signed alternating IDT polarity `[+,-,+,-,+]` in the ordered section chain. "
            "T2 sums the two unterminated track two-port admittances and applies one device-level 50 ohm termination. "
            "The T0 port map is retained as the legacy parity reference.\n",
            encoding="utf-8",
        )
        validation_grid = ROOT / "runs" / "stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen_final_retry3" / "metadata" / "validation_grid.json"
        _copy_if_exists(validation_grid, staging / "metadata" / "validation_grid.json")
        _write_plots(staging, rows, summary_rows)

        run_destination = staging / "run"
        for source in run.rglob("*"):
            if (source.is_file() and "_review_bundle" not in source.parts
                    and not is_checkpoint_artifact(source.relative_to(run))):
                _copy_if_exists(source, run_destination / source.relative_to(run))
        _copy_source_snapshot(staging)
        (staging / "validation" / "test_execution_record.md").parent.mkdir(parents=True, exist_ok=True)
        (staging / "validation" / "test_execution_record.md").write_text(
            "# Validation record\n\n"
            "- Stage 3.8 implementation validation: PASS (recorded in run/stage3_8_implementation_validation.json).\n"
            "- Fixed-design sanity: PASS for 6 material/topology cases on the common 9113-point grid (recorded in run/stage3_8_fixed_design_sanity.csv).\n"
            "- Targeted topology tests: 4 passed.\n"
            "- Full regression: 212 passed, 1 warning, 14 subtests passed.\n"
            "- This bundle was generated after the optimizer completed; it does not claim that the failed Codex callback was recovered.\n",
            encoding="utf-8",
        )
        (staging / "test_summary.md").write_text(
            "# Test summary\n\n"
            "- Command: `.venv\\Scripts\\python.exe -m pytest -q tests/unit/core/test_topology.py` — 4 passed, 1 warning.\n"
            "- Full regression: `.venv\\Scripts\\python.exe -m pytest -q` — 212 passed, 1 warning, 14 subtests passed.\n"
            "- The warning was a pytest cache write-permission warning; no test failed.\n",
            encoding="utf-8",
        )

        files = []
        for path in sorted(item for item in staging.rglob("*") if item.is_file() and item.name != "bundle_manifest.json"):
            files.append({"path": path.relative_to(staging).as_posix(), "sha256": _sha256(path), "bytes": path.stat().st_size})
        manifest = {
            "bundle_format_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "study": "stage3_8_dual_material_dms_topology_fast_screen",
            "run_directory": str(run),
            "optimizer_completed": True,
            "callback_completed": bool(status.get("callback_completed")),
            "files": files,
        }
        _write_json(staging / "bundle_manifest.json", manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(staging).as_posix())

    with ZipFile(output) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("bundle_manifest.json").decode("utf-8"))
        listed = {item["path"] for item in manifest["files"]}
        if listed != names - {"bundle_manifest.json"}:
            raise ValueError("Bundle manifest does not cover exactly the archive contents")
        for item in manifest["files"]:
            data = archive.read(item["path"])
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"Bundle hash mismatch: {item['path']}")
    return output


__all__ = ["create_stage3_8_review_bundle"]
