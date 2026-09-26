# C2C project integration

## Purpose and dependency model

C2C (`codex-with-chatgpt`) supports `saw-com-optimizer` development as a
planning and review control plane:

- ChatGPT plans and independently reviews work.
- Codex executes the approved plan, runs appropriate validation, and owns the
  workspace changes.

C2C is a first-class development dependency. Its source remains in an external
sibling repository; it is not vendored or added as a submodule, Python package,
or runtime dependency of `saw-com-optimizer`. The SAW package, tests, optimizer,
experiment tools, production runner, and analysis scripts remain independently
usable without C2C.

The expected local layout is two sibling repositories under a common parent:

```text
<ChatGPT workspace parent>/
├── saw-com-optimizer/
└── codex-with-chatgpt/
```

## Project sources of truth

When reconciling project and task context, use this priority order:

1. Current `saw-com-optimizer` code
2. Current task C2C/HANDOFF state
3. Project instructions and `AGENTS.md`
4. C2C operational documentation
5. Historical Pilot/Closeout records

This is the project-level trust order. The C2C documents below have separate
responsibilities; their roles do not create a competing project-level order:

- [`baseline.json`](baseline.json) stores exact machine-readable approved
  baseline values.
- [`SECURITY_BASELINE.md`](SECURITY_BASELINE.md) explains the security
  invariants and their limits.
- [`OPERATIONS.md`](OPERATIONS.md) defines normal operation and recovery.
- [`UPGRADE_POLICY.md`](UPGRADE_POLICY.md) defines candidate review and
  upgrade approval.
- [The Pilot Closeout report](../../reports/c2c_secure_pilot_validation_20260925.md)
  is the validation evidence. Older [pilot notes](../../handoff/c2c_pilot_validation.md)
  and handoff instructions remain historical records.

## Entry points

- [Security baseline](SECURITY_BASELINE.md)
- [Operations](OPERATIONS.md)
- [Upgrade policy](UPGRADE_POLICY.md)
- [Machine-readable baseline](baseline.json)
