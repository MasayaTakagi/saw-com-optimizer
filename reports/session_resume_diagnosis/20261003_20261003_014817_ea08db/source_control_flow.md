# Source and control flow used by this run

Execution source SHA: c44798266067fa4b8b7d3b2873a798b7a1600ae8 on codex/stage4b-hybrid-production-20261003.
Production config: configs/studies/hybrid_stage4b_topology_comparison.yaml.
Run protocol: stage4b_hybrid_topology_production_v1; manifest schema 2; computation fingerprint c63910623cb9a5d2a05ecb51f3685becf448f8ac91f169752f1b9703beef8464.

## Entry and worker

- src/sawopt/orchestration/cli.py, launch() lines 169–310: for Stage 4B, rejects --no-callback, requires the production authorization flag, resolves an explicit session target, runs callback preflight, stores the returned identifier as codex_session_id, sets callback_enabled and review_after_completion, writes the one-shot Stage 4B production authorization claim, creates the manifest and starts the detached worker.
- Orchestrator entry: python -m sawopt.orchestration.cli launch --config <CONFIG> --run-dir <RUN_DIR> --session-id <ID> --authorize-stage4b-production. The manifest records the optimizer child command as python -m sawopt run-study with the Stage 4B config and authorization manifest.\n- src/sawopt/orchestration/process_runner.py, build_worker_command() lines 13–29 builds python -m sawopt.orchestration.cli worker --run-dir <RUN_DIR>; launch_detached() lines 32–78 starts it detached on Windows, and the launcher does not wait for it.
- src/sawopt/orchestration/worker.py, execute_run() lines 61–147: after the optimizer and checkpoint finalization, gates callback on manifest.callback_enabled and manifest.review_after_completion; under a lock, prepare_callback(automatic=True) claims the attempt, then the worker calls run_codex_callback() and records its exit.

## Trigger, claim and completion state

- Trigger condition actually used: both callback booleans are true. It is not a queue trigger and is not keyed to a dedicated COMPLETED-only branch; the callback prompt receives the optimizer outcome.
- src/sawopt/orchestration/run_manager.py, prepare_callback() lines 252–284: callback_completed/REVIEWED and an existing automatic attempt suppress duplicates; first attempt increments callback_attempts and transitions to CALLBACK_RUNNING.
- finish_callback() lines 287–296: callback exit 0 records callback_completed=true and transitions to REVIEWED. That state proves process-level callback success under this implementation, not receipt by a different/original thread and not GitHub closeout.
- The Stage 4B production authorization claim in experiment_metadata is a distinct launch gate; it is not a queue/delivery claim.

## Identity selection and invocation

- cli.launch() lines 225–241 resolves the supplied explicit --session-id and preflights that identifier. Lines 262–282 serialize it as codex_session_id in the manifest. The manifest records codex_session_source=explicit and callback preflight PASS for 01a0ff60-991d-7dc3-bde4-cc3640853a0d.
- src/sawopt/orchestration/codex_callback.py, run_codex_callback() lines 368–389: reads manifest.codex_session_id and delegates to _run_codex_prompt().
- build_resume_command() lines 133–159 and _run_codex_prompt() lines 236–308 build an explicit codex exec --json -c sandbox_mode="workspace-write" resume <ID> <prompt> command, validate emitted session/thread identifiers against the requested ID, and return the process code.
- Prelaunch evidence says the ID was originally captured from the dedicated idle channel's thread.started.thread_id; the historical callback emitted that thread_id, and app history confirms the same dedicated thread completed the callback turn.

## Queue boundary

No Stage 4B queue-submit function was selected in this run. The manifest schema and source path use legacy callback fields; the recorded process command is codex exec resume. No codex queue --thread ... --message ... invocation, queue target, queue exit result, or queue-specific one-shot claim is evidenced. Current CLI help offers queue flags, but that is not evidence those flags were used or supported by the historical executable.
