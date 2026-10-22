# R4 optimizer ownership and migration inventory

**Tracking:** [Issue #67](https://github.com/MasayaTakagi/saw-com-optimizer/issues/67) / parent #53.
**Baseline:** `main` / R3 merge `81d18ba3bd3e29b13958d4b32dfec5585ab9d947` (PR #66).
**Status:** R4 implementation inventory and local validation record; source consolidation is implemented on the Issue #67 branch, with independent review pending. Authorization is R4-only: no R5+, COM/FE or optimizer research, Q1 qualification, checkpoint/data migration, or changes to frozen scientific contracts. This is not an acceptance claim.

## Scope and immutable behavior

Consolidate the two software packages under one `sawopt.optimization` owner. Preserve existing L-SHADE and SciPy-DE proposal mechanics, initialization/RNG order, comparator behavior including stable ties, unique-FE and budget limits, cache keys/order, evaluator boundary, checkpoint state/version/recovery behavior, and exception distinctions. Keep `problem.evaluator.dense` as the explicit adaptive/cache/counter orchestration boundary. Use only current synthetic/injected software tests; no COM/provider evaluation, real design search, replay of historical runs, or uncontrolled optimizer FE.

At the R3 baseline, `optimizers.selection` was the only comparator implementation; it now lives at `optimization.selection`. Do not add a comparator to `evaluation.py`, change its tuples, or move design/evaluation policy into the optimizer. Do not add import-proxy packages or old-checkpoint readers.

## R3 baseline source → current canonical owner

| Current source | Observed responsibility | R4 disposition / target |
|---|---|---|
| `optimizers/base.py` | Evaluator/backend protocol and `backend_name`. | `optimization/base.py`; retain API and evaluator-agnostic boundary. |
| `optimizers/lshade.py` | L-SHADE proposals, deterministic RNG, canonical key/cache, unique-design accounting, generation/schedule/archive, frequency-grid versioning, traces/state codec; contains `FixedDEReferenceBackend`. | `optimization/lshade.py`; preserve implementation and state schema 4 exactly. Keep DE reference behavior attached to its existing strategy implementation unless separation is needed solely to remove duplication without changing calls/draws. |
| `optimizers/scipy_de.py` | `ScipyDELegacyBackend`, a non-resumable SciPy DE adapter for controlled backend regression/API use. | `optimization/scipy_de.py`; retain its distinct backend semantics. |
| `optimizers/selection.py` | Sole `FeasibilityFirstComparator` / `GeometryFirstComparator`, rank functions, ties and time-to-target. | `optimization/selection.py`; sole canonical comparator. |
| `optimizers/polish.py` | Generic Powell continuous-only search with comparator-checked promotion. | Consolidate with the current `optimization/polish.py` under one optimization-owned API; retain Powell proposal/merit behavior and mixed-variable behavior as distinct functions. |
| `optimizers/checkpoint_session.py` | L-SHADE session adapter over `io.checkpoints` / `io.lifecycle`, with managed rolling stream and legacy direct-file handling. | `optimization/checkpoint_session.py`; keep CheckpointStore and run lifecycle ownership in IO; preserve state validator and paths/protocol. |
| `optimization/{accounting,adaptive_frequency,budget,cache,counters,convergence_evidence,history,population}.py` | Shared budget, adaptive grid, cache/counter, population and evidence services. | Remain under `optimization/`; preserve behavior and distinct counter meanings. `problem.evaluator.dense` continues using these services unchanged. |
| `optimization/runner.py` | Existing SciPy-driven application runner; adaptive rounds, FE limits, history, validation and result persistence. | Remains the canonical application runner for this migration. Do not silently replace its SciPy call with another backend or fold study-specific search loops into it. |
| `problem/evaluator.py::dense` | Dense/adaptive evaluation orchestration with validation, cache and counters; delegates point response to `evaluation.py`. | Retain at its existing boundary; no R4 policy move or arithmetic change. |
| `optimization/polish.py` + `optimizers/polish.py` | Mixed-variable coordinate polish and generic Powell polish live in different packages; the former re-exports the latter and uses the sole comparator. | One owner/API family in `optimization`; preserve separate behaviors and comparison calls, remove duplicate re-export/import path. |

### Callers, persisted references, and focused tests

- Direct backend/session/comparator callers: `studies/hybrid.py`, `studies/hybrid_stage4b.py`, `studies/dms_topology_screening.py`, `optimization/runner.py`, `optimization/polish.py`, `reporting/candidate_integrity.py`, `reporting/hybrid_stage4c.py`, `studies/lshade_records.py`, `__main__.py`, `tools/wsl/qualification_smoke.py`, and `tests/unit|integration` optimizer/checkpoint/study tests. Several imports are function-local; inventory those as well as module imports.
- `io/checkpoints.py` owns durable checkpoint stream/file mechanics. `LShadeCheckpointSession` owns the backend-specific adapter, its validator, and whether an existing legacy direct file is selected; do not change either layer's data protocol.
- Provenance/source manifests contain old source paths in `studies/hybrid.py`, `studies/hybrid_stage4b.py`, `scripts/build_stage3_9b_source_compatibility.py`, and Q1-A `production_identity.py` / tests. Active current-code source lists should name the new owners where they measure current code. Historical execution identities and frozen source-path contracts must not be rewritten to imply a new source SHA.
- Configs select strategy parameters (e.g. `lshade` settings in `configs/studies/hybrid_stage4a_qualification.yaml` and topology screening configs); no optimizer/search budgets or config meanings change in R4.
- Main focused behavior evidence now lives in `tests/unit/optimization/` (including L-SHADE, comparator, cache/history and accounting tests), `tests/unit/io/test_checkpoints.py`, `tests/integration/test_stage4a_hybrid_protocol.py`, study adapter tests, architecture/import guards, and the Q1-A public/leaf golden verifiers. Optimizer component tests moved under `tests/unit/optimization/`; Q1-A fixtures were not moved or rewritten.

## Q1-A and historical evidence disposition

Q1-A remains `WORK_UNIT_READY / CLOSED`; no Q1-01…Q1-23 gate has passed. Preserve the three frozen fixture files byte-for-byte and their current SHA-256:

- `tests/fixtures/stage5a2/canonicalization_legacy_golden.json`: `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2` (92 public and leaf characterization cases).
- `tests/fixtures/stage5a2/q0_design_space_contract.json`: `c7902e30f7becf2e2c0aa280d8f51c25f31f524cbf06c3516252bf47b2faddc9`.
- `tests/fixtures/stage5a2/seed_derivation_golden.json`: `1a824a07a6e7d652f47388e6604889e612c2809704b7681df713bb9ec8c7087a`.

Retain the 234 ordered initial-member seal, 4,096 unique search-FE-per-arm ceiling, Q0 source/config/grid IDs, PCG64 replay/transaction protocol, comparator/ties, and Q1-A source/test/report evidence. Q1-A remains `WORK_UNIT_READY / CLOSED`, with no official Q1 gate passed. Its reviewed source head is `ba0d13f69a34422669fee9dd88819dfbab45d392`, PR #54 merge is `03d673052c7570d86b78b43849f649758bb7d3f4`, and post-review tested source is `03b9a5495111a1f933f542682f76b5ec9bad4e53`; see the [Q1 contract disposition](restructure_q1_contract_disposition_20261022.md) for the full source/config/grid IDs, gate status and classifications. Q1-A implementation under `studies/stage5a2/` is not relocated or integrated in this R4 change. Historical source paths and source SHAs remain evidence; code changes do not upgrade any qualification status. If preserving a Q1-A source identity or boundary would require changing its contract, stop for an owner decision. No legacy replay or raw/checkpoint mutation.

## Implementation and local validation record

- The inventory and caller/provenance disposition above were completed before code edits. A new RED architecture test first failed because the old `src/sawopt/optimizers/` package still existed; after migration it passes and asserts required component modules and no runtime imports of `sawopt.optimizers`.
- Baseline synthetic/injected behavior suite before migration: `uv run --locked pytest tests/unit/optimizers tests/unit/optimization tests/unit/io/test_checkpoints.py tests/unit/studies/test_stage5a2_foundation.py tests/integration/test_stage4a_hybrid_protocol.py -q` — **145 passed**.
- R4 moves backend protocols, L-SHADE, legacy SciPy DE, the one selector, and checkpoint session into `optimization/`; merges the two polish owners into `optimization/polish.py`; moves optimizer unit tests; and updates current callers/source lists. `problem.evaluator.dense`, optimizer arithmetic, study configs, and Q1-A implementation remain unchanged. Stage 3.9B source comparison maps current owner paths to the historical R3 source paths; both L-SHADE and selector blobs match exactly at baseline SHA `81d18ba3bd3e29b13958d4b32dfec5585ab9d947`.
- Focused post-migration tests, including architecture, optimization, checkpoint, Stage 4A synthetic protocol, reporting and study caller tests: **231 passed**.
- Locked full suite: `uv run --locked pytest` — **572 passed, 1 skipped**.
- Q1-A canonicalization verification: public **92/92**, leaf **92/92**, both fixture SHA-256 `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2`. Foundation and pure-leaf fresh-process guards both report no forbidden imports. Other frozen Q1-A fixture hashes were checked before editing and are unchanged in the worktree.
- `uv sync --locked --extra test` and `uv run --locked python -m sawopt --help` pass. No COM/FE, research optimizer run, Q1 qualification, historical replay, raw/checkpoint mutation, or external-data action was performed.
- GitHub Actions on the initial code head `f64c11e61baf146bc32eaf9b2de0cac6b6796b1a` failed in `tests/unit/test_evaluation_contracts.py`: two exact response-array SHA checks observed `43271d532fbc3d2c86952b1bb0a68e8c7e92350bdee81fe4b1f4c04f9702b99d` instead of `6c21974996f08352b09f19d32f403cd13d5dc831d42cebe3157c7dbfa0ca49a5`, and `31a09b80249c8904c2679c649223ff29db1b65c6f54290e5a4807f0157804558` instead of `4ee60a4ae1831825d46fdbc7d82ab54264235642e02e54e0b639962a9d51dbdc`. A subsequent Actions run `39808048326` passed on head `965bd1028cc72e7ee49cb084ae1a35de32b54054` (572 passed, 1 skipped); that head changed only the R4 evidence document, not source/tests. The initial exact scientific-output discrepancy therefore remains unexplained despite a green rerun. Preserve it for independent review; do not change tolerances or expected hashes.

## Handoff and stop condition

Draft PR [#68](https://github.com/MasayaTakagi/saw-com-optimizer/pull/68) is open against `main`, based on `81d18ba3bd3e29b13958d4b32dfec5585ab9d947`. Keep it in Draft and stop for independent review of the CI hash discrepancy before any merge or scientific change. R5, Q1 requalification, COM/FE, and all run/data actions require their separate gates.
