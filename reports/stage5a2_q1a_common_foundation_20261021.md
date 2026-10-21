# Stage 5A-2 Q1-A common foundation — local evidence

**Issue:** [#52 — Q1-A canonicalization seam, identity/RNG/journal foundation](https://github.com/MasayaTakagi/saw-com-optimizer/issues/52)

**Status:** `LOCAL_EVIDENCE_READY / AWAITING INDEPENDENT REVIEW`. This is work-unit evidence only; no official Q1 gate is passed.

**Authorization:** Issue #52 explicitly authorizes Q1-A implementation and deterministic synthetic/unit qualification, including the narrow legacy canonicalization characterization. Q1-B/C/D/E, synthetic integration, COM/network/physics evaluation, real SAW optimization, Stage 4C mutation, and production orchestration/run are not authorized.

**Integrity correction (2026-10-21):** This section supersedes the earlier A2 claims that caller-supplied preflight certificates could authorize an initial FE. The four mandatory findings from PR #54 review were repaired within Q1-A scope under the bounded Sol judgment (`PROCEED_WITH_SPECIFIED_REPAIRS`); see `reports/escalation_packets/pr54_integrity_findings_20261021.md` and `reports/escalation_log.md`. The current preflight evidence is synthetic/non-authoritative, and `dispatch_initial_evaluation` always rejects. No official gate has passed; Q1-04 remains `PENDING_DEPENDENCY`.

**Worktree:** `/home/user/src/saw-com-optimizer`, branch `codex/stage5a2-q1a-common-foundation`; based on `f32b8f8dac928f21c567b34593b1ed227a4c9c9e`.

**Initial Q1-A implementation commit:** `0c7b23fd528abc16f43b1f1ac269d7c664676fbd`

**PR #54 integrity-repair commit:** `d066b49` (`Fix Stage 5A-2 Q1-A integrity gaps`); published on the Draft PR branch. This does not pass an official Q1 gate.

**Draft PR:** [#54 — Stage 5A-2 Q1-A common foundation](https://github.com/MasayaTakagi/saw-com-optimizer/pull/54)

## A0 — pre-extraction characterization

The compatibility characterization ran before modifying `HybridDesignSpace.canonicalize`, in a separate process using the ordinary public import path. That process called only `HybridDesignSpace.canonicalize`; it made no decode, geometry, provider, evaluator, network, physics, or optimizer call.

- Baseline source commit: `f32b8f8dac928f21c567b34593b1ed227a4c9c9e`.
- Pre-extraction `src/sawopt/problem/hybrid.py` SHA-256: `b892be9360174d6701f3db0dc8ba49c82d1b75d8b3c1886dbbba998bd3242462`.
- Captured environment: CPython 3.12.3, NumPy 2.5.3, Linux/WSL2 x86_64; full NumPy build metadata, SOABI, platform, source/config fingerprints, bounds, integer-index order, exact inputs/outputs/errors, dtype/shape/ownership, and input non-mutation are archived in `tests/fixtures/stage5a2/canonicalization_legacy_golden.json`.
- The initial captured corpus checksum was `927960479e7c4b274661485351e03f8275ed2b6526763a105bcd57af7a4a8f31`. The checked-in frozen corpus, after its metadata annotation, has SHA-256 `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2`. The capture utility now refuses to capture after extraction.
- Coverage: 92 cases over `D`, `P_D`, `D_P`, and `P_D_P`; dimensions 10/13/13/16; every integer coordinate's half-up tie and adjacent ULPs; lower/upper clipping; rounded-integer second clipping; signed zero; wrong shapes; NaN/±Inf; conversion error; exact keys/output bytes; ownership and input immutability.
- Sample case: `P_D_P/integer_14_tie_at` returned `<f8`, shape `(16,)`, ordered 16-element float key, independent writable output, and unchanged input. `D/signed_zero` preserved the negative-zero vector/key bits.

## A1 — extraction, parity, and imports

- Moved the exact operation order into `src/sawopt/design/canonicalization.py`; the NumPy/typing-only helper retains conversion, shape/finiteness validation, clip → half-up round → clip, key construction, and exception behavior. `HybridDesignSpace.canonicalize` is a same-signature delegate passing its existing bounds, integer-index order, dimension, and topology.
- Fresh-process public-delegate verification: 92/92 cases passed; fixture SHA-256 `3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2`.
- Fresh-process pure-leaf verification: 92/92 cases passed against the same corpus/checksum.
- The one-time checked-in Q0 design-space contract fixture `tests/fixtures/stage5a2/q0_design_space_contract.json` binds the Stage 4A and base config fingerprints to all four ordered active bounds/index/dimension/topology records; fixture SHA-256 `c7902e30f7becf2e2c0aa280d8f51c25f31f524cbf06c3516252bf47b2faddc9`.
- Fresh-process leaf-only and Q1-A-package import checks both observed `forbidden_imports: []`, including during a canonicalization call. Forbidden boundaries include `sawopt.problem`, COM/network/physics modules, Stage 4B/4C studies, and orchestration.
- Caller protection review: only `src/sawopt/problem/hybrid.py` was changed among shared/caller source. Stage 4B's `space.canonicalize` sampler and L-SHADE canonicalizer call sites and Stage 4C's delegation through Stage 4B are unchanged. No decoder rounding, Stage 4B/4C source, checkpoint, saved state, or study data was changed. Actual Stage 4B/4C runtime/caller execution was deliberately not performed because those paths reach geometry/optimizer execution outside this Q1-A scope; the direct public-method parity corpus is the executed compatibility evidence.

## A2 — foundation and synthetic tests

Implemented the study-scoped typed identity, journal, RNG, and initialization components under `src/sawopt/studies/stage5a2/`. The tests use deterministic synthetic vectors, injected transforms/geometry, and injected evaluator callbacks only.

- Pair/cell immutable Phase-I records, ordered roster with reciprocal identity hashes and locators, and a separate-database G0–G4 coordinator. Writes are individually transactional; no cross-database atomicity claim is made. Reconciliation validates exact records/events, permits only exact pre-G4 recovery in a pristine destination, and fails closed on orphan/conflicting/corrupt state or post-G4 identity loss. Every common-sampler call now freshly revalidates the pair, roster, barrier and both cell journal chains before state restoration, START persistence, or any draw.
- Append-only SQLite event chain and immutable-record digests; a journal verifies existing records/events when opened, checks the cached verified tail before extending, poisons a live journal after a detected chain-integrity failure, and rejects writes after corruption is observed. Idempotency conflicts, event corruption, record-digest corruption, and full-chain/tail verification are tested.
- `stage5a2_rng_call_v1` and the Q0-R2 §8.1 fixed-width-hex `stage5a2_pcg64_state_v1` wire format: exact typed arguments/results, full pre/post state plus hashes, owner/role/cursor/ordinal identity, START-before-draw, committed replay without redraw, pending recovery restored from its verified pre-state, and new-call continuity from the identity-derived initial state through each preceding committed post-state. Drift is rejected before a new START/draw; every common-sampler call revalidates G4. All seven allowed methods are exercised. Eighteen frozen seed vectors cover two topologies, three root seeds, and three stream roles. The typed NumPy codec preserves plain dtypes/arrays and explicitly rejects object, structured, and subarray dtypes it cannot encode losslessly.
- Representation-aware 234-member synthetic common population: raw, provisional canonical, L-SHADE input genotype, reconstructed physical vector, sealed evaluator vector/key, DE direct physical input, and normalized DE phenotype genotype are preserved in ordered records/hashes. The test verifies duplicate-before-geometry, exact counters, 10,000-draw shortfall, sampler replay, durable pair-owned seal, unchanged Phase-I IDs, and per-arm Phase-II attachment references.
- Pure per-arm preflight interfaces and durable certificates remain synthetic evidence only. Hash-valid, caller-minted certificates do not prove either actual optimizer transformation ran. A seal-derived certificate forgery test proves the public persistence/readiness/dispatch chain cannot reach an evaluator: `dispatch_initial_evaluation` unconditionally raises until authorized B/C integration qualifies both actual paths. Q1-04 remains `PENDING_DEPENDENCY`.
- Production identities now carry a canonical, validated Q0 manifest binding the exact permitted `P_D`/`D_P` topology, 13-DOF bounds/names/units/indices/rounding, both fixed grids, frozen roots, configuration/evaluator/environment/optimizer/schema inputs, and aggregate identity hashes. Metadata mismatch fails before genesis, RNG, or evaluator access. Explicit synthetic identity scope cannot enter production genesis, and production scope rejects low-dimensional fixtures.
- Focused regressions inject between-call G4 corruption (removed/corrupted cell identity, wrong UUID, barrier and cell-event damage); RNG drift/wrong initial seed/pending and committed replay states; fabricated seal-derived preflight certificates; invalid production manifests and synthetic/production cross-use; and fixed-width PCG64 codec malformed fields. The earlier Q1-A claims in this report about preflight dispatch are superseded by this correction.
- Genesis fault injection covers G0, G1, G2, G3, and G4 commit boundaries. Tests also cover orphan state, conflicting pre-G4 state, post-G4 loss, pre-barrier RNG rejection, and certificate/attachment/journal integrity.

## A3 — command results and gate status

Commands run:

```text
uv run --locked pytest -q tests/unit/studies/test_stage5a2_foundation.py
50 passed in 46.30s

uv run --locked python scripts/verify_stage5a2_canonicalization_golden.py --mode public
92 passed; fixture SHA-256 3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2

uv run --locked python scripts/verify_stage5a2_canonicalization_golden.py --mode leaf
92 passed; same fixture SHA-256

uv run --locked python scripts/check_stage5a2_pure_leaf_import.py
forbidden_imports: []

uv run --locked python scripts/check_stage5a2_foundation_imports.py
forbidden_imports: []; `production_identity` included

uv run --locked python -m compileall -q src/sawopt/studies/stage5a2 scripts/check_stage5a2_foundation_imports.py tests/unit/studies/test_stage5a2_foundation.py
git diff --check
passed

uv run --locked ruff check src/sawopt/studies/stage5a2/identity.py src/sawopt/studies/stage5a2/initialization.py src/sawopt/studies/stage5a2/rng.py src/sawopt/studies/stage5a2/production_identity.py tests/unit/studies/test_stage5a2_foundation.py
failed to launch: `ruff` is not installed in the locked environment (`Failed to spawn: ruff`); no package was installed
```

No full repository test suite was run because it includes tests/workflows that can invoke physics, optimizer, or production paths outside the explicit Q1-A authorization. No COM/network/physics calculation, real optimization, production orchestration, or long-running run was started.

| Official gate | Current disposition | Why Q1-A does not close it |
|---|---|---|
| Q1-03 | `PENDING_DEPENDENCY` | Proposal-stream/no-hidden-draw parity needs B/C/D. |
| Q1-04 | `PENDING_DEPENDENCY` | Both actual evaluator paths need B/C. |
| Q1-05 | `PENDING_DEPENDENCY` | Arm initialization and recovery need B/C/D. |
| Q1-14 | `PENDING_DEPENDENCY` | The live L-SHADE codec remains Q1-C work. |
| Q1-15 | `PENDING_DEPENDENCY` | Optimizer/checkpoint hydration and recovery need B/C/D. |
| Q1-16 | `PENDING_DEPENDENCY` | Cross-optimizer transaction/recovery qualification is Q1-D work. |

Q1-B/C/D/E remain `NOT AUTHORIZED / NOT STARTED`. No Q1 gate is `FULL_PASS`. Q1-A is `LOCAL_EVIDENCE_READY`; `WORK_UNIT_READY` awaits independent GitHub review and user acceptance.

## Changed files

- Canonicalization seam: `src/sawopt/design/__init__.py`, `src/sawopt/design/canonicalization.py`, `src/sawopt/problem/hybrid.py`.
- Q1-A foundations: `src/sawopt/studies/stage5a2/{__init__,codec,identity,initialization,journal,rng,production_identity}.py`; the no-physics import guard now includes `production_identity`.
- Characterization/import tools: `scripts/capture_stage5a2_legacy_canonicalization.py`, `scripts/verify_stage5a2_canonicalization_golden.py`, `scripts/check_stage5a2_pure_leaf_import.py`, `scripts/check_stage5a2_foundation_imports.py`.
- Fixtures/tests: `tests/fixtures/stage5a2/{canonicalization_legacy_golden,seed_derivation_golden,q0_design_space_contract}.json`, `tests/unit/studies/test_stage5a2_foundation.py`.
- Current status docs: `docs/plans/stage5a2_q1_execution_plan.md`, `docs/plans/stage5a2_q1_qualification_matrix.md`, `docs/plans/stage5a2_minimum_fair_comparison.md`, `docs/project_roadmap.md`.
- PR #54 integrity repair evidence: `reports/escalation_packets/pr54_integrity_findings_20261021.md`, `reports/escalation_log.md`, and this corrected work-unit report.

## Residual risks and next review gate

- No actual Q1-B/C optimizer/evaluator adapter exists yet; both production-arm preflight paths and their transaction/recovery behavior remain unqualified.
- The Stage 4A/4B/4C protection is based on exact direct `canonicalize` parity plus call-site/source review; the actual callers were not executed in this Q1-A work unit.
- Synthetic population/preflight transforms are injected, two-coordinate unit fixtures where appropriate; they are software contract tests, not SAW or physical geometry evidence.
- No independent review or user acceptance has occurred. The next step is independent GitHub review of the focused Draft PR. Stop there; do not start Q1-B/C/D/E, mark any formal gate passed, merge, or launch follow-up work without later explicit authorization.
