# Issue #86 — Read-only static startup triage

**Date:** 2026-10-24 JST
**Pi version inspected:** 1.4.0
**Result:** Static inspection identifies a deterministic, configuration-consistent pre-RPC exit as the likely explanation for the prior status 1. The exact prior stderr was not retained, so the historical failure remains unclassified as an observed event. No Pi process was started for this triage.

## Scope

This phase followed the owner-authorized second-stage diagnostic scope: read-only inspection of the installed Pi launcher, CLI, session and RPC implementation, plus the prior sanitized Issue #86 report. It did not inspect existing sessions, credentials, personal configuration, tool/extension/MCP contents, provider requests, or scientific data. It did not modify Pi or project runtime code, and did not retry or reopen the previous process/session.

## Static findings

The prior report records that the trial used a fresh isolated profile, an empty environment, `--offline`, RPC mode, no model/provider selection, and no prompt. This combination has the following path in Pi 1.4.0:

1. Offline mode prevents catalog refresh from using the network. Pi's model runtime still has built-in catalog definitions, but initial non-interactive model selection is based on models in the *available* snapshot, not merely the catalog. The initial selection code checks a saved default only when present and authenticated, then checks available models; otherwise the model remains unset.
2. With a fresh profile, no saved default, and no provider credentials in the sanitized environment or test profile, the recorded launch inputs imply an empty available-model set and `session.model === undefined`.
3. RPC mode is non-interactive. In `main`, Pi checks for a missing model and exits with status 1 before calling `runRpcMode`. Consequently, the RPC request loop cannot emit correlated replies to `get_state` or `get_entries`.
4. This expected path matches the observed status 1 and absence of accepted RPC responses. Because the original stderr was intentionally not preserved and other earlier startup failures cannot be ruled out from the surviving evidence, this is a strong static explanation, **not proof of the exact historical exception/message**.

Relevant implementation points in the installed 1.4.0 distribution: `main`'s `resolveAppMode` and non-interactive no-model guard; `findInitialModel` in `core/model-resolver`; `ModelRuntime`'s distinction between all catalog models and authenticated available models; and the `get_state` RPC handler.

## Session-file interpretation

Pi 1.4.0's `SessionManager` creates the initial session state in memory but persists a JSONL file lazily, when a user or assistant conversation message is appended. A read-only RPC state/entries query does not itself create a session JSONL. Therefore, the previous test fixture's zero JSONL files are consistent with the absence of a prompt and are not, by themselves, evidence that session initialization failed. The `get_state` response includes `sessionId` and `sessionFile`, so a successful state reply could establish the in-memory test session identity without a persisted transcript. Reopening that identity as a persisted session would require separate evidence and authorization; it was not attempted.

## Disposition

- Retain `REAL_PI_OFFLINE_TEST_BLOCKED` for the previous trial: no successful correlated RPC response or accepted exact-session identity was observed.
- Do not upgrade the original outcome to a confirmed root-cause classification: stderr was not retained.
- No further Pi launch was made. The source path explains the observed status under the recorded launch inputs; changing the invocation to supply a model would be a distinct diagnostic configuration and is not needed to complete this static triage. Any further runtime work remains stopped unless separately authorized.
- Exact-session identity, branch context, RPC integration, prompt replay, and scientific FE restart remain unverified.

No runtime tests were run because this is a read-only static-triage record; no code or scientific behavior changed.
