"""Read-only preflight and result verification for the Stage 3.9B 16k extension."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ...io.config import load_experiment_config
from . import stage3_9b_overlap_parity as parity


ROOT = Path(__file__).resolve().parents[4]
SEEDS = parity.SEEDS
MATERIAL = parity.MATERIAL
TOPOLOGY = parity.TOPOLOGY
OVERLAP_CHECKPOINTS = parity.CHECKPOINTS
EXTENSION_CHECKPOINTS = tuple(range(2000, 16001, 2000))
OVERLAP_CONFIG = ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml"
EXTENSION_CONFIG = ROOT / "configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml"
CONTROL_RUN_DIR = ROOT / "runs/stage3_9b_mlit_t1_50ohm_overlap_parity_20260927_retry2/optimizer"
EXTENSION_RUN_DIR = ROOT / "runs/stage3_9b_mlit_t1_50ohm_budget_extension_20260927/optimizer"
GATE_B_BUNDLE = ROOT / "artifacts/review_bundles/stage3_9b_source_compatibility_gateb_final"
GATE_D_BUNDLE = ROOT / "artifacts/review_bundles/stage3_9b_overlap_parity_retry2_review"
PREFLIGHT_BUNDLE = ROOT / "artifacts/review_bundles/stage3_9b_budget_extension_preflight_20260927_final3"
RESULT_BUNDLE = ROOT / "artifacts/review_bundles/stage3_9b_budget_extension_review"

SEED_CONTRACT = {
    "identifier": "stage3_8c_r1_2_independent_rejection",
    "namespace": "stage3_8c_r1_geometry_first_v1",
    "derivation_suffix": "r1_2_independent_rejection",
}
INITIAL_SAMPLING_SEEDS = {
    f"{MATERIAL}/{TOPOLOGY}/20260917": 3938065196,
    f"{MATERIAL}/{TOPOLOGY}/20260918": 1982837181,
}
PROTOCOL_FIELDS = (
    "material", "topology", "impedance_ohm", "active_bounds", "hard_bounds",
    "integer_indices", "manufacturing_geometry_limits", "profile_id",
    "profile_parameters", "aperture_bounds_um", "initializer_method",
    "initial_population_seed_contract", "initial_sampling_seeds", "population_size",
    "backend_config", "initializer", "initial_design_vector",
    "initial_design_vector_sha256", "initial_design_source_sha256", "specification",
    "manufacturing_constraints", "common_grid_id", "common_grid_array_sha256",
    "common_grid_count", "search_grid_sha256", "search_grid_count", "seeds",
    "cold_start",
)
PREFIX_TOTAL_RUN_BUDGET_FIELDS = ("hard_max_budget",)
PREFIX_FINALIZATION_COUNTER_FIELDS = (
    "solved_frequency_points",
    "validation_evaluations",
    "validation_physics_failures",
    "validation_frequency_points",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _review_bundle_path(path: Path) -> Path:
    resolved = path.resolve()
    allowed_root = (ROOT / "artifacts/review_bundles").resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"review bundle must stay under {allowed_root}: {resolved}") from exc
    return resolved


def _control_run_errors(optimizer_dir: Path, expected_config: Path) -> list[str]:
    root = optimizer_dir.resolve().parent
    errors: list[str] = []
    try:
        manifest = _read_json(root / "run_manifest.json")
        status = _read_json(root / "status.json")
        checkpoint = _read_json(root / "session_checkpoint.json")
    except (OSError, ValueError) as exc:
        return [f"run control metadata unavailable under {root}: {exc}"]
    if manifest.get("schema_version") != 2:
        errors.append("run manifest is not schema version 2")
    if _path_key(Path(str(manifest.get("config_path", "")))) != _path_key(expected_config):
        errors.append("run manifest config_path differs from the approved config")
    if _path_key(Path(str(manifest.get("run_dir", "")))) != _path_key(root):
        errors.append("run manifest run_dir differs from its containing directory")
    if _path_key(Path(str(manifest.get("optimizer_run_dir", "")))) != _path_key(optimizer_dir):
        errors.append("run manifest optimizer_run_dir differs from the supplied optimizer directory")
    if status.get("state") != "COMPLETED" or status.get("optimizer_state") != "COMPLETED" or status.get("exit_code") != 0:
        errors.append("durable orchestration status is not a clean COMPLETED / exit 0")
    if status.get("callback_enabled") is not False or status.get("resume_count") != 0:
        errors.append("run status does not preserve disabled-callback / no-resume controls")
    if manifest.get("callback_enabled") is not False or manifest.get("review_after_completion") is not False:
        errors.append("run manifest does not preserve disabled-callback controls")
    if manifest.get("codex_session_id") is not None or manifest.get("codex_session_source") is not None:
        errors.append("run manifest unexpectedly contains a Codex session")
    if manifest.get("callback_preflight") is not None:
        errors.append("run manifest unexpectedly contains a callback preflight")
    run_id = manifest.get("run_id")
    if not run_id or checkpoint.get("run_id") != run_id:
        errors.append("session checkpoint run ID does not match the run manifest")
    if checkpoint.get("session_id") is not None or checkpoint.get("resume_count") != 0:
        errors.append("session checkpoint does not preserve the no-session / no-resume controls")
    return errors


def _resolve_configs(overlap_config: Path, extension_config: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    overlap_cfg = load_experiment_config(overlap_config.resolve())
    extension_cfg = load_experiment_config(extension_config.resolve())
    overlap_protocol = parity._config_protocol(overlap_cfg)
    extension_protocol = parity._config_protocol(extension_cfg)
    return overlap_cfg, extension_cfg, overlap_protocol, extension_protocol


def _config_errors(
    overlap_cfg: Mapping[str, Any],
    extension_cfg: Mapping[str, Any],
    overlap_protocol: Mapping[str, Any],
    extension_protocol: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    overlap_settings = overlap_cfg["dms_topology"]
    extension_settings = extension_cfg["dms_topology"]
    for label, settings, protocol, budget, checkpoints in (
        ("overlap", overlap_settings, overlap_protocol, 8000, OVERLAP_CHECKPOINTS),
        ("extension", extension_settings, extension_protocol, 16000, EXTENSION_CHECKPOINTS),
    ):
        if int(settings.get("budget", -1)) != budget:
            errors.append(f"{label} config budget is not {budget}")
        if tuple(int(value) for value in settings.get("checkpoints", ())) != checkpoints:
            errors.append(f"{label} config checkpoint lattice is not {list(checkpoints)}")
        if int(settings.get("population_schedule_terminal_budget", -1)) != 8000:
            errors.append(f"{label} population-schedule horizon is not 8000")
        if tuple(int(value) for value in settings.get("seeds", ())) != SEEDS:
            errors.append(f"{label} seed set differs from the approved pair")
        if settings.get("cold_start") is not True:
            errors.append(f"{label} does not explicitly use cold starts")
        if protocol.get("impedance_ohm") != 50.0:
            errors.append(f"{label} source/load impedance is not 50 ohm")
        if protocol.get("initial_population_seed_contract") != SEED_CONTRACT:
            errors.append(f"{label} does not resolve to the approved historical seed contract")
        if protocol.get("initial_sampling_seeds") != INITIAL_SAMPLING_SEEDS:
            errors.append(f"{label} derived initializer seeds differ from the approved pair")
    for field in PROTOCOL_FIELDS:
        errors.extend(parity.compare_values(
            overlap_protocol.get(field), extension_protocol.get(field), f"shared_protocol.{field}", limit=50,
        ))
    return errors


def _effective_extension_backend_config(
    extension_cfg: Mapping[str, Any], extension_protocol: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    _active, hard_bounds, _integer_indices = parity.study.material_bounds(
        extension_cfg, MATERIAL, TOPOLOGY,
    )
    backend = parity.study._backend_config(extension_cfg, TOPOLOGY, 16000, hard_bounds)
    return backend, _effective_backend_config_errors(backend, extension_protocol)


def _effective_backend_config_errors(
    backend: Mapping[str, Any], extension_protocol: Mapping[str, Any],
) -> list[str]:
    expected = {
        "total_budget": 16000,
        "hard_max_budget": 16000,
        "population_schedule_terminal_budget": 8000,
        "initial_population": 180,
        "hard_bounds": extension_protocol["hard_bounds"],
    }
    errors = [
        mismatch
        for key, value in expected.items()
        for mismatch in parity.compare_values(
            backend.get(key), value, f"effective_extension_backend_config.{key}",
        )
    ]
    return errors


def run_config_preflight(
    *,
    overlap_config: Path = OVERLAP_CONFIG,
    extension_config: Path = EXTENSION_CONFIG,
    gate_b_bundle: Path = GATE_B_BUNDLE,
    gate_d_bundle: Path = GATE_D_BUNDLE,
    control_run_dir: Path = CONTROL_RUN_DIR,
    extension_control_root: Path = EXTENSION_RUN_DIR.parent,
    output_dir: Path = PREFLIGHT_BUNDLE,
) -> dict[str, Any]:
    output_dir = _review_bundle_path(output_dir)
    errors: list[str] = []
    source_hashes: dict[str, Any] = {}
    overlap_cfg: dict[str, Any] | None = None
    extension_cfg: dict[str, Any] | None = None
    overlap_protocol: dict[str, Any] | None = None
    extension_protocol: dict[str, Any] | None = None
    effective_backend: dict[str, Any] | None = None
    effective_backend_errors: list[str] = []

    try:
        gate_b_summary = _read_json(gate_b_bundle / "compatibility_summary.json")
        gate_b_hashes = _read_json(gate_b_bundle / "source_hashes.json")
        gate_b_ok = (
            gate_b_summary.get("status") == "PASS"
            and all(value == "PASS" for value in gate_b_summary.get("categories", {}).values())
            and gate_b_summary.get("historical_source_provenance_status") == "PASS_WITH_CAVEAT"
        )
        if not gate_b_ok:
            errors.append("Gate-B source-compatibility summary is not PASS")
        current_files = gate_b_hashes.get("current_source_files", {})
        for relative, expected in current_files.items():
            path = ROOT / relative
            actual = _sha256(path) if path.is_file() else None
            source_hashes[relative] = {"expected": expected, "actual": actual, "match": actual == expected}
            if actual != expected:
                errors.append(f"Gate-B source/config hash drift: {relative}")
        if not current_files:
            errors.append("Gate-B source_hashes.json contains no current_source_files")
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"Gate-B bundle could not be verified: {type(exc).__name__}: {exc}")

    try:
        gate_d = _read_json(gate_d_bundle / "parity_summary.json")
        gate_d_ok = (
            gate_d.get("status") == "PASS"
            and gate_d.get("checkpoint_comparison_count") == 8
            and gate_d.get("mismatches") == []
            and all(gate_d.get("gates", {}).values())
            and len(gate_d.get("checkpoint_comparisons", [])) == 8
            and all(row.get("status") == "PASS" and row.get("mismatch_count") == 0
                    for row in gate_d.get("checkpoint_comparisons", []))
        )
        if not gate_d_ok:
            errors.append("Gate-D parity artifact is not an 8-cell zero-mismatch PASS")
        expected_control = gate_d.get("overlap_run_dir")
        if expected_control and _path_key(Path(str(expected_control))) != _path_key(control_run_dir):
            errors.append("Gate-D result bundle points to a different overlap control run")
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"Gate-D parity bundle could not be verified: {type(exc).__name__}: {exc}")

    errors.extend(_control_run_errors(control_run_dir, overlap_config))

    try:
        overlap_cfg, extension_cfg, overlap_protocol, extension_protocol = _resolve_configs(
            overlap_config, extension_config,
        )
        errors.extend(_config_errors(overlap_cfg, extension_cfg, overlap_protocol, extension_protocol))
        effective_backend, effective_backend_errors = _effective_extension_backend_config(
            extension_cfg, extension_protocol,
        )
        errors.extend(effective_backend_errors)
    except Exception as exc:
        errors.append(f"config-only resolution failed: {type(exc).__name__}: {exc}")
        effective_backend_errors.append(f"effective backend resolution failed: {type(exc).__name__}: {exc}")

    root_is_fresh = (
        not extension_control_root.exists()
        or (extension_control_root.is_dir() and not any(extension_control_root.iterdir()))
    )
    if not root_is_fresh:
        errors.append(f"fresh extension control root is not absent/empty: {extension_control_root}")

    gate_b_errors = [error for error in errors if "Gate-B" in error]
    gate_d_errors = [error for error in errors if "Gate-D" in error]
    summary = {
        "status": "PASS" if not errors else "FAIL",
        "scope": "read-only config/control/artifact preflight",
        "optimizer_executed": False,
        "physics_evaluations": 0,
        "production_run_launched": False,
        "gate_b": {"status": "PASS" if not gate_b_errors else "FAIL", "source_hashes": source_hashes},
        "gate_d": {"status": "PASS" if not gate_d_errors else "FAIL", "bundle": str(gate_d_bundle.resolve())},
        "effective_extension_backend": {
            "status": "PASS" if not effective_backend_errors else "FAIL",
            "config": effective_backend,
            "errors": effective_backend_errors,
        },
        "control_run_dir": str(control_run_dir.resolve()),
        "extension_control_root": str(extension_control_root.resolve()),
        "extension_root_fresh": root_is_fresh,
        "overlap_config": str(overlap_config.resolve()),
        "extension_config": str(extension_config.resolve()),
        "overlap_protocol": overlap_protocol,
        "extension_protocol": extension_protocol,
        "effective_extension_backend_config": effective_backend,
        "shared_projection_backend_semantics": (
            "The shared protocol backend_config is resolved at the 8k schedule horizon for prefix comparison; "
            "effective_extension_backend_config separately records the actual 16k launch backend."
        ),
        "shared_protocol_fields": list(PROTOCOL_FIELDS),
        "allowed_config_differences": {
            "budget": [8000, 16000],
            "checkpoints": [list(OVERLAP_CHECKPOINTS), list(EXTENSION_CHECKPOINTS)],
        },
        "launch_command": [
            str(ROOT / ".venv/Scripts/python.exe"), "-m", "sawopt.orchestration.cli", "launch",
            "--config", str(extension_config.resolve()),
            "--run-dir", str(extension_control_root.resolve()),
            "--experiment-name", "stage3_9b_budget_extension",
            "--no-callback",
        ],
        "errors": errors,
    }
    _write_json(output_dir / "config_preflight.json", summary)
    markdown = [
        "# Stage 3.9B 16k config-only preflight", "",
        f"Status: **{summary['status']}**", "",
        "- Optimizer executed: no.",
        "- COM/RF physics evaluations: 0.",
        "- Production run launched: no.",
        f"- Gate-B source/config hashes: {'PASS' if not gate_b_errors else 'FAIL'}.",
        f"- Gate-D accepted parity artifact: {'PASS' if not gate_d_errors else 'FAIL'}.",
        f"- Effective 16k backend total/hard budget, schedule horizon, initial population and hard bounds: {'PASS' if not effective_backend_errors else 'FAIL'}.",
        f"- Fresh extension root absent/empty: {'PASS' if root_is_fresh else 'FAIL'}.",
        "- Shared protocol fields: material/topology, impedance, search and hard bounds, integer indices, COM profile, initializer and seed contract, initial design, specification, common/search grids, seed set, 8k prefix-backend projection, and cold-start policy.",
        "- Effective 16k launch backend is checked separately for total/hard budget 16,000, schedule horizon 8,000, initial population 180, and accepted hard bounds.",
        "- Approved differences: total evaluation budget and checkpoint lattice only; the population-schedule horizon remains 8,000.",
        "",
        "## Errors", "",
    ]
    markdown.extend(f"- {error}" for error in errors) if errors else markdown.append("- None.")
    markdown.extend(["", "## Conditional launch command", "", " ".join(summary["launch_command"]), ""])
    (output_dir / "config_preflight.md").write_text("\n".join(markdown), encoding="utf-8")
    return summary


def _expected_lattice(checkpoints: tuple[int, ...]) -> set[tuple[int, int]]:
    return {(seed, budget) for seed in SEEDS for budget in checkpoints}


def _without_expansion_limits(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only the total-run hard limit that differs in an extension."""
    return {key: value for key, value in projection.items() if key not in PREFIX_TOTAL_RUN_BUDGET_FIELDS}


