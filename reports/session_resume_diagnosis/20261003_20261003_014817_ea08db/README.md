# Session-resume non-fire forensics

Purpose: preserve a compact, reviewable reconstruction of the completed production run and its continuation path. No continuation was replayed and no run data was modified.

- Run: 20261003_014817_ea08db — Stage 4B hybrid topology production comparison.
- Completion: optimizer COMPLETED, exit 0, 20/20 cells at 24,000 unique evaluations; explicit completion time 2026-10-03T12:05:18Z (2026-10-03T21:05:18+09:00). Orchestration later ended REVIEWED after one callback, exit 0.
- Expected by the forensic task: continuation to original task thread 01a0fcca-3d9f-7a23-8622-1afe71e79c02.
- Observed: no codex queue submission. The actual run used one legacy codex exec resume targeting dedicated callback thread 01a0ff60-991d-7dc3-bde4-cc3640853a0d; app history confirms that thread received and completed the callback turn. The original task thread has no callback turn in its available history.
- The callback agent did run, but its GitHub closeout was blocked by an approval-policy rejection; PR #16 was not updated.
- Primary classification: OTHER_EXACTLY_IDENTIFIED_FAILURE:LEGACY_CALLBACK_TARGETED_DEDICATED_THREAD_NOT_ORIGINAL_TASK.
- Production source: branch codex/stage4b-hybrid-production-20261003, commit c44798266067fa4b8b7d3b2873a798b7a1600ae8.
- Computation fingerprint: c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464.

## Evidence files

- analysis.md
- timeline.csv
- run_identity.json
- continuation_state.json
- queue_evidence.json
- identity_audit.json
- process_lifecycle.md
- source_control_flow.md
- log_excerpts.txt
- artifact_inventory.csv
- environment_context.txt
- redaction_report.md

The inventory records hashes and metadata for local run files, checkpoints, relevant source, Codex rollout, and C2C logs. Full checkpoints, dense results, raw logs, app rollout, credentials, and unbounded callback prompt text were deliberately excluded. No PR was created.
