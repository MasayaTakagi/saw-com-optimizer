"""Stage 3.7B literature COM reconstruction gate.

This stage deliberately stops at the source/convention gate when critical
source metadata is unavailable. It writes an auditable package and never
starts B28 scaling or optimization from a blocked profile.
"""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..core.literature_com import profile_from_mapping


ROOT = Path(__file__).resolve().parents[3]
STOP_MARKER = "STAGE3_7B_COM_MAPPING_BLOCKED_STOP"


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _git(command: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *command], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"UNAVAILABLE: {exc}"
    return result.stdout.strip()


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _source_values(profile_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"parameter": "velocity", "value": profile_data["velocity_m_s"], "unit": "m/s", "status": "CONFIRMED"},
        {"parameter": "kappa_p", "value": profile_data["kappa_p_percent"], "unit": "%", "status": "CONFIRMED"},
        {"parameter": "alpha_n", "value": profile_data["alpha_n_value"], "unit": "10^-5 ohm^(-1/2)", "status": "CONFIRMED"},
        {"parameter": "C_n", "value": profile_data["capacitance_n_value"], "unit": "10^-5 pF/um", "status": "CONFIRMED"},
        {"parameter": "gamma_p", "value": profile_data["gamma_p"], "unit": "1", "status": "CONFIRMED"},
    ]


def _conversion_rows() -> list[dict[str, Any]]:
    return [
        {"parameter": "kappa", "source_definition": "kappa_p = kappa * lambda", "solver_value": "kappa = (kappa_p / 100) / lambda", "status": "BLOCKED", "reason": "Exact source equation/phase reference not confirmed."},
        {"parameter": "alpha", "source_definition": "alpha_n = alpha_p / sqrt(W/lambda), alpha_p = alpha * lambda", "solver_value": "alpha = alpha_n * sqrt(W/lambda) / lambda", "status": "BLOCKED", "reason": "Exact source normalization and electrical reference not confirmed."},
        {"parameter": "capacitance", "source_definition": "C_n = C * lambda / W", "solver_value": "C = C_n * W/lambda; pF/um -> 1e-6 F/m", "status": "BLOCKED", "reason": "Exact source aperture definition not confirmed."},
        {"parameter": "gamma", "source_definition": "gamma_p = gamma * lambda", "solver_value": "gamma = gamma_p / lambda", "status": "BLOCKED", "reason": "Amplitude versus power loss convention not confirmed from the primary source."},
        {"parameter": "loss_db_per_lambda", "source_definition": "amplitude attenuation", "solver_value": "gamma_p * 20 / ln(10)", "status": "BLOCKED", "reason": "Cannot promote without source loss convention."},
    ]


