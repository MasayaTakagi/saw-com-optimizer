# Stage 5A-1 — Accounting, cache identity and finalist provenance audit

**Scope:** read-only review of saved Stage 4C run `20261006_124153_ed50ba` (P_D/D_P × 5 seeds); based on source `a6eb6434150af43d8bcb836698e264201ef8cc41` before this audit branch. No optimization or COM physics was run. The frozen review package was not modified.

## Independent checks of the 10 saved cells

| Field | Total | Interpretation |
| --- | ---: | --- |
| Unique evaluations | 960,000 | 96,000 per cell |
| Objective proposals | 1,003,677 | Unique + same-grid cache hits |
| Cache hits / duplicate proposals | 43,677 / 43,677 | Equal in all ten saved cells |
| Geometry rejects | 320 | Within the unique-evaluation partition |
| Physics failures | 0 | Physics valid partition matches |
| Common-grid validation evaluations | 1,280 | 16 finalists × 8 checkpoints × 10 cells |
| Common-grid validation failures | 0 | 9,113 points per successful validation |
| Initial population draws | 2,481 | 2,340 accepted plus 141 initializer geometry rejects |
| Search evaluator time | 56,216.9296 s | Measured within each cell |
| Common validation time | 646.8678 s | Measured within each cell |
| Total cell wall time | 65,004.4564 s | Includes other optimizer/checkpoint overhead |

All ten records pass the independently recomputed identities: `objective_proposals = unique + cache_hits`; `unique = geometry_rejections + geometry_valid_candidates`; `geometry_valid = physics_evaluated + physics_failed`; frequency points match successful evaluations × frozen grid size; and initial draw/accepted/rejected counts partition exactly. Each of eight checkpoint entries matches the frozen budget, and each terminal finalist metric matches the terminal checkpoint summary. Search and common-grid candidates pass the strict candidate integrity validator. The standalone regression suite includes deliberate accounting and candidate corruption tests.

## Canonical cache identity — source review

`HybridDesignSpace.canonicalize` checks a finite dimension-correct vector, clips to bounds, rounds integer indices and constructs its cache key from the canonical physical vector. `LShadeBackend._canonical` normalizes to the physical vector then delegates to this canonicalizer. `_evaluate` looks up the canonical key in `_cache_frequency_versions`; same-grid duplicates are cache hits, while a changed grid version forces reevaluation without charging another unique design. The compact finalist implementation holds stable ordered rank/vector evidence even when full cached payloads are evicted. Existing unit tests exercise canonical rounding, same-grid unretained cache hits, grid refresh and compact-vs-full ranking parity.

**Evidence limit:** the exported Stage 4C review has only the terminal incumbent and the selected common-grid finalist, not the complete canonical-key history or raw optimizer checkpoint. Therefore the independent audit checks counted consistency and source semantics, **not** a replay proof that all 960,000 distinct canonical keys were evaluated exactly once.

## Finalist provenance — source review

The cell engine reevaluates up to 16 historically ranked search-grid candidates on the fixed 9,113-point common grid at each of eight checkpoints. It selects the minimum canonical rank among `PHYSICS_EVALUATED` validation records, then projects only the selected finalist into `cell_result.json`. Search and validation grid IDs/hashes are recorded at protocol/run level, but not inside each projected candidate. The compact export cannot prove that the saved selected finalist won over all 16 validation candidates.

**Scientific disposition remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.** Search-grid and common-grid matched-seed rankings each remain P_D 3 wins / D_P 2 wins. No new experiment was authorized by this audit.

## Reproducible verification

`uv run --locked pytest tests/unit/studies/audits/test_stage5a1_accounting_provenance.py`

The function `audit_package(path)` reads the tracked review package without writing any data and returns a per-cell PASS/FAIL table and explicit unverified limitations. Full raw finalist-replay, independent canonical-cache replay and physics correctness remain unverified and should not be inferred from aggregate counter parity.
