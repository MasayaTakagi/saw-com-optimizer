# Stage 3.8.6 checkpoint lifecycle baseline

Captured before Stage 3.8.6 implementation edits:

- Git HEAD: `c0370bd97789e6d9c0925abfdb8643a8814224d7`
- Branch: `main`
- Worktree: already dirty with Stage 3.8.5 edits and untracked source/docs; that
  state was preserved. Known pre-existing paths included
  `reports/escalation_log.md`, `src/sawopt/optimization/counters.py`,
  `src/sawopt/optimization/population.py`, `src/sawopt/optimizers/selection.py`,
  `src/sawopt/studies/stage3_8c_r1_geometry_gate.py`, and
  `src/sawopt/studies/stage3_8_dual_material_dms_topology_fast_screen.py`.
- Baseline command: `.venv\\Scripts\\python.exe -m pytest`
- Baseline result: **256 passed, 1 warning** in 105.27 seconds. The warning was
  pytest's inability to write its cache directory under `.pytest_cache`.

No reset, clean, stash, commit, or historical-run cleanup was performed. The
review bundle records the current complete Git state; `scoped_changes.md`
separates this task's lifecycle changes and the Stage 3.8 fingerprint exception
from the pre-existing dirty worktree.