def _audit_text(profile_data: Mapping[str, Any], profile: Any, status: str) -> str:
    source = profile_data["source"]
    return f"""# Stage 3.7B COM conversion audit

## Source lock

- Primary source: {source['title']}
- Authors: {source['authors']}
- Citation: {source['venue']}, DOI [{source['doi']}]({source['url']})
- Table: {source['table']}
- Locked condition: {source['source_condition']}
- Substrate: {profile.substrate}
- Electrode material: unresolved in the accessible primary-text body; the task target is Al, but no other paper is mixed in.

The source reports at 25 °C: `v=4045 m/s`, `kappa_p=-18.96 %`,
`alpha_n=92.566 x 10^-5 ohm^(-1/2)`, `C_n=52.80 x 10^-5 pF/um`, and
`gamma_p=0.002684`. These raw values are preserved in the profile and CSV.

## Current solver convention

The repository uses exp(+j omega t), x increasing left-to-right, peak voltage
V, terminal current into the transducer, and acoustic power normalization
`|R|^2 - |S|^2`:

```text
dR/dx = -j delta R + j kappa S + j alpha V
dS/dx = -j kappa* R + j delta S - j alpha* V
dI/dx = -2j alpha* R - 2j alpha S + j omega C V
delta = omega/v - 2 pi/lambda - j gamma
```

The solver units are `v [m/s]`, `kappa [1/m]`, `alpha [sqrt(S)/m]`,
`C [F/m]`, and `gamma [1/m]`. The existing M0 `FixedProvider` is unchanged.

## Candidate mapping (not promoted)

The normalized identities recorded for audit are:

```text
kappa_p = kappa * lambda
alpha_p = alpha * lambda
alpha_n = alpha_p / sqrt(W/lambda)
C_n = C * lambda / W
gamma_p = gamma * lambda
```

The corresponding dimensional formulas are `kappa=(kappa_p/100)/lambda`,
`alpha=alpha_n*sqrt(W/lambda)/lambda`, `C=C_n*W/lambda`, and
`gamma=gamma_p/lambda`. The source capacitance scale converts through
`1 pF/um = 1e-6 F/m`. If `gamma_p` is confirmed to be amplitude loss, the
configuration equivalent is `loss_db_per_lambda=gamma_p*20/ln(10)`.

## Status by parameter

| Item | Status | Reason |
|---|---|---|
| `v` and Table 2 value | CONFIRMED | Explicit table value at 25 °C. |
| `kappa_p`, `alpha_n`, `C_n`, `gamma_p` raw values | CONFIRMED | Explicit Table 2 values and displayed units. |
| normalization equations | BLOCKED | Rendered primary equations require exact source-level confirmation of symbols and references. |
| electrode material | BLOCKED | Primary body says metal electrodes but does not identify Al. |
| aperture `W` | BLOCKED | Native resonator aperture is not stated in the accessible source text. |
| phase/reference registry | BLOCKED | No complete complex phase/reference data is given. |
| attenuation convention | BLOCKED | Amplitude versus power convention is not explicit enough for promotion. |

## Decision

`{status}`. No fallback to M0, no source mixing, no sign flip, phase rotation,
factor-of-two correction, or empirical fitting was used.
"""


def _reconstruction_text(profile_data: Mapping[str, Any], status: str) -> str:
    geometry = profile_data["device_geometry"]
    return f"""# Source-device reconstruction

## Native resonator

The source identifies λ={profile_data['wavelength_um']} µm, h={profile_data['wavelength_um'] * profile_data['h_over_lambda']:.4f} µm,
duty={profile_data['metallization_ratio']}, {geometry['idt_fingers']} IDT fingers,
and {geometry['reflector_gratings_each_side']} reflector gratings per side.
It does not state the aperture, electrode material, terminal convention, or
enough phase information for an auditable native reconstruction. The
resonator calculation was therefore not run; a guessed aperture would violate
the source-device gate.

## Native three-IDT DMS

The source reports pitches 1.08 µm (input), 1.073 µm (output), and 1.1 µm
(reflector), h=0.1728 µm, and duty=0.65. It does not provide complete IDT
counts, reflector boundaries, aperture, gap/terminal definitions, or electrode
polarity registry. A partial DMS setup would require guessed geometry and is
not a production validation.

## Gate result

`{status}`. Native resonator and DMS rows are recorded as not run. No B28
scaling, fixed-design sensitivity, or optimization was started. The next
approved branch is source-level confirmation or a separately scoped FEM COM
extraction; FEM itself is not executed in this stage.
"""


