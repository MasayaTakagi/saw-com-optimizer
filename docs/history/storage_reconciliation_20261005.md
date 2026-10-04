# Historical Run and Log Storage Reconciliation — 2026-10-05

Applied the current [data storage, logging, and review policy](../guides/data_storage_logging_review_policy.md) after the policy merge at `3b272b6d49ef44b5e68cc92296fada68b37aab4b`.

## Storage outcome

- The repository retains source, protocol, compact canonical review evidence, and decision history. The external persistent root retains historical raw runs, qualification runs, checkpoints, full logs, and recovery data.
- The inventory found 29 historical raw-run directories and 21 qualification-run directories. All 50 have verified external snapshots. Forty-nine were copied during reconciliation; the existing Stage 4B archive was revalidated.
- After exact path, size, and SHA256 verification, 3,374 repository-local run files (23,920,898,180 bytes) were retired. Each file was rechecked immediately before removal. Stage 4B's 242 files (6,304,828,522 bytes) passed the existing full archive manifest; its separate authorization-claim source remains preserved.
- `stage3_7_material_com_50ohm_sanity` and `stage3_7_material_com_50ohm_sanity_final` were independently preserved and verified. Interpretation remains `STAGE3_7_EXECUTED_RESULTS_PRESERVED`; `COM_MAPPING_BLOCKED`.
- The untracked 915-file legacy `artifacts/review_bundles` tree (2,385,840,501 bytes) was archived, fully hashed, and retired. Seventeen individual legacy ZIP sources were copied and verified externally and remain in place. No Git-tracked legacy bundle was removed.

## Logs and review evidence

- Full logs remain with their external run snapshots. Of 47 artifact-side logs inventoried, 41 were matched to or attached to verified run snapshots. Six logs with unresolved ownership were copied to `<persistent-root>/archive/orphan-logs/20261005/`; their original files remain in place.
- The compact, Git-tracked package at `reports/experiment_reviews/qualification/20261004_084741_1ef70e/` remains intact (13 files, 13,056 bytes). Its referenced raw qualification run was not found at the recorded workspace path, in the repository, or in persistent storage. The missing raw run remains unresolved; no payload was fabricated.

## Retained items and evidence

- Five unknown run-like directories and 18 cache/temp directories remain. Known inaccessible residue under `.tmp-postrun-tests/` and `pytest-of-sub/` was left untouched; no cache cleanup or permission repair was performed.
- After retirement, the only five untracked worktree files larger than 10 MiB are binaries under `.venv/`; no classified raw or qualification source remains in the worktree.
- Raw numerical contents, historical manifests, and scientific conclusions were not changed. No production run, queue continuation, C2C operation, or Stage 4C launch occurred. The active-run registry was initialized with zero active records.
- Machine-local inventories and per-file hashes are under `<persistent-root>/manifests/historical-reconciliation-20261005/`. The run index is `<persistent-root>/manifests/historical_run_index_20261005.json`; the legacy bundle hash manifest is `<persistent-root>/archive/legacy-review-bundles/legacy_review_bundle_manifest_20261005.json`.
