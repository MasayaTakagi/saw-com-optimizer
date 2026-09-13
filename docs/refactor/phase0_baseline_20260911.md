# Refactor Phase 0 baseline

Recorded on 2026-09-11 from commit
`902984fc355750dc2cc9fecee33c3ccd690bb563`.

The worktree was clean before the Phase 0 characterization test was added.
No production source behavior was changed in Phase 0.

## Test baseline

- The reviewed environment does not have the `pytest` package installed, so
  `PYTHONPATH=src pytest --collect-only -q` and the pytest command from the
  plan cannot run here.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: 66 tests passed
  in 66.728 s before the characterization test was added.
- The 26 module-level `test_*` functions (which unittest discovery does not
  collect) were invoked directly in a small in-memory runner: 26 passed.
  This gives the expected 92-test effective baseline for this snapshot.
- The architecture-focused unittest subset passed: 25 tests in 12.153 s.
- The new Stage 3.2 characterization tests passed: 2 tests.

The CLI help entry points all exited with code 0:

```text
python -m sawopt --help
python -m sawopt.optimization.hybrid_study --help
python -m sawopt.optimization.stage2_study --help
python -m sawopt.optimization.convergence_study --help
python -m sawopt.optimization.stage32_study --help
```

## Stage 3.2 stagnation-recovery contract

`tests/unit/optimization/test_stage32.py` now characterizes the existing
continuation behavior with fake DE and population builders, without launching
a production search:

- four zero-progress DE attempts are made;
- the initializer is diversified only between attempts 1–2, 2–3, and 3–4;
- `segment_index` advances once per DE call;
- retry seeds are `seed + prior_segment_index`;
- the retained population prefix is `max(1, n // 4)`;
- refreshes use the trajectory RNG and active bounds;
- refresh centers use the current best design, or the default `FilterDesign`;
- progress on a retry exits immediately and clears `stop_reason`;
- four failed attempts end with `no_new_unique_designs`.

## Resolved configuration fingerprints

Each digest is the SHA-256 of the complete `_load_config()` result after
canonical JSON normalization:

```python
json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

The raw `inputs` field is included. Fragment order is therefore part of the
fingerprint.

| Config | Resolved-config SHA-256 |
|---|---|
| `configs/studies/stage3_2_convergence_50ohm.yaml` | `c08fb428efa66d7fa824bb6d4dfce386ee1feb1ecf04d6188805325d8f79c4e0` |
| `configs/studies/next_50ohm_dms_production.yaml` | `9019f1e7ec1e29db13e5a4db3f126e3f63f5567cdd7c172df4fcb2e3a527114d` |
| `configs/studies/next_50ohm_center_outer_same_16000.yaml` | `e3a86a1feba308029c34be392bddf689b70a57616f85f7a6cb31d312e6e2d023` |
| `configs/studies/stage3_3_convergence_50ohm.yaml` | `84e82f1cbf6d6daff9e9c97521bbdd13b6e89a6e2af0671f20318eae8fc379e6` |
| `configs/studies/stage3_3_1_preprod.yaml` | `315a82ab486ee4162cdbb57cf13167622db52d194dd7a2df85cc3c27c1116589` |
| `configs/studies/stage3_3_1a_preprod.yaml` | `a09f2873f6e365838cf431ac078019f46fa367fb9ae356f34dd1be69342dfdd8` |

The current Stage 3.2 production fixtures resolve to:

| Config | Fragment order | Budgets | Optional max | Workers | BLAS threads |
|---|---|---|---:|---:|---:|
| `next_50ohm_dms_production.yaml` | convergence, production-process5 | `[500, 1000, 2000, 4000]` | 8000 | 5 | 1 |
| `next_50ohm_center_outer_same_16000.yaml` | convergence, production-process5, center16000 | `[500, 1000, 2000, 4000, 8000]` | 16000 | 5 | 1 |

Both use impedance grid `[50]` and the seed list
`[20260909, 20260910, 20260911, 20260912, 20260913]`.
