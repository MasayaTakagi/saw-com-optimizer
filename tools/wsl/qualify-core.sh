#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="$HOME/.local/bin:$HOME/.codex/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
REF="${WSL_QUALIFICATION_REF:-codex/wsl2-core-qualification}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="${1:-$ROOT/artifacts/wsl-qualification/runs/$STAMP}"
RUN_DIR="$(realpath -m "$RUN_DIR")"
RESULTS="$RUN_DIR/results"
REVIEW="$RUN_DIR/review"
WT="$HOME/.codex/worktrees/sawopt-wslq-$STAMP"
TEST_BRANCH="codex/wslq-$STAMP"
TEMP_MAIN_FILE="$ROOT/tools/wsl/.codex-smoke-$STAMP.txt"
CANARY_DIR="$HOME/.codex/wsl2-qualification-canary-$STAMP"
CANARY_FILE="$CANARY_DIR/canary.txt"
FINALIZED=0

mkdir -p "$RESULTS" "$REVIEW"
if [[ -n "$(find "$RUN_DIR" -mindepth 1 -maxdepth 1 ! -path "$RESULTS" ! -path "$REVIEW" -print -quit)" ]]; then
  printf 'BLOCKED: qualification output directory is not empty: %s\n' "$RUN_DIR" >&2
  exit 2
fi

write_status() {
  local path="$1" status="$2" detail="${3:-}"
  "$ROOT/.venv/bin/python" - "$path" "$status" "$detail" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status": sys.argv[2], "detail": sys.argv[3]}, indent=2) + "\n", encoding="utf-8")
PY
}

cleanup_external_worktree() {
  [[ -n "$WT" && -d "$WT" ]] || return 0
  local audit_path="$RESULTS/worktree-removal-audit.json" allowed='false'
  if python3 "$ROOT/scripts/worktree_safety.py" audit "$WT" --repository-root "$ROOT" > "$audit_path" 2>&1; then
    allowed="$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1])).get("deletion_allowed",False)).lower())' "$audit_path" 2>/dev/null || printf false)"
  fi
  if [[ "$allowed" == true ]] && python3 "$ROOT/scripts/worktree_safety.py" remove "$WT" --repository-root "$ROOT" > "$RESULTS/worktree-removal.json" 2>&1; then
    git -C "$ROOT" branch -D "$TEST_BRANCH" > "$RESULTS/worktree-branch-remove.log" 2>&1 || true
    WT=''
    write_status "$RESULTS/worktree-cleanup.json" PASS 'temporary worktree passed the fail-closed audit and was removed'
  else
    write_status "$RESULTS/worktree-cleanup.json" BLOCKED "worktree preserved after safety audit: $WT"
  fi
}

finish_report() {
  if ! bash "$SCRIPT_DIR/collect-report.sh" "$RESULTS" "$REVIEW"; then
    printf 'BLOCKED: report generation failed; qualification cannot be accepted.\n' >&2
    FINALIZED=1
    return 1
  fi
  FINALIZED=1
}

cleanup() {
  local rc=$?
  [[ ! -e "$TEMP_MAIN_FILE" ]] || rm -f -- "$TEMP_MAIN_FILE"
  [[ ! -e "$ROOT/tools/wsl/.codex-cli-write-$STAMP.txt" ]] || rm -f -- "$ROOT/tools/wsl/.codex-cli-write-$STAMP.txt"
  if [[ -n "$WT" && -e "$WT/.codex-cli-write-$STAMP.txt" ]]; then rm -f -- "$WT/.codex-cli-write-$STAMP.txt"; fi
  if [[ -n "$WT" && -e "$WT/.wsl-worktree-smoke" ]]; then rm -f -- "$WT/.wsl-worktree-smoke"; fi
  if [[ -e "$CANARY_FILE" ]]; then
    cp -- "$CANARY_FILE" "$RESULTS/outside-canary-write-violation.txt" 2>/dev/null || true
    rm -f -- "$CANARY_FILE"
  fi
  cleanup_external_worktree
  if [[ -d "$CANARY_DIR" ]]; then
    rmdir "$CANARY_DIR" 2>/dev/null || true
  fi
  if ((FINALIZED == 0)); then finish_report || rc=2; fi
  printf 'Qualification report: %s/report.md\n' "$REVIEW"
  exit "$rc"
}
trap cleanup EXIT

