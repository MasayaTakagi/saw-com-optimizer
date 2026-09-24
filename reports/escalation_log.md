# Luna → Sol Escalation Log

Pilot: Stage 1
Status: stopped at mandatory review gate

Each escalation must be recorded as a self-contained packet followed by the
decision, Luna's action, verification, and outcome. Requested model and
reasoning effort must be kept separate from independently observed backend
identity and behavior.

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
