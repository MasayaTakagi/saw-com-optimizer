# Post-run workflow queue contract — bounded Sol judgment

## Decision requested

Review the proposed orchestration boundary for moving new runs to exact-thread
queue delivery and GitHub evidence publication. This is a bounded architecture
and state-semantics judgment; no scientific model or optimizer behavior is in
scope.

## Risk

The detached worker, queue sender, same-thread receiver, and external review
publisher are separate actors. Confusing their states could cause duplicate
delivery, mark a result reviewed without external review, or rerun completed
science during callback recovery.

## Judgment received

- Keep the detached worker responsible for terminal optimizer evidence and one
  finite queue attempt, then let it exit.
- Persist the one-shot delivery claim before process spawn or queue I/O. Treat a
  malformed/uncertain existing ledger as consumed and ambiguous; never resend
  based only on status metadata.
- Treat queue exit code zero as sender acceptance only. Receiver confirmation
  must use trusted runtime `CODEX_THREAD_ID` and match the original thread,
  run, delivery ID, and sentinel. Do not accept a CLI-supplied receiver ID.
- Keep schema-v1/v2 legacy and schema-v3 historical queue readers. Schema v4
  is the new C2C-independent queue/disabled contract; do not silently upgrade
  old manifests.
- Completion, delivery, export, publication, and external scientific review
  remain distinct. Only pushed review evidence may transition a new run to
  `REVIEW_WAITING`; no automatic `REVIEWED` transition or follow-up run.
- Build and validate the bounded message before consuming the one-shot claim.

## Implementation boundary

Port queue mechanics selectively from the historical queue implementation;
retain legacy callback support only for old manifests. Add a generic
declarative exporter and keep the historical ZIP exporter unchanged.
