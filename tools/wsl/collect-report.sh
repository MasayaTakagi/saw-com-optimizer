#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s <results-directory> <report-directory>\n' "$0" >&2
  exit 2
fi
RESULTS="$(realpath -m "$1")"
REPORT="$(realpath -m "$2")"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
mkdir -p "$REPORT"

python3 - "$RESULTS" "$REPORT" "$ROOT" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

results, report, root = map(Path, sys.argv[1:])

def git(*args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    ).stdout

try:
    source_commit_sha = git("rev-parse", "HEAD").strip()
    source_status = git("status", "--porcelain=v1", "--untracked-files=all")
    source_working_tree = {"clean": not source_status, "status": source_status.splitlines()}
except (OSError, subprocess.CalledProcessError) as exc:
    source_commit_sha = None
    source_working_tree = {"clean": None, "status": [], "error": str(exc)}

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
if not source_commit_sha:
    blockers.append({"category": "SOURCE_COMMIT_NOT_RECORDED", "reason": "could not read the qualification checkout HEAD"})
if source_working_tree["clean"] is None:
    blockers.append({"category": "SOURCE_WORKTREE_NOT_RECORDED", "reason": "could not read qualification checkout status"})
elif not source_working_tree["clean"]:
    blockers.append({"category": "SOURCE_WORKTREE_DIRTY", "reason": "qualification report was generated from a dirty checkout"})
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
env = files["environment"] or {}
bootstrap_source = env.get("git_head") or {}
bootstrap_source_commit_sha = bootstrap_source.get("output") if isinstance(bootstrap_source, dict) else None
payload = {
    "schema_version": 1,
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "final_status": final_status,
    "blockers": blockers,
    "source_commit_sha": source_commit_sha,
    "bootstrap_source_commit_sha": bootstrap_source_commit_sha,
    "source_working_tree": source_working_tree,
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
for label, value in (
    ("Distribution", env.get("wsl_distro")),
    ("Kernel", env.get("kernel")),
    ("Python", env.get("python")),
    ("NumPy", env.get("numpy")),
    ("SciPy", env.get("scipy")),
    ("Git", (env.get("git_version") or {}).get("output")),
    ("Codex CLI", (env.get("codex_version") or {}).get("output")),
    ("Source commit", source_commit_sha),
    ("Bootstrap source commit", bootstrap_source_commit_sha),
    ("Source working tree", "CLEAN" if source_working_tree["clean"] is True else "DIRTY" if source_working_tree["clean"] is False else "NOT_RECORDED"),
):
    lines.append(f"- {label}: {value or 'NOT_RECORDED'}")
if source_working_tree["status"]:
    lines.extend(["", "### Source working-tree status", "", "```text", *source_working_tree["status"], "```"])
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
