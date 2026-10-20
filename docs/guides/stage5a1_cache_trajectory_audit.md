# Stage 5A-1 L-SHADE cache identity and trajectory audit

## Purpose and scope

This read-only audit examines the saved Stage 4C run
`20261006_124153_ed50ba`. It does not resume L-SHADE, execute an optimizer
step, evaluate a candidate, run COM physics, or alter the external raw run.

The auditor lives at
`src/sawopt/studies/audits/stage5a1_cache_trajectory.py`. It stays outside the
optimizer execution layer and imports only the saved-run configuration loader
and pure frequency-grid constructor needed to rebuild the declared search-grid
identity. It does not import `sawopt.optimizers`, `sawopt.optimization`, or
`sawopt.orchestration`.

## Reproduction

In a fresh managed worktree, install the locked test environment and run the
synthetic regression tests:

```bash
uv sync --locked --extra test
uv run --locked pytest tests/unit/studies/audits/test_stage5a1_cache_trajectory.py
```

Set `RUN_DIR` to the already-existing external persistent Stage 4C run
location, then produce the redacted review files inside the repository:

```bash
RUN_DIR=/path/to/external/20261006_124153_ed50ba
OUTPUT_DIR=reports/experiment_reviews/stage5a1/20261006_124153_ed50ba
uv run --locked python -m sawopt.studies.audits.stage5a1_cache_trajectory \
  --run-dir "$RUN_DIR" --output-dir "$OUTPUT_DIR"
```

The output directory must be outside the external raw run. The auditor rejects
an output directory at or below the raw run root (including symlink aliases)
before reading its manifests or creating output files.

The source opens raw files read-only. Processing is serial by cell: one final
optimizer-state JSON is parsed at a time, followed by one `B*.json` record at a
time. Only the compact per-cell summary is retained for the final report. The
output contains no candidate vectors, checkpoint body, RNG internals, or source
run filesystem path.

## Evidence and invariants

The protocol/run manifests are checked against the Stage 4C run ID, original
execution SHA
`65e1815db1cc18d74ff0dcee20ffd5e9098709df`, computation fingerprint
`fdff19b63739efe1022092aa21e2ba3651c82a3344d54721522e5e0fc5cef9dd`, cell
matrix, 96,000-evaluation budget, eight declared checkpoints, and the exact
1,001-point search-grid digest.

For each cell the auditor checks:

- finalized `rolling_latest_previous` retention (`final.json`, runtime
  `latest.json`/`previous.json`, and pinned-state presence);
- state schema 4, `compact_history_cache`, history-index and retained-result
  counts, active and hard bounds, and computation fingerprint;
- 13-element finite canonical keys and candidate vectors, exact clip plus
  `floor(value + 0.5)` integer rounding, key/vector identity, duplicate keys,
  and a complete zero-based insertion-order sequence;
- one unchanged search-grid version and design-space version, plus exact
  equality and SHA-256 identity of the saved grid;
- unique-evaluation, proposal, duplicate, cache-hit, physics, geometry,
  search-frequency, and separate finalist-validation accounting;
- all eight historical finalist pools, reconstructed by filtering insertion
  order `< B`, sorting `(saved rank key, insertion order)`, then matching each
  of the 16 saved `search_source_rank` positions and candidate vectors;
- best-so-far, population, and archive trace chronology/rank behavior, exact
  checkpoint trace prefixes, incumbent consistency, population/archive
  structure and the configured L-SHADE population schedule;
- SHADE memory shape/range, PCG64 state structure, boundary-repair arrays,
  optimizer counters, and terminal checkpoint/final-state agreement.

The Stage 4C ranking implementation at the original execution SHA was checked
against current source. The only intervening changes in `lshade.py` and
`selection.py` add trace telemetry; `GeometryFirstComparator.rank_key`, the
compact-cache identity update, and finalist ordering are unchanged. Thus the
independent rank reconstruction applies the frozen Stage 4C `(rank_key, insertion_order)`
ordering and its first-on-tie behavior.

## Evidence limits

The final state is the only full optimizer state retained for each cell. The
80 `B*.json` files are per-budget result/validation summaries, not 80 optimizer
states. With compact history enabled, complete evaluation results are retained
only for the top 16; consequently the saved rank keys for the other historical
entries cannot all be independently recomputed from raw evaluation records
without rerunning physics. This audit checks their structure and unchanged
version/order context and uses the saved keys as historical evidence. It
recomputes retained-result ranks where full records exist and independently
reconstructs the saved finalist vectors/ranks at all 80 budgets.

Structural validity of RNG, population, memory, traces, and counters does not
replay the 96,000 optimizer transitions. No global-optimum, convergence, or
physical-calibration claim follows from this saved-state audit.

The existing PR #42 finalist-provenance audit reported 80/80 checkpoint pools
and 1,280/1,280 finalists PASS. Its saved `B*.json` finalist projection omits
`search_source_rank_key`, so per-record rank-key fields cannot be compared
directly. This audit sorts the final compact-index rank history and matches each
saved ordinal source rank and exact candidate vector at all 80 checkpoints. It
also checks optimizer trajectory/state invariants. The scientific disposition remains
`STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`.
