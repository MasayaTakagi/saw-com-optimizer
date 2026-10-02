# C2C MCP One-Shot Live Diagnosis — 2026-10-01

## Outcome

Classification: `C2C_ENDPOINT_TRACKING_INCONSISTENT`.

The controlled `workspace_info` call was **not issued**. The diagnostic deployment changed the Quick Tunnel endpoint fingerprint, while Doctor reported `chatgptRepair.needed=false`. The task's explicit stop condition therefore applied; no connector recreation was attempted and no data-plane conclusion was drawn.

## Baseline

- SAW repository: `codex/production-queue-continuation`, HEAD `e00e47a23076793cdd093edaf5f7c060365edcf9`.
- Pre-existing SAW changes were preserved: `AGENTS.md`, `docs/c2c/OPERATIONS.md`, `docs/c2c/SECURITY_BASELINE.md`, `reports/escalation_log.md`, and `reports/escalation_packets/stage4b_duplicate_gate_process_inventory_2026-09-30.md`.
- Canonical C2C: version `0.1.3`, commit `9663b88753e35c76796c5bce000293e0bd22cd9e`, clean.
- Diagnostic C2C: commit `b9aafd89072d037c32563c45b8de0d7f36b8f425`, clean.
- Ordinary state preflight: `ACTIVE_SANDBOX_DENIED`. Targeted preflight: `PASS` as `desktop-9ipace7\sub`, with `USERPROFILE` and Windows `UserProfile` both `C:\Users\sub`.
- Canonical baseline bridge PID `41816`; Quick Tunnel fingerprint `8901362d54872159`; Doctor bridge/MCP/OAuth/tunnel checks passed; `chatgptRepair.needed=false`; connector metadata named `Codex with ChatGPT · saw-com-optimizer`.
- Existing C2C session was in Project mode with a blocked checkpoint. No session, record, or checkpoint mutation was made.

## Diagnostic deployment and stop

- Canonical bridge PID `41816` and its Quick Tunnel child PID `19720` were stopped through the canonical CLI. The old port had no listener afterward, and no matching workspace runtime remained.
- The diagnostic bridge ran from the reviewed diagnostic checkout for workspace `saw-com-optimizer`, PID `40816`, under `desktop-9ipace7\sub`.
- `C2C_MCP_TRACE=1` and `C2C_LOG_LEVEL=info` were set only in the launch process. The diagnostic source confirms trace activation reads `C2C_MCP_TRACE` and trace events use `logger.info`. An INFO-level bridge startup line was observed.
- Diagnostic Quick Tunnel fingerprint: `af506f34757d5935`, different from the canonical baseline.
- Diagnostic Doctor reported bridge/MCP/OAuth/tunnel healthy but `chatgptRepair.needed=false` and `connectorAction=none`.
- The reviewed CLI's `start` path persists the new endpoint before Doctor reads the endpoint record. Thus Doctor's false repair indication did not satisfy the runbook's changed-endpoint gate; the run stopped before creating the trace cursor or sending `workspace_info`.
- Diagnostic bridge PID `40816`, tunnel child PID `7332`, port listener, workspace runtime, and matching serve process were all absent after stop.
- `C2C_MCP_TRACE` and `C2C_LOG_LEVEL` were absent from User and Machine environment settings after stop.

## Restoration

- Canonical C2C was restarted from clean commit `9663b88753e35c76796c5bce000293e0bd22cd9e`, bridge PID `15720`.
- Canonical Quick Tunnel fingerprint: `1b294fd1968a82ab`.
- Final Doctor: node, sandbox, workspace, bridge, MCP, OAuth, and tunnel all passed; `chatgptRepair.needed=false`; connector metadata retained the intended name.
- No connector was created, deleted, or edited by this run. No duplicate or unrelated connector change was introduced. The actual ChatGPT connector inventory/endpoint was not independently inspected because the stop condition prohibited guessing or forcing repair.
- Canonical and diagnostic source checkouts remained at their reviewed clean commits. No C2C qualification or additional `workspace_info` attempt was performed.

## Trace and interpretation

- Controlled request ID: none; request was not sent.
- MCP request/auth/handler/tool events: not collected because the controlled call did not occur.
- ChatGPT-visible result, `workspaceName`, and `rootAlias`: not applicable.
- Secrets or request/response bodies recorded: none.

Observed facts are the endpoint fingerprint change and Doctor's `chatgptRepair.needed=false` result. The interpretation is only that endpoint tracking was inconsistent for this deployment path; this run does not establish whether ChatGPT would reach the bridge or what caused the earlier tool failure.

## Qualification status

- Quick Tunnel 3-cycle: not run.
- C2C state/session/record, detached child, queue E2E: not run.
- Stage 4B/4C: not launched.

Recommended next action: resolve the endpoint-tracking decision gate in a separate bounded plan before repeating the one-shot request. Do not infer a data-plane cause from this run.
