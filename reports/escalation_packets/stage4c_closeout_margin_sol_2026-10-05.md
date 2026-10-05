# Stage 4C closeout and equivalence-margin judgment packet

## Scope

Bounded high-risk judgment before freezing Stage 4C closeout interpretation.
No optimizer, COM, model, bounds, specification, or production execution change
was requested from Sol.

## Question

Stage 4B left P_D versus D_P unresolved and did not report per-cell
last-significant-improvement fractions. The Stage 4C plan needs a predeclared
late-checkpoint winner rule and a practical-equivalence envelope. What can the
tracked Stage 4B evidence support, and what safeguards should govern the
Stage 4C interpretation?

## Evidence reviewed

- Stage 4B review package:
  `reports/stage4b_production_review/20261003_20261003_014817_ea08db/`.
- P_D/D_P median max violation was approximately 0.492/0.483 at 16k and
  0.381/0.388 at 24k. All five cells per topology materially improved from
  16k to 24k.
- The tracked package did not include fine best-so-far traces or a final
  significant-improvement fraction. The run manifest's historical raw path was
  not present on this host.
- Stage 4B's matched-seed ordering was unresolved; the run was not a
  convergence certificate.

## Judgment requested

The active Sol target is `gpt-6-sol`. Backend model identity and actual
reasoning effort are not independently exposed. Request judgment only, not
implementation or production authorization.

## Judgment received

The available Stage 4B record cannot justify a numerical paired-equivalence
margin or a mature-tail claim. Preserve the feasibility-first lexicographic
comparator. For late direction, require the same topology to win at least 4/5
matched seeds at each of 64k, 80k, and 96k; inspect reversals and material
80k→96k gain so changing seeds cannot create an apparent stable result.
Practical equivalence requires a numerical engineering margin declared before
outcomes, all five terminal pairs inside that margin, and mature tails. Without
a predeclared margin or adequate maturity, the outcome stays unresolved; a
3–2 split is not a winner. No numeric margin was recommended by Sol.

## Decision and implementation

Before production and independent review, Codex froze this explicit planning
assumption: max and sum normalized violation differences must each be within
both 0.02 absolute and 1% relative; worst in-band IL and ripple must each be
within 0.05 dB. All five terminal pairs must fit all margins and all cells
must be mature for `STAGE4C_PRACTICALLY_EQUIVALENT`. A clear winner requires at
least 4/5 matched wins at each of 64k, 80k, and 96k, the same at least four
seeds retaining that direction at every late checkpoint, mature cells, and
at least four winning pairs outside the equivalence envelope.

These numeric margins are a pre-run judgment, not an estimate or conclusion
from Stage 4B data. Stage 4C remains unresolved for 3–2, unstable late
direction, material 80k→96k improvement, incomplete evidence, or boundary
limitations. Maturity remains a post-run interpretation and does not stop the
optimizer.

## Verification and outcome

Stage 4C config and reporter encode the same comparator, margins, maturity
criteria, and late-checkpoint rule. Focused tests verify protocol drift fails
closed. No Stage 4C production was launched or authorized by this judgment.
