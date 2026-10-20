# Pi Sol review routing (Stage 5A-2 and later)

**Status:** REVIEW ROUTING DOCUMENTED — `medium` route not yet requalified.  
**As of:** 2026-10-20.  
**Scope:** model selection and bounded high-risk design review. This is not a
Stage 5A-2 Q0 freeze, Q1 implementation approval, or COM/production authorization.

## Pinned review target

| Field | Value |
|---|---|
| Pi provider/model | `openai-codex/gpt-6.1-sol` |
| Thinking level | `medium` (exact Pi spelling) |
| Tool | `agent_spawn` from the installed Pi subagent extension |
| Parallelism | One Sol reviewer at a time |
| Fallback | Never silently change provider, model, or thinking level |
| Scope | Bounded judgment on escalation packet, not implementation |

Pin the explicit identifier above rather than an implicit `latest` alias.
Check Pi's model registry and consciously revise this document when upgrading
to a newer qualified model. The older `gpt-6-sol` is historical.

The installed extension's `agent_spawn` interface documents `prompt`,
`label`, `model`, `thinking`, `tools`, `resume`, `timeoutMs`, and
`persistent`. It does **not** accept `run_in_background`. Pi's
`agent_spawn` also does not accept the Codex-specific `fork_context`
parameter. Use actual tool schema at runtime; stop on mismatch.

References:
- Pi model catalogue: https://pi.dev/models/openai-codex/gpt-6-1-sol
- Pi extension tool contract: https://github.com/everyx/pi-extensions/blob/master/packages/pi-subagent/README.md
- Project gate: [Stage 5A-2 minimum comparison](../plans/stage5a2_minimum_fair_comparison.md)

## Reported connectivity evidence and limitation

On 2026-10-20, a Pi parent reportedly requested a child with
`openai-codex/gpt-6.1-sol`, label `sol-connectivity-test`, and
`thinking=high`. The child returned `SOL_SUBAGENT_OK`, and Pi reported
a saved session under `~/.pi/agent/subagent-sessions/*.jsonl`.

The displayed completion label was `openai/gpt-6.1-sol · high` even though
the requested provider was `openai-codex`. Therefore the run demonstrates
that a Sol 6.1-named child responded; it does **not** independently establish
which provider executed the request. It also does **not** validate
`thinking=medium`, which was not requested in that test.

Before claiming the standard route qualified, run one read-only test at the
new settings. Use `agent_spawn` with these **supported fields**:

```text
prompt: "Read-only routing check. Reply SOL_MEDIUM_OK only."
label: "sol-medium-routing-test"
model: "openai-codex/gpt-6.1-sol"
thinking: "medium"
tools: ["read"]
persistent: false
```

Do not add `run_in_background`. Do not run optimization, tests involving
COM physics, Git writes, or unrelated project work during this check.

After completion:
1. Record requested model and thinking; capture status and session location.
2. Inspect the saved child session's metadata and any provider/model/thinking
   fields actually exposed by the Pi runtime. Never publish OAuth tokens, raw
   session contents, or other credentials.
3. Reconcile the `openai` versus `openai-codex` completion-label difference.
   If the actual provider remains unverified, mark it `UNVERIFIED`, not
   `openai-codex verified`. If there is a real route mismatch, fail closed.
4. Verify whether `medium` was actually selected in available metadata.
   If the runtime does not expose effective effort, log requested `medium`
   separately from unverified effective effort.
5. Commit only a redacted summary (and references as appropriate) to the
   review packet / `reports/escalation_log.md`. Keep raw session files local.

Do not infer model, provider, or effort from `SOL_MEDIUM_OK` alone.

## Real Stage 5A-2 Q0 Sol review

Once the routing gate has passed, supply the self-contained, current Q0
escalation packet and ask Sol to judge the DE comparison protocol, initialization
and lexicographic selection contracts, exact unique-evaluation accounting,
checkpoint/history semantics, and qualification/authorization gates. Restrict
child tools as appropriate for read-only review.

Record a distinct Sol decision in `reports/escalation_log.md`; do not count
the routing connectivity check as a Q0 design review. The Pi child must not
implement or approve production experiments. Q1 stays blocked until the Q0
review and normal project acceptance gates have been satisfied.
