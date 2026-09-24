# Stage 3.8C-R1 geometry-ranking validation

## Ranking regression coverage

The R1 study-local comparator has a strict geometry-status prefix:

1. Any geometry-valid result outranks every geometry-rejected result.
2. Geometry-rejected candidates are ordered only by their normalized geometry violations; no filter metrics are fabricated.
3. Geometry-valid, physics-successful candidates retain the exact `DEFAULT_COMPARATOR` rank suffix.
4. Geometry-valid physics failures rank after successful physics results but before geometry-rejected candidates.
5. L-SHADE replacement, p-best ordering, population shrink, incumbent tracking, and traces use the same comparator.
6. Common-grid selection accepts only finite successful results.

The ranking tests include the five requested cases: tiny-violation geometry rejection versus valid filter result, invalid versus invalid, valid versus valid, incumbent non-regression, and final common-grid selection. Additional tests cover finite comparator improvement values, non-finite physics output classification, deterministic valid-population sampling, search/validation counter identities, and the documented aggregate ranking priority.

## Regression result

Command:

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Result after the R1 import-boundary correction: **224 passed, 14 subtests passed**. The first run found three architecture-boundary violations from imports of private Stage 3.8 helpers. Those calls were replaced with R1-local adapters over the same provider, grid, and L-SHADE configuration data; the full suite then passed.

The pilot separately executed Stage 3.8 implementation validation and all six fixed-design sanity cases. All six known seed designs passed both search and common validation grids; every initial population was geometry-valid; every cell had positive physics/frequency counters and finite metrics. The gate correctly stopped because geometry rejection during T2 initial sampling was 93.27% for M0 and 91.99% for MLIT, above the 90% limit. Production was not launched.
