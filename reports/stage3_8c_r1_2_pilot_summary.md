# Stage 3.8C-R1.2 pilot summary

- Gate status: **PASS**
- Cells passing the gate: 6/6
- Run directory: `C:\Users\sub\Documents\ChatGPT\saw-com-optimizer\runs\stage3_8c_r1_2_pilot_20260924`
- Source fingerprint: `52168fc055f1df6a900f44a0fac317004292b71a1bc95f5912d31027d2dd8588`
- Common validation grid: `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`
- Performance interpretation: diagnostic only; one seed is not a topology ranking.

| Material | Topology | Status | Population | Attempts | Initial geometry rejection | Init time (s) | Physics valid | Solved points |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | T0_CURRENT_3IDT | VALID_RUN | 162/162 | 1343 | 88.01% | 0.136 | 255 | 401063 |
| M0 | T1_SYMMETRIC_5IDT | VALID_RUN | 180/180 | 185 | 3.24% | 0.021 | 256 | 402064 |
| M0 | T2_PARALLEL_3IDT_X2 | VALID_RUN | 180/180 | 2552 | 92.99% | 0.183 | 254 | 400062 |
| MLIT | T0_CURRENT_3IDT | VALID_RUN | 162/162 | 1420 | 88.66% | 0.146 | 250 | 396058 |
| MLIT | T1_SYMMETRIC_5IDT | VALID_RUN | 180/180 | 182 | 1.65% | 0.023 | 256 | 402064 |
| MLIT | T2_PARALLEL_3IDT_X2 | VALID_RUN | 180/180 | 2410 | 92.57% | 0.171 | 254 | 400062 |

## Gate failures

- None.

The pilot uses 256 unique decoded evaluations per cell, one seed (20260917), geometry-valid initial populations, and a separate common-grid re-evaluation of search finalists. R1.1/R1.2 pilots stop for review; no pilot authorizes or starts production automatically.

R1.2 uses independent real-uniform proposals, existing integer canonicalization, and geometry rejection/resampling; rejected designs are never repaired. Rejection fraction is diagnostic only.
Initializer runtime median/max: 0.141/0.183 s.
R1.1's conditional initializer is not the R1.2 default. Production was not started; review is required before any production run.
M0 and MLIT retain 30–150 um and 30–180 um aperture ranges respectively; cross-material differences do not isolate material effects.