# Luna → Sol Escalation Log

## 2026-10-21 — Stage 5A-2 Q0-R1 independent re-review outcome (final for this work unit)

- **Decision: `REQUEST_Q0_REVISIONS`.** The one authorized read-only re-review is complete. Q0 remains open and Q1 is blocked; Sol did not authorize implementation, tests, synthetic evaluations, COM/network calculations, optimizer execution, or production runs. No second Sol agent will be started automatically.
- Requested routing was `openai/gpt-6.1-sol`, thinking `medium`, tools `read`, non-persistent. The actual child record shows provider `openai`, API `openai-responses`, model `gpt-6.1-sol`, recorded `thinkingLevel=medium`, and normal `stop`. Child label/session `stage5a2-q0-r1-sol-review` / `01a15a0a-4381-7496-a29d-3fc053d66ad9`. It read the Q0 packet, prior Sol packet, plan, qualification matrix and `src/sawopt/optimizers/lshade.py`; no source or Stage 4C file was changed. Recorded thinking is a runtime setting, not evidence of hidden reasoning effort or billing/credential path.
- Sol closed bounded findings on the full-package estimand/exploratory horizon, controlled DE proposal semantics, common population/evaluation distinction, evaluator/cache isolation, unchanged comparator/ties, dense validation and governance. Cross-cutting issues remain open: exact L-SHADE first-`None` fallback exit; durable/idempotent journal transitions for proposal, duplicate, retry and optimizer-only no-FE state changes; pre-sampling versus frozen-population versus mutable journal identity and complete lossless PCG64/inner-state serialization; fixed reporting for censored matched pairs without survivor-only ranking or budget-complete treatment of stalls.
- The packet and matrix record these findings and new Q1 gates. After the review, documentation was corrected to describe the observed L-SHADE first-`None` exit and to make the standalone 23-ID Q1 matrix authoritative; these post-review edits were not re-reviewed by Sol. They do not close the remaining design blockers or authorize Q1.
- Baseline is `origin/main=daa646ba7c9fab0d5d1b6c3e3054213fdb9ab10e`, as specified; local branch is `codex/stage5a2-q0-protocol-revision`. Its pre-edit `c2f002c00da0339c4f43fe1ac9e50d7793cdb233` tree matched `origin/main`; local docs are being published on the dedicated branch only. No production execution or tests were run.
- Published branch `codex/stage5a2-q0-protocol-revision` at commit `0376885edbb11b6ed91b299c34b67c69398d7b48` and created Draft PR #48: https://github.com/MasayaTakagi/saw-com-optimizer/pull/48. It remains unmerged. Next gate is independent GitHub review and explicit user acceptance; Q1 implementation remains blocked until Q0 protocol blockers are resolved and accepted. No merge or run authorization follows from this packet or Sol review.

## 2026-10-21 — Stage 5A-2 Q0-R1 protocol revision (pre-review dispatch; superseded)