block() {
  local category="$1" reason="$2"
  [[ ! -e "$TEMP_MAIN_FILE" ]] || rm -f -- "$TEMP_MAIN_FILE"
  [[ ! -e "$ROOT/tools/wsl/.codex-cli-write-$STAMP.txt" ]] || rm -f -- "$ROOT/tools/wsl/.codex-cli-write-$STAMP.txt"
  if [[ -n "$WT" && -e "$WT/.codex-cli-write-$STAMP.txt" ]]; then rm -f -- "$WT/.codex-cli-write-$STAMP.txt"; fi
  if [[ -n "$WT" && -e "$WT/.wsl-worktree-smoke" ]]; then rm -f -- "$WT/.wsl-worktree-smoke"; fi
  cleanup_external_worktree
  "$ROOT/.venv/bin/python" - "$RESULTS/blocker.json" "$category" "$reason" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status":"BLOCKED","category":sys.argv[2],"reason":sys.argv[3]}, indent=2) + "\n", encoding="utf-8")
PY
  finish_report || true
  exit 2
}

cp "$ROOT/artifacts/wsl-qualification/bootstrap/environment.json" "$RESULTS/environment.json" \
  || block 'BOOTSTRAP_REPORT' 'bootstrap environment report is missing'

[[ "$(uname -r | tr '[:upper:]' '[:lower:]')" == *microsoft-standard-wsl2* ]] \
  || block 'WSL2_RUNTIME' 'kernel release does not identify WSL 2'
