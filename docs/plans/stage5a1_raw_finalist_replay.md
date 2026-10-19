# Stage 5A-1 — Raw Stage 4C finalist provenance replay

## Objective and boundary

The compact Stage 4C review establishes aggregate accounting but lacks the complete validation candidate pools. Reconstruct **recorded** 16-candidate selection decisions for all 80 frozen checkpoints from the external persistent run, without rerunning an optimizer or COM evaluation.

The auditor is a separate read-only module, does not import/load optimizer checkpoints, and never modifies `main` scientific results, the frozen protocol, raw `B*.json`, caches, or external run metadata.

## Inputs

- The existing Stage 4C external optimizer run directory, **containing** `optimization/P_D/seed20261007/B8000.json` etc. (80 `B*.json` files in total). Confirm the exact location; do not reconstruct or replace a missing file.
- The tracked package `reports/experiment_reviews/stage4c/20261006_124153_ed50ba/`.

Invocation from a worktree with the installed project:

```bash
uv run --locked python -m sawopt.studies.audits.stage5a1_raw_finalist_provenance \
  --optimizer-run "/absolute/path/to/existing/stage4c/optimizer" \
  --review-package reports/experiment_reviews/stage4c/20261006_124153_ed50ba
```

The command writes a JSON result **to stdout only**, returns exit code 0 for all-80 PASS and exit code 1 otherwise. Redirect stdout to an **external dedicated audit output** if evidence retention is desired; do not put output into any raw run folder.

## Checks and limitations

- Checkpoint source/run fingerprint, topology/seed, exact 8-budget lattice and cumulative common-grid validation point accounting.
- All 16 `validated_finalists` per checkpoint, ranks 1 through 16 in saved order, finite 13-element vectors and duplicate-vector detection.
- Full physics-evaluated candidate integrity using the existing strict Stage 5A-1 filter/geometry validator, with explicit checks for failed physics/geometry statuses.
- Recompute `min(eligible, key=GeometryFirstComparator.rank_key)` with stable first-on-tie semantics. Check selected record projection against the saved selected finalist and, at budget 96k, the compact terminal result.
- Match saved checkpoint metrics/generation counters to the compact review summaries.

This audits **selection replay only**. The raw B records do not expose historical `search_source_rank_key` inside `validated_finalists` because `_summary_record` drops that field. Therefore the prior *search-grid* ordering of all 16 candidates, complete cache-key uniqueness throughout 96k evaluations, and optimizer trajectory cannot be independently proven from B files. COM correctness likewise requires separate numerical replay; do not infer it from ranking parity.

## Local execution delegated to pi code

Direct filesystem access to the external production run is not available from the GitHub-linked coding environment. Perform this audit on the WSL2 machine that has the raw run mounted, using a **new independent worktree** and without launching optimization.

1. Verify the exact optimizer directory exists and all 80 B checkpoint files are present.
2. Run the existing full test suite and the new focused unit tests on the audit branch.
3. Run the read-only command above. Record the exit code, all-80 PASS/FAIL count, and per-cell failures. Do not claim PASS if any file is unavailable.
4. Review the audit logic against the original Stage 4C execution source commit `65e1815db1cc18d74ff0dcee20ffd5e9098709df` before using the result as final provenance evidence.
5. Store only a **small redacted summary** in a dedicated follow-up audit document/branch after reviewer approval; do not commit raw checkpoints, candidates, personal paths, tokens, spectra, or private metadata.
