# Stage 5A-2 Q0-R1 — frozen minimum-fair comparison protocol

**Status after independent re-review:** `REQUEST_Q0_REVISIONS`; Q0 remains open and Q1 is blocked. The review below did not authorize implementation or execution.
**Revision:** Q0-R1, 2026-10-21
**Purpose:** resolve the first Sol review and PR #47 findings before Q1. The first revision was independently re-reviewed once; Sol found additional unresolved protocol defects recorded in §14. This is the final Sol review for this work unit; no automatic second re-review will be started.
**Not authorized:** Q1 implementation, tests, synthetic evaluation, COM/network calculations, optimization, run launch, or Stage 4C data changes.
**Source baseline:** current publication base is `origin/main` `daa646ba7c9fab0d5d1b6c3e3054213fdb9ab10e`. The read-only source audit began at local `c2f002c00da0339c4f43fe1ac9e50d7793cdb233`; its tree is identical to the current base despite a different commit history. PR #47 is merged. This revision preserves its prior packet and findings.
**Authority:** this document freezes a proposed Q0 protocol only. Sol re-review, independent GitHub review, and user acceptance are separate gates; none authorizes an experiment.

## 1. Decision and estimand

The future Stage 5A-2 comparison is an **exploratory matched-budget comparison of two complete algorithm packages**, not a controlled experiment isolating mutation alone:

1. the audited Stage 4C `LShadeBackend` package, cold-started with the same ordered initial population and a 4,096-FE terminal population-schedule horizon; and
2. a new, purpose-built, synchronous canonical-phenotype `DE/rand/1/bin` package with fixed population 234, `F=0.5`, `CR=0.9`, reflection repair, and no adaptation, archive, shrinking, polishing, or fallback.

The frozen model, COM inputs, topology definitions, specification, geometry constraints, bounds, port conditions, and frequency grids remain exactly those in the Stage 4C frozen contract. No method may change them. The experimental question is short-budget quality and efficiency on this one fixed problem; it is not feasibility proof, convergence, global optimality, or general algorithm superiority.

| Item | Frozen Q0-R1 decision |
|---|---|
| Topologies | `P_D`, `D_P`; independent searches, 13 variables each |
| Root seeds | `20261012`, `20261013`, `20261014`; matched by topology and seed across methods; fresh relative to Stage 4B/4C seeds |
| Initial population | 234 geometry-valid unique canonical designs per topology/root seed; same physical vector order for both methods; methods evaluate separately |
| Search budget | 4,096 unique canonical search evaluations per method/topology/seed, including the 234 initial evaluations |
| Post-initialization allowance | 3,862 unique FEs |
| DE full-generation arithmetic | 16 complete 234-target generations plus a final 118-target partial generation if no duplicates, retry cutoff, or interruption occurs |
| Cell matrix | 2 methods × 2 topologies × 3 seeds = 12; maximum 49,152 unique search FEs |
| Search grid | Existing Stage 4C 1,001-point grid; SHA-256 `212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0` |
| Dense validation | Existing common 9,113-point grid; ID `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`; SHA-256 `54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554` |
| Terminal validation set | Stable best 16 distinct canonical designs from the entire search history; for an incomplete but rankable cell, validate `min(16, unique search designs)` and label the run incomplete |
| Selection | Existing `GeometryFirstComparator.rank_key` tuple, unchanged; never scalarize for selection |
| Claim | Report best-found under this finite budget, feasibility, violations, uncertainty and convergence limits; never claim a proven optimum |

Seeds are fixed design inputs, not inferred from fitness. If any future preflight fails, do not replace a root seed, sampler stream, or initial population based on outcomes. No seed substitution or automatic budget extension is allowed.

## 2. Read-only L-SHADE audit and fully resolved reference package

The reference is the Stage 4C package from `src/sawopt/optimizers/lshade.py::LShadeBackend`, wired by `src/sawopt/studies/hybrid_stage4b.py::_run_cell` and `src/sawopt/studies/hybrid_stage4c.py::run_stage4c_production`, with `configs/studies/hybrid_stage4c_confirmatory.yaml`. This is an algorithm-package comparison, and the existing L-SHADE path must not be edited to make it look like DE.

### 2.1 Settings: source defaults versus Stage 4C-resolved pilot values

| Setting | Source default / behavior | Stage 4C-resolved value for Q0-R1 | Evidence |
|---|---|---|---|
| Dimension | Given by design space | 13 (`P_D`, `D_P`) | `HybridDesignSpace`, `hybrid_stage4c.expected_matrix` |
| Initial population | `initial_population` else `initial_population_per_dimension × D`; `min_population` is lower floor | `18 × 13 = 234` | `hybrid_stage4c.py::expected_matrix`; Stage 4C YAML |
| Minimum population | `min_population`, default 4; values below 4 rejected | 4 | `lshade.py::__init__`; Stage 4B runner explicitly sets 4 |
| Total / hard unique budget | `total_budget`, `hard_max_budget` | 4,096 / 4,096 in Q0-R1; Stage 4C historical value 96,000 | Stage 4B runner; Q0-R1 cold horizon rule |
| Population schedule horizon | `population_schedule_terminal_budget`, defaults to hard maximum | 4,096, immutable from cold start; never resume a 96,000-horizon state | `population_size_for_budget`; runner config |
| Schedule | `round(N0 - clamp(FE/H,0,1) × (N0-Nmin))`; Python built-in `round` (ties-to-even); shrink-only, after offspring processing | `N0=234`, `Nmin=4`, `H=4096` | `population_size_for_budget`, `_resize_population`, `_generation` |
| SHADE history size | `history_size`, default 6 | 6 | `lshade.py::__init__`; no Stage 4C override |
| Initial memories | `M_F=M_CR=0.5`; ring index 0 | 6 entries each, all 0.5 | `_reset_state` |
| p-best fraction | `pbest_max_fraction`, alias `pbest_fraction`, default 0.20 | 0.20; `pbest_count=max(2, ceil(0.20*N))` | `__init__`, `_generation` |
| Archive rate attribute | `archive_rate`, default 1.0 | attribute 1.0; implementation's effective capacity is current `N`, because insertion/trim passes `len(population)` and does not consult the rate field | `__init__`, `_archive_insert`, `_trim_archive` |
| Success-memory batch | `memory_update_batch_size`, default 0 means set to initial N at initialization | 234 offspring-attempt steps, not 234 FEs | `initialize`, `_maybe_flush_success_memory` |
| Duplicate mutation retries | `max_duplicate_retries`, default 5 | 5 retries after the first normal attempt: 6 normal mutation attempts total | `__init__`, `_generation` |
| Existing unseen fallback | The source loop has a nominal allowance of 64 fallback iterations, but `_unseen_proposal() is None` immediately breaks that loop; a returned unseen point is evaluated and ends the offspring step. Thus the current mixed-space path makes at most one fallback call per offspring, drawing at most 256 normalized uniform vectors in that call. | Retain exactly as implemented; do not remove, relabel, or add a different fallback. This factual correction is post-review documentation and has not been re-reviewed by Sol. | `_generation`, `_unseen_proposal`; §14 post-review note |
| Duplicate-streak exhaustion | default `None` | None in the algorithm. The external watchdog in §2.5 is outside the optimizer and does not change proposals before it terminates | `__init__`, `_check_search_space_exhausted` |
| Cache/history | Stage 4C uses compact history cache and 16 finalists | compact history index on; 16 retained full-result finalists; complete event journal/history required by Q0-R1 remains outside the behavior-changing core | Stage 4C calls `compact_history_cache=True`; `state_dict`, `_update_compact_history` |
| RNG | Source calls `np.random.default_rng(seed)` | Under pinned NumPy 2.5.3, explicit PCG64-equivalent stream using a derived per-cell L-SHADE seed; this preserves the backend algorithm but deliberately establishes a new independent Stage 5A-2 seed namespace | `lshade.py::__init__`; `uv.lock` |

The Stage 4C configuration has no explicit `lshade` override. Its runner resolves `min_population=4`, `compact_history_cache=true`, `historical_finalist_count=16`, the dimension-scaled population, budget and horizon. The seed derivation and cold-start horizon in this new comparison are independent of Stage 4C's historical production trajectory. No old checkpoint is eligible for continuation.

### 2.2 Exact existing L-SHADE proposal and update sequence

For one offspring step, preserve the source sequence and numerical operations:

