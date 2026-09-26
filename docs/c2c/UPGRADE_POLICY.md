# C2C upgrade policy

The reviewed baseline is repository `XiaoDuoYa/codex-with-chatgpt`, SHA
`9663b88753e35c76796c5bce000293e0bd22cd9e`, package `0.1.3`. Automatic
updates are prohibited. Detection is notification only; finding a candidate
does not authorize a checkout, dependency, Skill, or configuration change.

## Required approval flow

```text
candidate detected
        ↓
keep the current Reviewed SHA; do not update
        ↓
record current and candidate SHAs
        ↓
notify the user
        ↓
ChatGPT Security Review of current..candidate and dependencies/lockfile
        ↓
Security PASS
        ↓
explicit user approval for that candidate SHA
        ↓
update the external C2C checkout
        ↓
frozen install → build → typecheck → tests → Windows canary
        ↓
C2C doctor/workspace and control-loop validation
        ↓
independent review → new Reviewed Baseline
```

The Security Review must inspect the full current-to-candidate source diff,
dependency manifests and lockfile, Skill changes, and authentication, network,
or subprocess behavior. Do not promote a candidate until every validation
gate succeeds and the reviewed baseline is recorded.

## Prohibited actions

- Automatic update or updating merely because a candidate was detected
- Unattended `git pull`, `git stash`, or revision switching
- Dependency updates or installation before review and explicit approval
- Build, restart, or Skill overwrite before approval
- Unconditional replacement of the installed Skill from upstream
- Automatic switching of the Reviewed SHA

Keep the current reviewed version and continue the user's work when it remains
usable. If the approved update process succeeds, update
[`baseline.json`](baseline.json), [the security baseline](SECURITY_BASELINE.md),
and any affected operational details together. Until then, the SHA and package
above remain authoritative. The first actual `updateAvailable=true` candidate
must also verify the notification-only behavior that remains untested in the
Pilot Closeout.