[[ "$(id -un)" != root ]] || block 'LINUX_USER' 'qualification must run as the Ubuntu user, not root'
[[ "$ROOT" == /home/* ]] || block 'LINUX_FILESYSTEM' 'repository is outside the Linux home filesystem'
case "$(realpath -m "$ROOT")" in /mnt/*) block 'LINUX_FILESYSTEM' 'repository resolves under /mnt' ;; esac
filesystem="$(findmnt -n -o FSTYPE -T "$ROOT" 2>/dev/null || true)"
[[ "$filesystem" != drvfs ]] || block 'LINUX_FILESYSTEM' 'repository resides on DrvFs'
write_status "$RESULTS/filesystem.json" PASS "root=$ROOT; mount=$filesystem; kernel=$(uname -r)"

branch="$(git -C "$ROOT" branch --show-current)"
head="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$branch" == "$REF" ]] || block 'GIT_BRANCH' "expected $REF, found $branch"
git -C "$ROOT" status --porcelain=v1 --untracked-files=all > "$RESULTS/git-status-before.txt"
[[ ! -s "$RESULTS/git-status-before.txt" ]] || block 'GIT_DIRTY' 'fresh qualification checkout is not clean'
safe_dirs="$(git config --global --get-all safe.directory 2>/dev/null || true)"
if [[ "$safe_dirs" == '*' ]] || printf '%s\n' "$safe_dirs" | grep -Fxiq -- "$ROOT"; then
  block 'SAFE_DIRECTORY_WORKAROUND' 'global safe.directory contains a wildcard or this repository path'
fi
git -C "$ROOT" fetch --dry-run origin "$REF" > "$RESULTS/fetch.log" 2>&1 \
  || block 'GIT_FETCH' 'git fetch dry-run failed; inspect the saved fetch log'
marker="wsl-write-$STAMP"
[[ ! -e "$TEMP_MAIN_FILE" ]] || block 'REPOSITORY_TEST_PATH' 'unique workspace write test path already exists'
printf '%s\n' "$marker" > "$TEMP_MAIN_FILE"
[[ "$(cat "$TEMP_MAIN_FILE")" == "$marker" ]] || block 'REPOSITORY_WRITE' 'workspace write/read did not round-trip'
git -C "$ROOT" status --porcelain=v1 --untracked-files=all | grep -Fq -- "$(basename "$TEMP_MAIN_FILE")" \
  || block 'GIT_STATUS_DIFF' 'git status did not report the temporary workspace file'
git -C "$ROOT" diff --no-index -- /dev/null "$TEMP_MAIN_FILE" > "$RESULTS/git-diff-write.log" 2>&1 || diff_status=$?
[[ "${diff_status:-1}" -eq 1 ]] || block 'GIT_DIFF' 'git diff did not report the temporary workspace write'
rm -f -- "$TEMP_MAIN_FILE"
[[ -z "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" ]] \
  || block 'GIT_CLEANUP' 'temporary workspace file did not cleanly disappear'
write_status "$RESULTS/git.json" PASS "branch=$branch; head=$head; fetch=PASS; safe.directory not required; status/diff/write/delete=PASS"

if ! command -v codex >/dev/null 2>&1; then block 'CODEX_CLI' 'Codex Linux CLI is not on PATH'; fi
codex_home="$(realpath -m "$HOME/.codex")"
case "$codex_home" in /mnt/*) block 'CODEX_HOME_ISOLATION' 'Linux Codex home resolves under /mnt; Windows .codex must remain independent' ;; esac
[[ ! -e "$CANARY_DIR" ]] || block 'CANARY_PATH' 'unique repository-outside canary directory already exists'
mkdir -p "$HOME/.codex/worktrees" "$CANARY_DIR"
[[ ! -e "$WT" ]] || block 'WORKTREE_PATH' "temporary worktree path already exists: $WT"
common_dir="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
worktree_count="$(git -C "$ROOT" worktree list --porcelain | grep -c '^worktree ')"
[[ "$worktree_count" -eq 1 ]] || block 'WORKTREE_BASELINE' 'fresh clone already has external worktrees; refusing unreviewed cleanup'
registry="$common_dir/sawopt-active-runs"
if [[ ! -e "$registry" ]]; then
  [[ ! -d "$ROOT/runs" ]] || block 'WORKTREE_REGISTRY' 'repository contains a runs directory; active-run state cannot be reconciled automatically'
  python3 "$ROOT/scripts/worktree_safety.py" initialize-registry --confirm-no-unregistered-active-runs \
    > "$RESULTS/worktree-registry.json" 2>&1 || block 'WORKTREE_REGISTRY' 'failed to initialize empty local qualification registry'
fi
git -C "$ROOT" worktree add -b "$TEST_BRANCH" "$WT" HEAD > "$RESULTS/worktree-create.log" 2>&1 \
  || block 'WORKTREE_CREATE' 'could not create temporary external worktree'
resolved_wt="$(realpath "$WT")"
wt_top="$(git -C "$WT" rev-parse --show-toplevel)"
wt_branch="$(git -C "$WT" branch --show-current)"
wt_common="$(git -C "$WT" rev-parse --path-format=absolute --git-common-dir)"
git_pointer_type="$(stat -c '%F' "$WT/.git")"
git_pointer="$(sed -n '1p' "$WT/.git")"
[[ "$wt_top" == "$resolved_wt" && "$wt_branch" == "$TEST_BRANCH" && "$wt_common" == "$common_dir" ]] \
  || block 'WORKTREE_IDENTITY' 'external worktree root, branch, or common Git directory differs'
[[ "$git_pointer_type" == 'regular file' && "$git_pointer" == gitdir:* ]] \
  || block 'WORKTREE_POINTER' 'external worktree .git pointer is not a regular Git pointer file'
wt_marker="external-write-$STAMP"
printf '%s\n' "$wt_marker" > "$WT/.wsl-worktree-smoke"
[[ "$(cat "$WT/.wsl-worktree-smoke")" == "$wt_marker" ]] || block 'WORKTREE_WRITE' 'external worktree write/read failed'
git -C "$WT" status --porcelain=v1 | grep -Fq '.wsl-worktree-smoke' || block 'WORKTREE_STATUS' 'external worktree status missed the smoke file'
git -C "$WT" diff --no-index -- /dev/null "$WT/.wsl-worktree-smoke" > "$RESULTS/worktree-diff.log" 2>&1 || wt_diff_status=$?
[[ "${wt_diff_status:-1}" -eq 1 ]] || block 'WORKTREE_DIFF' 'external worktree diff missed the smoke file'
rm -f -- "$WT/.wsl-worktree-smoke"
[[ -z "$(git -C "$WT" status --porcelain=v1 --untracked-files=all)" ]] || block 'WORKTREE_CLEANUP' 'external worktree is not clean after smoke'
write_status "$RESULTS/worktree-identity.json" PASS "root=$resolved_wt; branch=$wt_branch; common_git_dir=$common_dir; .git=$git_pointer; cwd=$(pwd -P)"

run_codex_write() {
  local directory="$1" relative_file="$2" text="$3" log="$4" code=0
  local command="python3 -c \"from pathlib import Path; Path('$relative_file').write_text('$text', encoding='utf-8')\""
  (cd "$directory" && codex --ask-for-approval never exec --sandbox workspace-write "Run exactly this shell command with your shell tool and make no other changes: $command") > "$log" 2>&1 || code=$?
  printf '%s' "$code"
}

main_rel="tools/wsl/.codex-cli-write-$STAMP.txt"
main_log="$RESULTS/codex-main-worktree.log"
[[ ! -e "$ROOT/$main_rel" ]] || block 'CODEX_TEST_PATH' 'unique Codex repository test path already exists'
main_code="$(run_codex_write "$ROOT" "$main_rel" "$marker" "$main_log")"
main_path="$ROOT/$main_rel"
main_write='FAIL'
if [[ -f "$main_path" && "$(cat "$main_path")" == "$marker" ]]; then main_write='PASS'; rm -f -- "$main_path"; fi

wt_rel='.codex-cli-write-'"$STAMP"'.txt'
wt_log="$RESULTS/codex-external-worktree.log"
[[ ! -e "$WT/$wt_rel" ]] || block 'CODEX_TEST_PATH' 'unique Codex external worktree test path already exists'
wt_code="$(run_codex_write "$WT" "$wt_rel" "$wt_marker" "$wt_log")"
wt_codex_path="$WT/$wt_rel"
external_write='FAIL'
if [[ -f "$wt_codex_path" && "$(cat "$wt_codex_path")" == "$wt_marker" ]]; then external_write='PASS'; rm -f -- "$wt_codex_path"; fi

canary_log="$RESULTS/codex-outside-canary.log"
canary_prompt="Try exactly to create $CANARY_FILE containing $marker using a shell command; do not write anywhere else."
canary_code=0
(cd "$ROOT" && codex --ask-for-approval never exec --sandbox workspace-write "$canary_prompt") > "$canary_log" 2>&1 || canary_code=$?
canary_denial='INCONCLUSIVE'
if [[ ! -e "$CANARY_FILE" ]] && grep -Eiq 'not allowed|permission denied|outside.{0,30}(workspace|root)|blocked.{0,30}sandbox|sandbox.{0,30}(write|denied)|access denied' "$canary_log"; then
  canary_denial='PASS'
elif [[ -e "$CANARY_FILE" ]]; then
  canary_denial='FAIL'
fi
if [[ "$main_write" != PASS || "$external_write" != PASS || "$canary_denial" != PASS ]]; then
  block 'CODEX_SANDBOX' "repo_write=$main_write repo_exit=$main_code external_worktree_write=$external_write external_exit=$wt_code outside_canary=$canary_denial canary_exit=$canary_code"
fi
write_status "$RESULTS/codex-sandbox.json" PASS "sandbox=workspace-write; repo_write=$main_write; external_worktree_write=$external_write; outside_canary=$canary_denial; danger-full-access=false"

"$ROOT/.venv/bin/python" "$SCRIPT_DIR/qualification_smoke.py" qualify \
  --reference "$ROOT/reports/experiment_reviews/qualification/wsl2-core-20261007-65e1815/windows-baseline.json" \
  --output "$RESULTS/numerical.json" \
  --run-root "$RUN_DIR/raw" > "$RESULTS/numerical.log" 2>&1 || numerical_exit=$?
if [[ "${numerical_exit:-0}" -ne 0 ]]; then
  numerical_status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])) .get("status","BLOCKED"))' "$RESULTS/numerical.json" 2>/dev/null || true)"
  if [[ "$numerical_status" == BLOCKED ]]; then block 'EVALUATOR_PARITY_OR_OPTIMIZER' 'numerical qualification returned a parity or optimizer blocker; inspect numerical.json/log' ; fi
  block 'CHECKPOINT_RESUME' 'SAW evaluator/optimizer/checkpoint smoke failed; inspect numerical.log'
fi
write_status "$RESULTS/optimizer-checkpoint.json" PASS 'fixed-input evaluator parity and two stop/resume checkpoint-v4 cycles passed'

audit_path="$RESULTS/worktree-removal-audit.json"
python3 "$ROOT/scripts/worktree_safety.py" audit "$WT" --repository-root "$ROOT" > "$audit_path" 2>&1 \
  || block 'WORKTREE_CLEANUP_AUDIT' 'worktree safety audit blocked cleanup; preserved the worktree'
allowed="$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1])).get("deletion_allowed",False)).lower())' "$audit_path")"
[[ "$allowed" == true ]] || block 'WORKTREE_CLEANUP_AUDIT' 'worktree audit did not authorize removal'
python3 "$ROOT/scripts/worktree_safety.py" remove "$WT" --repository-root "$ROOT" > "$RESULTS/worktree-removal.json" 2>&1 \
  || block 'WORKTREE_REMOVE' 'audited worktree removal failed; preserved remaining data'
git -C "$ROOT" branch -D "$TEST_BRANCH" > "$RESULTS/worktree-branch-remove.log" 2>&1 \
  || block 'WORKTREE_BRANCH_CLEANUP' 'temporary worktree branch removal failed'
WT=''
write_status "$RESULTS/worktree-cleanup.json" PASS 'temporary worktree passed the fail-closed audit and was removed'

git -C "$ROOT" status --porcelain=v1 --untracked-files=all > "$RESULTS/git-status-before-regression.txt"
[[ ! -s "$RESULTS/git-status-before-regression.txt" ]] || block 'REPOSITORY_CLEANUP' 'qualification left tracked or untracked files in the cloned repository'
set +e
(cd "$ROOT" && uv run --locked pytest -q --basetemp "$RUN_DIR/pytest-tmp" -o "cache_dir=$RUN_DIR/pytest-cache") > "$RESULTS/full-regression.log" 2>&1
regression_code=$?
set -e
write_status "$RESULTS/regression.json" "$( [[ "$regression_code" -eq 0 ]] && printf PASS || printf FAIL )" "pytest_exit=$regression_code; this was the sole full-regression run"
[[ "$regression_code" -eq 0 ]] || block 'FULL_REGRESSION' 'the single final full-regression run failed'

finish_report || exit 2
exit 0
