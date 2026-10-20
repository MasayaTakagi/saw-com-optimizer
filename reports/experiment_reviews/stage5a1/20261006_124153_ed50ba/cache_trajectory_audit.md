# Stage 5A-1 L-SHADE cache identity and trajectory audit

**Status: PASS**

- Run: `20261006_124153_ed50ba`
- Original execution source SHA: `65e1815db1cc18d74ff0dcee20ffd5e9098709df`
- Computation fingerprint: `fdff19b63739efe1022092aa21e2ba3651c82a3344d54721522e5e0fc5cef9dd`
- Search grid: 1,001 points; SHA-256 `212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0`
- Cells: 10/10 PASS; 0 FAIL; 0 evidence-limited
- Reconstructed search-grid pools: 80/80; 1280/1,280 finalist positions checked
- Read-only analysis; no optimizer continuation, optimization, COM simulation, or raw-state mutation.

## Per-cell evidence

All ten cells have `final.json`; `latest.json` and `previous.json` are absent, and no `pinned/` directory or pinned checkpoint remains, consistent with finalized `rolling_latest_previous` retention.

| Topology | Seed | final / schema | Compact index / retained results | Canonical / insertion identity | Grid version / points | Rank pools | Traces: best / pop / archive | Result |
|---|---:|---:|---:|---|---|---:|---|---|
| P_D | 20261007 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 83 / 95767 / 95767 | PASS |
| P_D | 20261008 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 76 / 95767 / 95767 | PASS |
| P_D | 20261009 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 79 / 95767 / 95767 | PASS |
| P_D | 20261010 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 71 / 95767 / 95767 | PASS |
| P_D | 20261011 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 57 / 95767 / 95767 | PASS |
| D_P | 20261007 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 70 / 95767 / 95767 | PASS |
| D_P | 20261008 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 72 / 95767 / 95767 | PASS |
| D_P | 20261009 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 45 / 95767 / 95767 | PASS |
| D_P | 20261010 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 74 / 95767 / 95767 | PASS |
| D_P | 20261011 | yes / 4 | 96000 / 16 | True / True | 1 / 1001 | 8/8 | 48 / 95767 / 95767 | PASS |

## Per-cell optimizer counters

| Topology | Seed | Unique | Proposals | Raw offspring | Duplicates / cache hits | Generations | Boundary repairs |
|---|---:|---:|---:|---:|---:|---:|---:|
| P_D | 20261007 | 96000 | 100078 | 99844 | 4078 / 4078 | 95766 | 107732 |
| P_D | 20261008 | 96000 | 100622 | 100388 | 4622 / 4622 | 95766 | 115993 |
| P_D | 20261009 | 96000 | 100251 | 100017 | 4251 / 4251 | 95766 | 89093 |
| P_D | 20261010 | 96000 | 100340 | 100106 | 4340 / 4340 | 95766 | 116460 |
| P_D | 20261011 | 96000 | 100301 | 100067 | 4301 / 4301 | 95766 | 128070 |
| D_P | 20261007 | 96000 | 100444 | 100210 | 4444 / 4444 | 95766 | 100057 |
| D_P | 20261008 | 96000 | 100296 | 100062 | 4296 / 4296 | 95766 | 108332 |
| D_P | 20261009 | 96000 | 100357 | 100123 | 4357 / 4357 | 95766 | 124216 |
| D_P | 20261010 | 96000 | 100637 | 100403 | 4637 / 4637 | 95766 | 119293 |
| D_P | 20261011 | 96000 | 100351 | 100117 | 4351 / 4351 | 95766 | 126697 |

## Validation

- Synthetic focused regression tests: 18 passed.
- Full `uv run --locked pytest`: 493 passed, 1 skipped.
- Saved-data audit: 80/80 pools and 1280/1,280 finalist positions; PASS.

## Interpretation and limitations

The rolling `latest`/`previous` store has been finalized to one complete optimizer state per cell. The 80 `B*.json` files are checkpoint result/validation records, not 80 complete optimizer states. All checkpoint rank reconstructions use the terminal compact history index's zero-based insertion order and saved search-grid rank keys, with original stable `(rank_key, insertion_order)` ordering.

The trace, population, archive, SHADE memory, RNG and counter checks establish saved-state structural and cross-record consistency only. They do not replay 96,000 optimizer transitions or re-evaluate COM. Compact mode retains full result payloads only for the terminal top 16; rank keys for the other historical entries are checked for structure and used as saved evidence, not recomputed from physics. The terminal retained records, incumbent, active population, every finalist vector/rank position, and all unchanged grid/design-space versions were cross-checked against their saved records.

The original-source comparison found no changes to cache identity, comparator rank, or checkpoint selection semantics; intervening L-SHADE/comparator edits were trace telemetry only. PR #42 independently reported 80/80 finalist-record selection replay PASS. Its B-record finalist projection does not store `search_source_rank_key`, so rank-key fields cannot be compared directly. This audit sorts the complete final compact-index rank history and matches each saved ordinal source-rank and exact vector across all 1,280 finalist positions.

The scientific disposition remains `STAGE4C_TOPOLOGY_SELECTION_UNRESOLVED`; no topology selection or global-optimum claim follows from this audit.

Raw candidate vectors, checkpoint bodies, RNG internals, and local filesystem paths are intentionally excluded from this committed report.