def _checkpoint_budget_metadata_errors(
    record: Mapping[str, Any], label: str, expected_hard_max_budget: int,
) -> list[str]:
    errors: list[str] = []
    if int(record.get("hard_max_budget", -1)) != expected_hard_max_budget:
        errors.append(
            f"{label}.hard_max_budget={record.get('hard_max_budget')!r}, "
            f"expected {expected_hard_max_budget}"
        )
    if int(record.get("terminal_budget", -1)) != 8000:
        errors.append(f"{label}.terminal_budget={record.get('terminal_budget')!r}, expected 8000")
    if int(record.get("population_schedule_terminal_budget", -1)) != 8000:
        errors.append(f"{label}.population_schedule_terminal_budget is not 8000")
    return errors


def _prefix_search_counter_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    counters = parity._normalized_counters(record)
    return {
        name: value for name, value in counters.items()
        if name not in PREFIX_FINALIZATION_COUNTER_FIELDS
    }


def _prefix_finalization_counter_observations(
    control: Mapping[str, Any], extension: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    control_counters = parity._normalized_counters(control)
    extension_counters = parity._normalized_counters(extension)
    return {
        name: {"control": control_counters[name], "extension": extension_counters[name]}
        for name in PREFIX_FINALIZATION_COUNTER_FIELDS
    }


def _prefix_record_mismatches(
    control: Mapping[str, Any], extension: Mapping[str, Any], seed: int, budget: int,
) -> list[str]:
    errors = parity._validate_checkpoint_accounting(control, seed, budget)
    errors.extend(parity._validate_checkpoint_accounting(extension, seed, budget))
    for label, record, total in (("control", control, 8000), ("extension", extension, 16000)):
        errors.extend(_checkpoint_budget_metadata_errors(record, label, total))
    try:
        left = _without_expansion_limits(parity._record_projection(control))
        right = _without_expansion_limits(parity._record_projection(extension))
        left["evaluation_counters"] = _prefix_search_counter_projection(control)
        right["evaluation_counters"] = _prefix_search_counter_projection(extension)
        errors.extend(parity.compare_values(left, right, f"seed{seed}.B{budget}", limit=120))
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"prefix record projection failed: {type(exc).__name__}: {exc}")
    return errors


