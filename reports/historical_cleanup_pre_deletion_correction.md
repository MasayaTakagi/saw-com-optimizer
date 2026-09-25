# Historical Cleanup Pre-Deletion Correction

Date: 2026-09-25

## Git state

- Branch: `codex-historical-cleanup`
- Starting HEAD: `baed01c365a5a7d0f87ae03344475037d9e476b8`
- Ending HEAD: `baed01c365a5a7d0f87ae03344475037d9e476b8` (correction remains
  in the worktree; no commit was created)
- Freeze tag: `archive/pre-historical-cleanup-2026-09-25`
- Freeze target: `444d3a430797d32d688f74bb76ffda615cddfba0`
- Remote verification: a successful `git ls-remote --tags origin` check
  confirmed annotated tag object
  `df98df9ff96e386c47ec442cbd337055f57d5d70` and peeled commit
  `444d3a430797d32d688f74bb76ffda615cddfba0`. A later repeat check could not
  connect to GitHub, so no newer remote state is claimed.

## Corrections

- Corrected the branch name in the freeze and architecture escalation reports
  to `codex-historical-cleanup`.
- Moved optimizer-independent checkpoint evidence derivation to
  `src/sawopt/optimization/convergence_evidence.py`. The old studies module is
  a temporary compatibility re-export for historical callers; the reusable
  L-SHADE serializer now imports the canonical module.
- Restored both Stage 3.8C configs' `final_confirmation_test_gate` reference to
  `reports/stage3_8c_r1_2_final_confirmation_test_gate.json`. No copy of the
  gate was left under `runs/`. Existing run paths elsewhere in those historical
  configs are retained as historical-only references for next-phase removal.
- Added evidence-level labels to the experiment register: retained result
  documents for Prototype and 50 Ω hybrid; retained config/README/decision
  records with no canonical raw run for Stage 3.1–3.4b; retained
  config/README/escalation evidence with no canonical raw run for Stage
  3.3–3.5; canonical run evidence for Stage 3.6 and 3.7; and canonical
  production run, review bundle, and closeout evidence for Stage 3.8C.
- Added released-DMS characterization for canonical exports, fields, section
  geometry, S-parameters, and key metrics. DMS topology, L-SHADE serialization,
  and convergence evidence parity are covered by the focused test set.
- No historical source, test, config, experiment descriptor, report, handoff,
  or run was bulk-deleted. The user-provided handoff documents remain
  unstaged.

## Dependency audit

| Classification | Findings |
|---|---|
| Keep | `problem/dms_topologies.py`, `problem/released_dms.py`, `optimization/convergence_evidence.py`, `studies/dms_topology_common.py`, and `studies/lshade_records.py` hold reusable topology, released-filter, telemetry, DMS-helper, and record-serialization responsibilities. The reusable L-SHADE serializer now imports canonical convergence evidence. |
| Extracted | Released DMS model/simulation, DMS topology definitions, DMS study-common helpers, L-SHADE record serialization, and convergence evidence have canonical modules outside Stage-numbered runners. Stage 3.8 imports public DMS helper exports rather than private helper names. |
| Historical-only | Study-to-study edges remain among `optimizer_ab.py`, `convergence.py`, `continuation.py`, `search_efficiency.py`, `phase_c_*`, `matched_protocol_parity.py`, Stage 3.6 runners, Stage 3.7 runners, and the Stage 3.8 screen. These edges are confined to old protocols and their adapters; they are candidates for coordinated next-phase removal. |
| Compatibility / delete-next-phase | `studies/convergence_evidence.py` is a temporary three-symbol re-export. `optimization/stage2_study.py`, `stage32_study.py`, `stage33_study.py`, `stage331_preprod.py`, `convergence_study.py`, and `hybrid_study.py` are legacy shims. `sawopt.__main__` retains historical CLI aliases and lazy imports. Remove these with their old runners and compatibility tests. |
| Historical-only / delete-next-phase | `reporting/search_space_diagnostics.py` is used by old search-efficiency code; `reporting/stage3_8_review_bundle.py` is Stage-specific. Stage 3.8C configs retain pre-existing `runs/` inputs and historical runner paths. Remove the adapters/configs together in the deletion phase; this correction introduced no new `runs/` dependency. |

Static source inspection found no Stage-numbered imports in the canonical
`problem/dms_topologies.py`, `problem/released_dms.py`, or
`optimization/convergence_evidence.py` modules. The branch's older runners,
registry entries, compatibility shims, and historical report tooling remain
present by design and are explicitly mapped above.

## Tests

- Focused command:
  `.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/unit/test_architecture.py tests/unit/optimization/test_convergence_evidence.py tests/unit/optimization/test_lshade_record_serialization.py tests/unit/io/test_checkpoints.py tests/unit/problem/test_dms_topologies.py tests/unit/studies/test_stage3_6_gate2a.py tests/unit/studies/test_stage3_8c_r1_geometry_gate.py tests/unit/studies/test_stage3_8c_production_closeout.py -q`
- Focused result: **72 passed** in 31.54 s.
- Full command: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q`
- Full result: **297 passed, 14 subtests passed** in 106.24 s.
- CI: this branch push does not trigger the configured GitHub Actions workflow;
  the workflow is limited to `main`/`master` pushes and pull requests. No
  workflow change or PR was made.

## Numerical impact

**NO NUMERICAL EXPERIMENT RERUN**

**NO COM/NETWORK/OBJECTIVE/OPTIMIZER SEMANTICS CHANGE**

No canonical saved numerical output was modified. Changes in this pass were
ownership/import, compatibility, provenance, config-reference restoration,
and characterization coverage only.

## Next-phase readiness

**READY_FOR_HISTORICAL_DELETION**

The freeze tag is recorded and its remote target was verified, branch
provenance is corrected, reusable dependencies are extracted, remaining
historical references are mapped, and focused plus full regression tests pass.
The next phase can remove the mapped historical runners, tests, configs,
experiments, CLI aliases, compatibility shims, and Stage-specific reporting as
a coordinated change while retaining the experiment register and current
baseline.
