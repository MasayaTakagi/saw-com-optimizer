# Stage 3.8C-R1.1 pilot summary

- Gate status: **PASS**
- Cells passing the gate: 6/6
- Run directory: `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer\runs\stage3_8c_r1_1_pilot_20260924`
- Source fingerprint: `0837b06387ed1c60d3da9b8f4d7b732ee5bf078c36f0b928fd91aacd1fca0cd6`
- Common validation grid: `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`
- Performance interpretation: diagnostic only; one seed is not a topology ranking.

| Material | Topology | Status | Unique | Physics valid | Solved points | R1 initial rejection | R1.1 conditional rejection | Uniform reference rejection | Optimizer rejection |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 | T0_CURRENT_3IDT | VALID_RUN | 256 | 250 | 396058 | 87.96% | 0.00% | 87.17% | 2.34% |
| M0 | T1_SYMMETRIC_5IDT | VALID_RUN | 256 | 256 | 402064 | 4.28% | 0.00% | 4.32% | 0.00% |
| M0 | T2_PARALLEL_3IDT_X2 | VALID_RUN | 256 | 252 | 398060 | 93.28% | 0.00% | 92.69% | 1.56% |
| MLIT | T0_CURRENT_3IDT | VALID_RUN | 256 | 250 | 396058 | 86.10% | 0.00% | 88.16% | 2.34% |
| MLIT | T1_SYMMETRIC_5IDT | VALID_RUN | 256 | 256 | 402064 | 7.25% | 0.00% | 3.72% | 0.00% |
| MLIT | T2_PARALLEL_3IDT_X2 | VALID_RUN | 256 | 247 | 393055 | 91.99% | 0.00% | 92.67% | 3.52% |

## Gate failures

- None.

The pilot uses 256 unique decoded evaluations per cell, one seed (20260917), geometry-valid initial populations, and a separate common-grid re-evaluation of search finalists. A passing R1.1 pilot stops for review and user approval; it does not authorize or start production automatically.

M0 and MLIT use different aperture search ranges (30–150 um and 30–180 um); cross-material differences therefore do not isolate material effects.
The conditional initializer changes population sampling distribution; the independent-uniform column is a geometry-only reference estimate, not the R1.1 population.
Production was not started. Review is required before any production run.
