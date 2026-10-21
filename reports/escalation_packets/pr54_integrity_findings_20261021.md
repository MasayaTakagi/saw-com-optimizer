# PR #54 — Q1-A integrity findings implementation judgment

**Purpose:** bounded, judgment-only review before repairing the mandatory findings on PR #54. This packet does not authorize Q1-B/C/D/E, synthetic integration, COM/network/physics work, optimizer execution, production work, or merge.

**Reviewed PR:** [#54 — Stage 5A-2 Q1-A common foundation](https://github.com/MasayaTakagi/saw-com-optimizer/pull/54), branch `codex/stage5a2-q1a-common-foundation`, reviewed HEAD `6486745023d6b47ec352b9cd2e53b64dab8d1f49` (the branch currently has no local modifications). Independent review comment: https://github.com/MasayaTakagi/saw-com-optimizer/pull/54#issuecomment-6318470894.

**Current stage limits:** Q0 was accepted/closed by explicit user decision on 2026-10-21. Issue #52 authorizes Q1-A implementation and deterministic synthetic/unit tests only. Keep Q1-A at `LOCAL_EVIDENCE_READY` until independent review/user disposition; no Q1 official gate is passed. Q1-B/C/D/E remain unauthorized. Do not weaken Q0-R3 semantics or mark Q1-03/04/05/14/15/16 `FULL_PASS`.

## Authoritative contract and relevant implementation

- Q0-R3 packet: `reports/escalation_packets/stage5a2_q0_protocol_revision_r3_20261021.md`, especially §§2–3 and 5.3. Q0-R3 requires G4 full-reference verification before every sampler draw, lossless RNG state and replay continuity, and both complete actual-path preflight transformations before either first FE.
- Q1 gate matrix: `docs/plans/stage5a2_q1_qualification_matrix.md`, especially Q1-03/04/05/14/15/16.
- Current Q1-A implementation: `src/sawopt/studies/stage5a2/{rng,initialization,identity,journal}.py`.
- Current focused evidence: `reports/stage5a2_q1a_common_foundation_20261021.md` and `tests/unit/studies/test_stage5a2_foundation.py`.
- Frozen Q0 design-space contract fixture: `tests/fixtures/stage5a2/q0_design_space_contract.json`; Stage 4A/4C context: `docs/plans/stage5a2_minimum_fair_comparison.md` and `history/stage5a2_q0_closeout_20261021.md`.

## Mandatory findings from the independent review

1. **G4 barrier must be checked for every common sampler draw.** `RNGCallService._validate_owner` caches `_verified_common_pair_id`, so after the first draw it skips `GenesisCoordinator.require_ready(pair)`. A cell identity DB or barrier can be corrupted/deleted between calls while a live service continues. Required outcome: every sampler call revalidates the durable pair/roster/two-cell reference set; each fault (cell identity removal, identity corruption, wrong UUID, barrier corruption) rejects before the next underlying RNG invocation and leaves generator state, ordinal and journal unchanged.

2. **Enforce uninterrupted PCG64 state continuity across logical calls.** `_accept_rng_start` currently enforces ordinal/pending-call order but not that a new START's pre-state equals the prior COMMITTED post-state. A draw made through `generator` outside the facade can therefore be accepted as the next call. Required outcome: reject state drift before any draw; bind first-call state to the identity-derived seed; enforce exact committed post-state→next pre-state continuity; distinguish pending START recovery from authorization of a new ordinal. Cover hidden out-of-facade draw, wrong initial/recovered state, and next-ordinal-after-pending-start cases. Preserve same-call pending recovery and committed-result replay semantics.

3. **Do not authorize first FE using caller-minted certificates.** `persist_both_preflight_certificates` accepts public certificate records and verifies seal-derived hashes, not proof that `preflight_lshade` and `preflight_controlled_de` actually traversed all 234 transformations. A fabricated pair of correctly reconstructed seal-derived certificates can reach `dispatch_initial_evaluation`. Required outcome: make authoritative persistence/evaluation authorization inseparable from running and comparing both full pure preflight paths, or explicitly keep current API non-authoritative/unusable for FE until B/C integration. Keep Q1-04 `PENDING_DEPENDENCY`; no optimizer/evaluator integration is authorized by this repair. A regression must attempt synthetic certificates without calling either preflight and prove no evaluator is reached.

4. **Enforce the frozen Q0 production identity contract before genesis/sampling.** `DesignSpaceMetadata` validates internal hash consistency but not the frozen topology-specific 13-DOF P_D/D_P bounds and integer indices, frozen fixed search/validation grids, permitted topologies/seeds, or required config/source/comparator/canonicalizer/runtime/horizon identity mapping. Current P_D 2-D unit metadata can be sealed through the same API as production. `PairIdentity` binds only aggregate hashes, with no documented/auditable mapping proving all required Q0 inputs are covered. Required outcome: an explicit validated production identity/metadata construction or verification path that rejects mismatched dimension/bounds/indices/validation-grid fingerprint before genesis, sampler RNG or evaluator, while any lower-dimensional fixtures are unmistakably synthetic/unit-only. Specify the exact required-field→canonical identity/hash binding. If Q0 leaves this schema/mapping ambiguous, stop and return for a further decision rather than inventing a contract.

## Judgment requested

Assess, without implementation, the minimum source/API boundaries that preserve Q0-R3 and safely address each finding. In particular:

- Is per-call durable G4 revalidation sufficient, including barrier and all cell journal event-chain validation, and where should it occur to guarantee rejection before any RNG state mutation?
- What exact invariant should tie a new stream call's pre-state to the identity-bound initial state and prior committed state while still allowing a pending START to be retried from its recorded pre-state? Should drift rejection or state restoration apply in each state, and what is consistent with Q0-R3 §§3.2–3.3?
- Which API shape best ensures both actual pure preflight paths execute before their certificates can authorize any FE, without pulling Q1-B/C integration into Q1-A or marking Q1-04 passed?
- Does the frozen Q0 contract already specify enough inputs to construct a strict production identity verifier, or is the schema genuinely ambiguous? Identify exact documents/fixtures that govern topology bounds, search/validation grids, permitted seeds, canonicalizer/comparator/rank/state-codec, source/config/lock/runtime and horizon. Recommend a fail-closed separation between synthetic test fixtures and any run-capable path; do not propose new Q0 semantics.
- Recommend focused regression-test evidence and documentation/status updates. Do not authorize COM/physics, optimizer runs, production runs, Q1-B/C/D/E, formal gate passage, or merge.

## Requested response format

Return `DECISION` (`PROCEED_WITH_SPECIFIED_REPAIRS` / `STOP_FOR_Q0_SCHEMA_DECISION` / `BLOCKED`), followed by `FINDING_1` … `FINDING_4`, `PRODUCTION_IDENTITY_REQUIRED_FIELDS`, `PREFLIGHT_AUTHORIZATION_BOUNDARY`, `FOCUSED_TESTS`, and `SCOPE_LIMITS`. Separate definite conclusions from unresolved assumptions. This is a bounded design judgment, not implementation or acceptance of PR #54.
