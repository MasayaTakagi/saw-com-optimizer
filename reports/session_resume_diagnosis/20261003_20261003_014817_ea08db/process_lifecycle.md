# Process lifecycle reconstruction

## Observed

- At 2026-10-03T01:48:27Z, orchestration status entered the production run. Final status records worker_pid=10948 and optimizer child optimizer_pid=34456.
- The optimizer ended COMPLETED, exit 0, at 2026-10-03T12:05:18Z. Its explicit completion record lists the twenty final checkpoint streams.
- Checkpoint lifecycle status is FINALIZED for 20/20 streams, with five writes per stream (100 total) and one retained final checkpoint per stream.
- At 12:10:03Z, status records callback start; at 12:34:05Z, callback completed with exit 0 and orchestration state REVIEWED.
- The dedicated Codex app thread has the callback user message and a completed agent turn from 12:10:04Z to 12:34:03Z.

## Ownership model from source at c44798266067fa4b8b7d3b2873a798b7a1600ae8

launch_detached() starts a worker with a detached Windows process group and returns immediately to the launcher. The worker runs the optimizer as a child, records its terminal state, finalizes checkpoints, then—while the worker is still executing—claims and runs the callback. The worker, not the original launcher terminal, owns the continuation action.

Therefore the parent launcher did not need to remain alive at optimizer completion. Its historical process lifetime is not recorded and is UNKNOWN. The detached orchestration worker did remain operational after optimizer completion, as shown by its subsequent callback start and completion. No external watcher is required by this implementation.

The callback was expected after the optimizer child exited, but before the orchestration worker exited. There is no evidence that continuation was supposed to occur after the worker itself terminated.

## Limits and discrepancy

The final status.json records worker_pid=10948 and optimizer_pid=34456; no durable worker-process exit record or worker exit code is present. The callback log's terminal flush warning says the thread was “not found”, but the app thread history and status subsequently available show a completed callback turn and exit 0. This discrepancy is preserved without inferring the worker's exact exit instant.