def run_stage37b(config_path: str | Path, run_path: str | Path, resume: bool = False) -> dict[str, Any]:
    del resume
    config_path = Path(config_path)
    raw_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_path = (config_path.parent / raw_cfg["literature_profile_file"]).resolve()
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    profile = profile_from_mapping(profile_data)
    out = Path(run_path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata").mkdir(exist_ok=True)
    (out / "results").mkdir(exist_ok=True)

    source = profile_data["source"]
    _write_csv(out / "results" / "literature_source_values.csv", _source_values(profile_data))
    _write_csv(out / "results" / "normalized_to_solver_conversion.csv", _conversion_rows())
    _write_csv(out / "results" / "native_resonator_results.csv", [{
        "status": "NOT_RUN_COM_MAPPING_BLOCKED",
        "wavelength_um": profile.wavelength_um,
        "idt_fingers": profile_data["device_geometry"]["idt_fingers"],
        "reflector_gratings_each_side": profile_data["device_geometry"]["reflector_gratings_each_side"],
        "reason": "native aperture and critical convention metadata are missing",
    }])
    _write_csv(out / "results" / "native_dms_results.csv", [{
        "status": "NOT_RUN_INCOMPLETE_SOURCE_GEOMETRY",
        "input_pitch_um": profile_data["device_geometry"]["dms_pitch_input_um"],
        "output_pitch_um": profile_data["device_geometry"]["dms_pitch_output_um"],
        "reflector_pitch_um": profile_data["device_geometry"]["dms_pitch_reflector_um"],
        "reason": "counts, aperture, gaps, terminations, and polarity registry are missing",
    }])

    (out / "metadata" / "profile_snapshot.yaml").write_text(
        yaml.safe_dump(_clean(profile_data), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (out / "metadata" / "repository_audit.json").write_text(json.dumps({
        "branch": _git(["branch", "--show-current"]),
        "head": _git(["rev-parse", "HEAD"]),
        "status": _git(["status", "--short"]),
        "current_com_files": [
            "src/sawopt/core/com.py",
            "src/sawopt/core/models.py",
            "docs/conventions/com_convention.md",
        ],
        "stage3_7a_artifact": "runs/stage3_7_material_com_50ohm_sanity_final",
        "stage3_7a_stop_marker": "STAGE3_7_COM_MAPPING_BLOCKED_STOP",
        "primary_source": source,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    status = STOP_MARKER
    (out / "com_conversion_audit.md").write_text(
        _audit_text(profile_data, profile, status), encoding="utf-8"
    )
    (out / "source_device_reconstruction.md").write_text(
        _reconstruction_text(profile_data, status), encoding="utf-8"
    )
    (out / "test_summary.md").write_text(
        "# Test summary\n\n"
        "The conversion adapter is covered by `tests/unit/core/test_literature_com.py`. "
        "The Stage 3.7B gate intentionally performs no native-device numerical run "
        "because the primary source is blocked at the convention/aperture gate.\n",
        encoding="utf-8",
    )
    (out / "stage3_7b_literature_com_reconstruction_summary.md").write_text(
        f"""# Stage 3.7B literature COM reconstruction summary

Primary source: {source['title']} ({source['doi']}).

The raw 25 °C Table 2 values were captured, but the profile remains
`REFERENCE_ONLY`. The primary source does not provide enough explicit
electrode-material, aperture, phase/reference, and terminal information to
meet the source-device reconstruction gate. The normalized-to-solver formulas
are therefore recorded as blocked audit candidates, not as a production
material model.

Decision: `{status}`

- Native resonator: not run; aperture is missing.
- Native 3-IDT DMS: not run; essential geometry and registry are missing.
- Passivity/reciprocity: not evaluated for a blocked source device.
- Arbitrary fitting or source mixing: none.
- B28 scaling and fixed-design sensitivity: not executed.
- 8k x 2-seed optimization: not executed.
- Recommendation: `FEM_EXTRACTION_REQUIRED` or obtain the missing source-level geometry/convention data.

The M0 FixedProvider and all prior Stage 3.6/3.7A artifacts are preserved.
""",
        encoding="utf-8",
    )
    (out / f"{STOP_MARKER}.txt").write_text(f"{STOP_MARKER}\n", encoding="utf-8")
    return {
        "run": str(out),
        "decision": status,
        "profile_id": profile.profile_id,
        "source": source["doi"],
        "b28_executed": False,
        "stop_marker": f"{STOP_MARKER}.txt",
    }


__all__ = ["run_stage37b"]
