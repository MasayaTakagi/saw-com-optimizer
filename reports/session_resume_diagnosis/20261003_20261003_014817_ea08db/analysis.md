# Observed

- A read-only scan found 22 orchestration run_manifest.json files. The newest by created_at is run 20261003_014817_ea08db; the next distinct run ID is the older queue_live_qualification_20260930_003701 record (REVIEW_WAITING, not a completed optimizer production run). No later completed production candidate appears in the recorded run tree.
- Run 20261003_014817_ea08db is Stage 4B hybrid topology production comparison. Source commit c44798266067fa4b8b7d3b2873a798b7a1600ae8; computation fingerprint c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464.
- run_completion.json records COMPLETED at 2026-10-03T12:05:18Z; status.json records optimizer exit 0 and final orchestration state REVIEWED.
- Integrity summary: PASS; 20 expected/present/completed cells, all 24,000 unique evaluations, all expected checkpoints, topologies, seeds, cold starts, one common-grid ID and one fingerprint; zero listed issues.
- The orchestration manifest says callback_enabled=true, review_after_completion=true, and callback preflight PASS. It stores codex_session_id=01a0ff60-991d-7dc3-bde4-cc3640853a0d.
- status.json records one callback attempt, callback completed, callback exit 0, callback started 12:10:03Z, finished 12:34:05Z. callback.log records an explicit codex exec resume to that ID and target validation matched.
- Codex app thread history confirms the dedicated thread 01a0ff60-991d-7dc3-bde4-cc3640853a0d received a callback user message for this run and completed its turn (12:10:04Z–12:34:03Z).
- The original task thread 01a0fcca-3d9f-7a23-8622-1afe71e79c02 has no callback user message/turn for this run in the complete 9-turn history returned by the read-only thread-history tool.
- The primary forensic window is completion ±15 minutes: 11:50:18Z–12:20:18Z. It was expanded only to 12:34:05Z to include the callback that started inside the original window and its recorded completion.
- No codex queue command is recorded in the run manifest, status, stdout/stderr, callback log, or associated dedicated-thread rollout. The actual invocation path is legacy exec resume; no queue claim/attempt appears.
- The dedicated callback agent final response says GitHub closeout did not commit/push its review bundle or update PR #16: the connector write required approval but policy was “never”, and browser fallback was unavailable. This is a downstream closeout block, not evidence that the callback did not run.
- callback.log contains a terminal rollout-flush warning at 12:34:04.028983Z (“thread … not found”). This conflicts with durable app history showing the dedicated thread's completed callback turn and with orchestration callback exit 0. It is retained as a discrepancy, not treated as proof of non-delivery.

# Trigger stage

continuation armed: YES — callback_enabled=true and review_after_completion=true in the manifest.

completion eligible: YES — optimizer ended COMPLETED, exit 0.

trigger reached: YES — the worker recorded one CALLBACK_RUNNING attempt, and callback start/finish timestamps exist.

callback owner alive: YES for the detached orchestration worker through callback dispatch; it continued after the optimizer child completed. The external launcher process's historical lifetime is UNKNOWN and it is not the callback owner in the source design.

# Queue stage

queue attempted: NO — no queue command or queue-process output is present; the run selected legacy codex exec resume.

target: no queued target. The legacy callback target was dedicated thread 01a0ff60-991d-7dc3-bde4-cc3640853a0d.

result: legacy callback exit 0, target validation matched, dedicated-thread turn completed. A queue result/exit code is not applicable because no queue process was launched.

# Receiver stage

- Dedicated callback thread: RECEIVER_CONFIRMED by its app history user message and completed callback turn.
- Original task thread: RECEIVER_NOT_CONFIRMED; no callback turn for this run appears in its available history.
- This is not a codex queue-accepted-but-unobserved case.

# Identity audit

The expected same-task thread in this forensic context is 01a0fcca-3d9f-7a23-8622-1afe71e79c02. The callback thread actually selected and received was 01a0ff60-991d-7dc3-bde4-cc3640853a0d; equality is false. There was no queue target. Prelaunch evidence shows the selected ID was originally reported as thread.started.thread_id, then stored under codex_session_id and passed via --session-id / exec resume. This is thread/session field/API conflation; runtime and app history identify the actual resumed target as the dedicated thread.

# Primary classification

OTHER_EXACTLY_IDENTIFIED_FAILURE:LEGACY_CALLBACK_TARGETED_DEDICATED_THREAD_NOT_ORIGINAL_TASK

The run did not fail to trigger continuation. The legacy callback fired once and succeeded against the configured dedicated callback thread. The original task thread did not receive it. The queue-to-original-thread contract described by the present forensic task was not the mode used by this run.

# Contributing factors

- The immediately preceding launch instruction explicitly required a fresh dedicated callback thread and prohibited reusing the active implementation thread. The dedicated target was therefore intentional under the launch instruction; it differs from the same-original-thread contract stated by the present forensic task.
- The production manifest faithfully stores that dedicated ID as codex_session_id. The selected source path uses legacy session resume and has no queue submission.
- REVIEWED means the callback process returned 0, not that the original task thread or a PR was updated.
- The callback log has a flush warning after its terminal turn event, while app history and status record a completed turn. This discrepancy warrants separate review but does not change the identity finding.
- C2C persistent bridge logs found locally are dated before the forensic window and contain no run or thread IDs. No C2C event is evidenced at completion; runtime availability is unknown.

# Interpretation

The continuation trigger was reached and a legacy callback completed. Relative to the current forensic task's same-original-thread expectation, the boundary mismatch is receiver identity: the callback went to the deliberately separate dedicated channel. The callback's later GitHub closeout was blocked by approval policy. No evidence supports claiming a queue was accepted or lost.

# Not proven

- Whether the original launcher shell/process remained alive at optimizer completion; the detached design does not require it, and no historical process table is preserved.
- Whether C2C/bridge runtime was alive at completion; available bridge logs predate the window.
- Whether the Codex executable installed at completion supported codex queue --thread/--message; current help supports both, but historical queue help was not captured.
- Whether any external UI event occurred beyond durable app thread history.
- Whether the terminal flush warning reflects a transient telemetry/rollout persistence race; that is unresolved.

# Recommended next action

Have ChatGPT review this evidence branch. If future continuation is needed, separately decide and qualify a queue-based path using the intended exact thread identity and a durable one-shot queue claim. Do not replay or alter this completed run as part of this diagnosis.