1. Set `target_index = generations % current_population_size`; retain a reference to that target. An unsuccessful offspring step still increments `generations` when its existing bounded retry body finishes.
2. Draw `memory_index = rng.integers(0, history_size)` once per offspring step.
3. Draw `F = 0.1 × standard_cauchy() + M_F[memory_index]`, at most 100 draws seeking finite `F>0`; if none qualifies, use that memory value; clip to `[machine_epsilon,1]`.
4. Draw `CR = normal(M_CR[memory_index], 0.1)` and clip to `[0,1]`. The selected F/CR pair is reused across all normal duplicate retries for this offspring; a duplicate does not resample either value.
5. Compute `pbest_count=max(2,ceil(pbest_fraction×N))`. Rank current population by `rank_key` using stable list order for key ties. Draw p-best from that prefix excluding target if possible, then draw `r1` from population excluding target and p-best, then draw `r2` from the population excluding target/r1 plus the archive. Existing draw calls are `choice`, `choice`, then `integers` respectively.
6. Mutate `v = x_target + F(x_pbest-x_target) + F(x_r1-x_r2)`. `x` is normalized **latent genotype**, not canonical phenotype. Repair each mutant coordinate before crossover with parent-midpoint rule: below 0 becomes `0.5*x_parent`; above 1 becomes `0.5*(1+x_parent)`; a nonfinite value falls back to the parent coordinate; then clip to `[0,1]`.
7. Draw forced coordinate with `integers(0,D)`, then draw `random(D)` in coordinate order and set the binomial mask where draw `< CR`; force the selected coordinate true. Form trial by mutant where mask is true, target genotype otherwise.
8. Decode and canonicalize only for evaluation/cache. The retained L-SHADE population member stores trial latent genotype separately from canonical physical phenotype/key. Do **not** remap the retained latent genotype to the canonical phenotype; that difference from DE is part of the comparison.
9. After six normal attempts, the existing source switches to `_unseen_proposal`: for a mixed continuous/integer space it draws at most 256 normalized uniform candidates in that call. If it returns `None`, `_generation` immediately breaks; if it returns an unseen candidate, that candidate is evaluated and the offspring retry loop ends. Therefore only one fallback call is reachable in the current mixed-space source path, despite the enclosing loop's nominal 64-iteration allowance. A returned candidate goes through the same canonical cache/evaluator. Fallback proposals do not use the sampled F/CR but, if successful and better, the source associates that replacement with the F/CR pair sampled at the start of the offspring step for memory adaptation. Count actual fallback calls/draws. This source correction is post-Sol-review and has not received another review; the finding remains open pending accepted Q0 disposition.
10. On a newly evaluated design, compare its result to target immediately. Replace only when `comparator.better(trial,parent)`; equal rank retains parent. Successful better trials archive the displaced target genotype and collect `(F, CR, comparator.improvement)` for memory adaptation. No successful improvement means no replacement/memory success sample.
11. Archive entries are unique by exact genotype tuple. Effective capacity is current population size; random archive deletion uses `rng.integers` when over capacity. On shrink, keep the current best ranked N and trim archive.
12. Every 234 offspring-step attempts, flush collected successes into current memory slot: weighted Lehmer mean for F and weighted arithmetic mean for CR, then advance ring index modulo 6. If there were no successes, clear batch counters but do not advance the index. `GeometryFirstComparator.improvement` remains the existing positive weight calculation; it is not a selection score.
13. At each offspring-step end, resize using committed unique-FE count and the fixed 4,096 horizon; record search-history event. The fixed unique budget, not a checkpoint, controls shrinkage.

### 2.3 L-SHADE counters required without changing proposals

Record: normal mutation proposals, fallback invocations, fallback candidate draws (including internal draws that return `None`), duplicates by proposal source, cache hits, unique evaluation intents and commits, geometry rejects, physics dispatches/results/failures, retries, unsuccessful offspring steps, population shrink events, archive insertions/removals, and watchdog count. Counter instrumentation must not call RNG, reorder evaluation, change target selection, or add a retry. The prior Stage 4C compact-state `proposals_total` alone is insufficient to reconstruct every internal fallback draw; the new Q1 journal must record it prospectively.

### 2.4 Population schedule horizon

Construct a fresh L-SHADE backend with `total_budget=hard_max_budget=population_schedule_terminal_budget=4096`. The `round` formula always uses this horizon, irrespective of checkpoint location. No state from a 96,000 terminal-horizon trajectory may be loaded, sliced, or represented as a cold 4,096 run.

### 2.5 External finite watchdog; justified alternative to algorithm edits

Preserve all L-SHADE mutation, retry, fallback, selection, adaptation, and shrink behavior. A protocol-level watchdog runs outside its search rule and terminates the cell with `BUDGET_STALLED` after **65,536 consecutive post-initialization raw canonical proposal attempts without a newly committed unique FE**. The counter resets only after a new canonical design's terminal result transaction commits (including geometry rejection or modeled physics failure). Every fallback internal draw counts once. The watchdog checks before each next candidate draw and never draws a random number on the abort boundary. It may stop an otherwise still-running trajectory, so it can affect which cell completes and must be reported as a censoring/termination condition; it cannot change a trajectory before the boundary. It is not a convergence claim or search-space exhaustion certificate.

The 65,536 cap was chosen as a finite, identical global no-progress proposal ceiling for both arms, equal to 16 times the entire 4,096 FE budget; it tolerates substantial canonical collision/retry work while preventing indefinite looping. Under the actual L-SHADE source control flow, one fully unproductive offspring step can consume at most six normal proposals plus one fallback call with at most 256 candidate draws (262 raw proposals); an alternative 262 global limit would stop after that single maximal no-progress step and risks excessive early stalls. A materially larger cap increases unproductive proposal work and active runtime, not a direct wall-time cutoff; a smaller one increases early-stall frequency. Q1 reports exact watchdog exposure and never calls a stalled cell complete.

## 3. Controlled DE/rand/1/bin, fully specified

