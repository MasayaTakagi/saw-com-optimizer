# Historical Decision Recovery Audit — 2026-09-25

## Purpose

This audit was created after local historical run directories were partially
deleted. Its purpose is to separate what can still be recovered from Git from
what had to be reconstructed from prior project conversations and uploaded
review material.

No missing metric is guessed. If an exact value or closeout artifact could not
be found, the record remains UNRECOVERED.

## Source classes

- **GIT_RECOVERABLE** — tracked file/config/commit/tag exists in repository
  history, especially `archive/pre-historical-deletion-2026-09-25`.
- **CHAT_OR_ATTACHMENT_RECOVERED** — exact review statements were recovered
  from prior ChatGPT project conversations or indexed uploaded project files.
- **UNRECOVERED** — searched but exact evidence was not available.
- **LOCAL_ARTIFACT_UNVERIFIED** — a historical run/review path is known, but
  Git cannot prove that the current local file still exists because `runs/`
  and most of `artifacts/` are ignored.

## Recovery summary

| Area | Recovery status | Important recovered content |
|---|---|---|
| Prototype | GIT_RECOVERABLE | 45 Ω provisional best under hypothetical COM; all points fail |
| 50 Ω hybrid | GIT_RECOVERABLE | DMS→ladder improvement; P_D_P remains infeasible |
| Stage 2 | GIT_RECOVERABLE | 20/50/100 Ω pilot, joint topology/wiring and adaptive-grid design decisions |
| Stage 3.1 | CHAT_OR_ATTACHMENT_RECOVERED | 4k center_outer_same local plateau but active IDT lower-bound pressure; outer_ports still dispersed |
| Stage 3.2 | GIT + CHAT_RECOVERED | bounded zero-progress retry semantics; 8k→16k still underoptimized; 15→10 probe improved 4/5 seeds |
| Stage 3.3 | CHAT_OR_ATTACHMENT_RECOVERED | first A/B invalid from L-SHADE budget shortfall; corrected 4k A/B modestly favored Legacy-DE |
| Stage 3.3.1 | GIT_RECOVERABLE | 98% budget gate, source freeze, human-review gate, auto-bound off for A/B isolation |
| Stage 3.4 | GIT + CHAT_RECOVERED | boundary-recovery rationale and 20→15→10 IDT lower-bound progression |
| Stage 3.4b | CHAT_RECOVERED + GIT_CONFIG | eight-seed 256k convergence evidence; more budget judged unnecessary for that question |
| Stage 3.5 | GIT + ESCALATION_LOG | protocol mismatch explains apparent Legacy-DE/L-SHADE preference change; Phase D intentionally not run |
| Stage 3.6 Gate 1 | UNRECOVERED | exact numeric Gate 1 closeout not found; do not infer from Gate 2A |
| Stage 3.6 Gate 2A/B/C | GIT + CHAT/ATTACHMENT | G1+G2 reference, asymmetric-port screens, Gate 2C added aperture signal but no feasible design |
| Stage 3.7B/R1 | GIT + ESCALATION_LOG | normalized literature mapping, 3.13% feature-scale uncertainty, no production qualification |
| Stage 3.7C | CHAT_RECOVERED + GIT_CONFIG | MLIT fixed-M0 geometry performs very poorly; 8k re-optimization recovers strongly but remains unconverged |
| Stage 3.7D | CHAT_RECOVERED + GIT_CONFIG | 150 µm upper bound active-moderate; adopt MLIT 30–180 µm; 200 µm rejected |
| Stage 3.8/R1/R1.1/R1.2/3.8C | GIT + ESCALATION_LOG | comparator/initializer lineage and canonical 96k production conclusions |
| Async/Codex resume | CHAT_OR_ATTACHMENT_RECOVERED | local optimizer resume works; autonomous Codex session resume frozen/deferred |

## Important correction — Stage 3.7D aperture lineage

The prior active history documents stated that Stage 3.7D found the 150 µm
upper bound inactive and recommended 30–150 µm, with 30–180 µm introduced only
later as a user override.

The earlier Stage 3.7D review recovered on 2026-09-25 says instead:

- label: `APERTURE_BOUND_ACTIVE_MODERATE`;
- seed 20260917 max violation at 150/165/180/200 µm:
  1.0454 / 0.9019 / 0.8320 / 0.8837;
- seed 20260918:
  1.1170 / 1.0891 / 1.1201 / 1.1790;
- seed 20260917 best probe: 180 µm;
- seed 20260918 best probe: 165 µm;
- 200 µm worsened the relevant trend for both seeds;
- adopted next-stage range: MLIT 30–180 µm;
- M0 remained 30–150 µm;
- closeout label: `STAGE3_8_READY_APERTURE_EXPANDED`.

The pre-deletion Stage 3.7D config independently confirms the exact probe
points `[150,165,180,200]`, two seeds, no optimizer rerun, and source
checkpoint budget 8000.

Because later Stage 3.8-era documents contain conflicting wording, this audit
records the recovered Stage 3.7D closeout as the earlier experiment decision
and marks the later wording as a historical documentation inconsistency.

## Stage 3.6 Gate 1 limitation

A targeted search of:

- current Git history,
- the pre-historical-deletion tag,
- tracked Stage 3.6 configs/handoffs,
- indexed project attachments,
- prior project conversation retrieval

did not recover a sufficiently supported Gate 1 numerical closeout.

The exact Gate 1 comparison values must therefore remain UNRECOVERED.
The later Gate 2A results must not be back-projected into Gate 1.

## Artifact availability rule

Historical references such as:

- `runs/stage3_6_...`
- `runs/stage3_7_...`
- `runs/stage3_8c_production_20260924`
- `artifacts/review_bundles/*.zip`

are provenance locations, not existence assertions.

Git ignores these paths. After local cleanup, their current state must be
checked independently before relying on them as raw evidence.

## Closeout rule for future stages

Before removing or externally archiving any future run:

1. write Result → Decision → Limitations → Carry-forward into
   `experiment_register.md`;
2. update `current_baseline.md` only when the adopted current state changes;
3. record the canonical run/review-bundle paths and hashes where available;
4. verify artifact existence before saying it is retained;
5. then prune Stage-specific code/config/tests if no longer active.
