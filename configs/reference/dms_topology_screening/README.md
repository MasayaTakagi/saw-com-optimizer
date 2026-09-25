# DMS topology screening reference inputs

These immutable inputs make the role-based DMS topology study independent of
gitignored `runs/` paths while retaining the exact saved validation grid and
initial designs used by the Stage 3.8C study.

- `common_validation_grid_hz.csv` has 9,113 points and file SHA-256
  `84afd1e7ecf7c66ce937e7dc265a31f2ae4017ab08f7242b25577dd80279ffab`.
  Its grid identity is
  `2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f`.
  The source run file and metadata hashes are recorded in
  `common_validation_grid.json`.
- `initial_designs/M0.json` and `initial_designs/MLIT.json` preserve the exact
  design dictionaries already used as Stage 3.8 test fixtures. Their source
  run files and SHA-256 values are in `initial_design_origins.json`.

These are reference inputs only. The archived run directories and review
bundles remain untouched; future runs record a new configuration and source
fingerprint and are not represented as reproductions of the archived run.
