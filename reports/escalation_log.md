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