- **Corrected ancestry in this superseded pre-review note:** the fetch recorded `origin/main=a1cbd9eab3999fb18ca3e0683ddfbabe21ea0559` (earlier PR #46 merge), but this was an outdated main reference relative to the already user-provided `daa646ba7c9fab0d5d1b6c3e3054213fdb9ab10e` (later PR #47 merge). **`daa646ba…` descends from `a1cbd9ea…`, not the reverse.** The subsequent confirmed Q0-R1 baseline was `daa646ba…` as documented in the later outcome entry above. The clean prior branch `codex/stage5a2-q0-sol-review` was preserved; the Q0-R1 branch was created in the existing directory without a new worktree.
- Read-only review of PR #47 found one independent GitHub issue-comment review at https://github.com/MasayaTakagi/saw-com-optimizer/pull/47#issuecomment-6294426203 and no inline review comments. It accepted the prior review record but kept Q0 revision-required. Stage 4C implementation and config were inspected and verified unchanged relative to `origin/main`.
- Consolidated the prior Sol `REQUIRED_CHANGES` and PR #47 gates in `reports/escalation_packets/stage5a2_q0_protocol_revision_20261021.md`. The protocol fixes the L-SHADE source/default/resolved package and fallback, fully deterministic DE proposal/update/retry behavior, seed/sampler/population hash, transactional FE and failure states, strict schema/comparator/serialization, checkpoint compatibility/identity, per-FE traces, resource/timing policy, cell order, and Q1 qualification gates. §13 maps every prior finding to `RESOLVED_WITH_SPEC` or `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE`; no Q1 implementation choices remain.
- Justified alternative: preserve L-SHADE's existing retry/fallback algorithm and use an external shared 65,536-proposal no-progress watchdog, with explicit `BUDGET_STALLED` censoring and no trajectory changes before the cutoff. Controlled DE has a 4,096-attempt per-target cap and the same global watchdog. The risk and alternatives are explicit.
- Updated `docs/plans/stage5a2_minimum_fair_comparison.md` as the current Q0 plan and added `docs/plans/stage5a2_q1_qualification_matrix.md`. All are design-only. No tests, synthetic evaluation, COM/network call, optimizer, production run, or Stage 4C data change was made.
- **Sol re-review has not yet been executed** at the time of this entry. It is permitted only after the completed packet and finding matrix; request is one read-only `openai/gpt-6.1-sol` / recorded-medium review, no implementation. Await exact child provider/model/thinking inspection. If revisions are requested, record and stop; do not spawn another Sol.
- Current decision remains pending Sol, external GitHub review and explicit user acceptance. Q1 and all runs remain prohibited.


## 2026-10-21 — Stage 5A-2 Q0 L-SHADE vs controlled DE design review

- Prepared the bounded, read-only design packet at
  `reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md`
  against confirmed main `a1cbd9eab3999fb18ca3e0683ddfbabe21ea0559` (PR #46).
  The Stage 5A-1 closeout, Stage 5A-2 proposal, and qualified routing guide
  were confirmed present at that base; the earlier local note claiming they
  were missing was stale and is superseded.
- **Routing/session verification:** requested `openai/gpt-6.1-sol`,
  `thinking=medium`, read-only tools, non-persistent child. The saved child
  record identifies `provider=openai`, `modelId=gpt-6.1-sol`, and
  `thinkingLevel=medium`; it contains the expected completed review response
  and normal `stop` completion. Session name:
  `stage5a2-q0-sol-design-review`; session ID
  `01a159d5-d230-71ea-818e-f9b077168d83`. Full session remains local and was
  not added to Git. Recorded `medium` is a runtime setting, not proof of
  internal reasoning effort.
- **Sol decision: `REQUEST_Q0_REVISIONS`.** Sol judged the proposed comparison
  defensible as an exploratory matched-budget comparison of complete algorithm
  packages, but not sufficiently frozen for Q1. A new controlled DE is
  justified; neither `ScipyDELegacyBackend` nor `FixedDEReferenceBackend` may
  be relabelled as the requested standard DE arm.
- Key findings: L-SHADE itself has offspring-wise immediate updates, latent
  pre-canonical normalized genotypes, parent-midpoint boundary repair, and an
  unseen-proposal fallback after duplicate retries; comparison therefore
  measures complete algorithm packages. L-SHADE lacks a default duplicate
  no-progress stop. Its existing state/trace does not yet establish exact
  checkpoint replay, strict identity/schema validation, per-unique-FE tracing,
  or lossless infinity serialization. 4,096 FEs × 3 seeds supports exploratory
  evidence only, not convergence or general superiority.
- Sol endorsed as **design choices only** fixed DE population 234, `F=0.5`,
  `CR=0.9`, reflection, canonical phenotype remapping, synchronous parent
  snapshots, no DE shrink/adaptation/archive/polish/fallback, exact-budget
  partial generation; the provisional 4,096/234/three-seed envelope; and a
  cold L-SHADE 4,096 horizon. These are not Q0 freeze or run authorization.
- Required before Q1: freeze exact L-SHADE settings/fallback and comparison
  estimand; DE donor/target/RNG/retry/survivor order; exact initializer stream,
  representation, cap and partial-failure recovery; bounded retry/stall and
  infrastructure-failure semantics for both arms; strict record schema,
  stable tie and lossless key/infinity encoding plus missing-identity rejection;
  per-unique-FE search-only trace; and timing/counter/resource/cell-order
  contracts. Q1 qualification must cover these, including L-SHADE fallback,
  partial initialization, pending DE generation checkpoint, ties, serialization,
  failure boundaries and trajectory-neutral tracing.
- Updated the Q0 packet and plan draft to record this conditional disposition
  and outstanding work. **Q0 remains OPEN / REVISIONS REQUIRED; Q1 NOT STARTED.**
  The packet requires a future consolidated revision and separate Sol
  re-review, then independent GitHub review and user acceptance before Q1
  implementation permission can be considered. This one-review task launched
  no second reviewer, test, synthetic qualification, COM evaluation,
  optimization, DMS acceleration, production run, or Stage 4C data change.

## 2026-09-29 — Stage 4A hybrid protocol pre-implementation judgment

- C2C PLAN `c2c_0b52`, iteration 0, classified pre-edit Sol judgment as
  required because Stage 4A adds hybrid design variables, comparison
  conditions, and a T1/resonator composition interface.
- Escalation packet:
  `reports/escalation_packets/stage4a_hybrid_sol_judgment_2026-09-29.md`.
- Requested target: `gpt-6-sol`; backend model identity is not exposed.
  Bounded judgment: approve qualification with gates. Reuse the complete
  MLIT provider for both T1 and existing resonator physics; stop if provider
  validation or existing assumptions fail rather than borrowing M0 values.
  Keep current T1 and resonator bounds and exactly D/P_D/D_P/P_D_P. Use a
  common 32-member cold initial population, 256 unique evaluations per family,
  checkpoints at 128/256, and require mutation plus checkpoint-continuation
  telemetry. Preserve matched 50/50 conditions, geometry-first comparison,
  fail-closed D-only parity, and `REVIEW_WAITING` pending C2C acceptance.
  This is qualification only and does not authorize Stage 4B or production.
- Sol corrected the dimensional count: T1 is 10 DOFs, so P_D_P is 16 DOFs;
  the default 18-per-DOF initializer would consume 288 candidates and cannot
  be used for a 256-evaluation smoke.
- No implementation or optimizer run was performed before the judgment.

Pilot: Stage 1
Status: stopped at mandatory review gate

Each escalation must be recorded as a self-contained packet followed by the
decision, Luna's action, verification, and outcome. Requested model and
reasoning effort must be kept separate from independently observed backend
identity and behavior.

## 2026-09-28 — C2C active-sandbox state access boundary

### Packet and judgment

- Scope: determine whether the project may add a least-privilege C2C state
  preflight to prevent routine `doctor`/`session`/`record` operations from
  repeatedly stopping on EPERM.
- Evidence: normal-user `doctor` and `session set` failed with EPERM on files
  under the exact `%LOCALAPPDATA%\codex-with-chatgpt` root; one retry after
  narrowly authorizing that exact state directory succeeded. No administrator
  command or OS ACL change was used. `sandbox-allow --json` reported `alreadyAllowed=true`,
  while the active managed sandbox's writable-root metadata omitted AppData.
  No external C2C source changes or broad permission changes are allowed.
- Judgment requested from GPT-6 Sol: exact canary design, startup/sandbox
  distinction, failure behavior, and validation threshold. Backend identity
  and actual internal reasoning effort are not independently verified.
- Decision: proceed with a project-owned canary inside only the canonical,
  existing C2C state root. Reject conflicting `C2C_STATE_DIR` redirects; do
  not create directories, change permissions, use admin, relocate state, or
  touch C2C source. The probe creates one exclusive random empty file, closes
  and deletes only that file, with cleanup failure surfaced. Classify observed
  permission denial separately from suspected `ACTIVE_SANDBOX_STALE`, missing
  path, mismatch, other I/O, and cleanup failure. SessionStart output is
  informational; require a direct unelevated probe through the same execution
  boundary before C2C operations. A root-level PASS is necessary, not
  sufficient for nested operation paths. Do not claim the issue fixed until
  two fresh managed sessions pass direct probe and first-attempt
  doctor/session/record. If fresh sessions still deny, report a host policy
  blocker without widening access.

### Codex action and outcome

- Added the SessionStart diagnostic and direct-probe entrypoint, preserving the
  existing session-capture hook. Updated project C2C startup/recovery and
  security-boundary guidance. No C2C external checkout, ACL, credential, or
  permission configuration was changed.
- Implementation validation: 9 focused tests passed using temporary state
  roots and simulated errors; Python AST parsing, hooks JSON parsing, and
  `git diff --check` passed. Pytest emitted a non-fatal cache warning because
  `.pytest_cache` is not writable. The direct probe in this existing task
  session returned `STATE_PATH_MISMATCH` because the resolved state root
  redirects outside its declared `%LOCALAPPDATA%` child; the probe created no
  canary. Per the gate, doctor/session/record were not run after this result.
- C2C independently accepted the bounded implementation in task `c2c_1b7a`,
  iteration 3. Fresh-sandbox host validation remains pending; this existing
  task session cannot prove behavior in fresh managed sandboxes, so no
  permission fix is claimed until the documented validation is completed.

### Bounded path-identity correction

- Scope: resolve the direct preflight's `STATE_PATH_MISMATCH` caused by the
  Windows textual resolution of the default lexical state path, without
  authorizing another root or weakening redirect protection.
- Judgment requested from `gpt-6-sol`: allow a `samefile` exception for the
  default `%LOCALAPPDATA%\codex-with-chatgpt` lexical path while keeping canary
  I/O lexical and all noncanonical overrides rejected. Sol conditionally
  approved the exception only when `lstat` first rejects symlinks, junctions,
  and every other reparse point on the state directory; samefile by itself is
  insufficient because it also succeeds for redirects.
- Decision implemented: retain the normalized lexical path as the only probe
  path. Accept different resolved text only if both names are existing
  directories and `os.path.samefile` proves the same object. Fail closed on
  reparse-point inspection failure, identity mismatch, or identity error.
  No elevation, ACL change, broader writable root, state relocation, or
  external C2C source change is authorized.
- Validation: 15 focused tests passed; Python AST parsing, hooks JSON parsing,
  and `git diff --check` passed. The approved `cloudflared` version and hash
  matched. C2C CLI version 0.1.3 was invoked from the external sibling without
  modifying it; update detection reported offline and made no update. The
  direct preflight was attempted exactly once, unelevated, and returned
  `ACTIVE_SANDBOX_DENIED` (exit 1); a follow-up read-only check found zero
  canary files. The process identity was `CodexSandboxOffline` while
  `USERPROFILE` and the Windows user-profile special folder both resolved to
  `C:\Users\sub`, showing that this managed execution boundary is not running
  under the profile owner's Windows identity.
- Read-only C2C connector checks succeeded in one request: `workspace_info`
  reported `saw-com-optimizer` / `workspace:/` at commit `0168e40`, and
  `git_status` reported the expected current branch and unstaged work. Because
  the direct preflight denied access, no C2C `doctor`, `session`, or `record`
  command was attempted, as required by the fail-closed gate. C2C task
  `c2c_state_root_identity_20260928`, iteration 1, accepted the bounded path
  identity implementation while classifying host qualification as blocked.
  The required next check is in a newly instantiated managed Codex sandbox
  after read-only confirmation that the exact persistent root is configured;
  no state-writing C2C operation should run in this denied boundary. The
  helper maps `ACTIVE_SANDBOX_DENIED` to exit code 2, while the outer command
  reported exit 1, so a future qualification record should capture both the
  JSON status and outer process code separately. A second fresh managed session
  must repeat the successful first-attempt sequence before claiming resolution.
- Fresh Codex session check requested on 2026-09-28: the direct preflight was
  run once and returned `ACTIVE_SANDBOX_DENIED` (outer exit code 1), so no
  C2C `doctor`, `session`, or `record` command was run. The effective process
  identity was `DESKTOP-9IPACE7\CodexSandboxOffline`. Read-only ACL inspection
  showed the state directory owner `DESKTOP-9IPACE7\sub`, with
  `CodexSandboxUsers` granted only `ReadAndExecute` and the profile owner
  granted `FullControl`. The exact user-level `writable_roots` declaration
  remains configured, but this new session still could not write the canary.
  No ACL, persistent configuration, or C2C state was changed. This does not
  qualify a passing fresh session; the execution boundary must provide
  least-privilege write/delete access to the exact canonical state root before
  C2C state operations can proceed.

### User-authorized exact-root ACL qualification

- Bounded Sol judgment: an explicit inheritable grant to
  `DESKTOP-9IPACE7\CodexSandboxOffline` on only the canonical C2C state root is
  narrower than a parent-directory or group grant and is within the user's
  specific authorization. It is not least-privilege across time if this
  Windows principal is shared by managed sessions: inherited `Modify` permits
  changing and deleting C2C state throughout that root. Retain it only for
  C2C use the user intends to support, and disclose that scope.
- The user asked to grant the necessary permission and verify a new session
  with it active. Added one explicit `Modify, Synchronize` ACE for that
  principal on `%LOCALAPPDATA%\codex-with-chatgpt`, inherited by files and
  subdirectories. No elevation, parent/group ACL, other writable root, global
  Codex setting, external C2C checkout, or credential was changed.
- Two fresh managed sessions each passed the direct unelevated canary probe
  with removal confirmed. In both, the first doctor, session read, and record
  succeeded; doctor reported the workspace, bridge, MCP, OAuth, and tunnel
  checks green. The connector returned `saw-com-optimizer` / `workspace:/`.
  C2C independently reviewed the recorded evidence and returned `DONE` for
  `c2c_state_root_identity_20260928`, iteration 3. The C2C record used
  `changedFiles=0`; Git status matched the reviewed pre-existing working-tree
  baseline before and after.
- The exact-root ACE remains in place to support future C2C sessions under
  this managed execution identity. Its shared-principal and descendant
  write/delete scope is the residual permission risk.

### Qualification closeout — 2026-09-28

- **Status: CLOSED / RESOLVED.** The original access failure was an effective
  managed-session ACL boundary: the exact persistent writable root was
  configured, but the `CodexSandboxOffline` execution identity initially
  lacked write/delete access to the canonical C2C state directory. The
  user-authorized exact-root inheritable `Modify, Synchronize` ACE and the
  canonical writable-root representation were followed by two independent
  fresh managed-session qualifications. No wider ACL or root was authorized.
- **Qualification: PASS 1/2 and PASS 2/2.** Both sessions passed the direct
  unelevated state-access preflight with canary cleanup, `sandbox-allow`
  (`alreadyAllowed=true`, `added=false`), normal Doctor/documented recovery,
  first-attempt Session read, workspace identity (`saw-com-optimizer` /
  `workspace:/`), and first-attempt Record with `changedFiles=0`. Neither had a
  permission/state-access failure. The project and external C2C checkout
  integrity and persistent configuration were preserved.
- The verified persistent declaration is:

  ```toml
  [sandbox_workspace_write]
  writable_roots = ["C:/Users/sub/AppData/Local/codex-with-chatgpt"]
  ```

  The configuration SHA-256 remained unchanged during qualification; the
  second session recorded `0e25c82c3402138d92a1946e9eb76d3b4195b1d0140e13d195279c0e479bb9fe`
  before and after. That session used C2C 0.1.3 at
  `9663b88753e35c76796c5bce000293e0bd22cd9e`; the C2C checkout remained clean.
  The project branch was `codex/c2c-state-access-20260928` at
  `a7bab2612fa6049a20388547f524cc745d41711c`, with a clean working tree before
  and after qualification.
- **Bounded C2C 0.1.3 parser compatibility note:** an observed single-quoted
  Windows backslash literal for `writable_roots` was valid TOML but was not
  recognized by `sandbox-allow` as the existing path (`alreadyAllowed=false`).
  The forward-slash double-quoted form above was recognized as the exact
  existing root (`alreadyAllowed=true`, `added=false`). This is external C2C
  behavior, not a SAW source defect; the sibling C2C checkout was not changed.
- In the second qualification, `update-check` returned
  `checked=false`, `updateAvailable=false`, `exit=0` because update detection
  was skipped offline. This was informational. Normal Doctor recovery
  re-established the secure connection and finished with bridge, MCP, OAuth,
  tunnel, sandbox, and workspace checks green; no ACL/config change, root
  expansion, or elevation was needed during recovery.
- Execution summary contained a pre-existing and a new successful record for
  `c2c_88b2`, iteration 0. The duplicate record identity was not a qualification
  failure; use a unique task ID for future qualification or diagnostic records.
- The exact-root inherited ACE remains the residual security risk: if the
  managed-session principal is shared, it permits write/delete access throughout
  the canonical state directory and descendants. No additional fresh-session
  qualification is requested for this closeout.

## 2026-09-27 — Stage 3.9B overlap retry orchestration recovery

### Packet and decision

- Scope: recover the already authorized 8,000-evaluation × 2-seed overlap-parity
  run after an asynchronous launch failed before any optimizer evaluation.
- Evidence: orchestration control files occupied the study output directory,
  violating its empty-at-start contract. The callback separately failed to
  access the Codex state store in the detached worker context. The failed run
  is retained unchanged and has no scientific checkpoint to resume.
- Judgment requested from `gpt-6-sol`: select the smallest safe orchestration
  repair and define callback recovery boundaries. Backend identity and actual
  reasoning effort were not independently exposed.
- Decision: give schema-v2 runs a nested `optimizer/` output directory while
  preserving the top-level directory for orchestration state. Keep schema-v1
  manifests readable with their historical effective output path. Route
  lifecycle/finalization operations to the optimizer path. Before callback-
  enabled launch, run a no-op probe using the exact session, resolved Codex
  executable, structured target validation, and the same environment as the
  eventual callback. Block launch on permission, target, executable, timeout,
  or process failures. Do not broaden state-store access, disable callbacks,
  alter the experiment protocol, or resume/reuse the failed attempt.
- C2C PLAN iteration 3 accepted implementation of this bounded repair. C2C
  requires independent acceptance of implementation and callback preflight
  before a fresh retry. The separate 16,000 × 2-seed run remains gated on a
  completed overlap PASS and later C2C acceptance.

### Codex action and outcome

- Implemented schema-v2 control/output separation, legacy manifest fallback,
  lifecycle routing, dual-path callback prompts, and fail-closed callback
  preflight. Added focused orchestration tests for those boundaries. The
  accepted overlap and 16k configs, canonical Stage 3.8C run, and failed
  attempt remain unchanged.
- C2C's first independent review accepted path separation and lifecycle
  routing, then found two fail-closed gaps: substring acknowledgement matching
  and acceptance of an expected target alongside a foreign target ID. The
  follow-up fixes now require an exact completed `agent_message` response and
  the complete observed ID set to equal only the requested session. Regression
  tests cover acknowledgement fragments/echoes and mixed target IDs.
- Re-validation after that correction: 57 focused tests and 9 subtests passed;
  `py_compile` and `git diff --check` passed. The initial correction attempt
  exposed a syntax error in the new test fixture, which was fixed before the
  passing rerun. No optimizer retry or 16k optimizer was launched.
- No additional Sol escalation was needed for this strictness correction.
  Independent C2C review of the follow-up is pending.

## 2026-09-25 — Historical cleanup architecture boundary

### Packet

- Scope: choose the smallest ownership map to remove current Stage 3.8/3.8C
  imports from historical Stage modules without changing numerical or record
  semantics.
- Evidence and constraints: `problem/dms_topologies.py` already owns T0/T1/T2;
  Stage 3.8 still imports the released design/simulator and `lshade_record`
  from Stage 3.6/3.3 modules. Stage 3.8C imports helpers from the Stage 3.8
  module and hashes historical files. No COM, optimizer, objective, bounds,
  RNG, budget, checkpoint, or saved-run changes; no production rerun.
- Requested reviewer: GPT-6 Sol (`gpt-6-sol`), high reasoning, judgment only.
- Full packet: `reports/historical_cleanup_architecture_escalation.md`.

### Decision

- Move `ReleaseSection`, `ReleasedFilterDesign`, and the unchanged released
  filter simulator into the existing problem-layer DMS module (or a small
  problem-layer sibling if needed). Keep Stage 3.6 release groups, schema,
  bounds, and vector decoding study-owned.
- Give the Stage 3.8 study a fixed `G1_G2` T0 decoder; its current imports of
  Stage 3.6 `release_schema` and `release_bounds` are unused.
- Move the exact L-SHADE record assembly and JSON-cleaning helper into a small
  study-level record module that may depend on `convergence_evidence`; retain
  old imports until remaining historical callers are removed.
- Extract only the Stage 3.8 helpers consumed by Stage 3.8C into a current
  study adapter. Preserve old run metadata and manifests; write new source
  fingerprints honestly after the source move.
- Gate removal with old/new design and section equality, T0 response parity,
  Stage 3.8 helper parity, L-SHADE record JSON equality under controlled
  timing, and import-boundary checks. Production optimization is unnecessary.

### Luna action and outcome

- Decision accepted. The repository freeze and 288-test baseline are recorded
  in `reports/historical_cleanup_freeze_20260925.md`.
- Moved the unchanged released DMS design/simulator into
  `src/sawopt/problem/released_dms.py`; Stage 3.6 keeps its release schema,
  bounds, and decoder. Stage 3.8 now decodes its fixed G1+G2 release locally.
- Extracted L-SHADE record serialization to
  `src/sawopt/studies/lshade_records.py` and current DMS study helpers to
  `src/sawopt/studies/dms_topology_common.py`. Stage 3.8C no longer imports the
  Stage 3.8 runner.
- Removed Stage 3.8C runtime reads/copies of historical reports and handoff
  files. Its source fingerprint now hashes the current study, topology,
  released-design, and record modules. The historical test-gate JSON was copied
  under the saved Final Confirmation run's metadata and the active configs now
  point there; the saved run outputs were otherwise untouched.
- Focused characterization/regression set: 63 passed. No COM equation,
  optimizer, objective, bounds, RNG, evaluation budget, or saved optimization
  result changed, and no production optimization was launched. Historical
  module/config/test removal remains in progress.
- The runtime exposes the requested reviewer/model setting but does not
  independently expose backend identity or actual internal reasoning effort;
  neither is claimed as verified.

## 2026-09-13 — Stage 3.5 L-SHADE parity root-cause review

### Packet

- Scope: evidence-only review of the current-versus-historical L-SHADE
  trajectory divergence before any source change or production experiment.
- Decision requested: choose provenance reconstruction, first-divergence
  tracing, or another bounded audit; classify RC1–RC8.
- Constraints: no source edits, optimizer changes, Phase D, production reruns,
  tuning, tolerance changes, or `multi_agent_v2` configuration.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer.

### Decision

- Recommendation: **B — reconstruct historical provenance and checkpoint/grid
  protocol first**.
- Confidence: high for B; medium-high for **RC6 historical provenance mismatch**.
- Evidence: historical and current best/population/archive traces are exactly
  equal through 4,000 unique evaluations. The first observable divergence is
  the current-only 4k adaptive-frequency exchange. Historical checkpoints use
  16k/32k/64k exchanges, while current diagnostic checkpoints use 4k/8k/16k.
- Population bounds, initial/minimum population, 64k schedule horizon, and 16k
  population size agree. Missing historical schedule telemetry is not evidence
  of RC3.
- No optimizer or diagnostic source change is justified from current evidence.

### Luna action, verification, and outcome

- Accepted the review decision. No experiment was launched and no optimizer,
  objective, search-space, COM, tolerance, or budget behavior was changed.
- Required next validation is a provenance/source/config/protocol diff, followed
  only after protocol equivalence by one bounded 16k parity verification with a
  64k population horizon and no objective-changing 4k/8k exchange.
- Stop for review if exact historical provenance cannot be reconstructed, the
  matched-protocol parity check fails, or a repair would change optimizer
  behavior or require repeating a long production run.
- Backend model identity and actual internal reasoning effort were not
  independently verified by the runtime; GPT-5.6 Sol and high reasoning were
  requested through the task API.

## 2026-09-24 — Stage 3.8C-R1.1 initializer judgment

### Packet

- Scope: recommend a bounded geometry-aware initial-population sampler for
  the R1.1 six-cell pilot; judgment only, no reviewer implementation.
- Evidence: R1 used independent uniform proposals and geometry rejection;
  T0/T2 rejection was 86–93%. The study already injects its initial
  population into the generic L-SHADE backend.
- Constraints: keep the feasible search space, all active bounds, geometry
  limits, topology definitions, COM/network/evaluation/objective behavior,
  comparator, L-SHADE update rule, budget, impedance, profiles, and validation
  grid unchanged. No clamp or projection.
- Requested reviewer: GPT-6 Sol (`gpt-6-sol`), one bounded judgment review.

### Decision

- Retain one study-level initializer interface and condition integer counts
  on exact topology-specific electrode and acoustic-length budgets, reserving
  minimum values for counts still to be sampled.
- Continue validating every design with the existing decoder and geometry
  evaluator; fail if derived constraints disagree.
- The feasible support is retained, but the initializer distribution changes.
  Record variable quantiles, geometry margins, and an independent-uniform
  reference; interpret one-seed pilot performance as diagnostic only.

### Luna action and outcome

- Implemented a study-level conditional integer feasible-set initializer.
  Generic L-SHADE, declared bounds, physical constraints, and comparator code
  were left unchanged. Added all-cell deterministic/bounds/geometry/unique
  population tests and active Sol policy regression coverage.
- Targeted tests: 14 passed. Full repository suite: 227 passed and 14
  subtests passed. Independent preflight: implementation PASS, fixed-design
  sanity 6/6, known-seed preflight 6/6, and geometry-valid population 6/6.
- R1.1 Pilot: `PASS_AWAITING_REVIEW`, 256 evaluations per cell, seed
  20260917; all six cells had finite search/common metrics, successful physics
  evaluations, and solved frequency points. Initial conditional-sampler
  geometry rejection was 0/6 cells. The independent-uniform reference remained
  close to the R1 rejection rates.
- A post-pilot gate-only correction retains the legacy R1 90% rejection threshold and applies the R1.1 50% threshold; a regression test covers both. Saved Pilot data was not rerun or changed.
- The 96k production run was not started. The R1.1 pass marker and review
  bundle are provided for review; no production, Stage 3.9, hybrid, or
  impedance-sweep work was started.
- Requested model was `gpt-6-sol`; runtime-visible backend identity and
  internal reasoning effort were not exposed and are not claimed as verified.

## 2026-09-23 — Stage 3.8C-R1 post-review pilot outcome

- Implemented the approved geometry-first study comparator, geometry-valid
  initialization, explicit search/validation counters, common-grid finalist
  reevaluation, and the MLIT 30–180 um user-directed aperture override.
- Full regression passed: 224 tests and 14 subtests. Targeted R1 tests passed:
  11.
- The six-cell, 256-evaluation pilot reached physics with finite search and
  common-grid metrics in all six cells. Stage 3.8 implementation validation,
  six fixed-design sanity cases, known-seed preflight, and valid-population
  preflight also passed.
- The pilot gate returned `STAGE3_8C_R1_PILOT_FAIL_STOP`: geometry rejection
  during initial population sampling was 93.27% for M0/T2 and 91.99% for
  MLIT/T2, exceeding the specified 90% limit. Replay diagnostics indicate the
  two dominant hard limits are maximum total acoustic length and maximum total
  electrode count. No search-space or manufacturing limits were changed.
- The 96,000-evaluation production rerun was not started. A bounded review of
  the T2 initialization/search-space definition is required before a new pilot
  or production launch. No Stage 3.9 work, hybrid run, or impedance sweep was
  started.

## 2026-09-13 — Stage 3.5 matched-protocol configuration gate

### Packet

- Scope: decide whether the existing L-SHADE trajectory worker can express the
  matched-protocol run with a 64,000 population-schedule horizon, a 16,000
  diagnostic stop, and one adaptive-grid exchange at 16,000.
- Evidence: the historical D/S1/seed20260917 B16000 snapshot records traces at
  grid version 1 through evaluation 16,000 and serializes the version-2
  exchange after that observation. The current trajectory worker derives its
  L-SHADE total budget and schedule horizon from `max(budgets)`, so a
  `[16000]` request would incorrectly use a 16,000 horizon.
- Constraints: no optimizer/objective/physics/search-space/canonicalization/
  tolerance/seed/budget-semantic changes; one diagnostic run only.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer.

### Decision

- Recommendation: proceed only after a minimal orchestration/configuration
  change that decouples the 64,000 schedule horizon from the 16,000 execution
  stop.
- Required assertions: seed 20260917, S1, Zport 50 ohm, L-SHADE total and
  population horizon 64,000, actual stop 16,000, no 4,000/8,000 exchanges,
  exactly one exchange at 16,000, pre-exchange trace at grid version 1, and
  protected numerical semantics unchanged.
- Historical B16000 semantics are sufficiently supported as PRE_EXCHANGE,
  while broader historical protocol semantics remain UNKNOWN. Do not claim
  FULL_PARITY_PASS from this inference alone.
- Any required change to L-SHADE behavior or protected numerical semantics
  requires a new escalation. No additional user clarification is needed.

### Luna action

Implement only an explicit matched-protocol orchestration/configuration path,
with the existing behavior preserved when the opt-in setting is absent. Add
preflight and post-run guardrails before launching the one diagnostic run.

## 2026-09-16 — CI cross-platform budget and frozen-fixture review

### Packet

- Scope: bounded review of GitHub Actions Run #12 failures after adding the
  missing frozen S1 input.
- Evidence: Python 3.11 CI returned `[8, 10, 10]` for
  `_adaptive_budget_limits(10, 2, [.7, .2, .1])`, while Python 3.12 local
  returned `[7, 9, 10]`; the raw frozen S1 hash also differed because Linux
  checkout normalized CRLF to LF.
- Constraints: no production experiment, objective, COM, search-space, or
  comparison-condition changes; review budget semantics before source edits.
- Requested reviewer: GPT-5.6 Sol, medium reasoning, one reviewer.

### Decision

- Root cause confirmed as Python-version-dependent floating-point summation at
  integer ceiling boundaries.
- Use `Fraction(str(value))` and exact rational cumulative ceilings rather than
  an epsilon or `math.fsum`; this preserves the intended cumulative fraction
  semantics and total-budget fairness.
- The narrow `.gitattributes` rule
  `artifacts/stage3_5/phase_a_revised/search_space_s1.yaml text eol=crlf` is
  appropriate because the provenance contract hashes raw file bytes.
- Retain the existing boundary test and add normalized/non-normalized,
  non-divisible, and monotonicity regression coverage.

### Luna action, verification, and outcome

- Applied the exact rational allocation fix, regression tests, and the narrow
  EOL rule. No production run was launched.
- Full local verification is required before pushing the follow-up commit;
  the GitHub Actions rerun must confirm both the Python 3.11 budget behavior
  and the frozen S1 raw hash.
- Backend model identity and actual internal reasoning effort were not
  independently verified by the runtime; GPT-5.6 Sol and medium reasoning
  were requested through the task API.

## 2026-09-18 — Stage 3.7 literature COM mapping gate

### Packet

- Scope: review the boundary for adding a literature-grounded 42°YX-LiTaO3/Al
  COM profile and for starting the Stage 3.7 50/50-ohm fixed-design and fast
  re-optimization screen.
- Evidence: current repository convention is exp(+j omega t), x left-to-right,
  power-normalized R/S, with dimensional kappa/alpha/C/loss; M0 is the existing
  hypothetical FixedProvider. Reviewed sources include Xue/Dong 2021 DMS,
  Naumenko/Abbott 2002 42°YX-Al trends, and Ma et al. 2022 COM extraction
  normalization definitions.
- Constraints: preserve Stage 3.6 artifacts; do not mix sources or fill
  missing alpha, capacitance, loss, phase, or normalization from M0; no Phase D
  or Stage 3.8 baseline without a complete profile.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer, judgment only.

### Decision

- Conditional GO for the literature audit, M0 parity verification, and clearly
  labeled fixed-design control evaluation.
- Hard NO-GO for Phase D until one indivisible single-source profile provides
  compatible equations/conventions, complex kappa and alpha, distributed C,
  explicit attenuation, phase/reference normalization, stack metadata, and
  source-reconstruction evidence.
- Velocity, k2, effective coupling, resonance frequencies, equivalent-circuit
  values, or incomplete literature tables are insufficient. Reference-only
  profiles may appear in audit/geometry tables but must not be simulated by
  borrowing M0 fields.
- The reviewed candidates were therefore classified REFERENCE_ONLY and the
  stage must terminate with COM_MAPPING_BLOCKED.

### Luna action and outcome

Added an explicit no-fallback LiteratureProfileProvider, M0 parity/unit tests,
an auditable Stage 3.7 registry, and a runner that writes the frozen Gate 2B-B
reference/control artifacts before emitting `STAGE3_7_COM_MAPPING_BLOCKED_STOP`.
No Phase D optimizer run was launched.

- Backend model identity and actual internal reasoning effort were not
  independently verified by the runtime; GPT-5.6 Sol and high reasoning were
  requested through the task API.

## 2026-09-23 — Stage 3.8 dual-material DMS topology fast screen

### Packet

- Scope: implement the Stage 3.8 T0/T1/T2 topology framework and its
  validation/screening protocol without changing COM equations, objective,
  or the production L-SHADE backend.
- Baseline: T0 is the existing fixed R-gap-outer-IDT-gap-center-IDT-gap-
  outer-IDT-gap-R path; Stage 3.6 has a reusable section-geometry path but
  not a generic multi-IDT port map; M0 and MLIT inputs and the 9113-point
  validation-grid identity were audited.
- Requested reviewer: GPT-5.6 Sol, high reasoning, judgment only, no file
  edits.

### Decision

- **APPROVED WITH VALIDATION GATE.** An ordered acoustic section chain plus
  an explicit signed IDT-to-port matrix may reuse `acoustic_admittance` and
  the existing two-port network evaluator. COM equations, objective, and
  L-SHADE must remain unchanged.
- T0 parity must compare generalized versus both legacy and Stage 3.6
  released paths for Y, S, IL, VSWR, metrics, and passivity diagnostics.
- T1 must freeze and record an explicit signed 5x2 mapping. The selected
  implementation uses mirror sections R-A-B-C-B-A-R, P=A+C+A, Q=B+B,
  with alternating signed electrical polarity `[+,-,+,-,+]`; reflector
  count remains a declared fixed reference rather than an extra DOF.
- T2 must sum the two tracks' unterminated two-port Y matrices before one
  source/load termination. Each track receives half of one total aperture;
  the identity is `Y_parallel = Y_A + Y_B`, and for identical tracks it is
  `2 * Y_half_aperture_track`, not twice a full-aperture design.
- The Stage 3.7D recorded recommendation overrides the ambiguous handoff
  wording: use aperture 30--150 um for both M0 and MLIT. A failed physics or
  regression gate rejects the optimization screen.

### Luna action and outcome

- Accepted the review. Implementation is restricted to topology definitions,
  decoders, study/reporting layers, metadata, and tests. No production
  optimization or Stage 3.9/hybrid/impedance-sweep work is authorized by
  this escalation.
- Backend model identity and actual reasoning effort were not independently
  verified by the runtime; GPT-5.6 Sol and high reasoning were requested
  through the task API.

## 2026-09-23 — Stage 3.8C-R1 geometry gate and rerun

### Packet

- Scope: judgment-only review of the hard-geometry ranking correction,
  geometry-valid L-SHADE initialization, auditable evaluation counters, common
  validation-grid final selection, and aperture-bound provenance before any
  Stage 3.8C-R1 pilot/main optimization.
- Evidence: the old evaluator returns geometry-invalid records before COM and
  mixes geometry with filter violations; `DEFAULT_COMPARATOR` then orders
  infeasible records by one `max_violation`. The old 96k run has zero valid
  physics evaluations and zero solved points in all 12 cells. The current R1
  user handoff requests MLIT 30–180 um, while the archived Stage 3.7D record and
  prior Stage 3.8 decision say 30–150 um.
- Requested reviewer: GPT-5.6 Sol, high reasoning, judgment only, no edits or
  tests.

### Decision

- **APPROVED WITH REQUIRED REVISIONS before the 96k rerun.** Keep changes
  study-local: pass a geometry-first comparator to the existing L-SHADE backend;
  preserve `DEFAULT_COMPARATOR` ordering for successful physics records; put
  successful physics ahead of physics failures; and keep all geometry-valid
  results ahead of geometry-invalid results. Use finite positive comparator
  improvements because L-SHADE uses them for SHADE weights.
- Use the same comparator throughout p-best ordering, replacement, shrink,
  incumbent, trace, and final common-grid selection. Re-evaluate eligible
  finalists on the frozen common grid instead of labeling search-grid records
  as validated results.
- Seed each population with the known fixed design, assert its active/hard
  bounds and canonical round-trip, then boundedly sample unique geometry-valid
  members. Keep sampling attempt counters outside the optimizer evaluation
  budget and record a complete partition of attempts, geometry rejections,
  duplicate rejections, and accepted draws.
- At each checkpoint require
  `unique_decoded_evaluations = geometry_invalid_evaluations + valid_physics_evaluations + physics_failure_evaluations`
  and
  `physics_attempted_evaluations = valid_physics_evaluations + physics_failure_evaluations`.
  Count search-grid and common-grid validation work separately. Do not fill
  missing counters with zero.
- Run cold in a fresh run directory/fingerprint; do not resume old Stage 3.8
  checkpoints because their incumbent, trace, counter, population, and bound
  semantics are incompatible.
- Follow the latest explicit R1 user handoff for MLIT 30–180 um, but record it
  as an **R1 user-directed bound override**, not a Stage 3.7D recommendation.
  Keep M0 at 30–150 um. Cross-material differences are confounded by the
  unequal search spaces; within-material topology comparisons remain
  interpretable.
- Required gates before production: rank-path and finite-improvement tests,
  counter identities, fixed-seed validation, a low-budget positive-physics
  smoke, all-cell population preflight, and a detached launch with valid
  callback manifest fields.

### Outcome tracking

- This implementation will preserve T0/T1/T2 physics and will not change the
  global comparator or L-SHADE algorithm. Stage 3.9 and third-seed work remain
  outside this run.
- Backend model identity and actual reasoning effort were not independently
  verified by the runtime; GPT-5.6 Sol and high reasoning were requested
  through the task API.

## 2026-09-18 — Stage 3.7B literature COM reconstruction boundary

### Packet

- Scope: define evidence and stop/go boundaries for mapping one 2024
  42°YX-LiTaO3/Al normalized COM profile into the repository convention,
  reconstructing its native source device, and deciding whether B28 scaling is
  authorized.
- Evidence: the original source has not yet been checked; the handoff values
  are approximate hints only. The repository uses exp(+j omega t),
  power-normalized acoustic envelopes, peak voltage/current, and dimensional
  kappa/alpha/C/gamma. The current no-fallback literature provider delegates
  dimensional alpha/C values to FixedProvider at a reference aperture.
- Constraints: no file edits or experiments by the reviewer; no arbitrary
  fitting, mixed-source values, FEM execution, B28 optimization before source
  reconstruction PASS, or changes to frozen Stage 3.6/3.7A artifacts.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer, judgment only.

### Decision

- Current status is **`STAGE3_7B_COM_MAPPING_BLOCKED_STOP`**. GO is limited to
  retrieving/auditing the original paper, a non-production normalized-provider
  skeleton, synthetic conversion/parity tests, and explicitly partial native
  reconstruction labeled `SOURCE_RECONSTRUCTION_INCONCLUSIVE`.
- A parameter is `CONFIRMED` only when the original source establishes its
  exact definition, units, source row/conditions, and compatibility with the
  repository's phasor, acoustic-power, electrical, sign/phase, spatial-origin,
  aperture, wavelength, and attenuation conventions. `PROVISIONAL` is allowed
  only for a source-supported value with a remaining noncritical ambiguity.
  Any unresolved normalization, sign/phase, acoustic mode, wavelength meaning,
  or amplitude-versus-power loss issue is `BLOCKED`.
- The proposed identities are valid only after that source audit:
  `kappa=kappa_p/lambda`,
  `alpha=alpha_n*sqrt(W/lambda)/lambda`,
  `C=C_n*W/lambda`, and `gamma=gamma_p/lambda`. Native reconstruction must use
  the exact source-device aperture `W`; no substitute representative aperture
  is permitted. If the paper does not report it, alpha/C reconstruction and
  source-device validation remain blocked.
- A dimensional FixedProvider representation derived at `(lambda0, Wref)`
  preserves aperture scaling for all W only while `lambda=lambda0`. It does
  not preserve normalized alpha/C when wavelength changes. A locked derived
  provider must reject other wavelengths; B28 scaling requires runtime
  conversion from raw normalized values.
- Hard stops include incompatible or unresolved substrate stack/cut,
  propagation direction, acoustic mode, electrode material, h/lambda, duty,
  temperature, electrical/acoustic boundary conditions, wavelength definition,
  phasor/power/current conventions, phase registry, and attenuation definition.
  A source-proven notation conversion is acceptable; inferred factor-of-two,
  sign/phase changes, or empirical scaling are not.
- Reported resonator geometry may support a partial reconstruction, but missing
  aperture, gaps, reflector boundaries, terminal conditions, or electrode
  registry must not be guessed. Such a result is `INCONCLUSIVE`, even if the
  dominant resonance lies near `v/lambda`.
- Freeze the reconstruction rubric before simulation. PASS requires conversion
  identities (recommended `rtol <= 1e-12`), finite/passive/reciprocal behavior,
  no tuning or post-result tolerance changes, correct published resonance and
  antiresonance ordering, frequencies within the larger of 2% or source plot/
  table resolution, and native DMS mode count/order/frequencies meeting the
  same tolerance. Missing geometry/observables is `INCONCLUSIVE`; wrong
  ordering, nonpassivity, severe mismatch, or required fitting is `FAIL`.
- Native-resonator PASS with incomplete native 3-IDT DMS geometry does not
  authorize B28 fixed-design evaluation or re-optimization. A complete native
  DMS `SOURCE_RECONSTRUCTION_PASS` is the hard gate; the later
  `PHYSICALLY_PLAUSIBLE_BUT_UNCERTAIN` label cannot bypass it.
- Conservative classification remains `REFERENCE_ONLY`. If any critical
  mapping or source geometry stays unavailable, record:
  `FEM_EXTRACTION_REQUIRED — Stage 3.7B stops without B28 scaling or
  re-optimization. A separate approved stage must extract v, kappa_p, alpha_n,
  C_n, and gamma_p for 42°YX-LiTaO3/Al at the locked h/lambda, duty,
  temperature, acoustic mode, and B28-scale wavelength using short-circuit
  periodic dispersion, stopband edges, open/short velocity, static
  capacitance, harmonic admittance, and resonance-Q/loss evidence. FEM
  execution is not authorized in Stage 3.7B.`
- A normalized provider is acceptable only as a separate no-fallback path that
  stores raw normalized values, converts at runtime, enforces profile validity
  conditions and complete region data, and preserves complex phase references.
  Keep M0 on unchanged FixedProvider semantics and retain exact
  `rtol=atol=0` parity tests. Reverse-normalization, multi-aperture,
  multi-wavelength, locked-wavelength rejection, passivity/reciprocity, and
  immutable-metadata tests establish algebraic correctness only, not scientific
  eligibility.

### Luna action and outcome

- Accepted the review. No implementation or experiment was run. The only file
  change from this review is this requested escalation-log entry.
- Stage 3.7B remains stopped at the source/mapping gate pending acquisition and
  direct audit of the original paper.
- Backend model identity and actual internal reasoning effort were not exposed
  or independently verified by the runtime; GPT-5.6 Sol and high reasoning
  were requested through the task API.

## 2026-09-18 — Stage 3.7B implementation outcome

The primary candidate was audited against the current solver convention. The
raw Table 2 values are preserved, but the accessible source does not expose
the native aperture, electrode material, complete DMS geometry, phase/terminal
registry, or an unambiguous loss convention. The normalized adapter is
therefore research-only and has no M0 fallback.

Decision: `STAGE3_7B_COM_MAPPING_BLOCKED_STOP`. No native-device numerical
reconstruction, B28 scaling, or optimization was launched. Source-level
confirmation or a separately approved FEM extraction is required.

## 2026-09-18 — Stage 3.7B-R1 normalized COM validation

### Packet

- Scope: execute the revised R1 frequency-only validation using the 2024
  paper as the sole numeric source and the 2022 paper only for normalization
  definitions, with an explicit evaluation aperture and no re-optimization.
- Evidence: the 2024 Table 2 values are retained as raw source data; the
  source-device aperture and complete native DMS registry remain unavailable.
  The current solver uses peak-V/current-into-transducer conventions, while
  the definition source describes half-power amplitude values.
- Requested judgment: whether an 80 um evaluation aperture, signed-real phase
  policy, and amplitude-loss gamma mapping are acceptable for frequency-only
  diagnostics and whether the frozen B28 fixed-design sensitivity may run.
- Requested reviewer: GPT-5.6 Sol, high reasoning, one reviewer, judgment only.

### Decision

- **`CONDITIONAL_GO_STAGE3_7B_R1_FREQUENCY_ONLY`**. The 80 um value is
  acceptable only as an explicitly labelled evaluation aperture; it is not
  source geometry and cannot support absolute admittance, conductance, or
  matching claims.
- Use the 2024 paper for all numeric values. Use the 2022 paper only for the
  algebraic definitions `kappa_p=kappa*lambda`, `alpha_p=alpha*lambda`,
  `alpha_n=alpha_p/sqrt(W/lambda)`, and `C_n=C*lambda/W`; retain the
  half-power-versus-peak-V convention mismatch as an uncertainty.
- Gamma conversion is allowed only as the explicit amplitude-attenuation
  assumption. One-port reciprocity is not a meaningful gate; report it as
  not applicable and retain passivity validation.
- Missing source phase may use only the explicit
  `SIGNED_REAL_TABLE_ASSUMPTION` policy (`kappa` signed-real, `alpha`
  positive-real) for frequency-only work. Without digitized source features,
  the native result is at most `INCONCLUSIVE`; 2% is the preferred feature
  tolerance and 5% is the failure boundary. Do not fit or sign-correct after
  observing the result.
- The frozen Gate 2B-B fixed-design sensitivity is permitted only after the
  round-trip, native frequency, full regression, passivity, phase-sensitivity,
  and frozen-reference checks pass. It remains exploratory and must not be
  interpreted as source-device matching. 8k re-optimization is not automatic.

### Luna action and outcome

- Implemented the explicit R1 phase/loss policies, normalized source-value
  audit output, frequency-only native resonator validation, phase sensitivity,
  and frozen-reference gating. No optimizer or FEM execution was performed.
- R1 run completed with round-trip mapping PASS, native resonator
  `RESONATOR_FREQ_INCONCLUSIVE` (3.13% feature scale error and no numeric
  source feature digitization), targeted tests `10 passed`, and full
  regression `202 passed`. Phase sensitivity was not robust within 2% of f0,
  so the B28 fixed-design sensitivity was correctly not executed.
- Final run label: `LITERATURE_COM_MAPPING_PASS`; this label covers the
  algebraic mapping only and does not promote the profile to a calibrated
  material model. The next scientific branch remains
  `FEM_EXTRACTION_REQUIRED` if phase/loss uncertainty must be resolved.
- Backend model identity and actual internal reasoning effort were not
  independently verified by the runtime; GPT-5.6 Sol and high reasoning were
  requested through the task API.

## 2026-09-24 — Stage 3.8C-R1.2 initializer judgment

### Packet and requested reviewer

- Scope: judgment only on the initializer proposal law, rejection/uniqueness
  semantics, attempt cap, diversity gates, and initializer-only distribution
  regression before implementation.
- Requested review target: `gpt-6-sol`, as required by the active project
  policy. No fallback to GPT-5.6 Sol was requested.
- Packet: `reports/stage3_8c_r1_2_initializer_escalation.md`.

### Decision

- Preserve the R1 law: independently draw each active real-valued coordinate
  uniformly in its declared interval, then apply the existing
  `_canonical_physical` integer rule (`floor(x + 0.5)`), then apply the hard
  geometry test. Integer endpoints consequently have half the mass of an
  interior integer coordinate when bounds are integral; replacing this with
  categorical uniform integer draws would change the original law.
- Keep one known valid fixed design as the explicit first member. Fill the
  remaining slots with independent proposals, rejecting geometry-invalid
  candidates and duplicate canonical designs. No invalid-candidate repair or
  topology-dependent conditional resampling is allowed.
- Use a finite cap `max(10000, 60 * N)` and fail explicitly with
  `INITIALIZER_EXHAUSTED`. Record the full accounting identity and keep
  rejection fraction diagnostic-only for R1.2.
- Gate exact population size, 100% geometry validity, cap completion,
  canonical uniqueness, reference-informed diversity, and measured practical
  runtime. Compare initializer-only samples against a no-COM Monte Carlo
  reference, including integer variables and total electrode/length metrics.
- Pilot only: six material/topology cells, seed `20260917`, 256 evaluations
  per cell. No production run or promotion is authorized by this judgment.

### Luna action and outcome

- Implemented the specified initializer, diagnostics, gates, and pilot-only
  R1.2 path. Targeted tests passed (19); full repository regression passed
  (232 tests and 14 subtests). The six-cell initializer-only preflight passed
  distribution/diversity checks, and historical R1 seeded populations
  replayed exactly.
- Requested GPT-6 Sol review was accepted through the task routing. The
  runtime did not expose resolved backend identity or internal reasoning
  effort; neither is claimed as verified.

## 2026-09-24 — Stage 3.8.5 architecture boundary review

### Packet

- Scope: bounded architecture-risk review before structural edits; judgment only.
- Decision requested: define safe boundaries for additive fingerprint v2 and generic review bundles, DMS topology extraction, and comparator/counter/accounting/sampler ownership.
- Constraints: no source edits by reviewer, no optimizer or Stage 3.8 reruns, preserve the Stage 3.8 legacy fingerprint/gates/artifacts, and avoid numerical, comparator, accounting, or RNG behavior changes.
- Inventory: existing canonical candidates are `reporting/review_bundle.py`, `optimization/counters.py`, `optimization/population.py`, `optimizers/selection.py`, and `io/run_store.py`; Stage 3.8 R1 combines its fingerprint, geometry-first comparator, counters, sampler, and checkpoint validator in the study module. T0 imports its released design and simulator from Stage 3.6.
- Requested reviewer: `gpt-6-sol`, high reasoning effort requested through the task API. Runtime-visible backend identity and actual reasoning effort were not independently exposed.

### Decision

- Add `io/provenance.py` as an opt-in schema-v2 API using explicit, sorted dependency manifests. Keep `run_store.initialize`, Stage 3.8 `_source_fingerprint`, persisted v1 fields, and v1 gates untouched. The mixed Stage 3.8 study file must not be included in a future computation dependency set if reporting-only edits are to remain isolated.
- Preserve the legacy `create_review_bundle` API/CLI and its Stage 3.1/3.2 behavior. Factor content-agnostic packaging primitives; add declarative new-study bundle specifications. Bundle generation must consume saved run artifacts and must not import a study runner or optimizer. Do not substitute current source for a historical source snapshot.
- Extract pure DMS structures, section construction, topology simulation, and decoders into `problem/dms_topologies.py`; retain old imports as re-exports. Keep config/material-dependent initialization in the Stage adapter. T0's Stage 3.6 dependency remains an extraction boundary to resolve without importing a study from `problem`.
- Move geometry-first comparison verbatim to `optimizers/selection.py` as a distinct comparator; it is not semantically interchangeable with `FeasibilityFirstComparator`. Keep R1 counters distinct from the existing generic counters. Move checkpoint validation verbatim behind a compatibility adapter. Move the R1.2 sampler only after fixed-seed array and statistics replay coverage.
- Preserve legacy current-source verification for old bundle creation. A new generic v2 bundle must carry the run's recorded/snapshotted source evidence and must not rewrite the historical manifest.
- Recommended sequence: additive fingerprint v2; generic bundle APIs; comparator/counter/accounting extraction; sampler last; DMS extraction; deterministic parity and smoke checks.

### Luna action, verification, and outcome

- Accepted the boundary recommendations. Implementation remains limited to structural moves and additive v2 APIs; Stage 3.8 historical run artifacts will not be rewritten and no optimizer is being rerun.
- Baseline full tests: 242 passed, 1 warning, 14 subtests passed. See `reports/stage3_8_5_baseline.md`.
- Final verification: targeted structural/parity/fingerprint/bundle regressions passed; final full suite passed **256 tests, 1 warning, 14 subtests** in 106.59 s. The warning remains the existing pytest cache permission warning.
- A deterministic MLIT/T1 smoke (seed `385085`, 8 evaluations) passed, including repeatable population/incumbent replay, result persistence, schema-v2 fingerprints, independent saved-run bundle generation, and archive hash validation. It is not a performance comparison.
- No Stage 3.8 Production/Pilot/8k/96k/Monte Carlo optimizer rerun was performed. No Stage 3.8 historical artifacts were rewritten. The Stage 3.8 legacy fingerprint implementation and `run_store.initialize` remain unchanged; schema v2 is additive for future runs.
- Review bundle: `artifacts/review_bundles/stage3_8_5_architecture_cleanup_review.zip`.

## 2026-09-24 — Stage 3.8.6 checkpoint lifecycle architecture review

### Packet

- Scope: bounded high-risk architecture judgment before checkpoint storage lifecycle edits; judgment only.
- Decision requested: canonical owner/API, safe fallback behavior, success-gated finalization, coverage of L-SHADE and custom continuation checkpoints, and generic review-bundle metadata integration.
- Constraints: preserve optimizer state payload and all numerical/RNG semantics; no Stage 3.8 or historical-run cleanup; no fingerprint schema v3; keep reporting separate from lifecycle deletion.
- Inventory: no lifecycle owner exists; L-SHADE writes raw JSON at several study call sites; continuation writes per-milestone population snapshots without a matching load path; buffered JSONL history already exists; generic review bundle filters every path component containing `checkpoint`.
- Requested reviewer: `gpt-6-sol`, high reasoning effort requested through the task API. Runtime-visible backend identity and actual reasoning effort were not independently exposed.

### Decision

- Use `sawopt.io.checkpoints` as the canonical owner of per-stream atomic rolling stores. New call sites provide their existing serializer callback; do not change optimizer state payloads. Keep direct L-SHADE file APIs for legacy single-file compatibility.
- Validate staged JSON before rotation. Resume newest-to-oldest and fall back to `previous` after validation/load failure using a fresh backend/trajectory instance, never a partially mutated instance. Preserve legacy loading and leave old runs unmigrated.
- Finalize idempotently only after a durable successful completion marker. Promote the newest valid payload to `final`; remove runtime files only after that succeeds. Failed or incomplete direct runs retain recovery state.
- Continuation may use the same filesystem retention lifecycle, but its snapshots are not exact RNG-resume states. Preserve lightweight milestone accounting without asserting removed full snapshots still exist.
- Keep checkpoint metadata at a neutral path such as `metadata/recovery_policy.json` so the generic bundle's checkpoint filter does not omit it. Keep deletion and rotation out of reporting.

### Luna action, verification, and outcome

- Implemented a shared rolling checkpoint store, L-SHADE compatibility adapter,
  success-gated finalization, lightweight continuation accounting, and compact
  Review Bundle metadata handling. Stage 3.8C-R1 and the hashed Stage 3.8 topology
  source callsites were left on their prior checkpoint path to preserve their
  legacy gate inputs; rolling retention there is deferred.
- Targeted checkpoint, continuation, review-bundle, and worker tests passed
  (40 passed); final checkpoint/worker regression after the prior-final
  preservation adjustment passed (20 passed). Final full regression passed
  (273 passed, 14 subtests; one existing pytest cache-permission warning).
- A deterministic synthetic 64-evaluation L-SHADE smoke matched uninterrupted
  and resumed optimizer state, retained four history rows, reduced four
  old-style milestone payloads (132,936 bytes) to two runtime generations
  (88,253 bytes), then finalized to one state. The generic review bundle
  validated all manifest hashes and sizes.
- Review bundle: `artifacts/review_bundles/stage3_8_6_checkpoint_retention_cleanup_review.zip`.

## 2026-09-24 — Stage 3.8.6 checkpoint-retention correction review

### Packet

- Scope: bounded architecture judgment for runtime checkpoint references,
  explicit run disposition, and historical marker compatibility.
- Decision requested: keep a future `final.json` out of active result metadata;
  remove Stage marker names and outcome inference from the generic checkpoint
  core; define safe handling for missing and unknown dispositions.
- Constraints: preserve checkpoint payloads and optimizer/RNG semantics, keep
  Stage 3.8 historical source and artifacts protected, and do not launch an
  optimizer run.
- Requested reviewer target: `gpt-6-sol`; the runtime did not expose verified
  backend identity or actual reasoning effort.

### Decision

- Use a shared `RunDisposition` type with `COMPLETED`, `REVIEW_WAITING`,
  `FAILED`, and `UNKNOWN`; generic finalization requires explicit
  `COMPLETED`. Missing or unknown values preserve runtime checkpoints.
- Move the four historically recognized review markers to a compatibility
  adapter. Keep scientific gate pass/fail separate from execution lifecycle.
  Legacy clean process returns may establish execution completion; marker-based
  review waiting overrides it.
- Managed result records identify a rolling checkpoint stream and policy.
  Legacy direct-file mode keeps its physical path. Do not point active records
  at a future final checkpoint.
- Run-level discovery accepts only validated `retention.json` files directly
  inside managed `checkpoints/` directories. A later review release requires
  an explicit reviewed-closeout action; callback or `REVIEWED` state alone does
  not finalize.

### Luna action and verification

- Accepted the recommendations. No optimizer algorithm, state payload,
  fingerprint schema, or Stage 3.8 historical runner change was made.
- Targeted and full regression outcomes will be recorded after verification.

### Supplemental decision — legacy run fingerprint boundary

- Finding: historical `run_store.initialize` v1 hashes every Python source file
  and rejects a changed source tree before legacy checkpoint loading can occur.
- Decision: preserve that v1 contract. Do not bypass or migrate its manifest.
  Legacy checkpoint-format loading and read-only review remain supported; a
  legacy run cannot resume under changed source without its matching historical
  checkout. This is a compatibility boundary, not a successful legacy run
  resume claim. Existing dirty Stage 3.8.5 source edits may also affect saved
  hashes, so mismatches are not attributed exclusively to Stage 3.8.6.
- Reviewer: `gpt-6-sol` requested through the project escalation workflow;
  the runtime did not expose resolved backend identity or reasoning effort.

### Supplemental decision — scoped review-bundle Git diff

- Finding: the generic builder's default Git snapshot included the entire dirty
  worktree diff, which would put unrelated pre-existing edits in this correction
  bundle despite the instruction to include a scoped diff.
- Reviewer judgment: add an optional literal `git_diff_paths` scope for staged
  and unstaged patches; keep HEAD, branch, and full `git status --short`. Record
  the scope in the manifest, reject absolute/traversing/glob/pathspec-magic
  entries, and use Git's literal pathspec mode. Untracked relevant files remain
  available in the source snapshot and scoped baseline patch.
- Outcome: implemented and covered by a temporary Git-repository test,
  including full-status retention and staged/unstaged scope. No computation
  fingerprint or numerical behavior changed.
- Reviewer: `gpt-6-sol` requested through the project escalation workflow;
  runtime-visible backend identity and internal reasoning effort were not
  independently exposed.

### Final verification

- Targeted checkpoint, worker, provenance/fingerprint-v2, and bundle tests
  passed (49); after the final bundle-scope adjustments, the bundle module's
  targeted tests passed again (14).
- Final full regression passed: 288 tests and 14 subtests in 115.96 s, with one
  existing pytest cache-permission warning.
- Resume parity and RNG continuation matched the uninterrupted fixed-seed
  L-SHADE run. No production optimizer run was started.
- Review bundle: `artifacts/review_bundles/stage3_8_6_checkpoint_retention_correction_review.zip`.

## 2026-09-25 — Historical cleanup pre-deletion convergence evidence review

### Packet and decision

- Packet: `reports/historical_cleanup_convergence_evidence_escalation.md`.
- Scope: canonical ownership of optimizer-independent checkpoint evidence,
  temporary compatibility behavior, and minimum parity gates. The correction
  instructions prohibit historical bulk deletion and numerical changes in
  this pass.
- Judgment requested from `gpt-6-sol`: whether
  `optimization/convergence_evidence.py` is the appropriate owner, whether
  old study callers need an interim import path, and what checks should gate
  the move. The runtime did not expose independently verified backend identity
  or actual reasoning effort.
- Decision: `sawopt.optimization.convergence_evidence` is the appropriate
  canonical location because evidence derivation is optimizer-independent.
  Move the reusable L-SHADE record caller now, retain the studies path as a
  temporary re-export for historical callers, and remove that shim with the
  historical runners in the deletion phase. Gate with fixed expected evidence
  fixtures covering events, incomplete telemetry and missing fields,
  checkpoint selection/overrides, and numeric/trace fallbacks; also compare a
  controlled L-SHADE serialization fixture while normalizing volatile timing.
- Outcome: implemented the ownership move and compatibility re-export. The
  moved implementation preserves its behavior; public helper names were
  exposed at the DMS common-helper boundary so downstream imports no longer
  depend on private names. No optimizer algorithm, serialized record meaning,
  COM, network, objective, or experiment condition changed.

### Verification

- Focused historical-cleanup characterization command passed: 72 tests in
  31.54 s. This covered architecture boundaries, convergence evidence,
  L-SHADE serialization, checkpoints, T0/T1/T2 topology behavior, released DMS
  field/geometry/S-parameter/metric parity, and Stage 3.8C closeout regressions.
- Full regression passed: `297 passed, 14 subtests passed` in 106.24 s using
  `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q`.
- No production optimizer or historical optimization run was started.

## 2026-09-25 — Historical cleanup deletion-phase boundary review

### Packet and decision

- The temporary Sol review packet was consolidated into this decision record
  after implementation and verification.
- Scope: the boundary between the completed, Stage-named 3.8C R1.2 gate
  sequence and the cleanup plan's living DMS topology study, plus safe deletion
  order for historical runners and their configs/tests/shims.
- Judgment requested from `gpt-6-sol`. Runtime-visible backend identity and
  reasoning effort were not independently exposed.
- Decision: preserve the R1.2 numerical study capability by moving its
  behavior to a role-based DMS topology study module. Treat the completed R1,
  R1.1, and R1.2 approval/gate sequence, exact production config, separate
  Stage 3.8 fast-screen runner, and Stage 2 topology study as historical. Keep
  geometry-first ranking, independent-uniform rejection sampling,
  per-material/per-seed T0/T1/T2 evaluation, deterministic RNG, unique
  evaluation/checkpoint accounting, common-grid evaluation, and result fields.
  Do not change canonical physics or optimizer code.
- The old R1.2 production YAML is not a reusable current config: it reads
  prior runs for validation grid and initial designs, compares R1/R1.1 runs,
  and depends on one-time pilot/report gates. Build a clean role-based config
  from explicit current inputs; preserve exact grid/design values and their
  historical origin where they remain necessary. Omit one-time gates and
  comparators. Do not claim numerical equivalence for future runs without
  evidence.
- Split work into verified waves: (1) cut over the current study adapter,
  config, dispatch, and focused tests; (2) remove historical Stage 2–3.7
  runners/configs/descriptors/shims/aliases and matching tests; (3) remove the
  separate Stage 3.8 fast screen plus the old Stage 3.8C runner/revision
  configs/closeout tests/report builder; (4) prune completed handoffs and
  temporary reports, then run the final gates. Keep runs and review bundles
  intact. Existing source snapshots, recorded fingerprints, old paths, and
  SHA strings remain immutable historical evidence.

### Implementation status

- Preserved the R1.2 numerical capability in the role-based
  `studies/dms_topology_screening.py` adapter and a clean role-based config.
  The dispatch now accepts only that current protocol. The common released-DMS
  representation and numerical behavior remain in canonical problem/optimizer
  modules; no COM physics, objective, optimizer algorithm, or experiment
  conditions were changed.
- Removed Stage 2–3.8 historical runners, shims, experiment configs and
  descriptors, Stage-specific tests/report builders, completed tracked
  handoffs, and temporary reports. Updated the current README and history
  register. Kept `runs/`, review bundles, the annotated pre-deletion tag, and
  the two untracked user-provided handoff documents.
- Focused migration suite passed: `88 passed, 1 subtest passed` in 57.60 s.
- Full regression passed: `165 passed, 11 subtests passed` in 72.04 s using
  `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q`.
- Static Python import search found no references to removed modules. The
  architecture boundary test passed. No production optimizer was launched.

## 2026-09-26 — C2C IAB computer-use control boundary

### Packet and decision

- Scope: choose the project-specific procedure for operating ChatGPT through
  the built-in IAB after the user requested that the computer-use Skill be the
  standard.
- Evidence and constraints: `docs/c2c/OPERATIONS.md` and
  `docs/c2c/SECURITY_BASELINE.md` named the Browser Skill bootstrap and
  prohibited Computer Use generically. The user authorized computer use only
  within IAB. C2C/ChatGPT PLAN recommended preserving the existing
  `browser-client.mjs` bootstrap while narrowing the prohibition.
- Requested reviewer: GPT-6 Sol (`gpt-6-sol`), high reasoning, judgment only.
  Backend model identity and actual reasoning effort were not independently
  exposed.
- Judgment requested: whether to preserve the Browser Use bootstrap or
  document the currently exposed IAB computer-use API, and which credential,
  consent, and non-IAB boundaries must remain explicit.

### Sol judgment

- Use the current `mcp__cua_repl` IAB APIs for ChatGPT browser interaction;
  keeping the old Browser Use bootstrap would not implement the user's request.
- Use the computer-use Skill for its safety rules and the tool's current
  documentation for IAB initialization and tab selection. Do not imply
  approval for native Windows controls, `@oai/sky`, or external browsers.
- Hand authentication secrets, pairing-code entry, and consent or permission
  prompts to the user; preserve the doctor gate, workspace identity, read-only
  MCP boundary, and review governance.

### Codex action and outcome

- Updated only the project C2C operating and security-baseline guidance plus
  this required escalation record. Removed the Browser Use bootstrap as the
  approved path and documented IAB-only control and user handoffs. The
  reviewed C2C checkout, connector scope, tunnel baseline, and numerical code
  were not changed.

## 2026-09-27 — Stage 3.9B budget-extension protocol

### Packet and decision

- Scope: first bounded viability experiment for the MLIT/T1 cell following
  Stage 3.9A's no-rerun diagnosis. The proposed run uses Zs=Zl=50 ohm, cold
  starts, seeds 20260917 and 20260918, 16,000 unique evaluations per seed,
  and checkpoints every 2,000 evaluations. The common validation grid,
  constraints, objective, COM profile, comparator, initializer, frequencies,
  and search bounds remain unchanged.
- Judgment requested from `gpt-6-sol`: whether this is an appropriate first
  viability test; whether the population schedule should preserve its 8,000
  evaluation horizon or expand to 16,000; and whether parity and stopping
  criteria are sufficient. Backend identity and actual reasoning effort were
  not independently exposed.
- Decision: proceed with the two-seed 16,000-evaluation MLIT/T1 cold-start
  experiment while explicitly retaining the 8,000 population schedule
  horizon. This isolates the extra evaluation budget from a changed
  0–8,000 population-size schedule; after 8,000, the minimum population is
  retained.
- Required controls: preserve all other experiment inputs; retain separate
  outputs; compare initial samples, incumbent decoded designs, objective and
  components, population sizes, available population/cache trajectory, and
  evaluation accounting at 2k/4k/6k/8k; require exact deterministic equality
  where applicable and predeclare any numerical tolerance. An unexplained
  overlap mismatch invalidates the extension interpretation and must be
  diagnosed before proceeding.
- Acceptance/stopping: existing full feasibility and validity gates define
  viability; report improvement separately from viability. Complete the
  planned 16k per seed unless a numerical/accounting/parity failure or formal
  search-space exhaustion prevents valid continuation. Do not use plateau
  stopping. Two seeds are a bounded diagnostic only; neither a positive nor a
  negative outcome establishes a robust rate or physical impossibility.
  Further budget, schedule, or production runs require a separate approval.

### Codex action and outcome

- Added a backward-compatible optional material/topology selection to the
  current DMS study. The default remains the complete M0/MLIT × T0/T1/T2
  matrix; selected axes now flow through fixed/known-design preflight, run
  metadata, optimization loops, summary metadata, and checkpoint accounting.
- Added a Stage 3.9B config for only MLIT/T1 at Zs=Zl=50 ohm, seeds 20260917
  and 20260918, 16,000 unique evaluations per seed, and 2,000-evaluation
  checkpoints. The L-SHADE population schedule horizon is explicitly 8,000;
  the schedule is held at minimum population beyond that point.
- Added a reproducible Stage 3.9A no-rerun diagnosis and persistent JSON/CSV/
  Markdown evidence for separate M0/T0 and MLIT/T1 lanes under
  `artifacts/review_bundles/stage3_9a_search_viability_diagnosis/` (16
  checkpoint rows). M0/T0 plateaus from 2,000 with lower-bound pressure;
  MLIT/T1 improves through 8,000 without final active-bound hits. Both remain
  infeasible at 8,000 and pass hard geometry checks.
- Validation: focused DMS study suite passed (9 tests); both scripts compiled;
  Stage 3.9B implementation, known-design and fixed-design checks passed on
  the 9,113-point common grid, and a 200-evaluation smoke run completed. The
  experiment preflight evidence is under
  `artifacts/review_bundles/stage3_9b_budget_extension_preflight/`.
- No COM physics, objective, constraints, search bounds, initializer,
  comparator, or frequency grid were changed. No 16k production optimizer was
  launched. Before interpreting a future extension, its 2k–8k overlap must
  satisfy the Sol parity gate; before production launch, C2C must accept the
  implementation/preflight and the required callback session must be valid.

## 2026-09-27 — Stage 3.9B retry blocked at callback preflight

- C2C accepted the schema-v2 orchestration recovery and authorized a fresh
  8,000-evaluation-per-seed overlap-parity retry under
  `runs/stage3_9b_mlit_t1_50ohm_overlap_parity_20260927_retry1/`.
- The callback-enabled asynchronous launch was attempted with the current
  Codex session. Preflight failed closed before creating the retry root or
  starting a worker: the Codex CLI could not emit a target `session_id` or
  `thread_id` JSON event because it could not initialize its in-process
  app-server client.
- A direct diagnostic identified a read-only database failure at
  `C:\Users\sub\.codex\state_5.sqlite` and access denied under
  `C:\Users\sub\.codex\tmp\arg0\...`. One narrowly scoped elevated launch
  retry produced the same failure. No safe, narrowly scoped permission
  recovery was available; callback validation and sandbox boundaries were
  not weakened.
- Outcome: no optimizer process, worker, or retry run was created. The prior
  failed attempt remains preserved. The 16,000-evaluation extension remains
  gated on completion and C2C acceptance of the 8,000-evaluation overlap
  parity run. Recovery is blocked pending repair of the Codex session state
  and temporary app-server access so callback preflight can pass.
- C2C independently reviewed iteration 5 and confirmed the retry root and
  optimizer output are absent, the original failed attempt is preserved, and
  the task is `BLOCKED`. Unblocking requires repairing the host state/temp
  access and passing the exact-session callback preflight in the normal,
  non-elevated launch context; return to C2C before creating the fresh retry.

## 2026-09-27 — Stage 3.9B overlap retry launched without session resume

- The user stated that session resume is temporarily frozen and explicitly
  directed execution without it. C2C re-planned and authorized this specific
  8,000-evaluation × 2-seed overlap run with `--no-callback`; no science or
  comparison settings changed.
- Launched asynchronously with the project virtual environment and accepted
  config under the fresh root
  `runs/stage3_9b_mlit_t1_50ohm_overlap_parity_20260927_retry1/`.
  `run_id=20260926_183341_71d671`. The CLI verified the optimizer output
  directory was absent/empty before starting; startup artifacts now exist in
  the nested `optimizer/` directory.
- The schema-v2 manifest was verified: `optimizer_run_dir` is the nested
  `optimizer/` path; the recorded `--run` matches; config path is the accepted
  overlap config; `codex_session_id`, `codex_session_source`, and
  `callback_preflight` are null; `callback_enabled` and
  `review_after_completion` are false. The session checkpoint has the same
  run ID and null session ID.
- C2C independently confirmed durable status `RUNNING` and accepted the
  launch checkpoint. It reports worker PID 17832 and optimizer PID 24208;
  the launcher console reported PID 33080, so use durable status as the
  authority for subsequent operations. No stdout polling or synchronous
  wait was performed. Completion/parity review remains a later manual step;
  the 16,000-evaluation extension remains unauthorized.

## 2026-09-27 — Sol escalation: Stage 3.9B overlap parity divergence

### Packet and judgment requested

- Scope: interpret the completed, C2C-authorized Stage 3.9B overlap result
  before proposing any repair or additional optimization run. The experiment
  used the accepted MLIT/T1, 50/50 ohm config, seeds 20260917/20260918,
  cold starts, 8,000 evaluations per seed, and checkpoints at 2k/4k/6k/8k.
  It ran asynchronously without callback/session resume under the explicit
  user instruction and C2C's iteration-6 exception.
- Evidence: run `20260926_183341_71d671` completed with exit code 0. The
  accepted verifier reports FAIL at all 8 checkpoint cells and 16,979 total
  mismatches. Passing gates: both checkpoint lattices and resolved protocol
  inputs. Failing gates: checkpoint comparisons, full optimizer state/cache,
  initializer evidence, 8k common-grid finalists, and run metadata snapshots.
  Dominant differences are 15,998 cache keys, 760 archive-trace sizes, and
  80 exact optimizer archive state values. Initial geometry rejection counts
  differ (3 vs 7 for seed 20260917; 6 vs 7 for seed 20260918); selected
  common-grid designs/metrics also differ. A common-grid file-byte hash
  mismatch is also reported. Full evidence is under
  `artifacts/review_bundles/stage3_9b_overlap_parity_retry1_review/`.
- Requested reviewer: GPT-6 Sol, bounded judgment only. Assess whether the
  observed result establishes real trajectory/protocol divergence versus a
  verifier or provenance-normalization defect, identify the smallest
  read-only diagnostics that can distinguish them, and state whether any
  interpretation beyond “parity failed” is justified. Do not implement a
  fix, change scientific settings, or launch another optimization run.
- C2C has been asked to independently review/accept the actual result. No
  repair or rerun is in progress; the 16,000-evaluation extension remains
  unauthorized pending a valid parity PASS and C2C acceptance.

### Sol judgment and bounded follow-up diagnostics

- Sol judgment: the initializer RNG seeds and evaluated design sequence differ
  materially; this is real initialization/trajectory divergence, not merely
  metadata or float serialization. The complete historical cause was
  unresolved at judgment time. Do not claim optimizer regression, changed
  physics, or superior performance from these data; no code/config change or
  rerun was authorized.
- Read-only source/hash investigation recovered the retained R1.2 seed recipe:
  `stage3_8c_r1_geometry_first_v1/r1_2_independent_rejection/...`. It
  reproduces both canonical persisted initializer seeds (3938065196 and
  1982837181). The current recipe uses
  `dms_topology_geometry_first_independent_rejection_v1/independent_rejection`
  and reproduces the retry seeds (3688039291 and 2750583874). The recorded
  canonical Git head predates the runtime source path, which its own metadata
  records as untracked; the retained pre-prune implementation and persisted
  seeds corroborate the recipe, but the exact source blob at that Git head is
  unavailable.
- A no-physics replay used the historical seeds with the current initializer.
  Both seeds reproduced all 180 initial cache keys exactly in order; all
  sampling counters, rejection reasons, variable distributions, and geometry
  distributions matched the canonical metadata. This isolates the initial
  population difference to seed-contract drift rather than current sampler
  logic. No optimizer or COM/RF evaluation ran.
- The reference, canonical-run, and overlap-run grid CSV files are byte
  identical (raw SHA-256 `84afd1e7...`). All three parsed 9,113-point arrays
  are elementwise equal (array ID `2e24c4ce...`). Metadata contains the LF-
  normalized source hash `54c1daf6...`; the verifier compared that to raw file
  bytes and reported a serialization-only mismatch. Numerical grid equality
  remains exact.
- Diagnostic bundle: `artifacts/review_bundles/stage3_9b_overlap_parity_root_cause/`.
  The result and diagnostic bundle were sent to C2C for independent review.
  No scientific code/config edit, new overlap run, or 16,000-evaluation run is
  authorized. Obtain Sol judgment before any seed-contract correction or
  repeated overlap experiment; require C2C acceptance before implementation.

### C2C diagnostic acceptance and Sol remediation judgment

- C2C iteration 8 independently accepted the forensic bundle and confirmed
  the root-cause conclusion: the first real divergence is initializer RNG
  seed-contract drift; the current sampler reproduces both historical
  populations exactly when given the canonical seeds. The grid-hash issue is
  serialization-only; exact numerical-array equality remains a required gate.
- Sol judgment: the bounded repair should preserve the historical namespace
  and `r1_2_independent_rejection` suffix as an explicit parity compatibility
  contract, avoiding a global change to unrelated DMS studies. Correct the
  verifier's documented LF-normalized hash comparison separately; do not
  weaken the exact array/count/ID checks. This judgment authorizes no code
  change or production run.
- Before a fresh 8,000-evaluation overlap, Sol requires source-level
  compatibility evidence for comparator ordering, evaluator payload/ranking,
  design decoding/canonicalization, optimizer configuration, and checkpoint
  scheduling. Record source hashes and preserve the caveat that the exact
  canonical runtime source blob is unavailable at its recorded Git head. An
  unchanged tracked `lshade.py` alone does not close this gap.
- Required gates: C2C repair PLAN, recorded Sol judgment, targeted repair
  validation, C2C acceptance of the integrated implementation and launch
  preflight, then C2C review of the rerun. The 16,000-evaluation run remains
  unauthorized until repaired 8,000-evaluation parity passes and C2C accepts
  it.

### C2C repair PLAN and bounded implementation validation

- C2C iteration 9 accepted Sol's judgment and authorized only the scoped seed-
  contract mechanism, Stage 3.9B parity hash correction, tests, metadata, and a
  read-only compatibility evidence builder. No pilot or production optimizer
  launch was authorized. Source-compatibility evidence is a post-implementation,
  pre-launch gate.
- Added explicit `stage3_8c_r1_2_independent_rejection` selection to both Stage
  3.9B overlap and budget-extension configs. The default DMS seed derivation
  remains unchanged. Run metadata now records contract ID, namespace, suffix,
  and the actual initial sampling seed per material/topology/seed.
- Updated the parity verifier to keep exact numerical grid count/array/ID
  checks while validating normalized provenance hashes against the referenced
  source grid and normalized run copy. Added the no-optimizer read-only builder
  `scripts/build_stage3_9b_source_compatibility.py`, which writes its review
  bundle under `artifacts/review_bundles/stage3_9b_source_compatibility/`.
- Validation: 20 focused DMS/parity tests passed; the short optimizer unit test
  was intentionally excluded because this work unit forbids optimizer
  execution. `py_compile` passed for changed/new Python files and
  `git diff --check` exited 0 (Git emitted only existing LF-to-CRLF worktree
  warnings). The compatibility bundle reports PASS for comparator ordering,
  evaluator payload/ranking, design decode/canonicalization, optimizer config,
  and checkpoint schedule. Both historical initial populations replayed
  exactly 180/180 with sampling accounting matching (seed 20260917: 182 draws,
  3 geometry rejections; seed 20260918: 185 draws, 6 geometry rejections).
- The canonical run's recorded Git head still lacks the exact Stage 3.8C
  runtime source path. The retained pre-prune source and persisted behavior
  corroborate the contract but are not a cryptographically pinned runtime
  source blob; the evidence bundle records this caveat. No optimizer or RF/COM
  evaluation was run, no new 8,000-evaluation overlap run was launched, and
  16,000 evaluations remain unauthorized. A final compatibility hardening
  keeps the removed/present historical-config branches explicit: legacy
  Stage 3.8C config resolution does not require the new Stage 3.9 selector;
  the overlap config selector and persisted actual initializer seeds remain
  independently gated. C2C requested that persisted canonical snapshots stay
  authoritative regardless of whether a legacy config file is present, and
  that optimizer controls/source identity be evidenced explicitly. The final
  bundle tests historical config absent/present without routing it through the
  modern schema. It compares canonical and current active/hard bounds and
  integer indices, effective initial/minimum populations (180/4), budget and
  horizon (8,000), memory update batch (180), and history size (6). `lshade.py`
  matches the canonical recorded head; `selection.py` differs, with its
  persisted comparator/ranking trace replay passing. Validation passed: 21
  focused tests, one short optimizer test deselected, `py_compile`, bundle
  builder, and `git diff --check`. A pytest cache permission warning was
  emitted; test execution succeeded. No optimizer, COM/RF evaluation, or
  production run was performed. The final bundle is
  `artifacts/review_bundles/stage3_9b_source_compatibility_gateb_final/`,
  including `validation_results.json`. The canonical runtime-source caveat
  remains. Submitted for final C2C Gate B acceptance; no Gate C preflight or
  launch is authorized by this work unit.

### Gate B acceptance and Gate C retry2 launch checkpoint

- C2C accepted Gate B in iteration 12 after independently reviewing the
  corrected legacy-config branch, optimizer-control/source comparisons, both
  Stage 3.9 configs, regression, and final compatibility bundle. The retained
  canonical-runtime-source caveat remains explicit.
- The fresh preflight confirmed workspace identity `saw-com-optimizer` /
  `workspace:/` (`workspaceId` `ee7cba15db95`), the Gate B summary PASS, and
  every current source/config SHA-256 in
  `stage3_9b_source_compatibility_gateb_final/source_hashes.json`. The 8k
  overlap config resolved to MLIT/T1_SYMMETRIC_5IDT, 50 ohm source/load,
  cold-start, seeds 20260917/20260918, budget and schedule horizon 8000,
  checkpoints 2000/4000/6000/8000, and the historical seed contract. Derived
  initializer seeds were 3938065196 and 1982837181. The retry2 root and nested
  optimizer directory were absent before launch; the earlier run roots were
  terminal (`CALLBACK_FAILED` and `COMPLETED`) and no `python.exe` or
  `pythonw.exe` process was present.
- Under the Gate C plan and the standing no-session-resume instruction, launched
  only the fresh 8k x 2 retry with `--no-callback`; no session ID/file was
  supplied. Run ID: `20260927_043544_5ba048`, root:
  `runs/stage3_9b_mlit_t1_50ohm_overlap_parity_20260927_retry2/`.
- Immediate post-launch verification passed: schema-v2 manifest points to the
  exact overlap config and nested `optimizer/` directory; session ID/source are
  null; callback, review-after-completion, and callback preflight are disabled
  or null; session checkpoint has the same run ID, `session_id: null`, and
  `resume_count: 0`; durable state entered `RUNNING`; generated run-source
  metadata records the approved historical contract and both exact seeds.
  This is a launch checkpoint only. The detached worker is not being polled or
  awaited, and no result/parity claim is made. The 16k run remains unauthorized
  pending completed retry2 parity PASS and independent C2C acceptance.

### Gate D retry2 completion and parity review

- On explicit user request to check status and resume the work if complete,
  durable `status.json` showed `COMPLETED`, `exit_code: 0`, and
  `optimizer_state: COMPLETED` for run `20260927_043544_5ba048`. Manifest still
  records callbacks disabled, no session ID, and resume count 0. No optimizer
  output log was polled.
- Before verification, workspace identity remained
  `saw-com-optimizer` / `workspace:/`; every source/config SHA-256 listed in
  Gate B's `source_hashes.json` still matched.
- Ran only the persisted-result parity verifier (no optimizer or COM/RF
  evaluation):
  `scripts/verify_stage3_9b_overlap_parity.py --overlap-run-dir runs/stage3_9b_mlit_t1_50ohm_overlap_parity_20260927_retry2/optimizer --overlap-config configs/studies/stage3_9b_mlit_t1_50ohm_overlap_parity.yaml --output-dir artifacts/review_bundles/stage3_9b_overlap_parity_retry2_review`.
- Result: **PASS**, eight of eight cells, zero mismatches. All gates passed:
  canonical and overlap checkpoint lattices, resolved protocol inputs, run
  metadata snapshots, initializer evidence, exact checkpoint comparisons,
  complete 8k optimizer state/cache, and common-grid finalists. Summary and
  comparison table are preserved in
  `artifacts/review_bundles/stage3_9b_overlap_parity_retry2_review/`.
- Submitted for independent C2C Gate D acceptance. The 16k extension remains
  unauthorized until C2C accepts this full parity result and issues a separate
  authorization/plan.

### Gate D acceptance and Gate E preflight/verifier preparation

- C2C accepted Gate D in iteration 14. It verified the completed retry2 run,
  exit code 0, callbacks disabled, resume count 0, all eight seed/checkpoint
  comparisons PASS with zero mismatches, and every parity gate PASS. C2C issued
  a separate conditional Gate E plan for one fresh asynchronous 16k×2 run.
- Added a config-only preflight and read-only persisted-result verifier for the
  16k extension. The verifier compares each 2k/4k/6k/8k extension checkpoint
  against the accepted 8k control, allowing only the declared total-run hard
  and terminal budget fields to differ. It checks the exact 16k checkpoint
  lattice, unique-evaluation/physics accounting, the unchanged 8k population
  schedule, seed/initializer provenance, no-session/no-resume manifest and
  status, final optimizer cache/state, common-grid finalists, and reports
  objective/violation changes separately from feasibility for each seed.
  Results are explicitly descriptive for two seeds; no success-rate inference
  is made.
- Config-only preflight passed at
  artifacts/review_bundles/stage3_9b_budget_extension_preflight_20260927_final2/.
  All 10 Gate-B source/config hashes matched; Gate-D parity remained PASS;
  the budget-extension root was absent; the config resolved to 16,000
  evaluations per seed at 2k through 16k checkpoints with the 8,000 schedule
  horizon and the approved seed contract/seeds. Only budget and checkpoint
  lattice differ from the accepted overlap protocol.
- Validation passed: py_compile; focused Stage 3.9B tests (15 passed);
  git diff --check (only existing LF-to-CRLF warnings). Pytest emitted an
  access-denied .pytest_cache warning but completed successfully. A
  post-validation process check found no python.exe or pythonw.exe worker.
- No optimizer, COM/RF evaluation, or production run was launched. The
  conditional 16k×2 launch is held for independent C2C review of the new
  verifier and completed preflight, as required by review governance.

### Gate E bounded verifier/preflight corrections

- C2C iteration 15 did not accept the initial Gate E bundle. It requested two
  bounded corrections before launch: explicitly resolve and record the actual
  16k backend limits (rather than relying on the 8k prefix protocol projection),
  and compare the exact ordered first 8,000 cache entries in the final 16k
  optimizer state against the accepted 8k control cache.
- Added the actual 16k backend gate. It requires total/hard budget 16,000,
  schedule horizon 8,000, initial population 180, and hard bounds identical
  to the accepted search space. The prefix-specific 8k backend projection is
  retained separately and labeled.
- Added read-only cache-prefix verification for both seeds. It requires an
  8,000-entry control cache, compares ordered keys exactly, compares cached
  evaluation payloads with the existing Gate-D exact/tolerance policy, and
  compares cache frequency-version prefixes when both are represented.
  Entries beyond the first 8,000 do not affect the prefix gate.
- Regenerated the config-only preflight bundle at
  artifacts/review_bundles/stage3_9b_budget_extension_preflight_20260927_final3/.
  It passes: Gate B hashes 10/10; Gate D 8/8 with zero mismatches; fresh
  extension root absent; effective backend 16,000/16,000/8,000/180; approved
  hard bounds and seed contract retained.
- Focused validation passed: py_compile; 18 Stage 3.9B tests; git diff --check
  (existing LF-to-CRLF warnings only). Tests cover hard-budget/horizon
  mutations, ordered cache-prefix equality, changed key/metric rejection, and
  post-8k cache tail exclusion. Pytest reports an access-denied .pytest_cache
  warning but all tests passed. No Python worker was active after validation.
- No optimizer, COM/RF evaluation, or production run was launched. Submitted
  the corrected implementation and preflight for another independent C2C
  review; the conditional 16k launch remains unreleased until acceptance.

### Gate E acceptance and 16k×2 launch checkpoint

- C2C accepted the two bounded corrections in iteration 16, independently
  verifying the actual 16k backend configuration and the new cache-prefix
  gate. It released exactly one asynchronous 16k×2 launch under the existing
  no-session-resume / no-callback controls.
- Immediately before launch, the fresh extension root was absent and
  Get-Process reported no python.exe or pythonw.exe workers. The final3
  config-only preflight was PASS and C2C confirmed workspace identity
  saw-com-optimizer / workspace:/ at b3f7d37.
- Launched with the project virtual environment and only the approved 16k
  budget-extension config:
  .venv/Scripts/python.exe -m sawopt.orchestration.cli launch --config
  configs/studies/stage3_9b_mlit_t1_50ohm_budget_extension.yaml --run-dir
  runs/stage3_9b_mlit_t1_50ohm_budget_extension_20260927 --experiment-name
  stage3_9b_budget_extension --no-callback
- Run ID 20260927_053504_a62960; orchestration worker PID 3540. The worker
  detached asynchronously. Immediate schema-v2 manifest checks passed: fresh
  control root, nested optimizer directory, exact config, study command
  targeting the nested directory, null Codex session ID/source, callbacks and
  review-after-completion disabled, and callback preflight null.
- Durable state entered RUNNING with optimizer_state RUNNING and no exit code.
  Matching session checkpoint has null session ID and resume_count 0.
  run-source metadata records 16,000 evaluations; checkpoints 2k through
  16k; MLIT/T1_SYMMETRIC_5IDT; 50/50 ohm; cold start; no warm/parent/neighbor
  transfer; historical seed contract stage3_8c_r1_2_independent_rejection,
  namespace stage3_8c_r1_geometry_first_v1, suffix
  r1_2_independent_rejection, and initializer seeds 3938065196 /
  1982837181.
- The CLI launch response reported PID 3540, while durable status records
  worker PID 29772 and optimizer PID 35800. C2C independently confirmed the
  discrepancy is benign; durable status.json PIDs are authoritative for later
  review.
- C2C accepted the launch checkpoint in iteration 17. No optimizer output was
  read or polled, and completion is not claimed. Leave the detached run alone
  until terminal status, then use only the accepted persisted-result verifier.
  No additional budget or production run is authorized.

### Gate E terminal status and persisted-result verification

- Durable status for run 20260927_053504_a62960 reached COMPLETED with exit
  code 0, optimizer_state COMPLETED, resume_count 0, and no error. The run
  started at 2026/09/27 14:35:05 and finished at 2026/09/27 15:05:12.
- Ran only the C2C-accepted read-only persisted-result verifier:
  `.venv/Scripts/python.exe scripts/verify_stage3_9b_budget_extension.py`.
  It returned FAIL: 8 prefix comparisons, 55 mismatches. Main findings include
  persisted terminal budgets of 8,000 where the approved 16,000 was expected,
  missing common-grid fields in prefix records, B8000 counter differences,
  and run-source config provenance differing from the approved 16k config.
- The verifier preserved its result in
  `artifacts/review_bundles/stage3_9b_budget_extension_review/`.
  No repair, optimizer rerun, or new production run was started. Submit this
  Gate E result to C2C for independent disposition before resuming further work.

### Gate E verifier lifecycle correction and corrected result review

- C2C iteration 18 classified all 55 original mismatches as verifier/lifecycle
  false positives, not a substantive 0–8k search-trajectory divergence. It
  verified the ordered 8,000-entry cache prefixes for both seeds, identical
  B8000 search-frequency work and design/objective fields, 16,000 unique final
  evaluations per seed, and matching normalized retained input-config content.
- C2C authorized only a bounded verifier/test correction and re-verification
  of the existing persisted run. No optimizer, COM/RF evaluation, or new
  production run was authorized or started.
- Updated the verifier to treat `terminal_budget` and
  `population_schedule_terminal_budget` as the required 8,000 schedule
  horizon, while `hard_max_budget` remains the 16,000 extension limit. Prefix
  parity now retains exact search counters and reports, but excludes,
  finalization-only validation counters. Prefix B2k–B8k no longer requires
  post-run common-grid fields; the independent final 16k common-grid gate stays
  mandatory. Provenance now checks normalized content hashes of the retained
  `optimizer/input_config.yaml` against the approved config, and treats the
  run-source path field as optional for the current schema.
- Added focused regression tests. The targeted Stage 3.9B module passes
  12 tests; py_compile passes; `git diff --check` passes (Git reports only
  existing LF/CRLF normalization warnings).
- Re-ran only the read-only verifier against the completed run, writing a new
  bundle to
  `artifacts/review_bundles/stage3_9b_budget_extension_review_corrected/`.
  Result PASS: all 12 gates pass, all eight seed×checkpoint prefix cells have
  zero mismatches, and no errors remain. The original FAIL bundle is retained
  unchanged as audit history.
- The 16k trajectories improved objective and maximum violation for both
  specified seeds, but the final common-grid selections remain infeasible.
  This is descriptive evidence only; no two-seed success-rate inference is
  made.
- C2C iteration 19 independently accepted the corrected persisted-result
  bundle: all 12 verifier gates PASS, all eight 0–8k prefix cells have zero
  mismatches, ordered cache prefixes and final common-grid checks pass, and
  normalized retained-config provenance matches. C2C confirms Gate B, Gate D,
  and Gate E integrity PASS. Feasibility remains NOT ACHIEVED for both seeds;
  no further production run, budget increase, schedule/optimizer change,
  asymmetric-impedance exploration, or Stage 4 promotion is authorized here.

### Stage 3.9 closeout interpretation

- C2C closeout PLAN `c2c_stage39_close`, iteration 1, found that the Stage 3.9
  exit gate had two reasonable interpretations and required a bounded Sol
  judgment before formal closure. It recommended a no-run closeout if Sol
  accepted the narrow reference-path interpretation.
- Escalation packet:
  `reports/escalation_packets/stage3_9_close_sol_judgment_2026-09-27.md`.
- Sol judgment: close under exit branch (b) for the selected MLIT/T1 50/50 Ω
  DMS reference path. The two-seed 8k-to-16k accepted evidence, near-identical
  late plateau, common-grid infeasibility, and absence of unresolved bound
  pressure are sufficient for this scoped engineering closeout. Do not extend
  T1 again. T2 may remain unresolved and unpromoted; it does not block this
  scoped closure. Do not claim formal convergence, global impossibility,
  material superiority, or infeasibility of every DMS variant. Sol did not
  authorize a production run.
- Integrated closeout synthesis and documentation were prepared in
  `artifacts/review_bundles/stage3_9_closeout_20260927/` and the Stage 3.9
  history, baseline, and roadmap.
- C2C integrated review iteration 2 verified the scientific record and
  accepted the closeout scope, numbers, normalized constraints, Gate D/E
  references, T2 caveat, and Sol judgment. It requested one blocking
  documentation correction: update the roadmap's section 4 baseline from the
  post-Stage-3.8C state to the post-Stage-3.9 state, while retaining the
  impedance-sweep and model-qualification gates. Updated only that roadmap
  section. No experiment or source implementation changed.
- C2C integrated review iteration 3 issued final ACCEPT. It confirmed the
  post-Stage-3.9 roadmap baseline, scoped branch-(b) closure, empirical
  late-plateau wording (not formal convergence), unresolved/unpromoted T2,
  and the remaining 2-D impedance-sweep/model-qualification gates. Stage 3.9
  is CLOSED; no additional optimizer experiment is required. Stage 4 may
  proceed under its own C2C PLAN and ordinary pre-experiment gates.

### PR #13 architecture-boundary CI correction

- GitHub CI for PR #13 reported 206 passing tests and one failure in
  `test_live_study_adapters_are_role_named`: the two Stage 3.9B saved-run
  auditors were placed directly in `sawopt.studies`, alongside live adapters.
- Bounded Sol judgment: place these read-only auditors in
  `sawopt.studies.audits`; preserve the architecture test and audit semantics,
  and update imports, source paths, and architecture documentation. No further
  Sol review is needed unless the correction expands into audit behavior,
  launch behavior, science, or provenance contracts.
- C2C PLAN `c2c_pr13_architecture_ci`, iteration 1, accepted that scope and
  requires focused plus full pytest validation, syntax/import checks,
  `git diff --check`, and read-only reruns of the accepted Gate D and Gate E
  verifiers into fresh review bundles before merge. Historical bundles,
  persisted run data, manifests, and fingerprints must remain unchanged.
- The bounded relocation is implemented. The architecture test still rejects
  stage-specific live adapters at the `studies/` root, and now also fails if
  an audit imports the optimizer, optimization, or orchestration execution
  layers. CLI wrappers, focused tests, source-hash input path, and architecture
  documentation point to `studies/audits/`.
- Validation: 27 focused tests pass after the final test edit; full pytest
  reports 208 passed; moved-module and CLI-wrapper `py_compile` passes;
  `git diff --check` passes with only Git's LF/CRLF notices. The relocated
  Gate-D verifier reports PASS for 8/8 comparisons with zero mismatches; the
  relocated Gate-E verifier reports PASS for all 8 prefix checkpoint
  comparisons with zero errors. Fresh outputs are under
  `artifacts/review_bundles/stage3_9b_overlap_parity_audit_relocation_review_20260927/`
  and
  `artifacts/review_bundles/stage3_9b_budget_extension_audit_relocation_review_20260927/`.
  The full-suite pytest process also emitted a non-fatal cache warning because
  `.pytest_cache` is not writable in this environment; the run exited 0. No
  optimizer/COM-RF or production run was started, and no persisted run,
  accepted bundle, manifest, or historical fingerprint was rewritten.
- Independent C2C implementation acceptance is pending before commit/push;
  GitHub CI must then pass before merging PR #13.

### Stage 4B matched-topology comparison decisions

- Bounded high-risk judgment was requested from the existing Sol review agent
  before production implementation. The review considered fixed-horizon L-SHADE
  fairness, dimension-scaled cold populations, immutable launch authorization,
  and the P_D/D_P symmetry rule. Recommendation: retain one 24k terminal
  schedule per cell, 18 initial members per design dimension, independent
  per-cell streams, and bind resume/worker execution to the exact immutable
  authorization manifest, source SHA, config, fingerprint, and output path.
- A second bounded judgment found that the initial decision classifier needed
  explicit paired metrics and fallback criteria. The revised descriptive rule
  compares each matched seed lexicographically by maximum normalized violation,
  sum normalized violation, and worst passband IL; exact ties do not count as
  wins. A provisional primary and fallback each require at least four of five
  strict paired wins against every relevant competitor. Otherwise, include all
  topologies within the maximum observed five-seed IQR on the first
  discriminating median metric, using NumPy's linear/type-7 quartiles; if that
  leaves fewer than two topologies, report inconclusive. IQR is seed spread,
  not a confidence interval. This rule handles all-feasible cases by proceeding
  to sum violation and IL, and does not turn five seeds into a global-optimum
  claim. Symmetry warnings remain review flags, not evidence of physical
  superiority or failure.
- The Stage 4B report must remain `STAGE4B_EXECUTED_REVIEW_PENDING`; none of
  these judgments accept the Stage 4B result or authorize automatic follow-up
  runs.

### Post-run queue and evidence-publication contract

- Before changing orchestration interfaces/state semantics for PR #17, requested
  bounded Sol judgment on detached-worker ownership, exact-thread delivery,
  one-shot claims, receiver trust, historical manifest compatibility, and the
  boundary between evidence publication and scientific review. No scientific
  or optimizer behavior was in scope.
- Sol recommended: persist one claim before queue I/O; build/validate the
  bounded payload first; treat uncertain claimed delivery as consumed and
  ambiguous; accept only runtime `CODEX_THREAD_ID` for receiver proof; retain
  old schema readers without silent upgrades; and make `REVIEW_WAITING` depend
  on committed/pushed evidence, never on queue acceptance or continuation
  completion. Recovery must not rerun completed optimization.
- Implemented this separation in schema-v4 queue/publication paths while
  retaining the legacy callback only for historical manifests. E2E and test
  qualification remain pending; no queue send or experiment has been launched.
- Packet: `reports/escalation_packets/postrun_workflow_queue_contract_20261004.md`.

### Persistent run storage and worktree removal safety

- Bounded Sol judgment was requested before changing the orchestration launch
  interface. Recommendation: require explicit external storage for launches
  declared user-authorized or ranking-eligible; remove the Stage 4B new-launch
  fixed output path under repository `runs/`; preserve historical manifests;
  fail closed when Git worktree discovery or Windows path identity is uncertain;
  reject reparse points and compare paths by components, case-insensitively on
  Windows; and test the removal utility only with temporary repositories.
- Sol also identified that Stage 4B one-shot authorization claims are globally
  unique. A registry selected per run root could permit reuse. The existing
  repository-wide claim registry is therefore retained for this task; it is
  authorization metadata, while raw run outputs use external persistent
  storage.
- Exporter review confirmed that external raw input is already supported and
  the default schema-v4 output remains canonical under the source repository;
  the implementation adds regression coverage without changing export
  semantics.
- A follow-up review found a launch/removal race and a missing source-worktree
  dependency record. Recommendation: store active production-run markers under
  Git's shared common directory; register before run reservation, Stage 4B
  claim, or worker spawn; retain markers through optimizer termination until
  successful review publication; fail closed on absent/corrupt registry state;
  and serialize registration with the remover's final audit and Git removal
  under one shared lock. Publication retries should idempotently clear a marker
  left after a successful state transition. The implementation adds this
  registry and requires explicit one-time reconciliation before initialization.
- No optimizer, COM/RF, study conditions, historical manifests, or production
  results are changed. Stage 4C and queue requalification remain out of scope.

### STAGE4C_EXTERNAL_REVIEW_ROUND1_CHANGES_REQUESTED — 2026-10-05

- External review identified three substantive issues before production:
  resume regenerated `created_at_utc` before immutable comparison; any
  historical checkpoint bound hit permanently blocked maturity; and the
  multi-component equivalence margins carried unverified provenance.
- The requested correction uses the existing 0.02 significant-improvement
  scale solely as a model-level max-normalized-violation interpretation
  threshold. It is not a manufacturing or measurement equivalence tolerance.
- The same review round required moving Stage 4C authorization claims out of
  repository-local `runs/` and making the non-scientific Stage 4C shakedown a
  prerequisite to merge. No production launch or authorization is part of
  this fix round.
- The fixes preserve `created_at_utc` across resume, separate historical bound
  hits from terminal unresolved boundary states, apply the reviewed 0.02
  max-normalized-violation model-level rule, and store Stage 4C claims under
  Git common-directory state. The unverified Stage 4C Sol-attribution packet
  was removed.
- Focused tests: 70 passed. Full suite: 338 passed and 20 subtests passed.
  The external two-cell 512-evaluation shakedown and a later resume invocation
  both passed at
  `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer-runs\qualification\stage4c\pr22_round1_20261005`.
- Result: `STAGE4C_PROTOCOL_FROZEN_READY_FOR_EXTERNAL_REVIEW_ROUND2`. No
  Stage 4C production was authorized or launched; no queue continuation was
  sent.

### Stage 4C external review Round 2 — one-shot authorization lifecycle — 2026-10-05

- Classification entering the fix: `STAGE4C_EXTERNAL_REVIEW_ROUND2_CHANGES_REQUESTED`.
- Finding: the Stage 4C authorization claim ID was run-ID-scoped and the optimizer child did not independently verify the durable claim. Claim creation also followed active-run registration, which could leave stale state when duplicate claims become fail-closed.
- Fix: claim identity is now authorization-scope + computation-fingerprint + source-SHA scoped; run ID remains in the claim payload. Child verification requires the exact Git-common claim path and matching payload. Stage 4C consumes the claim before active-run registration/run-directory reservation.
- Scientific protocol, optimizer, 96k budget, seeds, grids, maturity/materiality rules, and Stage 4B behavior are unchanged. Production remains unauthorized and was not launched by this fix.

### Stage 4C MemoryError — compact L-SHADE checkpoint state — 2026-10-06

- Escalation was required before changing optimizer checkpoint architecture and
  orchestration failure semantics. Sol approved a canonical-key/grid-version
  history index with bounded results, exact stable-order cumulative top-16
  finalist retention, direct counter persistence, pre-parse rejection of v3
  checkpoints, and durable traceback/exit diagnostics.
- Preserve the frozen study conditions and all optimizer trajectory/accounting
  invariants. The failed production run remains untouched; no production launch
  or resume is authorized by this repair.
- The existing registry policy requires retaining the active-run marker until
  failure evidence is published and `REVIEW_WAITING` is durable. The fix follows
  that policy and will not clear a marker merely because optimization failed.
- Packet: `reports/escalation_packets/stage4c_memoryerror_compact_state_20261006.md`.


## 2026-10-07 — uv environment removal safety

A bounded review considered how to reconcile disposable root `.venv` cleanup
with symlink and reparse-point protection. The review advised retaining strict
checks while allowing a verified uv environment. After the user clarified the
required behavior, the implementation treats root `.venv` as a disposable
subtree, inspects internal links without following them, uses fd-safe removal,
and retains protected-data and mount-point checks. The change does not affect
scientific code.