def _normalized_content_sha256(path: Path) -> str:
    """Hash text content consistently across LF and CRLF checkout conventions."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _retained_input_config_provenance(
    optimizer_dir: Path, config_path: Path, run_source: Mapping[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    retained_path = optimizer_dir / "input_config.yaml"
    report: dict[str, Any] = {
        "approved_config_path": str(config_path.resolve()),
        "retained_config_path": str(retained_path.resolve()),
        "approved_normalized_content_sha256": None,
        "retained_normalized_content_sha256": None,
        "normalized_content_matches": False,
        "run_source_path_field_present": False,
    }
    errors: list[str] = []
    try:
        approved_hash = _normalized_content_sha256(config_path)
        retained_hash = _normalized_content_sha256(retained_path)
        report["approved_normalized_content_sha256"] = approved_hash
        report["retained_normalized_content_sha256"] = retained_hash
        report["normalized_content_matches"] = approved_hash == retained_hash
        if approved_hash != retained_hash:
            errors.append("retained optimizer/input_config.yaml content differs from the approved 16k config")
    except OSError as exc:
        errors.append(f"retained input-config provenance unavailable: {type(exc).__name__}: {exc}")

    recorded_path = run_source.get("source_config_path")
    report["run_source_path_field_present"] = recorded_path not in (None, "")
    if recorded_path not in (None, "") and _path_key(Path(str(recorded_path))) != _path_key(config_path):
        errors.append("run-source source_config_path differs from the approved 16k config")
    return errors, report


def _compare_cache_sequence_prefix(
    control_cache: Any,
    extension_cache: Any,
    *,
    expected_count: int = 8000,
    seed: int = 0,
    control_frequency_versions: Any = None,
    extension_frequency_versions: Any = None,
) -> tuple[list[str], bool]:
    errors: list[str] = []
    if not isinstance(control_cache, list) or len(control_cache) != expected_count:
        actual = len(control_cache) if isinstance(control_cache, list) else type(control_cache).__name__
        return [f"control cache length/type is {actual}, expected {expected_count} entries"], False
    if not isinstance(extension_cache, list) or len(extension_cache) < expected_count:
        actual = len(extension_cache) if isinstance(extension_cache, list) else type(extension_cache).__name__
        return [f"extension cache length/type is {actual}, expected at least {expected_count} entries"], False

    for index, (control_row, extension_row) in enumerate(
        zip(control_cache, extension_cache[:expected_count]),
    ):
        if (
            not isinstance(control_row, (list, tuple)) or len(control_row) != 2
            or not isinstance(extension_row, (list, tuple)) or len(extension_row) != 2
        ):
            errors.append(f"cache prefix row {index} is malformed")
            continue
        if control_row[0] != extension_row[0]:
            errors.append(f"cache prefix key {index} differs")
            continue
        try:
            control_result = parity._evaluation_projection(control_row[1])
            extension_result = parity._evaluation_projection(extension_row[1])
        except (TypeError, ValueError) as exc:
            errors.append(f"cache prefix result {index} is malformed: {exc}")
            continue
        errors.extend(parity.compare_values(
            control_result, extension_result, f"seed{seed}.cache_prefix[{index}]", limit=10,
        ))
        if len(errors) >= 100:
            errors.append("cache prefix mismatch list capped at 100 entries")
            break

    frequency_versions_checked = (
        isinstance(control_frequency_versions, list)
        and isinstance(extension_frequency_versions, list)
        and len(control_frequency_versions) >= expected_count
        and len(extension_frequency_versions) >= expected_count
    )
    if frequency_versions_checked:
        errors.extend(parity.compare_values(
            control_frequency_versions[:expected_count],
            extension_frequency_versions[:expected_count],
            f"seed{seed}.cache_frequency_versions_prefix",
            limit=100,
        ))
    return errors, frequency_versions_checked


def _cache_prefix_errors(control_run_dir: Path, extension_run_dir: Path) -> tuple[list[str], dict[str, bool]]:
    errors: list[str] = []
    frequency_versions_checked: dict[str, bool] = {}
    for seed in SEEDS:
        control_path = (
            control_run_dir / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}" / "optimizer_checkpoint.json"
        )
        extension_path = (
            extension_run_dir / "optimization" / MATERIAL / TOPOLOGY / f"seed{seed}" / "optimizer_checkpoint.json"
        )
        try:
            control_state = _read_json(control_path)
            extension_state = _read_json(extension_path)
            differences, versions_checked = _compare_cache_sequence_prefix(
                control_state.get("cache"),
                extension_state.get("cache"),
                expected_count=8000,
                seed=seed,
                control_frequency_versions=control_state.get("cache_frequency_versions"),
                extension_frequency_versions=extension_state.get("cache_frequency_versions"),
            )
            frequency_versions_checked[str(seed)] = versions_checked
            errors.extend(f"seed{seed}: {difference}" for difference in differences)
        except (OSError, ValueError, TypeError) as exc:
            frequency_versions_checked[str(seed)] = False
            errors.append(f"seed{seed} cache-prefix state invalid: {type(exc).__name__}: {exc}")
    return errors, frequency_versions_checked


def _extension_metadata_errors(
    optimizer_dir: Path, protocol: Mapping[str, Any], config_path: Path,
) -> list[str]:
    errors = parity._validate_current_run_metadata(optimizer_dir, protocol)
    run_source = _read_json(optimizer_dir / "metadata" / "run_source_metadata.json")
    provenance_errors, _ = _retained_input_config_provenance(optimizer_dir, config_path, run_source)
    errors.extend(provenance_errors)
    if run_source.get("budget") != 16000:
        errors.append("run-source budget is not 16000")
    if run_source.get("checkpoints") != list(EXTENSION_CHECKPOINTS):
        errors.append("run-source checkpoint lattice is not 2k through 16k")
    if run_source.get("initial_population_seed_contract") != SEED_CONTRACT:
        errors.append("run-source historical seed contract is missing or changed")
    if run_source.get("initial_sampling_seeds") != INITIAL_SAMPLING_SEEDS:
        errors.append("run-source exact initializer sampling seeds are missing or changed")
    return errors


def _initializer_errors(optimizer_dir: Path) -> list[str]:
    errors: list[str] = []
    topology_dir = optimizer_dir / "optimization" / MATERIAL / TOPOLOGY
    for seed in SEEDS:
        seed_dir = topology_dir / f"seed{seed}"
        try:
            trajectory = _read_json(seed_dir / "trajectory_metadata.json")
            sampling = trajectory["initial_population_sampling"]
            expected_seed = INITIAL_SAMPLING_SEEDS[f"{MATERIAL}/{TOPOLOGY}/{seed}"]
            expected_fields = {
                "initial_sampling_seed_contract_id": SEED_CONTRACT["identifier"],
                "initial_sampling_seed_namespace": SEED_CONTRACT["namespace"],
                "initial_sampling_seed_derivation_suffix": SEED_CONTRACT["derivation_suffix"],
                "initial_sampling_seed": expected_seed,
            }
            for field, expected in expected_fields.items():
                errors.extend(parity.compare_values(
                    sampling.get(field), expected, f"seed{seed}.trajectory.initializer.{field}",
                ))
            errors.extend(parity.compare_values(trajectory.get("budget"), 16000, f"seed{seed}.trajectory.budget"))
            errors.extend(parity.compare_values(
                trajectory.get("checkpoints"), list(EXTENSION_CHECKPOINTS), f"seed{seed}.trajectory.checkpoints",
            ))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"seed{seed} initializer metadata invalid: {type(exc).__name__}: {exc}")
    return errors


def _extension_accounting_errors(
    cells: Mapping[tuple[int, int], tuple[Path, Mapping[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    for (seed, budget), (_path, record) in sorted(cells.items()):
        errors.extend(
            f"seed{seed}.B{budget}: {error}"
            for error in parity._validate_checkpoint_accounting(record, seed, budget)
        )
        errors.extend(
            f"seed{seed}.B{budget}: {error}"
            for error in _checkpoint_budget_metadata_errors(record, "extension", 16000)
        )
        if record.get("disk_resume_used") is not False:
            errors.append(f"seed{seed}.B{budget}: disk resume was used or is unrecorded")
    return errors


def _final_optimizer_errors(
    optimizer_dir: Path, cells: Mapping[tuple[int, int], tuple[Path, Mapping[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    topology_dir = optimizer_dir / "optimization" / MATERIAL / TOPOLOGY
    for seed in SEEDS:
        try:
            state = _read_json(topology_dir / f"seed{seed}" / "optimizer_checkpoint.json")
            required = {
                "unique_evaluations": 16000,
                "total_budget": 16000,
                "requested_unique_budget": 16000,
                "hard_max_budget": 16000,
                "population_schedule_terminal_budget": 8000,
                "initial_population_size": 180,
                "minimum_population_size": 4,
                "memory_update_batch_size": 180,
            }
            for field, expected in required.items():
                errors.extend(parity.compare_values(
                    state.get(field), expected, f"seed{seed}.optimizer_checkpoint.{field}",
                ))
            cache = state.get("cache")
            if not isinstance(cache, list) or len(cache) != 16000:
                errors.append(f"seed{seed}.optimizer_checkpoint cache does not contain 16000 evaluations")
            elif len({tuple(row[0]) for row in cache if isinstance(row, list) and len(row) == 2}) != 16000:
                errors.append(f"seed{seed}.optimizer_checkpoint cache keys are not 16000 unique designs")
            population = state.get("population")
            final_record = cells[(seed, 16000)][1]
            if not isinstance(population, list) or len(population) != int(final_record["population_size"]):
                errors.append(f"seed{seed}.optimizer_checkpoint population size differs from B16000 record")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"seed{seed} final optimizer state invalid: {type(exc).__name__}: {exc}")
    return errors


def _common_grid_errors(
    optimizer_dir: Path, protocol: Mapping[str, Any],
    cells: Mapping[tuple[int, int], tuple[Path, Mapping[str, Any]]],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    outcomes: dict[str, Any] = {}
    topology_dir = optimizer_dir / "optimization" / MATERIAL / TOPOLOGY
    for seed in SEEDS:
        seed_dir = topology_dir / f"seed{seed}"
        try:
            candidates = [seed_dir / "final_common_grid_selection.json", seed_dir / "common_grid_selection.json"]
            present = [path for path in candidates if path.is_file()]
            if len(present) != 1:
                raise ValueError(f"expected one common-grid result file, found {present}")
            selection = _read_json(present[0])
            errors.extend(parity.compare_values(
                selection.get("common_validation_grid_id"), protocol["common_grid_id"],
                f"seed{seed}.common_grid.common_validation_grid_id",
            ))
            selected = parity._final_selection_projection(selection["selected"])
            if selected["evaluation_status"] != "PHYSICS_EVALUATED" or selected["geometry_valid"] is not True:
                errors.append(f"seed{seed} common-grid selected finalist lacks valid physics/geometry evidence")
            finalists = selection.get("validated_finalists")
            if not isinstance(finalists, list) or not finalists:
                errors.append(f"seed{seed} common-grid finalist list is empty or malformed")
                finalist_count = 0
            else:
                projected_finalists = [parity._final_selection_projection(row) for row in finalists]
                finalist_count = len(projected_finalists)
                rank_keys = [row["search_source_rank_key"] for row in projected_finalists]
                if rank_keys != sorted(rank_keys):
                    errors.append(f"seed{seed} common-grid finalists are not in rank order")
            final_record = cells[(seed, 16000)][1]
            errors.extend(parity.compare_values(
                selected["design"], final_record.get("common_grid_selected_design"),
                f"seed{seed}.B16000.common_grid_selected_design",
            ))
            errors.extend(parity.compare_values(
                selected["metrics"], final_record.get("common_grid_metrics"),
                f"seed{seed}.B16000.metrics.common_grid",
            ))
            outcomes[str(seed)] = {
                "common_grid_id": selection.get("common_validation_grid_id"),
                "finalist_count": finalist_count,
                "selected_feasible": selected["feasible"],
                "selected_filter_feasible": selected["filter_feasible"],
                "selected_max_violation": selected["max_violation"],
                "selected_objective": selected["objective"],
                "selected_metrics": selected["metrics"],
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"seed{seed} common-grid result invalid: {type(exc).__name__}: {exc}")
    return errors, outcomes


def _outcome_summary(
    control_cells: Mapping[tuple[int, int], tuple[Path, Mapping[str, Any]]],
    extension_cells: Mapping[tuple[int, int], tuple[Path, Mapping[str, Any]]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for seed in SEEDS:
        old = control_cells[(seed, 8000)][1]
        new = extension_cells[(seed, 16000)][1]
        output[str(seed)] = {
            "objective": {
                "at_8000": old["objective"],
                "at_16000": new["objective"],
                "delta_16000_minus_8000": float(new["objective"]) - float(old["objective"]),
            },
            "max_violation": {
                "at_8000": old["max_violation"],
                "at_16000": new["max_violation"],
                "delta_16000_minus_8000": float(new["max_violation"]) - float(old["max_violation"]),
            },
            "feasibility": {
                "at_8000": {
                    "filter_feasible": old["filter_feasible"],
                    "feasible": old["feasible"],
                    "geometry_valid": old["geometry_valid"],
                },
                "at_16000": {
                    "filter_feasible": new["filter_feasible"],
                    "feasible": new["feasible"],
                    "geometry_valid": new["geometry_valid"],
                },
            },
            "metrics": {"at_8000": old["metrics"], "at_16000": new["metrics"]},
            "objective_parts": {"at_8000": old["objective_parts"], "at_16000": new["objective_parts"]},
        }
    return output


def verify_extension(
    *,
    control_run_dir: Path = CONTROL_RUN_DIR,
    extension_run_dir: Path = EXTENSION_RUN_DIR,
    extension_config: Path = EXTENSION_CONFIG,
    gate_d_bundle: Path = GATE_D_BUNDLE,
    output_dir: Path = RESULT_BUNDLE,
) -> dict[str, Any]:
    output_dir = _review_bundle_path(output_dir)
    errors: list[str] = []
    gates: dict[str, bool] = {}
    control_run_dir = control_run_dir.resolve()
    extension_run_dir = extension_run_dir.resolve()
    try:
        gate_d = _read_json(gate_d_bundle / "parity_summary.json")
        control_status = _read_json(control_run_dir.parent / "status.json")
        control_ok = (
            gate_d.get("status") == "PASS"
            and gate_d.get("checkpoint_comparison_count") == 8
            and gate_d.get("mismatches") == []
            and all(gate_d.get("gates", {}).values())
            and control_status.get("state") == "COMPLETED"
            and control_status.get("exit_code") == 0
        )
        if gate_d.get("overlap_run_dir") and _path_key(Path(str(gate_d["overlap_run_dir"]))) != _path_key(control_run_dir):
            control_ok = False
        gates["accepted_8k_control"] = control_ok
        if not control_ok:
            errors.append("accepted Gate-D control is no longer a clean zero-mismatch PASS")
    except (OSError, ValueError, TypeError) as exc:
        gates["accepted_8k_control"] = False
        errors.append(f"Gate-D control evidence invalid: {type(exc).__name__}: {exc}")

    control_run_errors = _control_run_errors(control_run_dir, OVERLAP_CONFIG)
    extension_run_errors = _control_run_errors(extension_run_dir, extension_config)
    errors.extend(control_run_errors)
    errors.extend(extension_run_errors)
    gates["run_controls_no_session_resume"] = not control_run_errors and not extension_run_errors

    try:
        overlap_cfg, _extension_cfg, overlap_protocol, extension_protocol = _resolve_configs(
            OVERLAP_CONFIG, extension_config,
        )
        config_errors = _config_errors(overlap_cfg, _extension_cfg, overlap_protocol, extension_protocol)
        errors.extend(config_errors)
        gates["protocol_inputs"] = not config_errors
    except Exception as exc:
        gates["protocol_inputs"] = False
        errors.append(f"config protocol resolution failed: {type(exc).__name__}: {exc}")
        extension_protocol = None

    control_cells = parity._read_cells(control_run_dir)
    extension_cells = parity._read_cells(extension_run_dir)
    control_lattice_errors = [
        f"control: {item}" for item in parity.validate_checkpoint_lattice(control_cells)
    ]
    expected_extension = _expected_lattice(EXTENSION_CHECKPOINTS)
    actual_extension = set(extension_cells)
    extension_lattice_errors = []
    if actual_extension != expected_extension:
        extension_lattice_errors.append(
            f"extension checkpoint lattice mismatch: missing={sorted(expected_extension-actual_extension)}, "
            f"extra={sorted(actual_extension-expected_extension)}"
        )
    errors.extend(control_lattice_errors + extension_lattice_errors)
    gates["extension_checkpoint_lattice"] = not extension_lattice_errors
    gates["control_checkpoint_lattice"] = not control_lattice_errors

    prefix_rows: list[dict[str, Any]] = []
    for seed in SEEDS:
        for budget in OVERLAP_CHECKPOINTS:
            row_errors: list[str] = []
            lifecycle_counter_observations: dict[str, Any] = {}
            if (seed, budget) in control_cells and (seed, budget) in extension_cells:
                control_record = control_cells[(seed, budget)][1]
                extension_record = extension_cells[(seed, budget)][1]
                row_errors = _prefix_record_mismatches(
                    control_record, extension_record, seed, budget,
                )
                try:
                    lifecycle_counter_observations = _prefix_finalization_counter_observations(
                        control_record, extension_record,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    lifecycle_counter_observations = {"unavailable": f"{type(exc).__name__}: {exc}"}
            else:
                row_errors.append("matching control/extension checkpoint record is missing")
            prefix_rows.append({
                "seed": seed, "checkpoint_budget": budget,
                "status": "PASS" if not row_errors else "FAIL",
                "mismatch_count": len(row_errors), "mismatches": row_errors,
                "excluded_finalization_counter_observations": lifecycle_counter_observations,
            })
            errors.extend(f"prefix seed{seed}/B{budget}: {item}" for item in row_errors)
    gates["prefix_0_to_8k_parity"] = len(prefix_rows) == 8 and all(row["status"] == "PASS" for row in prefix_rows)

    metadata_errors: list[str] = []
    input_config_provenance: dict[str, Any] = {}
    if extension_protocol is not None:
        try:
            metadata_errors = _extension_metadata_errors(extension_run_dir, extension_protocol, extension_config)
            run_source = _read_json(extension_run_dir / "metadata" / "run_source_metadata.json")
            _, input_config_provenance = _retained_input_config_provenance(
                extension_run_dir, extension_config, run_source,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            metadata_errors.append(f"extension run-source metadata invalid: {type(exc).__name__}: {exc}")
    errors.extend(metadata_errors)
    gates["run_metadata_and_grid_provenance"] = not metadata_errors

    initializer_errors = _initializer_errors(extension_run_dir)
    errors.extend(initializer_errors)
    gates["initializer_evidence"] = not initializer_errors

    accounting_errors = _extension_accounting_errors(extension_cells)
    errors.extend(accounting_errors)
    gates["accounting_physics_and_cold_start"] = not accounting_errors and not extension_lattice_errors

    state_errors = _final_optimizer_errors(extension_run_dir, extension_cells)
    errors.extend(state_errors)
    gates["final_optimizer_state_and_cache"] = not state_errors

    cache_prefix_errors, cache_frequency_versions_checked = _cache_prefix_errors(
        control_run_dir, extension_run_dir,
    )
    errors.extend(cache_prefix_errors)
    gates["prefix_0_to_8k_cache_sequence"] = not cache_prefix_errors

    common_grid_outcomes: dict[str, Any] = {}
    common_grid_errors: list[str] = []
    if extension_protocol is not None:
        common_grid_errors, common_grid_outcomes = _common_grid_errors(
            extension_run_dir, extension_protocol, extension_cells,
        )
    else:
        common_grid_errors.append("extension config protocol did not resolve")
    errors.extend(common_grid_errors)
    gates["common_grid_finalists_and_feasibility"] = not common_grid_errors

    outcomes: dict[str, Any] = {}
    try:
        if all((seed, 8000) in control_cells for seed in SEEDS) and all(
            (seed, 16000) in extension_cells for seed in SEEDS
        ):
            outcomes = _outcome_summary(control_cells, extension_cells)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"8k/16k outcome summary failed: {type(exc).__name__}: {exc}")

    summary = {
        "status": "PASS" if all(gates.values()) and not errors else "FAIL",
        "scope": "read-only persisted-result verification; no optimizer or physics execution",
        "optimizer_executed": False,
        "physics_evaluations": 0,
        "control_run_dir": str(control_run_dir),
        "extension_run_dir": str(extension_run_dir),
        "extension_control_root": str(extension_run_dir.parent),
        "extension_config": str(extension_config.resolve()),
        "comparison_scope": {
            "material": MATERIAL,
            "topology": TOPOLOGY,
            "seeds": list(SEEDS),
            "control_checkpoints": list(OVERLAP_CHECKPOINTS),
            "extension_checkpoints": list(EXTENSION_CHECKPOINTS),
            "prefix_comparison_count": len(prefix_rows),
        },
        "allowed_prefix_differences": list(PREFIX_TOTAL_RUN_BUDGET_FIELDS),
        "prefix_excluded_finalization_counter_fields": list(PREFIX_FINALIZATION_COUNTER_FIELDS),
        "prefix_comparisons": prefix_rows,
        "gates": gates,
        "retained_input_config_provenance": input_config_provenance,
        "cache_frequency_versions_prefix_checked": cache_frequency_versions_checked,
        "outcomes_by_seed": outcomes,
        "common_grid_by_seed": common_grid_outcomes,
        "two_seed_inference_limit": "Descriptive results for two specified seeds only; no robust success/failure rate inference.",
        "errors": errors,
    }
    _write_result_outputs(output_dir, summary)
    return summary


def _write_result_outputs(output_dir: Path, summary: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "extension_summary.json", summary)
    with (output_dir / "prefix_comparisons.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = (
            "seed", "checkpoint_budget", "status", "mismatch_count", "mismatches",
            "excluded_finalization_counter_observations",
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in summary["prefix_comparisons"]:
            writer.writerow({
                **row,
                "mismatches": " | ".join(row["mismatches"]),
                "excluded_finalization_counter_observations": json.dumps(
                    row.get("excluded_finalization_counter_observations", {}), sort_keys=True,
                ),
            })
    lines = [
        "# Stage 3.9B 16k budget-extension review", "",
        f"Status: **{summary['status']}**", "",
        "The 0–8k extension prefix is compared with the independently accepted 8k×2 control.",
        "Only `hard_max_budget` is excluded from prefix equality because the extension's total-run hard limit is 16,000;",
        "`terminal_budget` and `population_schedule_terminal_budget` are both required to remain 8,000.",
        "Designs, ranking traces, objectives/components, optimizer/search counters, cache trajectory and schedule state remain gated.",
        "Finalization-only counters (`solved_frequency_points`, `validation_evaluations`, `validation_physics_failures`,",
        "`validation_frequency_points`) are reported per checkpoint but excluded from prefix equality because common-grid",
        "validation runs only after a run's terminal optimizer checkpoint.",
        "",
        "## Gates", "",
    ]
    for gate, value in summary["gates"].items():
        lines.append(f"- {gate}: **{'PASS' if value else 'FAIL'}**")
    lines.extend(["", "## Prefix checkpoint comparisons", "", "| Seed | Budget | Status | Mismatches |", "|---:|---:|---|---:|"])
    for row in summary["prefix_comparisons"]:
        lines.append(f"| {row['seed']} | {row['checkpoint_budget']} | {row['status']} | {row['mismatch_count']} |")
    lines.extend(["", "## Excluded finalization-counter observations", ""])
    for row in summary["prefix_comparisons"]:
        observations = row.get("excluded_finalization_counter_observations", {})
        differing = {
            name: values for name, values in observations.items()
            if isinstance(values, Mapping) and values.get("control") != values.get("extension")
        }
        if differing:
            lines.append(
                f"- Seed {row['seed']} / B{row['checkpoint_budget']}: "
                f"`{json.dumps(differing, sort_keys=True)}`"
            )
    provenance = summary.get("retained_input_config_provenance", {})
    if provenance:
        lines.extend([
            "", "## Retained input-config provenance", "",
            f"- Normalized content matches approved config: **{provenance.get('normalized_content_matches')}**.",
            f"- Approved config SHA-256 (line endings normalized): `{provenance.get('approved_normalized_content_sha256')}`.",
            f"- Retained input config SHA-256 (line endings normalized): `{provenance.get('retained_normalized_content_sha256')}`.",
            f"- Optional run-source path field present: `{provenance.get('run_source_path_field_present')}`.",
        ])
    lines.extend(["", "## Per-seed changes from 8k to 16k", ""])
    if summary["outcomes_by_seed"]:
        for seed, outcome in summary["outcomes_by_seed"].items():
            obj = outcome["objective"]
            violation = outcome["max_violation"]
            feas = outcome["feasibility"]
            lines.extend([
                f"### Seed {seed}", "",
                f"- Objective delta (16k - 8k): {obj['delta_16000_minus_8000']:.12g}.",
                f"- Maximum-violation delta (16k - 8k): {violation['delta_16000_minus_8000']:.12g}.",
                f"- Feasibility at 8k: {feas['at_8000']}; at 16k: {feas['at_16000']}.",
                "",
            ])
    lines.extend(["## Common-grid results", ""])
    for seed, result in summary["common_grid_by_seed"].items():
        lines.append(
            f"- Seed {seed}: finalists={result['finalist_count']}, "
            f"filter_feasible={result['selected_filter_feasible']}, "
            f"feasible={result['selected_feasible']}, "
            f"max_violation={result['selected_max_violation']:.12g}."
        )
    lines.extend(["", "## Errors", ""])
    lines.extend(f"- {error}" for error in summary["errors"]) if summary["errors"] else lines.append("- None.")
    lines.extend(["", summary["two_seed_inference_limit"], ""])
    (output_dir / "extension_summary.md").write_text("\n".join(lines), encoding="utf-8")


def preflight_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Stage 3.9B read-only 16k config preflight.")
    parser.add_argument("--overlap-config", type=Path, default=OVERLAP_CONFIG)
    parser.add_argument("--extension-config", type=Path, default=EXTENSION_CONFIG)
    parser.add_argument("--gate-b-bundle", type=Path, default=GATE_B_BUNDLE)
    parser.add_argument("--gate-d-bundle", type=Path, default=GATE_D_BUNDLE)
    parser.add_argument("--control-run-dir", type=Path, default=CONTROL_RUN_DIR)
    parser.add_argument("--extension-control-root", type=Path, default=EXTENSION_RUN_DIR.parent)
    parser.add_argument("--output-dir", type=Path, default=PREFLIGHT_BUNDLE)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"output directory is not empty: {args.output_dir}")
    summary = run_config_preflight(
        overlap_config=args.overlap_config,
        extension_config=args.extension_config,
        gate_b_bundle=args.gate_b_bundle,
        gate_d_bundle=args.gate_d_bundle,
        control_run_dir=args.control_run_dir,
        extension_control_root=args.extension_control_root,
        output_dir=args.output_dir,
    )
    print(f"{summary['status']}: Stage 3.9B read-only config preflight")
    print(f"review artifacts: {args.output_dir.resolve()}")
    if summary["errors"]:
        for error in summary["errors"][:30]:
            print(f"- {error}")
    return 0 if summary["status"] == "PASS" else 1


def verifier_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify persisted Stage 3.9B 16k budget-extension results.")
    parser.add_argument("--control-run-dir", type=Path, default=CONTROL_RUN_DIR)
    parser.add_argument("--extension-run-dir", type=Path, default=EXTENSION_RUN_DIR)
    parser.add_argument("--extension-config", type=Path, default=EXTENSION_CONFIG)
    parser.add_argument("--gate-d-bundle", type=Path, default=GATE_D_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=RESULT_BUNDLE)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"output directory is not empty: {args.output_dir}")
    summary = verify_extension(
        control_run_dir=args.control_run_dir,
        extension_run_dir=args.extension_run_dir,
        extension_config=args.extension_config,
        gate_d_bundle=args.gate_d_bundle,
        output_dir=args.output_dir,
    )
    print(f"{summary['status']}: {summary['comparison_scope']['prefix_comparison_count']} prefix checkpoint comparisons")
    print(f"review artifacts: {args.output_dir.resolve()}")
    if summary["errors"]:
        print(f"mismatch count: {len(summary['errors'])}")
        for error in summary["errors"][:30]:
            print(f"- {error}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(verifier_main())
