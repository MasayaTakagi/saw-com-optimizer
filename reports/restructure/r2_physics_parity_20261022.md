# R2 deterministic physics parity evidence — 2026-10-22

**Purpose:** software-only before/after evidence for Issue #63 / Draft PR #64.
This is a bounded deterministic regression calculation, not a SAW study, an
optimizer/FE run, production work, or new physical result. No raw/checkpoint or
historical evidence was read or changed.

## Source and environment

| Item | Identity |
|---|---|
| Base | `d6c0999093e9ba841ad5bedd95004ae258c30a17` (R1-B merge) |
| R2 head tested | `f895209c5c298dfa34c875c7f6b9416ac20127e9` |
| Recipe | `scripts/verify_r2_physics_parity.py` at R2 head |
| Python | `3.12.3` |
| NumPy | `2.5.3` |
| SciPy | `1.18.1` |
| PyYAML | `6.0.3` |
| uv | `0.12.23` |
| sawopt package | `0.1.0` |
| Platform | Ubuntu/WSL2, Linux x86_64, glibc 2.39 |
| Random seed | Not applicable; no random sampling |

Both revisions were executed with the same locked environment and the same
recipe. The script records the revision it runs against and emits JSON.

## Frozen deterministic inputs used by the recipe

- COM configuration: `configs/models/com_params_hypothetical.yaml`, raw-file
  SHA-256 `ad582b7ff33b041519ded8c471c40dde550bf20a4f89f96adebc66023109ce9d`.
- Filter design (`FilterDesign`): wavelength 5.0 µm; I/O IDT pairs 24; center
  IDT pairs 16; reflector electrodes 40; IDT and reflector gaps 0.5 λ; aperture
  80 µm; metallization ratio 0.5; thickness/λ 0.04. The floating-center
  configuration is used for the filter admittance.
- Frequency vector: `numpy.linspace(730e6, 830e6, 21, dtype=np.float64)`;
  21 values from 730 MHz to 830 MHz inclusive.
- Network: independent positive-real source/load resistances 37 Ω / 91 Ω.
- Analytic P-matrix section: length 120 µm, wavelength 5 µm; velocity
  3900 m/s, κ = 3500 + 700j m⁻¹, α = 900 − 100j √S/m, capacitance
  1e−8 F/m, and amplitude attenuation 120 m⁻¹.
- One-port resonator: default `ResonatorDesign` (5 µm wavelength, 25 pairs,
  70 µm aperture, 40 reflector electrodes, zero gap λ).
- Section-chain output: reflector 20 λ, gap 0.5 λ, IDT 24 λ on port 0,
  IDT 16 λ on port 1, reflector 20 λ; each uses 5 µm wavelength and 80 µm
  aperture. Identity 2×2 real port map. The recipe also composes the filter Y
  with the resonator as a shunt branch at port 0.

No budgets, optimizer settings, seeds, specification, or search/validation
study grids are involved.

## Exact output comparison

Every output was normalized to contiguous C-order bytes in explicit little-
endian NumPy dtype before SHA-256. Base and R2-head dtype, shape, and digest
were identical for all seven arrays; comparison was exact, not tolerance-based.

| Output | dtype | shape | SHA-256 (base = head) |
|---|---|---:|---|
| P matrix | `<c16` | `(21, 3, 3)` | `55800ac060863179a25e3c9c113268397e66bb021ff1bd1e6252be39d7d93bde` |
| Filter Y | `<c16` | `(21, 2, 2)` | `a0d763e42cfedcd835f75b0e077f8d548d44e07111372bc0fd1f1eaf3bf33f8e` |
| Network S | `<c16` | `(21, 2, 2)` | `e855ab559c3629d7f6eb3cf5f4b842dce52f384420fdc18c4342fdedb1c40475` |
| Transducer gain | `<f8` | `(21,)` | `431f575aeaece225b088bfcb2d5f1785e7bc9a6be21e32a4c78236837318b07b` |
| Resonator Y | `<c16` | `(21,)` | `f56642844adde0f2f99a030c6ad1b839f453b99531be7127f754fa4769508d61` |
| Circuit-composed Y | `<c16` | `(21, 2, 2)` | `c62408810cf55641d61f9c9af1aede787241d80f6a69ef8f2377e9c4a9cde49f` |
| Section-chain Y | `<c16` | `(21, 2, 2)` | `4b6f8292f6923a0f8a1ac84f9be2bb3893a8b88588227be411c6488322839136` |

Observed diagnostics were also identical: maximum acoustic solve relative
residual `2.8689370847930224e-17`, section-chain reciprocity error
`2.1103821920200808e-17`, and maximum transducer gain
`0.14978767751619448`.

## Reproduction

From the R2 checkout, the tested recipe can be extracted and run against the
base worktree as follows (use a disposable source worktree; do not point this
at raw data):

```bash
git show f895209c5c298dfa34c875c7f6b9416ac20127e9:scripts/verify_r2_physics_parity.py > /tmp/verify_r2_physics_parity.py
git worktree add --detach /tmp/sawopt-r2-base d6c0999093e9ba841ad5bedd95004ae258c30a17
(cd /tmp/sawopt-r2-base && uv run --locked python /tmp/verify_r2_physics_parity.py > /tmp/r2-parity-base.json)
uv run --locked python scripts/verify_r2_physics_parity.py > /tmp/r2-parity-head.json
```

Run this exact comparison after producing the two files:

```bash
uv run --locked python - <<'PY'
import json
from pathlib import Path
base = json.loads(Path("/tmp/r2-parity-base.json").read_text())
head = json.loads(Path("/tmp/r2-parity-head.json").read_text())
for name in base["outputs"]:
    for key in ("dtype", "shape", "sha256"):
        assert base["outputs"][name][key] == head["outputs"][name][key], (name, key)
assert base["diagnostics"] == head["diagnostics"]
print("exact parity:", ", ".join(sorted(base["outputs"])))
PY
```

It printed `exact parity: composed_y, filter_y, network_gt, network_s,
p_matrix, resonator_y, section_chain_y`. Afterward the disposable worktree was
removed with `git worktree remove --force /tmp/sawopt-r2-base` and pruned.
The maintained recipe also records exact input settings, configuration hash,
array serialization, package versions and revision in its JSON output.

This demonstrates exact parity for these fixed representative software
inputs only. Existing analytic/reference tests provide the broader numerical
contracts; finite deterministic parity is not a claim of universal equivalence
or scientific validation of hypothetical COM inputs.
