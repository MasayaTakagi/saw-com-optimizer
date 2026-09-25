# Review bundle usage

The generic builder packages an existing run directory without starting its
study or optimizer. Create a JSON specification that identifies the saved
artifacts and source files:

```json
{
  "study_type": "my_dms_study",
  "required_artifacts": [
    "run_manifest.json",
    "input_config.yaml",
    "results.csv",
    "REVIEW_ME.md"
  ],
  "optional_artifacts": ["responses.npz"],
  "source_paths": [
    "src/sawopt/problem/dms_topologies.py",
    "src/sawopt/studies/my_study.py"
  ],
  "review_me_path": "REVIEW_ME.md"
}
```

Then run from the project root using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m sawopt.reporting.review_bundle `
  --run runs/my_saved_run `
  --output my_saved_run_review.zip `
  --spec configs/review/my_saved_run.json
```

The ZIP is written under `artifacts/review_bundles/`. Required files are
validated before packaging. Optional files can be omitted with
`include_optional=False` in Python or by setting
`max_optional_artifact_bytes` in the JSON specification. Checkpoint payloads
are excluded from generic bundle archives. When a run uses rolling retention,
include its neutral `metadata/recovery_policy.json` file to show retention and
final-checkpoint metadata; do not include intermediate full-state payloads by
default. See [`checkpoint_lifecycle.md`](checkpoint_lifecycle.md).

The builder includes a recorded `source_snapshot/` from the run when one is
available. Explicit `source_paths` are captured separately under
`source_snapshot/current_repository/`; they are not substituted for the
recorded snapshot. The bundle also records current Git state and environment
metadata. It hashes every included file and checks the ZIP contents and hashes
after creation.

For Python callers:

```python
from sawopt.reporting.review_bundle import ReviewBundleSpec, build_review_bundle

spec = ReviewBundleSpec(
    study_type="my_dms_study",
    required_artifacts=("run_manifest.json", "input_config.yaml", "results.csv", "REVIEW_ME.md"),
    optional_artifacts=("responses.npz",),
    source_paths=("src/sawopt/problem/dms_topologies.py",),
)
build_review_bundle("runs/my_saved_run", "artifacts/review_bundles/my_saved_run_review.zip", spec)
```

The CLI requires a `ReviewBundleSpec`; there is no study-specific bundle
contract in the reporting module.
