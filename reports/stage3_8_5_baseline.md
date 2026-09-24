# Stage 3.8.5 Architecture Cleanup baseline

Captured before source changes on 2026-09-24.

- HEAD: `c0370bd97789e6d9c0925abfdb8643a8814224d7`
- Branch: `main`
- Working tree: one pre-existing untracked handoff instruction file at `docs/handoff/Stage 3.8.5 Architecture Cleanup 作業指示書.md`; no tracked diff.
- `git diff --stat`: empty.
- Full baseline: `.venv\\Scripts\\python.exe -m pytest -q` — **242 passed, 1 warning, 14 subtests passed** in 118.12 s.
- Existing warning: pytest could not write `.pytest_cache` due to `Permission denied`; no test failed.
- Environment setup: `.venv` was created, but `pip install -e .` could not fetch the build dependency `setuptools>=68` because network access was denied. The baseline tests ran from the project `.venv` successfully.

The pre-existing handoff instruction file is user-provided state and is not part of this cleanup's edits.
