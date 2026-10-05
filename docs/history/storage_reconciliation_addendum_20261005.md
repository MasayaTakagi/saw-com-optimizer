# Historical storage reconciliation addendum — 2026-10-05

## Scope and result

After the initial reconciliation, five historical run directories had been
re-added under the repository's ignored `runs/` tree. Each already had a
matching snapshot in the external historical archive. All five source and
archive trees matched by relative path, regular-file size, and SHA-256; the
existing historical index digests also matched. The repository copies were
retired only after a new exact-file deletion manifest was durably written and
each file was rechecked immediately before deletion.

| Historical run | Files | Bytes | External snapshot |
| --- | ---: | ---: | --- |
| `stage3_7_material_com_50ohm_sanity_final` | 22 | 487,526 | `archive/historical/stage3_7_material_com_50ohm_sanity_final` |
| `stage3_7b_literature_com_reconstruction_final` | 11 | 13,338 | `archive/historical/stage3_7b_literature_com_reconstruction_final` |
| `stage3_7b_r1_normalized_literature_com_validation_final` | 18 | 396,728 | `archive/historical/stage3_7b_r1_normalized_literature_com_validation_final` |
| `stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen_final_retry3` | 58 | 66,872,386 | `archive/historical/stage3_7b_r2_stage3_7c_literature_com_b28_fast_screen_final_retry3` |
| `stage3_7d_mlit_aperture_boundary_and_metadata_final` | 15 | 312,322 | `archive/historical/stage3_7d_mlit_aperture_boundary_and_metadata_final` |

The five copies totaled 124 files and 68,082,300 bytes. No new external raw
snapshot was needed. After retirement, all five external snapshots were hashed
again and still matched the recorded inventories. The Stage 3.7 interpretation
remains `STAGE3_7_EXECUTED_RESULTS_PRESERVED`; `COM_MAPPING_BLOCKED`.

The five trees contained no full execution logs. Ten checkpoint-like JSON
files in the Stage 3.7b R2 snapshot remain with that external run. The six
previously archived orphan logs remain unresolved and untouched.

## Path dependencies and retained items

Tracked DMS reference inputs remain in `configs/reference/dms_topology_screening/`.
The study reads those tracked copies; the old `runs/` paths in the origin
metadata are provenance strings and are not opened by the current study. No
active run required the re-added repository paths.

The existing 50-entry external historical index remains intact; a new
machine-local index snapshot records this recheck. The prior reconciliation's
missing qualification payload, five unknown run-like directories, 18 cache or
temporary directories, and inaccessible `.tmp-postrun-tests/` and
`pytest-of-sub/` residue remain unresolved and unchanged. The 13 tracked
canonical review-evidence files and the previously archived legacy review
bundles were not changed.

Machine-local evidence is under
`<persistent-root>/manifests/historical-reconciliation-20261005/retry-20261004T234825Z/`.
The corresponding index snapshot is
`<persistent-root>/manifests/historical_run_index_20261005_rerun_20261004T234825Z.json`.
The original index and historical manifests were not overwritten.

No historical manifest or numerical result was modified, no scientific
conclusion changed, and no production run, queue continuation, C2C operation,
or Stage 4C launch occurred. The active-run registry remained initialized with
zero active records.
