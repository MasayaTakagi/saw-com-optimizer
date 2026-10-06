#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s <results-directory> <report-directory>\n' "$0" >&2
  exit 2
fi
RESULTS="$(realpath -m "$1")"
REPORT="$(realpath -m "$2")"
mkdir -p "$REPORT"

python3 - "$RESULTS" "$REPORT" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

results, report = map(Path, sys.argv[1:])

def load(name):
    path = results / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"status": "INVALID", "error": str(exc)}

files = {
    "environment": load("environment.json"),
    "filesystem": load("filesystem.json"),
    "git": load("git.json"),
    "worktree_identity": load("worktree-identity.json"),
    "worktree_cleanup": load("worktree-cleanup.json"),
    "codex_sandbox": load("codex-sandbox.json"),
    "numerical": load("numerical.json"),
    "optimizer_checkpoint": load("optimizer-checkpoint.json"),
    "regression": load("regression.json"),
    "blocker": load("blocker.json"),
}
required = (
    ("filesystem", "WSL2_FILESYSTEM"),
    ("git", "GIT_OPERATIONS"),
    ("worktree_identity", "EXTERNAL_WORKTREE"),
    ("worktree_cleanup", "WORKTREE_CLEANUP"),
    ("codex_sandbox", "CODEX_SANDBOX"),
    ("optimizer_checkpoint", "CHECKPOINT_RESUME"),
    ("regression", "FULL_REGRESSION"),
)
blockers = []
if files["blocker"]:
    category = files["blocker"].get("category", "UNKNOWN")
    reason = files["blocker"].get("reason", "qualification stopped before all phases completed")
    blockers.append({"category": category, "reason": reason})
for key, category in required:
    value = files[key]
    if not value:
        blockers.append({"category": f"{category}_NOT_RUN", "reason": f"{key} result is missing"})
    elif value.get("status") != "PASS":
        blockers.append({"category": category, "reason": value.get("detail", value.get("status", "failed"))})

numerical = files["numerical"]
if numerical:
    parity = numerical.get("evaluator_parity", {})
    if parity.get("status") == "DIFFERENCE_REVIEW":
        blockers.append({"category": "EVALUATOR_PARITY_DIFFERENCE_REVIEW", "reason": "; ".join(parity.get("differences", []))})
    if numerical.get("optimizer", {}).get("status") != "PASS":
        blockers.append({"category": "OPTIMIZER_SMOKE", "reason": "optimizer smoke did not complete with reproducible finite metrics"})
    checkpoint = numerical.get("optimizer", {}).get("checkpoint", {})
    if checkpoint.get("state_version") != 4:
        blockers.append({"category": "CHECKPOINT_VERSION", "reason": f"expected L-SHADE checkpoint v4; found {checkpoint.get('state_version')}"})

final_status = "WSL2_CORE_QUALIFIED" if not blockers else "WSL2_CORE_BLOCKED"
payload = {
    "schema_version": 1,
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "final_status": final_status,
    "blockers": blockers,
    "environment": files["environment"],
    "checks": {key: files[key] for key in files if key != "blocker"},
    "regression_runs": 1 if files["regression"] else 0,
    "production_optimizer_runs": 0,
}
(report / "report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

lines = [
    "# WSL2 Core qualification report",
    "",
    f"**{final_status}**",
    "",
    f"Captured: {payload['captured_at_utc']}",
    "",
    "## Environment",
    "",
]
env = files["environment"] or {}
for label, value in (
    ("Distribution", env.get("wsl_distro")),
    ("Kernel", env.get("kernel")),
    ("Python", env.get("python")),
    ("NumPy", env.get("numpy")),
    ("SciPy", env.get("scipy")),
    ("Git", (env.get("git_version") or {}).get("output")),
    ("Codex CLI", (env.get("codex_version") or {}).get("output")),
    ("Source commit", (env.get("git_head") or {}).get("output")),
):
    lines.append(f"- {label}: {value or 'NOT_RECORDED'}")
lines.extend(["", "## Qualification checks", ""])
for key, category in required:
    value = files[key]
    lines.append(f"- {key}: {(value or {}).get('status', 'NOT_RUN')}")
lines.append(f"- evaluator parity: {(numerical or {}).get('evaluator_parity', {}).get('status', 'NOT_RUN')}")
lines.append(f"- optimizer smoke: {(numerical or {}).get('optimizer', {}).get('status', 'NOT_RUN')}")
lines.append(f"- selected finalist validation: {(numerical or {}).get('optimizer', {}).get('selected_finalist_validation', 'NOT_RECORDED')}")
lines.append(f"- finite metrics and constraints: {(numerical or {}).get('optimizer', {}).get('finite_metrics_and_constraints', 'NOT_RECORDED')}")
lines.append(f"- checkpoint state version: {(numerical or {}).get('optimizer', {}).get('checkpoint', {}).get('state_version', 'NOT_RECORDED')}")
lines.append(f"- checkpoint file bytes: {(numerical or {}).get('optimizer', {}).get('checkpoint', {}).get('bytes', 'NOT_RECORDED')}")
lines.append(f"- peak process RSS bytes: {(numerical or {}).get('optimizer', {}).get('peak_rss_bytes', 'NOT_RECORDED')}")
lines.append(f"- full regression runs: {payload['regression_runs']}")
lines.extend(["", "## Blockers", ""])
if blockers:
    lines.extend(f"- `BLOCKER={item['category']}` — {item['reason']}" for item in blockers)
else:
    lines.append("- None")
lines.extend(["", "Production optimizer runs: 0.", ""])
(report / "report.md").write_text("\n".join(lines), encoding="utf-8")
print(final_status)
for item in blockers:
    print(f"BLOCKER={item['category']}")
PY
