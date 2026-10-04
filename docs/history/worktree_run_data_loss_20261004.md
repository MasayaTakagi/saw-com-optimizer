# Worktree run-data loss incident — 2026-10-04

During the 2026-10-04 remote branch cleanup, ignored qualification run data was
present inside a disposable linked Git worktree. A clean `git status --short`
did not reveal that non-Git data. `git worktree remove` deleted the ignored
run directories while removing the checkout. Windows long-path cleanup then
left a partial directory whose Git worktree registration had already been
removed.

The affected data consisted of two zero-scientific-evaluation workflow
qualifications, not Stage 4B production science:

- Failed queue qualification `20261004_041346_4110e2` under
  `runs/postrun_workflow_qualification_20261004_041228/`.
- Successful queue qualification `20261004_084741_1ef70e` under
  `runs/postrun_workflow_qualification_20261004_queue_diag_requal_01/`.

Both raw qualification directories are confirmed lost. They were not
reconstructed or rerun. The successful qualification's canonical GitHub review
evidence remains committed and the accepted classification remains
`POSTRUN_QUEUE_GITHUB_REVIEW_E2E_QUALIFIED`. The failed qualification's
high-level diagnosis remains in PR #17 and repository history. This incident
does not invalidate the successful qualification.

The partial residual directory
`C:\Users\sub\.codex\visualizations\2026\10\02\01a0fcca-3d9f-7a23-8622-1afe71e79c02\w`
was left untouched. A read-only inventory enumerated 728 files totaling
4,915,243 bytes, but 75 paths under
`runs\_postrun_workflow_validation_scratch\.tmp-tests\tmp*` were inaccessible
(`Access is denied`); the inventory is incomplete. Neither lost run name
appeared in enumerable paths, which does not establish that they are absent
from inaccessible paths. Classification: `RESIDUAL_DIRECTORY_INVENTORY_INCOMPLETE`.

Stage 4B raw production data was not reported lost. It was copied, not moved,
to the machine-local persistent run root and independently verified against
the source by relative path, size, and SHA256 for every regular file. The
verified archive contains 242 files totaling 6,304,828,522 bytes. Its external
manifest is stored at
`C:\Users\sub\Documents\ChatGPT\saw-com-optimizer-runs\manifests\stage4b_raw_archive_20261004.json`.
The referenced one-shot authorization claim was copied to archive provenance
with its SHA256; the original claim remains in place.

Future production raw runs, checkpoints, populations, run-local continuation
ledgers, raw recovery logs, and scientific artifacts must be owned by storage
outside every Git worktree. Review evidence remains a small, tracked package in
the repository. Git worktree removability must be determined by the supported
safety audit, which inventories tracked, untracked, ignored, and filesystem
data; `git status --short` alone is not a deletion gate.
