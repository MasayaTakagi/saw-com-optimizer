# Pi Sol review routing (Stage 5A-2 and later)

**Status:** Pi Sol routing QUALIFIED (recorded provider/model/medium and normal child completion); Stage 5A-2 Q0 design review NOT STARTED.
**As of:** 2026-10-20.
**Scope:** model selection and bounded high-risk design review. No Q0 freeze, Q1 implementation approval, or COM/production authorization.

## Pinned Pi review target

| Field | Value |
|---|---|
| Pi provider/model | `openai/gpt-6.1-sol` |
| Thinking level | `medium` (exact Pi spelling) |
| Credential expected | `openai: oauth` (ChatGPT subscription sign-in) |
| Tool | Pi extension `agent_spawn` |
| Parallelism | One Sol reviewer at a time |
| Fallback | Verify actual child provider/model/effort; fail closed on mismatch |
| Scope | Bounded judgment only; no implementation |

Do not use an implicit `latest` alias. Revise the pinned model deliberately when a newer version has been qualified. `gpt-6-sol` is historical.

**Provider correction:** In current Pi, `openai` supports both OpenAI API keys and ChatGPT-subscription OAuth; `openai-codex` is labeled **OpenAI Codex (legacy)**. PR #45 had incorrectly pinned the legacy provider. The user confirmed only `openai` appears in Pi `/model`; a local metadata-only check returned `openai: oauth` from `~/.pi/agent/auth.json`. This establishes **stored** OAuth mode, not proof of the effective credential used by a particular request. Explicit command-line `--api-key` can override saved credentials; do not infer billing solely from the provider ID or this stored file.

Upstream references:
- Current Pi `openai` provider source: https://github.com/earendil-works/pi/blob/main/packages/ai/src/providers/openai.ts
- Legacy `openai-codex` provider source: https://github.com/earendil-works/pi/blob/main/packages/ai/src/providers/openai-codex.ts
- Pi model authentication and selection: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md
- Pi subagent extension resolver: https://github.com/everyx/pi-extensions/blob/master/packages/pi-subagent/model.ts
- Pi subagent supported parameters: https://github.com/everyx/pi-extensions/blob/master/packages/pi-subagent/README.md
- Project gate: [Stage 5A-2 comparison](../plans/stage5a2_minimum_fair_comparison.md)

## Observed read-only connectivity history

1. The 2026-10-20 `high`-effort request for `openai-codex/gpt-6.1-sol` completed with `SOL_SUBAGENT_OK`, but its display showed `openai/gpt-6.1-sol`. The requested and effective provider did not match.
2. A subsequent `medium` request still specified `openai-codex/gpt-6.1-sol`; the saved child events contained `provider=openai`, `api=openai-responses`, `model=gpt-6.1-sol`, and `thinkingLevel=medium`. The child returned `SOL_MEDIUM_OK` without a reported tool error; its JSONL session could be read. Thus model/version, **recorded** medium effort and execution/persistence passed, but the **requested** provider did not.
3. Inspection of the subagent extension `resolveModel()` explains the mismatch: it prefers a provider match and then performs loose model-only lookup across providers. Its documented `no fallback` claim must not be treated as an exact-provider guarantee. There is no need to modify the extension merely to use the now-correct `openai` provider, provided the resolved child identity is checked.
4. The user checked `~/.pi/agent/auth.json` without printing secrets: `openai: oauth`. Under standard Pi credential resolution this is consistent with ChatGPT sign-in, but the stored type does not independently prove the credential chosen for any given request.

Because prior child calls requested `openai-codex`, **do not treat them as a completed exact-request qualification for the corrected `openai` route**. The child record nevertheless verifies that `openai/gpt-6.1-sol` executes with recorded `medium` under the installed environment.

## Completed exact-request qualification (read-only)

From the existing Pi Web session, start **one** child with these supported `agent_spawn` fields:

```text
prompt: "Read-only routing check. Reply SOL_MEDIUM_OK only. Do not modify files."
label: "sol-openai-oauth-medium-check"
model: "openai/gpt-6.1-sol"
thinking: "medium"
tools: ["read"]
persistent: false
```

**Qualification evidence (user-reported Pi session, 2026-10-20):**

| Field | Requested / recorded result |
|---|---|
| Requested target | `openai/gpt-6.1-sol` |
| Recorded provider and API | `openai`, `openai-responses` |
| Recorded model | `gpt-6.1-sol` |
| Recorded thinking level | `medium` |
| Child response | `SOL_MEDIUM_OK`, completed, no recorded errors |
| Session evidence | Local JSONL under `~/.pi/agent/subagent-sessions/`, readable in read-only inspection |
| Stored credential type | `openai: oauth` |
| Credential overrides | No `OPENAI_API_KEY` detected; no runtime override reported |
| Route decision | **PASS** for exact provider/model and recorded `medium` |

The JSONL and local credential settings were inspected by the user's Pi session;
they were not independently accessed from this GitHub-only review. Session
files and credentials remain local. Absence of detected overrides plus stored
OAuth is consistent with subscription sign-in but not cryptographic proof of
the effective token or billing path. Recorded `medium` does not prove
internal inference effort.

**Do not re-run the qualification as a prerequisite solely because this
document's earlier version instructed it.** Requalify only after a relevant
Pi version, extension, authentication, or model-route change. The separate
Stage 5A-2 Q0 design judgment remains pending.

`agent_spawn` does not accept `run_in_background` or the Codex-only `fork_context`. Consult the live extension schema before issuing tool arguments; do not set unsupported fields.

After completion, record:

1. Requested provider, model, thinking level and actual child session path.
2. Actual provider `openai`, API `openai-responses`, model `gpt-6.1-sol`, recorded `thinkingLevel=medium`, normal completion and expected reply.
3. Whether any explicit `--api-key`/runtime override was present in the launching workflow **without printing keys**, and that `auth.json` stores `openai: oauth`. If effective credential provenance cannot be proven, mark **EFFECTIVE_CREDENTIAL_UNVERIFIED**, not API-billing or OAuth definitively.
4. Redacted proof only, with no OAuth token, API key, or full raw session in Git.

Require the **requested and recorded provider/model** to match. Treat recorded `medium` as an observable runtime setting, not proof of internal reasoning depth. If any required field mismatches, stop and investigate; do not silently reroute.

## Stage 5A-2 Q0 review remains separate

After this route check, use a **new** Sol child with the exact pinned target and send the self-contained Stage 5A-2 Q0 escalation packet. Ask for a bounded judgment on DE comparison/initialization, lexicographic comparator, exact unique-evaluation budgets and history/checkpoint semantics, qualification requirements and user authorization gates. The reviewer must not implement anything.

Record the separate Sol decision and evidence in `reports/escalation_log.md`. A connection test is **not** a Q0 design review. Q1 implementation and any COM or production experiment remain prohibited until the actual project gates authorize them.