This is a new backend; do not use/relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend`. The following defines all observable operator and restart behavior.

### 3.1 Representation, parameters and proposal draw order

- Dimension 13, fixed N=234, normalized phenotype genotype `x∈[0,1]^13`, `F=0.5`, `CR=0.9` for every cell. No p-best, adaptation, archive, shrink, polish, injected fallback, or parameter tuning.
- Parent generation is an ordered list of canonical phenotypes. For each new canonical phenotype, map physical coordinates back to normalized coordinates and store that remapped vector as its genotype. Therefore identical canonical keys cannot have distinct effective genotypes.
- Target traversal is indices `0,1,…,233`, once each in generation order. Retry a target in place against the unchanged generation snapshot; do not advance the cursor until that target's unique trial is evaluated or the cell terminates.
- For target `i`, create `eligible = [0,…,233]` without `i`, in ascending order. Draw `perm = rng.permutation(eligible)` using NumPy's pinned `Generator(PCG64)`; ordered donors are `r1=perm[0], r2=perm[1], r3=perm[2]`. They are mutually distinct and exclude i. One permutation call is consumed per complete trial attempt, including a duplicate trial; there is no redraw loop for donor choice.
- Mutation is exactly `v = x[r1] + 0.5*(x[r2]-x[r3])`.
- Draw forced coordinate `j_rand = rng.integers(0,13)`. Then draw a vector of 13 uniforms `u = rng.random(13)` in coordinate order 0..12. Mask coordinate j is mutant iff `u[j] < .9`, with `j_rand` forced mutant after mask creation. The crossover consumes those draws even for the forced coordinate.
- Form binomial trial `z[j] = v[j]` when mask true, otherwise `x[i][j]`. Apply reflection after crossover, componentwise: `r(z)=1-abs((z mod 2)-1)`. Record pre-reflection lower/upper excursions by target/coordinate; values already in range are unchanged. No clipping or parent-midpoint repair substitutes for reflection.
- Decode physical `low + reflected*(high-low)`, apply the unchanged `HybridDesignSpace.canonicalize` (clip to active bounds; integer coordinates `floor(value+0.5)`; clip again), then remap canonical phenotype to normalized coordinates. The original reflected trial is proposal telemetry only; population state is the canonical remap.
- RNG order per trial attempt is therefore exactly: `permutation(eligible)`; `integers(0,D)`; `random(D)`; no random calls for reflection, decoding, canonicalization, comparison, tracing, checkpointing, or retries beyond the next trial's three calls above. If a duplicate retries, consume a new full proposal sequence. A per-target limit abort consumes no additional draws.

### 3.2 Synchronous survivor semantics and exact partial generation

1. At generation start, freeze the ordered parent vectors, canonical keys, evaluation records and target traversal. Every donor and target uses this immutable snapshot for the entire generation.
2. Generate/evaluate trials serially in target order. Store each unique result as pending; do not mutate the parent generation or let earlier trials influence later donors.
3. A new unique trial is evaluated and recorded immediately for cache, FE and search-history purposes. After every target has a unique terminal record, commit survivor choices in target order 0..233: replace parent i only if `GeometryFirstComparator.better(trial_i,parent_i)`; exact rank-key tie retains the parent. Then clear pending generation state and start next generation.
4. Terminal budget may be reached partway through a generation. Commit only the completed targets in the final partial generation, in target order; leave unvisited targets unchanged. In the duplicate-free path the last generation evaluates/commits targets 0..117 (118 trials) and then ends at FE 4,096. The historical top-16 and incumbent come from the full search-history records, including pending trials before commit.
5. If interrupted mid-generation, persist the frozen parent snapshot, next target cursor, ordered completed pending trials, all per-target retry counts and current retry phase, pending proposal (if any), post-draw RNG state, FE ledger and trace. Resume the pending trial/evaluation/commit before drawing another proposal. A duplicate consumes no FE and retries the same target with a new full proposal. If a per-target stall cutoff occurs, do not partially commit the interrupted generation; preserve completed trial history and mark `BUDGET_STALLED`. Search-history best-found remains valid.
6. No FE can be requested once the committed unique-FE count is 4,096. If an evaluation intent was durably issued below the budget before interruption, recovery completes that same intent and commits it once; the backend cannot issue a second new intent beyond the cap.

### 3.3 DE duplicate/stall limits and reason

- Canonical duplicate means the post-canonical key already exists in that cell's committed cache or pending cache, including equality with target/other current population members or a prior search record. It is a cache-hit/duplicate proposal, not an evaluator call or FE. Check exact versioned canonical key equality.
- On any duplicate, increment raw proposal and duplicate/cache counters; discard that trial; regenerate all donors, forced coordinate and mask against the same frozen parent generation. No partial mask reuse, random restart, sentinel score, evaluator call, or hidden alternate fallback.
- Per target per generation: **4,096 total trial proposals**, including the initial proposal; at most 4,095 duplicate retries. The first unique proposal completes the target. If all 4,096 proposals are duplicates, stop at the boundary as `BUDGET_STALLED`, leave the generation uncommitted, and do not draw a 4,097th. This cap equals the full cell's unique-FE horizon and is deliberately generous; the shared 65,536 no-progress watchdog is an additional aggregate bound. A smaller 256 cap would reduce wasted compute but increase early censoring; no empirical tuning is allowed in Q0.
- A geometry-rejected canonical key not previously evaluated is a unique new design: screen, create the `GEOMETRY_REJECTED` record, charge one FE, consume the target, and do not retry. A modeled physics failure likewise consumes one FE and completes the target. Only a duplicate/cache hit retries.
- Global no-progress watchdog: the shared 65,536 consecutive raw canonical proposals without a committed unique FE (§2.5); it applies to DE too. Duplicate retry counters persist across resume. A new unique result commit resets the streak.
- `SEARCH_SPACE_EXHAUSTED` requires a formal finite canonical-space cardinality identity and proof that every key has a terminal cached result. Repeated duplicates alone never certify exhaustion. The 13-D mixed continuous space has no such finite certificate under this protocol; it will report `BUDGET_STALLED`, never guessed exhaustion.

## 4. Common initial population and RNG streams

### 4.1 Sampler contract

Use `independent_uniform_rejection_v1` with a protocol-specific versioned stream:

1. For each topology/root-seed, independently draw 13 physical coordinates in ascending design-vector order from uniform distributions over that variable's exact active physical bounds using `Generator(PCG64(seed))` and `rng.uniform(low, high)`; apply no bias, geometry repair, warm start, known design, or fitness-based filtering.
2. Canonicalize with the existing `HybridDesignSpace.canonicalize`: bounds clip, integer `floor(x+0.5)`, bounds clip. This exact mixed-integer law means endpoint integer bins have half the probability mass of interior bins when bounds are integer; do not replace it with categorical integer sampling.
3. Compare canonical key to already accepted geometry-valid keys first. If duplicate, count `sampler_duplicate_rejections` and continue without a geometry call. Otherwise run the existing geometry-only `hybrid_geometry` screen. If invalid, count `sampler_geometry_rejections` and continue; invalid keys are not inserted in `seen`, matching Stage 4B behavior. On valid geometry, add key to `seen` and append physical canonical vector in draw order.
4. Stop once 234 accepted members exist or after exactly 10,000 total sampler draws, whichever comes first. The partition must satisfy `draws = accepted + sampler_duplicate_rejections + sampler_geometry_rejections`. Sampler rejects do not call physics/COM and do not count toward optimizer FEs.
5. Construct the complete ordered population before either optimizer evaluates any member. Both algorithms receive the same ordered physical canonical vectors (normalized only as required by optimizer interfaces). Initializer hash is computed and persisted before either arm starts. Each algorithm then evaluates all 234 independently, in member order, with an empty private cache; cache/results are never copied between arms.
6. If fewer than 234 valid unique members exist at 10,000 draws, finalize `INITIALIZATION_FAILED`; retain the accepted ordered prefix/hash and counters, run neither optimizer, evaluate no candidates, do not replace seed, and do not widen bounds. No incomplete population is passed to either backend.
7. If interruption occurs before sampler completion, persist sampler RNG state, accepted ordered prefix, seen keys, draw/rejection counters and last draw transaction. Resume the exact stream at the next draw. If interruption occurs while evaluating the complete initial population, resume the same arm-local initialization cursor/cache/FE ledger; never regenerate it or reuse other-arm evaluations.

### 4.2 Seed derivation and population serialization

- Fixed matched root seeds: `[20261012, 20261013, 20261014]`, the next three unused integers after the frozen Stage 4C seed set `[20261007,…,20261011]`; selection is procedural and not based on optimizer outcomes. Same root seed/topology pair is shared by both arms; topology is in the sampler key so the two topologies have distinct population streams.
- Seed derivation object: UTF-8 canonical JSON with sorted keys and separators `(',', ':')`, fields `{protocol:'stage5a2-q0-r1-v1', role, root_seed, material:'MLIT', topology, design_space_sha256}`. `role` is exactly one of `common_init`, `optimizer_lshade`, `optimizer_controlled_de`. Derive `seed32 = int.from_bytes(SHA256(payload).digest()[:8], 'big') % 2**32`. No Python `hash()`, timestamps, filesystem paths, optimizer state, or fitness values enter derivation.
- Each role uses its own explicit `numpy.random.Generator(numpy.random.PCG64(seed32))`. Common initialization has no optimizer name/state in its derivation; L-SHADE and DE use separate role namespaces and states. Pin Python 3.12 and the committed `uv.lock` dependency set, including NumPy 2.5.3; record exact Python/NumPy/SciPy build and bit-generator name. The Stage 4C source's `default_rng` also resolves to PCG64 in this pinned NumPy, but Q0-R1's derived seed namespace intentionally creates a new cold trajectory.
- `design_space_sha256`: SHA-256 of canonical UTF-8 JSON (`ensure_ascii=True`, sorted keys, separators `(',', ':')`) containing topology, ordered variable names, active bounds as arrays of 16-hex-digit big-endian binary64 tokens (signed zero normalized), integer indices, units, and the literal rounding rule `floor(x+0.5)`.
- Ordered population serialization: schema `stage5a2_initial_population_v1`, topology, root seed, derived initializer seed, dimension 13, member count 234, design-space hash, and `members` as 234 ordered arrays of 16-hex-digit big-endian IEEE-754 binary64 words (physical canonical values; normalize signed zero to +0). Store no floating-point decimal rounding.
- Population hash: SHA-256 over the ASCII domain tag `sawopt-stage5a2-init-population-v1\0`, followed by canonical UTF-8 JSON (`ensure_ascii=True`, sorted keys, separators `(',', ':')`) for `{topology, design_space_sha256, dimension:13, member_count:234}`, followed by one NUL byte, followed by exactly the ordered 234×13 big-endian binary64 bytes. Same population means bit-identical ordered canonical vectors and hash. No objective/evaluation result enters this hash.
- The exact lossless sampler/optimizer PCG64 state codec and pre-population resume identity remain unresolved; see §14 R3. Q1 must not invent them. Seed and initial population generation complete before either optimizer-specific RNG starts; initial sampler draws cannot consume optimizer RNG state.

## 5. Unique FE, cache and failure-state contract

### 5.1 Definitions and disjoint counters

- **Search unique FE:** the first evaluation transaction for one canonical physical design key in one optimizer/topology/root-seed/search-grid cell. It is counted once regardless of outcome: `PHYSICS_EVALUATED`, modeled `PHYSICS_FAILED`, `GEOMETRY_REJECTED`, or a returned `INVALID_RECORD`. It is not counted for duplicate proposals, initialization sampler rejection, cache hits, or a pending evaluator call without a committed result.
- Each optimizer maintains an independent cache keyed by full evaluation identity + canonical key. Search grid, topology, optimizer, root seed, source/config fingerprint, bounds/design-space, evaluator identity, comparator/canonicalizer versions and protocol must match. Dense validation is an independent phase/cache namespace and is not a search-grid cache hit.
- Split sampler counters from optimizer counters. Per arm: initial sampler attempts/rejections; accepted members; initialization evaluation intents/results; optimizer raw proposals; duplicate/cache hits; unique post-initialization FEs; geometry screening rejects; physics evaluator attempts; returned physics successes/failures; infrastructure-interrupted evaluator attempts; invalid records; fallback calls/draws; watchdog streak; validation calls/failures; checkpoint I/O.
- Required identities: `sampler_draws = sampler_accepted + sampler_duplicate_rejections + sampler_geometry_rejections`; `initial_evaluated_unique + postinit_unique = search_unique_FEs`; `postinit_raw_proposals = postinit_new_key_intents + postinit_duplicate_proposals`; after recovery completes, `search_unique_FEs = geometry_rejected_FEs + physics_evaluated_FEs + physics_failed_FEs + invalid_record_FEs`; a geometry reject has zero physics dispatches; a terminal modeled result corresponds to exactly one canonical FE key; physics dispatch attempts are counted separately from unique FEs because infrastructure recovery can retry an interrupted call.
- A cache/duplicate hit never invokes the evaluator and never increments the FE counter. `PHYSICS_FAILED` is cached as a terminal modeled result for that grid/identity and consumes one FE. `GEOMETRY_REJECTED` is cached, consumes one FE, and does not call COM. A search physics dispatch is one composite evaluator call; log COM model entry points separately (Stage 4C geometry-valid P_D/D_P calls one T1 DMS model and one resonator model each; report calls actually entered, not frequency points).
- Stop before dispatching a new evaluator intent at unique FE 4,096. No sentinel evaluation, budget overrun, duplicate charge, or validation charge to search budget.

### 5.2 Failure and cell statuses

| Status | Exact meaning / transition |
|---|---|
| `COMPLETED` | All 4,096 search FEs are durably committed; no pending evaluation/optimizer transaction remains; all terminal validation candidates are processed and the final machine records pass schema/integrity checks. Search completion and validation completion are both required. |
| `INITIALIZATION_FAILED` | The shared sampler reaches 10,000 draws before 234 valid unique members; no candidate evaluation has begun; terminal for this seed/population, no seed substitution. |
| `BUDGET_STALLED` | The DE per-target limit (4,096 proposals) or shared 65,536 no-progress watchdog is reached before 4,096 FEs; incomplete, never treated as budget-complete. A terminal best-found set may still be dense-validated. |
| `SEARCH_SPACE_EXHAUSTED` | Formal finite canonical-space cardinality is known and every possible key has a terminal evaluation/cache record. Duplicate streaks or empirical lack of novelty cannot establish this. Not expected for this mixed continuous space. |
| `INFRASTRUCTURE_INTERRUPTED` | Process, filesystem, host, timeout, or unexpected infrastructure exception prevents a transaction from completing. Preserve pending intent and durable state; resume only under exact identity. It is not a physics failure. |
| `INVALID_RECORD` | Evaluator returned a malformed/inconsistent record or invalid numeric/schema payload. If a new candidate evaluator was called, charge its unique FE once, quarantine raw payload, do not rank it, and stop fail-closed. Repairing code/identity does not retroactively complete the cell. |
| `CHECKPOINT_IDENTITY_MISMATCH` | Any required checkpoint identity field is absent or differs. Refuse to load, evaluate, or overwrite the checkpoint. Record the failed resume attempt separately; original checkpoint remains immutable/recoverable only in its matching environment. |

Search status and terminal validation status are separate fields. An interrupted dense-validation phase resumes the same candidate/cursor and ends with `INFRASTRUCTURE_INTERRUPTED` at the overall cell level until validation completes. A stalled search may complete terminal validation and retain `BUDGET_STALLED` as its honest search disposition. A validation `INVALID_RECORD` remains fail-closed.

### 5.3 Geometry, physics and infrastructure classification

- **Sampler geometry rejection:** pre-evaluation population screening; sampler counter only, not optimizer FE, physics attempt or COM call.
- **Search geometry rejection:** a new canonical key passed to optimizer evaluation then rejected by the unchanged hard geometry gate; one unique FE, typed `GEOMETRY_REJECTED` record, zero physics/COM calls; not retried as if it were a duplicate.
- **Modeled physics failure:** only a typed result from the geometry-valid COM/network/metrics calculation for this candidate. The Q1 adapter may wrap the already-established numerical failure sites without changing equations: non-finite transducer gain, the existing nonpassive-gain guard, non-finite/incomplete computed metrics, `numpy.linalg.LinAlgError`, `FloatingPointError`, or `OverflowError` raised inside the validated physics boundary. Emit a stable `failure_code` and `PHYSICS_FAILED`, charge one unique FE, and cache it. An arbitrary `ValueError`, `TypeError`, missing config/key, assertion, or other unexpected failure is not automatically a physics failure; only the enumerated code/site is modeled. No equation, tolerance, passivity threshold or COM behavior changes.
- **Infrastructure exception:** filesystem/process/worker/host errors, unexpected exceptions, cancellation, or errors outside the narrowly typed modeled evaluation boundary. Persist an incomplete physics-attempt event, preserve candidate intent, set `INFRASTRUCTURE_INTERRUPTED`, and retry the same candidate under identical identity after recovery; do not emit `PHYSICS_FAILED` or a comparator record.
- **Invalid record:** schema/status/value inconsistency after evaluator return; distinct from a modeled failure and infrastructure interruption. Charge a new candidate FE as above, quarantine and stop.
- Stage 4C's broad exception conversion must not be used to disguise arbitrary exceptions. Q1's wrapper must classify only enumerated numerical/model exceptions arising within the physics boundary as modeled failure; all other raised exceptions are infrastructure or invalid-record errors according to origin. No silent exception-to-physics conversion.

### 5.4 Transactional evaluation, crash/recovery and exact accounting

Use a durable append-only transaction journal (SQLite WAL, `synchronous=FULL`, or an equivalently atomic implementation) with hash-linked event sequence and atomic state commits; journal events, not wall-clock telemetry, define scientific state:

1. Persist the complete immutable cell identity before sampling/evaluation. Persist each sampler draw and post-draw RNG state before proceeding; sampler recovery resumes the next draw.
2. Persist one `PROPOSAL_ATTEMPT` journal event for every complete canonicalized optimizer candidate, including duplicates and each internal L-SHADE fallback draw: pre/post RNG state, raw normalized proposal, canonical key/vector, generation/target/retry/fallback cursor, and whether key is new or duplicate. A crash before this event replays from the preceding durable RNG state and reproduces the same proposal; after it, recovery advances without drawing it again.
3. For a new key only, persist `EVALUATION_INTENT` before invoking evaluator: phase, canonical key/vector, first-evaluation ordinal reservation, proposal-event reference, target/retry/cursor, and immutable evaluation identity. No new intent can be created at or beyond budget. Persist `PHYSICS_ATTEMPT_STARTED` before each composite physics dispatch. After normal return, validate candidate schema and atomically commit the terminal result, cache entry, unique FE counter, first-evaluation ordinal, history/top-16 index, and one search-trace event in a database transaction. Geometry gate return commits without a physics event.
4. If a process dies before terminal result commit, the pending intent remains. Resume retries that exact candidate/evaluator identity; any extra dispatch is separately counted as a repeated infrastructure recovery attempt, not another unique FE. A durable terminal result is never reevaluated; recovery consumes it from journal and finishes pending optimizer transition.
5. Apply optimizer survivor/adaptation/cursor/RNG-after state and mark `OPTIMIZER_STEP_COMMITTED` atomically after the candidate result is durable. Until then, no next proposal is drawn. Recovery uses the committed result and pending target/snapshot to complete the same transition without a second evaluator call or FE increment. Duplicate events advance only the duplicate/retry counters and pending retry cursor; they do not create evaluation intents.
6. Initial population evaluation uses the same intent/result protocol and ordered member cursor. It resumes the exact member. Each arm has its own journal/cache and must independently commit all 234 initial FEs.
7. If an infrastructure interruption occurs within a model call, it cannot be known whether remote/low-level computation finished. Record the started attempt as unresolved, retry same deterministic key on recovery, and count actual attempts; unique FE/cache/history/rank are still committed exactly once. This is at-least-once physical invocation with exactly-once durable unique-design accounting, not a claim of exactly-once external computation.
8. Snapshot checkpoints at the declared FE lattice (§8.3) reference the journal sequence/hash. Journal append and snapshot use temp-file + fsync + atomic replace/transaction; a corrupt/truncated/hash-mismatched journal fails closed. No checkpoint may contain a counter whose candidate/result event is absent.

## 6. Comparator, record schema and stable ranking

### 6.1 Comparator contract

Call the existing `GeometryFirstComparator.rank_key` and `.better` exactly; no source change or scalar objective/penalty conversion is permitted. It ranks `PHYSICS_EVALUATED` first by the existing feasibility-first tuple, `PHYSICS_FAILED` after evaluated physics with its existing +Inf tuple, and geometry rejects after physics-valid geometry. The exact key order and tolerance behavior are inherited from `selection.py`.

- Candidate selection is `(rank_key(record), first_evaluation_ordinal)` only for stable history/incumbent/top-16/validation sorting. The ordinal is not inserted into or used to alter `rank_key` itself.
- On exact rank-key tie in DE parent/trial selection, keep parent. L-SHADE retains existing strict `.better()` replacement. Incumbent tie preserves the earlier first-evaluation ordinal. History/top-16 sort by rank then smaller ordinal. Validation rank sorts by validation rank key then original search first-evaluation ordinal. Equal keys do not trigger a replacement or memory-success update.
- L-SHADE operator p-best sorting remains the existing stable population-order tie behavior; do not inject history ordinals into its operator ranking. This distinction is needed to preserve its existing trajectory.
- Report scalar objective only as a diagnostic field if present. It never selects parents, survivors, incumbents, top-16, validation winner, or convergence status. No weighted scalarization.

### 6.2 Strict candidate-record schema (`stage5a2_candidate_record_v1`)

Validate at the evaluator boundary before comparator invocation. Missing, wrong-typed, extra-unversioned, internally inconsistent or unknown status is `INVALID_RECORD`; do not rely on comparator permissive defaults. Every terminal search/validation result contains:

- `schema_id`, `schema_version`, `evaluation_phase` (`search` or `dense_validation`), `evaluation_status`, `topology`, `candidate_key`, finite 13-element canonical physical `candidate_vector`, `first_evaluation_ordinal` (search) / `validation_ordinal` (validation), `source_search_ordinal` for validation, exact grid SHA-256, `geometry_valid`, `geometry_dimensions`, and `geometry_violations`;
- `metrics`, `violations`, `filter_metrics_available`, `feasible`, `max_violation`, `sum_violation`, `objective` (diagnostic only), `source_impedance_ohm=50.0`, `load_impedance_ohm=50.0`, and either `failure_stage=null` or a typed `failure_code`/safe message;
- optional diagnostic data only under a versioned `diagnostics` namespace. Those fields do not enter ranking.

Allowed evaluator `evaluation_status` values are exactly `PHYSICS_EVALUATED`, `PHYSICS_FAILED`, `GEOMETRY_REJECTED`.

Semantic validators:

- `PHYSICS_EVALUATED`: geometry valid; finite metrics `worst_il_db`, `ripple_db`, `input_vswr`, `output_vswr`, `source_return_loss_db_min`, `load_return_loss_db_min`, four-element `stop_attenuation_db`; finite violation keys exactly `il`, `ripple`, `input_vswr`, `output_vswr`, `stop_0`…`stop_3`; finite max/sum/objective; explicit bool feasible; geometry violations finite and nonpositive. Feasible/max/sum consistency is validated against frozen existing rules, but the comparator output is not recomputed with a new ranking.
- `GEOMETRY_REJECTED`: geometry invalid and positive finite geometry maximum; metric/filter violation payloads empty, `filter_metrics_available=false`, `feasible=false`, and physics fields not applicable/null by schema; zero COM call.
- `PHYSICS_FAILED`: geometry valid; typed nonempty failure code; empty metrics and filter violations; `filter_metrics_available=false`, `feasible=false`, and comparator's established failure rank; failure must not encode an infrastructure exception.
- `feasible` must be an actual bool, never a truthy string or omitted; physics metrics/violations cannot be missing and cannot be coerced to zero/defaults. Grid/topology/key must match cell identity and canonical vector. The comparator's missing-status-to-physics-failed and unknown-status-to-geometry-reject compatibility behavior is never exposed to optimizer inputs.

### 6.3 Lossless canonical key and non-finite handling

- Canonical key schema `f64be_tuple_v1`: dimension 13 plus one 16-character IEEE-754 binary64 big-endian hex token per coordinate. Coordinates are finite; signed zero is normalized to `+0.0`, matching tuple equality. Canonical vector remains finite. The cache/database key is this typed byte sequence, not shortened decimal JSON.
- Rank-key serializer `rank_tuple_f64_v1`: each component encoded as finite binary64 hex or an explicit token `+Inf`, `-Inf`, `NaN`; never JSON `null`. Round-trip must preserve exact value/class. NaN is invalid for any record/rank. `+Inf` is allowed only where unchanged comparator defines it (notably `PHYSICS_FAILED`); `-Inf` is never valid in a candidate rank. The codec supports round-trip of NaN and both infinities for test fixtures but validator rejects them except the specified +Inf rank. Null remains only for schema-declared not-applicable payload values, never as a rank number.
- Every serialized object states schema/version. JSON uses UTF-8, sorted keys, separators `(',',':')`, no NaN JSON literals, and the typed codec. Hash keys retain full values; SHA-256 is an integrity digest, not a replacement for the lossless key.

## 7. Checkpoint/resume identity and versioning

### 7.1 Required cell identity (all fields mandatory)

`protocol_id/version`, `source_commit_sha` and clean-tree flag, computation source fingerprint, raw config SHA-256 and canonical effective-config SHA-256, COM/profile identity, specification/constraint/topology identity, optimizer ID/version, exact resolved optimizer settings, topology, root and derived seeds, Python/NumPy/SciPy/platform/BLAS environment fingerprint and thread settings, active/hard bounds and design-space hash, integer indices/rounding/canonicalizer version, search-grid count/content hash, validation-grid ID/count/content hash, comparator class/source hash/version, candidate schema version, terminal unique budget, L-SHADE terminal horizon if applicable, RNG bit generator/state schema, initial-population serialization/hash, journal schema/head hash, and checkpoint schema version. Missing and mismatched identity are both fatal `CHECKPOINT_IDENTITY_MISMATCH` before state hydration or evaluator invocation.

### 7.2 State contents

Both arms persist: immutable identity; optimizer identity/config; generation/target/cursor; all RNG states; complete ordered current population and canonical keys; L-SHADE archive/memories/history index/success batches/shrink/fallback/retry state or DE parent snapshot/pending generation trials/per-target retry state; full private evaluation cache and every candidate record; sampler state/counters; evaluation intents/attempts/terminal results; unique/raw/failure counters; first-evaluation ordinals; per-FE search trace; top-16 history; comparator/rank state; validation cursor/results; checkpoint journal sequence/hash; active-runtime counters and separate downtime metadata.

### 7.3 L-SHADE compatibility and Stage 4C preservation

- Existing `LShadeBackend` compact state `state_version=4` remains the historical inner state schema. Existing Stage 4C files/config/checkpoints are read-only and are neither migrated nor rewritten.
- Q1 wraps a fresh v4 L-SHADE payload in a new strict outer checkpoint envelope `stage5a2_checkpoint_v1`, with the full required identity above, a strict nested-state key/shape validator and the new transactional journal. No bare legacy state, missing identity, 96,000 horizon, or Stage 4C checkpoint is accepted for the 4,096 pilot.
- No in-place migration is provided: old Stage 4C runs remain usable only by their historical readers. If a later algorithm-state schema changes, create a new envelope/inner version and explicit reader; never modify saved Stage 4C data. A missing source/config/grid/seed/comparator identity is rejected even though the current `load_state_dict` has compatibility defaults.

### 7.4 Deterministic resume guarantee

On the pinned same environment, uninterrupted versus checkpoint/resume must produce identical ordered proposal vectors, donor/target/mask sequence, RNG state, population/archive/memories, evaluation cache/results/statuses, rank-history order, per-FE trace, top-16 and terminal candidate records. Timestamp, elapsed wall and downtime fields are allowed to differ and must not enter identity-dependent proposal state. A pending evaluation result is consumed without reevaluation; a pending evaluator attempt with no durable result retries the same canonical vector and is separately counted.

## 8. Trace, counters, compute resources and comparison

### 8.1 One trace event per unique search FE

Write exactly one immutable event for every committed unique search FE, including each of the 234 ordered initialization evaluations and DE trials evaluated before generation commit. Record FE index, phase, candidate key/reference, rank key using lossless codec when the record is rankable, first-evaluation ordinal, raw proposal/counter snapshot, trial target/generation and pending/committed survivor state, current search-grid best-so-far key/rank, cumulative active elapsed time since the first sampler draw (downtime excluded), phase durations and checkpoint-journal sequence. A returned `INVALID_RECORD` still gets one FE/status event with no rank key and unchanged prior best-so-far, then stops fail-closed. Duplicate/cache-hit proposals create counter/journal events but no FE trace event. For rankable records, best-so-far rank is monotone nonincreasing. The search trace never contains dense-grid outcomes.

### 8.2 Counter and time fields

Separate and publish:

- initialization sampler draws, duplicate/geometry rejects, accepted count, sampler CPU/wall time;
- initialization evaluation FE and physics timing;
- post-initialization raw proposals, duplicate/cache hits, DE retries, L-SHADE normal/fallback attempts and internal draws, global watchdog attempts;
- search unique FEs, geometry rejected FEs, physics dispatches, COM model calls, evaluated results, modeled physics failures, infrastructure retries, invalid records;
- terminal validation design count, validation physics/geometry results, validation COM model calls;
- search evaluation time, optimizer proposal/selection exclusive time, checkpoint/journal I/O time, terminal dense-validation time;
- active runtime, end-to-end wall duration across resumes/downtime, process CPU time and peak RSS bytes/MiB.

Timers use monotonic/per-process clocks; instrumentation cannot consume RNG or call additional physics. Attribute durations to disjoint phases by suspending phase timers around evaluator and checkpoint calls. `initialization_active_time` is the non-overlapping sum of sampler generation, evaluation of the ordered 234 initial members and initialization checkpoint I/O; its component times are also reported. `search_active_time` is the non-overlapping post-initialization sum of proposal/selection work, subsequent search evaluator calls and search checkpoint I/O; its component times are reported. `terminal_dense_validation_time` is separate. `active_runtime` is the sum of those three phase times plus explicitly recorded protocol/serialization overhead; no time is double-counted. `end_to_end_wall` spans the first sampler operation through final validation completion including downtime. Report both objective-evaluation and wall-clock quality curves; do not infer one from the other.

### 8.3 Checkpoint schedule and resource policy

Durable snapshots at FE 234, every 512-FE boundary (`512,1024,…,3584`), and 4,096; plus safe failure/interruption snapshots. The journal remains transactionally recoverable between snapshots and identifies the latest durable proposal/evaluation state. Checkpoint and trace observation must not perturb RNG or proposal order.

For every cell: one process, one optimizer worker, one BLAS/OpenMP thread (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `BLIS_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`); no intra-cell or inter-cell parallelism. Record CPU model/affinity, RAM, Linux/WSL2 version, BLAS vendor and threadpool state. Q0/Q1 do not launch cells.

Run order is fixed and serial; alternating first method within each matched topology/seed pair balances ordering:

| Order | Seed | Topology | Method |
|---:|---:|---|---|
| 1 | 20261012 | P_D | L-SHADE |
| 2 | 20261012 | P_D | Controlled DE |
| 3 | 20261012 | D_P | Controlled DE |
| 4 | 20261012 | D_P | L-SHADE |
| 5 | 20261013 | P_D | Controlled DE |
| 6 | 20261013 | P_D | L-SHADE |
| 7 | 20261013 | D_P | L-SHADE |
| 8 | 20261013 | D_P | Controlled DE |
| 9 | 20261014 | P_D | L-SHADE |
| 10 | 20261014 | P_D | Controlled DE |
| 11 | 20261014 | D_P | Controlled DE |
| 12 | 20261014 | D_P | L-SHADE |

Do not interleave cells or run two cells concurrently. Report paired per-seed search-grid best-so-far versus unique FE and active wall time; separately report terminal dense validation, feasibility/violations, named RF metrics, all statuses, duplicate/fallback exposure, runtime/resources and spread. Three pairs are exploratory and weak for uncertainty; no universal winner, convergence or infeasibility claim.

## 9. Terminal history and validation

- Maintain all unique search records (or lossless journal-backed rank index) using search-grid `rank_key` and first-evaluation ordinal; cache does not cross method, seed, topology or grid identity.
- After search termination, select the stable best 16 distinct canonical keys from the entire search history, not terminal population. If a rankable incomplete cell contains fewer than 16 unique keys, validate each available key and disclose the shortfall. A malformed `INVALID_RECORD` is quarantined and cannot enter ranked history; if it prevents full protocol integrity, do not issue a completed comparison.
- Independently evaluate each finalist on the common dense grid using the same frozen model, geometry/physics gate and strict schema under a validation cache/phase identity. Geometry reject and modeled physics failure retain their typed status; do not call COM for geometry rejection. Validation calls do not consume 4,096 search FEs.
- Report every finalist's source search rank/FE ordinal, validation result/status/rank and metrics/violations; report search-grid incumbent separately. Select validated winner using exact `GeometryFirstComparator.rank_key` then original search first-evaluation ordinal. No average or scalarized objective can replace that rule.
- Dense validation is not optimization and does not prove the global dense-grid best: only the 16 search-history finalists are validated. Report this limitation.

## 10. Q1 implementation qualification matrix (design only)

The **single authoritative Q1 gate-ID matrix** is [`docs/plans/stage5a2_q1_qualification_matrix.md`](../../docs/plans/stage5a2_q1_qualification_matrix.md), IDs Q1-01 through Q1-23. The overview table below deliberately assigns no IDs; do not maintain a second numbering scheme. The standalone matrix includes gates for the §14 findings, but Q1 is blocked until Q0 design amendments are specified, not merely tested. All qualification is synthetic/unit-only with a synthetic evaluator. It must prove no COM provider/import/call, no orchestration/production run, and no optimizer study launch. No such code or test is implemented or run in Q0-R1.

| ID (see standalone matrix) | Qualification gate | Minimum evidence / pass rule |
|---|---|---|
| — | L-SHADE resolved configuration | Assert all Stage 5A-2 resolved values/source defaults above; injected population; source behavior unchanged; cold horizon 4,096; verify 96,000 state/horizon rejected. |
| — | DE golden operator | Exact fixed seed proposal fixture for ordered donor triple, target exclusion/distinctness, mutation equation, forced coordinate, vector mask draw order, reflection, physical decode, half-up integer canonicalization and phenotype remap. |
| — | RNG and seed derivation | Golden SHA-256 seed vectors for each role/topology/root seed; explicit PCG64; donor/crossover/retry draws and no hidden/conditional extra RNG consumption; same-seed identical proposal sequence. |
| — | Common initial population | Deterministically construct 234 ordered geometry-valid canonical designs; both optimizers receive bit-identical vectors/hash; test uniform-physical law, canonicalization, duplicate-before-geometry order, sampler accounting and no fitness-driven resampling. |
| — | Initialization failure/recovery | Synthetic draw stream capped at 10,000 yields `INITIALIZATION_FAILED` with exact partition and zero optimizer FEs; interruption at sampler draw resumes same stream; partial 234 member evaluation resumes same arm cache/cursor and no cross-arm sharing. |
| — | Duplicate and cache isolation | Both algorithms: canonical duplicates call no evaluator, consume no FE, preserve key/counters; geometry and physics outcomes cache within one cell only; topology/seed/method/grid identity prevents reuse. |
| — | Strict 4,096 budget | Initial 234 charged per arm; geometry rejects, physics failures and invalid records charge once; duplicates and sampler rejects do not; no evaluator dispatch beyond 4,096; no sentinel evaluation; 16×234 + 118 DE remainder with no duplicates. |
| — | DE synchronous survivor semantics | Frozen parent generation; generation-order target traversal; no within-generation donor leakage; parent-on-tie; commit order; final partial generation only applies completed target trials. |
| — | DE retry/stall bounds | 4,096 trial attempts per target-generation and 65,536 global no-progress proposals stop exactly at limits, consume no extra RNG at abort, yield `BUDGET_STALLED`, no fallback/sentinel; geometry rejection ends target rather than duplicate retry. |
| — | L-SHADE existing duplicate fallback and watchdog | Six normal attempts; verify the first-`None` immediate break and at most one mixed-space fallback call of up to 256 draws; historical fallback behavior retained; 65,536 external watchdog finite and no trajectory/RNG change before cutoff. |
| — | Failure taxonomy | Synthetic geometry reject, modeled physics failure, infrastructure exception/retry, malformed record, sampler failure and certified finite exhaustion map only to their distinct statuses and counters; infrastructure never appears as scientific physics failure. |
| — | Transaction/recovery | Crash at intent, evaluator-start, returned result, cache/FE commit, optimizer transition, initialization and validation; resume no double FE/cache/result, no unrecorded invocation event, pending candidate is not reevaluated once durable, and proposals/population/history remain identical. |
| — | Candidate/comparator rules | Strict missing/unknown schema rejection; geometry-first and feasibility-first exact rank order; violation values >1,000; tuple not scalarized; ties preserve parent/first ordinal; p-best population-order ties unchanged. |
| — | Serialization | Round-trip canonical binary64 keys, signed zero normalization, rank finite/+Inf/-Inf/NaN tokens, RNG state, cache and histories; validator rejects NaN and invalid -Inf while preserving allowed physics-failure +Inf. |
| — | Checkpoint identity | Reject every missing and mismatched identity field before evaluator call; schema/hash/journal corruption fails closed; source/config/grid/comparator/canonicalizer/horizon/population/environment mismatch detected; legacy Stage 4C data untouched. |
| — | Checkpoint replay | Uninterrupted/restarted equality at 234, 512-boundaries, mid-generation pending trials, duplicate retries, failure boundaries, terminal partial generation and 4,096; compare proposal vector order, RNG, population/archive/memory, cache, rank history, trace, top-16. |
| — | Search trace | One and only one event per unique FE including initialization and pre-commit DE trials; no duplicate trace; monotone nonincreasing best-so-far rank; search-grid/validation separated; trace/checkpoint timers do not perturb RNG. |
| — | 12-cell synthetic integration | Exact two topologies × two methods × three root seeds, 234 same initial members per matched pair, arm-local cache, specified serial cell order metadata, exact terminal/incomplete statuses and all counter partitions; prove zero COM model calls/imports and no orchestration. |
| — | Dense finalist validation | Stable full-history top-16 (or disclosed shortfall); validation call count/statuses; source/search rank retained; final selected validated design follows comparator+ordinal; dense stage excluded from search FE. |
| — | Resource/timing/storage | Exclusive phase timing reconciliation, checkpoint I/O, active/end-to-end/downtime split, process CPU, peak RSS, one worker/one BLAS thread, unique-FE and wall-clock quality traces separate; future authorized raw journals/checkpoints/populations stored outside Git worktrees. |
| — | Censored comparison reporting | Synthetic completed/stalled/interrupted matched-pair cases; all scheduled cells visible; no forward-fill or survivor-only ranking; compare genuine common observed FE support, report coverage/cutoff reasons; no superiority claim from censored/missing pairs. Exact estimator/support summaries remain a Q0 blocker, not a Q1 choice. |

Passing Q1 would qualify implementation for a later review only. It does not approve Q0, accept a pilot, authorize COM evaluation, launch optimization or imply a production run.

## 11. Explicit non-goals and safeguards

No Q1 implementation/tests/COM calculation/optimization or Stage 4C mutation in this task. No changes to COM parameters, model, specs, constraints, bounds, topology or objective; no L-SHADE algorithm change; no automatic budget expansion; no weighted penalty; no seed replacement; no claim that infeasible or stalled means mathematical infeasibility; no claim of optimum or broad DE/L-SHADE superiority; no worktree/parallel cell creation; no PR merge. A finite-budget solution is best-found only.

## 12. Read-only audit references

- `src/sawopt/optimizers/lshade.py`: defaults, memory/adaptation, mutation, repair, fallback, caching, schedule, checkpoints.
- `src/sawopt/optimizers/selection.py`: unchanged `GeometryFirstComparator.rank_key` and feasibility-first ordering.
- `src/sawopt/problem/hybrid.py`: canonical clip / half-up integer rule and design-space identity.
- `src/sawopt/studies/hybrid_stage4b.py`: Stage 4B initializer, exact seed payload, evaluator wiring, `LShadeBackend` resolved config and serial cell runner.
- `src/sawopt/studies/hybrid_stage4c.py`: frozen Stage 4C inputs/horizon and production/shakedown references.
- `configs/studies/hybrid_stage4c_confirmatory.yaml`: 96,000 historical budget, 18×D initializer, Stage 4C settings, grids and protected model/spec/bounds.
- `uv.lock`, `.python-version`: pinned environment inputs.
- `docs/history/stage5a1_closeout_20261020.md`: evidence-limited historical closeout; no convergence or algorithm winner.
- `docs/plans/stage5a2_minimum_fair_comparison.md`: planning proposal and prior conditional Sol gate.
- `reports/escalation_packets/stage5a2_de_protocol_sol_review_20261021.md`: full previous Sol decision and required changes.
- PR #47 independent review: [ChatGPT review comment](https://github.com/MasayaTakagi/saw-com-optimizer/pull/47#issuecomment-6294426203) (the sole review was a PR issue comment; no inline review comments were returned by the GitHub API). Its required gates are mapped in §13.

## 13. Previous-findings disposition matrix (current documentation status after Sol re-review)

Status legend: `RESOLVED_WITH_SPEC` means the request is explicitly specified; `RESOLVED_WITH_JUSTIFIED_ALTERNATIVE` means a specified alternative addresses it with disclosed consequences; `BLOCKED_WITH_REASON` means the prior request is not yet closed and blocks Q1. The matrix is updated to the independent Sol R1 result. Q1 may not resolve design choices left open here.

| Finding | Status | Frozen resolution and rationale | Source/evidence |
|---|---|---|---|
| Sol R1-1: exact L-SHADE reference and full package estimand | `RESOLVED_WITH_SPEC` | Sol found that the reviewed revision missed `_generation`'s decisive early `break` when `_unseen_proposal()` returns `None`. After review, §§2.1–2.2 were corrected to distinguish the syntactic 64-iteration allowance from the single reachable mixed-space fallback call; Q1-11 requires a first-`None` fixture. This post-review correction was not reviewed by Sol and remains subject to GitHub review. | `lshade.py::_generation/_unseen_proposal`; Sol R1 §14.1; §§2,10,14 |
| Sol R1-2: DE operators/RNG/donor/crossover/retry/survivor commit | `BLOCKED_WITH_REASON` | The proposal semantics are fixed, but Sol R1 found that the journal does not atomically specify duplicate/retry cursor transitions, new-key proposal-to-evaluation-intent recovery, or all pending proposal state. Close the §5.4/§7 crash windows before Q1. | §§3–5,7; Sol R1 §14.2 |
| Sol R1-3: complete common initializer and partial initialization | `BLOCKED_WITH_REASON` | Sampler law, cap and population format are specified, but §4.2/§5.4/§7 do not separate pre-sampling identity from the later population hash and mutable journal head, or define a lossless sampler-resume state. Freeze identity lifecycle and exact PCG64 state codec before Q1. | `hybrid_stage4b.py::_sample_stage4b_population`; Sol R1 §14.3; §§4.2,5.4,7 |
| Sol R1-4: bounded retries/stall, status taxonomy and modeled/infrastructure distinction | `BLOCKED_WITH_REASON` | The fallback control flow is now described post-review, but durable optimizer-only no-result transitions and fixed paired summaries for censored cells remain unresolved. The 65,536 proposal limit is not a wall-time cutoff; specify no survivor-only comparisons, common observed support and cutoff reporting. | `lshade.py::_generation/_unseen_proposal/advance_to_unique_budget`; Sol R1 §§14.1, 14.2, 14.4; §§2.5,3.3,5,8 |
| Sol R1-5: schemas, ties, lossless keys/infinities and missing identity | `BLOCKED_WITH_REASON` | Candidate/comparator rules are substantially specified, but §7.1 conflates pre-sampling identity with later population/journal hashes; the reviewed §4.2 had a broken §7.6 codec reference (now marked unresolved); the outer envelope still does not state how it avoids inner L-SHADE nonfinite-to-null serialization. Specify lifecycle and codec before Q1. | `selection.py`; `hybrid.py`; `lshade.py::_jsonable/load_state_dict`; Sol R1 §14.3; §§4.2,6–7 |
| Sol R1-6: per-unique-FE trace, cost/timing/resources/order | `BLOCKED_WITH_REASON` | Trace/resource details are specified, but §8 does not freeze aggregate handling of watchdog-censored pairs. The §2.5 wording equating proposal-count censoring with wall-time censoring was corrected after review; define observed-support and completion reporting before Q1. | Stage4C config; closeout resource evidence; Sol R1 §14.4; §§5,8 |
| Sol critical: no default duplicate-streak termination | `BLOCKED_WITH_REASON` | External watchdog is a defensible alternative; the fallback fact is now documented, but durable no-FE optimizer transitions and censored-pair reporting remain open; see Sol R1 §§14.2,14.4. It is a proposal-count limit, not wall-time limit. | `lshade.py::_check_search_space_exhausted`; §§2.5,8,14 |
| Sol critical: legacy DE backends ineligible | `RESOLVED_WITH_SPEC` | New backend only; prohibited to use/relabel `ScipyDELegacyBackend` or `FixedDEReferenceBackend`. | Prior Sol packet read-only audit; §1, §3 |
| Sol critical: 4,096×3 is exploratory only | `RESOLVED_WITH_SPEC` | §§1/8/11 limit interpretation; no convergence, impossibility, global optimum, or universal superiority claim. Censored-cell reporting remains separately blocked under R1-4/R1-6. | Roadmap; Stage5A-1 closeout; §§1,8,11 |
| PR #47 IR-1: fully freeze DE RNG/donor/crossover/target/retry/update | `RESOLVED_WITH_SPEC` | Exact operator and draw order plus retry/commit state in §3. | PR #47 review comment; §3 |
| PR #47 IR-2: common population sampler/seed/order/canonical representation/hash/recovery | `BLOCKED_WITH_REASON` | Draw law/order and serialization are specified, but sampler resume before population freeze and transition from pre-sampler identity to population hash are not. Resolve identity lifecycle and PCG64 resume state; no Q1 discretion. | PR #47 review comment; `hybrid_stage4b.py`; Sol R1 §14.3; §§4,7 |
| PR #47 IR-3: numeric bounded retry/watchdog without changing L-SHADE, distinct failure classes | `BLOCKED_WITH_REASON` | The L-SHADE first-`None` exit is documented post-review, but idempotent no-FE offspring transitions and censored-pair reporting remain open. The watchdog is proposal-count-based, not wall-time-based. | PR #47 review comment; Sol R1 §§14.1,14.2,14.4; §§2.5,3.3,5,8 |
| PR #47 IR-4: strict record/tie/lossless serialization/checkpoint missing identity | `BLOCKED_WITH_REASON` | Record and tie rules are specified; checkpoint identity lifecycle, PCG64 state codec and nonfinite inner-state serialization are not. Resolve Sol R1 §14.3 before Q1. | PR #47 review comment; Sol R1 §14.3; §§6–7 |
| PR #47 IR-5: geometry pre-screen vs search FE and counter equations | `RESOLVED_WITH_SPEC` | Sampler geometry reject is excluded; optimizer geometry reject is a unique FE; disjoint counters and equations defined. | PR #47 review comment; §5.1–5.3 |
| PR #47 IR-6: search-only per-FE trace, resources/timing/serial order | `BLOCKED_WITH_REASON` | The trace/resource contract and serial order are specified, but pair-level treatment of censored/incomplete cells is not. The proposal-count versus wall-time wording has been corrected after Sol review; freeze observed-support reporting. | PR #47 review comment; Sol R1 §14.4; §8 |
| PR #47 IR-7: do not overstate 3-seed/4k evidence or authorize Q1/run from review | `RESOLVED_WITH_SPEC` | Explicit interpretation and separate Sol/GitHub/user/implementation/run gates; no automatic run or merge. | PR #47 review comment; §§1,10–11 |
| Sol re-review: one authoritative Q1 gate-ID mapping | `RESOLVED_WITH_SPEC` | Standalone qualification matrix is the sole Q1-01…Q1-23 mapping; packet overview table carries no IDs. This post-review documentation correction was not reviewed by Sol and is not gate approval. | Sol R1 §14, item 5; §10; `docs/plans/stage5a2_q1_qualification_matrix.md` |

**Post-review finding disposition:** the first self-assessment above is not external acceptance. Current classifications reflect Sol's independent Q0-R1 re-review; every `BLOCKED_WITH_REASON` item remains a Q0 design blocker and cannot be deferred to Q1 implementation.

## 14. Sol Q0-R1 independent re-review result

**SOL_DECISION:** `REQUEST_Q0_REVISIONS`. Sol found substantial progress but did not consider the reviewed protocol sufficiently precise to qualify Q1. Q0 remains open; Q1 implementation is blocked pending resolution and acceptance of the still-open design issues below, independent GitHub review, and explicit user implementation permission. Sol's decision authorizes no code, tests, synthetic evaluation, COM/network calculation, optimizer, or run.

**Routing evidence:** requested `openai/gpt-6.1-sol`, Pi thinking `medium`, tools `read`, non-persistent. The child record shows provider `openai`, API `openai-responses`, model `gpt-6.1-sol`, recorded `thinkingLevel=medium`, and normal `stop`; the child session was `stage5a2-q0-r1-sol-review` / `01a15a0a-4381-7496-a29d-3fc053d66ad9`. It used read-only file reads for this packet, the prior Sol packet, plan, qualification matrix and `lshade.py`. The raw local session is not committed. Recorded `medium` is a runtime setting, not proof of internal reasoning effort; no claim about hidden reasoning or credential/billing path is made.

### CLOSED_FINDINGS (bounded)

- Complete algorithm-package comparison and exploratory 4,096-FE / three-root interpretation.
- Controlled DE proposal/operator semantics, common population distribution/hash, FE distinction for sampler versus search rejection, evaluator/cache isolation, and dense validation design.
- Unchanged comparator tuple, stable tie policy, governance separation, serial resource/cell-order intent and non-optimality claims.

These closures do not override the cross-cutting open transaction, identity, L-SHADE, and censored-reporting issues below.

### FINDINGS_OPEN_AT_REVIEW_AND_POST-REVIEW_DISPOSITION

1. **R1 — L-SHADE fallback control flow (finding at time of review; source description corrected after review)** (packet §§2.1–2.2, 2.5; source `lshade.py::_generation/_unseen_proposal`). Sol correctly found that when `_unseen_proposal()` returns `None`, `_generation` immediately breaks out of its attempt loop; it does not make the remaining nominal fallback-loop calls. A returned unseen candidate also ends the offspring retry loop. The reviewed revision's stated `up to 64 fallback calls` and maximum-envelope rationale did not describe reachable behavior. **Post-review correction:** §§2.1–2.2 now distinguish the syntactic loop allowance from one reachable mixed-space fallback call and §2.5 uses the corresponding 262-proposal maximum no-progress step. Q1-11 requires a first-`None` fixture. This correction was not re-reviewed by Sol; external review remains required.
2. **R2 — replay journal transition coverage (still open)** (§§5.4,7.2–7.4; Q1 transactional/replay gates). A durable new-key `PROPOSAL_ATTEMPT` may exist before its `EVALUATION_INTENT`; resume must create that same intent. Duplicate persistence and retry/watchdog/cursor movement need one idempotent transition. L-SHADE can finish an offspring with no new FE but still change memory-batch count, generation, shrink/trace state; that optimizer-only transition needs its own durable commit. Persist all pending F/CR, memory index, boundary and fallback state. Freeze a transition table across sampler, duplicate, new key, fallback `None`, unsuccessful offspring, result and optimizer-only commit, with deterministic recovery at every boundary.
3. **R3 — identity lifecycle and serialization (still open)** (§4.2, §5.4 step 1, §§7.1–7.3). The reviewed packet pointed to a nonexistent §7.6 for the RNG codec; §4.2 now labels that codec unresolved rather than presenting a broken reference. Population hash cannot be a pre-sampling immutable field, and journal head changes during execution. Split pre-sampling identity, once-frozen population attachment, and mutable snapshot/journal-chain references. Define sampler resume identity before population completion. Specify lossless PCG64 state encoding (128-bit state/inc, cached uint32 state, integer precision/version) and explicitly bypass or losslessly encode the historical L-SHADE inner JSON path that maps non-finites to `null`.
4. **R4 — censored-cell comparison rules (still open)** (§§2.5,3.3,8.3). The shared watchdog is a deterministic **proposal-count** limit, not a wall-time cutoff; equal counts do not imply equal censoring or work, and DE's per-target cap creates a further package-specific stop. Keep every scheduled cell visible; prohibit survivor-only aggregate rankings and forward-filling stalls to 4,096; compare only genuine common observed FE support with pair count/coverage; distinguish incomplete endpoints and report cutoff reason, fallback exposure and recovery overhead. Do not describe this policy as a wall-time censor.
5. **Q1 ID consistency** (§10 and standalone qualification matrix). One authoritative mapping was required. Post-review documentation correction: the standalone file is now the sole Q1-01…Q1-23 ID mapping and the packet table has no IDs. This resolves the duplicate-map defect as a documentation change, but it was not reviewed by Sol and carries no Q1 authorization.

### NEW_CRITICAL_FINDINGS

An L-SHADE offspring can affect future search state without a result/FE commit. Exactly-once FE accounting alone does not guarantee optimizer replay; unsuccessful-step memory/generation/shrink/trace transitions need independently durable, idempotent commits. This is a protocol precision defect, not evidence against the algorithm or physics.

### APPROVED_PROTOCOL_CONSTRAINTS (accepted in principle)

Retain frozen Stage 4C physics/spec/bounds/grids and historical data; cold 4,096-horizon L-SHADE; dedicated standard DE (no legacy backend relabeling); same ordered 234-member population with separate evaluations; exactly capped unique FEs and charged geometry/model failures; unchanged comparator and stable ties; full-history top-16 independent validation; explicit incomplete statuses; no seed substitution, extension, or global-optimum claim. The watchdog is acceptable in principle as an explicit termination rule only, not as equivalence past its boundary or a proof of convergence/exhaustion.

### Q1_QUALIFICATION_GATES

Retain the requested synthetic-only no-COM/unit gates. Strengthen them to test: first-`None` L-SHADE exit; unsuccessful L-SHADE offspring transitions; crash between proposal persistence and intent; atomic duplicate/retry/watchdog advance; crashes before/after memory flush, archive trim, shrink and cursor update; pre-population sampler identity/resume; lossless complete PCG64 and nested L-SHADE serialization; scientific replay equality separated from operational recovery history; and censored paired reporting without extrapolation or survivor-only conclusions. The standalone matrix carries the single authoritative Q1-01…Q1-23 identifiers.

### RESIDUAL_RISKS (recorded by Sol)

 three seeds provide weak uncertainty; equal FEs do not equalize physics, generations, fallback or runtime; deterministic cutoffs can censor packages differently; per-proposal RNG journaling may alter measured wall efficiency and its cost belongs to the tested package; infrastructure recovery is at-least-once work despite exactly-once FE ledger; initialization and update/boundary differences limit attribution; top-16 validation cannot establish global/dense-grid optimality.

**Re-review stop:** this was the one requested Sol review. No additional Sol agent will be started automatically. The documented open findings block Q1 pending user direction and independent GitHub review. The Draft PR remains unmerged; external review/user acceptance and run authorization remain separate.
