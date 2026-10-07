#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPOSITORY_URL="https://github.com/MasayaTakagi/saw-com-optimizer.git"
readonly QUALIFICATION_REF="${WSL_QUALIFICATION_REF:-codex/wsl2-core-qualification}"
readonly REPO_ROOT="$HOME/src/saw-com-optimizer"
readonly REF="${WSL_QUALIFICATION_REF:-codex/wsl2-core-qualification}"

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }

[[ -n "${WSL_DISTRO_NAME:-}" ]] || fail 'Run this script inside the target Ubuntu WSL distribution.'
[[ "$(. /etc/os-release && printf '%s' "$ID")" == ubuntu ]] || fail 'The target distribution must be Ubuntu.'
grep -qi 'microsoft-standard-WSL2' /proc/sys/kernel/osrelease || fail 'The active kernel does not identify as WSL 2.'
[[ "$HOME" == /home/* ]] || fail "Linux user home is unexpected: $HOME"
case "$(realpath -m "$HOME")" in /mnt/*) fail 'Linux home resolves under /mnt; use the Ubuntu Linux filesystem.' ;; esac
if [[ "${CODEX_HOME:-}" == /mnt/* || "${CODEX_HOME:-}" == /mnt/*/* ]]; then
  unset CODEX_HOME
fi
if [[ -e "$HOME/.codex" ]]; then
  codex_home_path="$(realpath "$HOME/.codex")"
  case "$codex_home_path" in /mnt/*) fail 'Linux ~/.codex resolves under /mnt; Windows Codex state must not be shared.' ;; esac
fi

printf 'WSL2 kernel: %s\nDistro: %s\nLinux user: %s\n' "$(uname -r)" "$WSL_DISTRO_NAME" "$(id -un)"
if [[ -d /run/systemd/system ]]; then
  SYSTEMD_STATUS="$(systemctl is-system-running 2>&1 || true)"
else
  SYSTEMD_STATUS='not active (qualification records this; systemd is not enabled automatically)'
fi

missing=()
for package in git curl ca-certificates python3 python3-venv python3-pip build-essential; do
  if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
    missing+=("$package")
  fi
done
if ((${#missing[@]})); then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends "${missing[@]}"
fi

mkdir -p "$HOME/src"
git ls-remote --exit-code "$REPOSITORY_URL" "refs/heads/$REF" >/dev/null \
  || fail "GitHub fetch check failed for the qualification branch '$REF'. No credentials are copied from Windows."
if [[ -e "$REPO_ROOT" ]]; then
  [[ -d "$REPO_ROOT/.git" ]] || fail "Repository target exists but is not a Git checkout: $REPO_ROOT"
  [[ "$(git -C "$REPO_ROOT" remote get-url origin)" == "$REPOSITORY_URL" ]] \
    || fail "Existing repository origin does not match the qualification repository."
  [[ "$(git -C "$REPO_ROOT" branch --show-current)" == "$REF" ]] \
    || fail "Existing repository is not on the qualification branch '$REF'."
  [[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]] \
    || fail "Existing repository is not clean; preserving it without modification."
  git -C "$REPO_ROOT" fetch origin "$REF"
  git -C "$REPO_ROOT" merge --ff-only "origin/$REF"
else
  git clone --single-branch --branch "$REF" "$REPOSITORY_URL" "$REPO_ROOT"
fi
resolved_repo="$(realpath "$REPO_ROOT")"
case "$resolved_repo" in /mnt/*) fail 'Repository clone resolved under /mnt; refusing to continue.' ;; esac
mount_type="$(findmnt -n -o FSTYPE -T "$resolved_repo" 2>/dev/null || true)"
[[ "$mount_type" != drvfs ]] || fail 'Repository filesystem is DrvFs; clone inside the Ubuntu Linux filesystem.'

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$REPO_ROOT/.venv"
fi
(
  cd "$REPO_ROOT"
  PIP_DISABLE_PIP_VERSION_CHECK=1 "$REPO_ROOT/.venv/bin/python" -m pip install -e '.[test]' --disable-pip-version-check
)

export PATH="$HOME/.local/bin:$HOME/.codex/bin:$PATH"
if ! command -v codex >/dev/null 2>&1; then
  curl -fsSL https://chatgpt.com/codex/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.codex/bin:$PATH"
fi
command -v codex >/dev/null 2>&1 || fail 'Codex Linux CLI installation completed without a codex executable on PATH.'

artifacts="$REPO_ROOT/artifacts/wsl-qualification"
mkdir -p "$artifacts/bootstrap"
export SYSTEMD_STATUS REPO_ROOT QUALIFICATION_REF REF mount_type
"$REPO_ROOT/.venv/bin/python" - "$artifacts/bootstrap/environment.json" <<'PY'
import datetime, json, os, platform, subprocess, sys
from pathlib import Path
import matplotlib, numpy, scipy, yaml

def decode_command_output(data):
    if not data:
        return ""
    if data.startswith((b"\\xff\\xfe", b"\\xfe\\xff")):
        return data.decode("utf-16", errors="replace")
    odd = data[1::2]
    if len(data) % 2 == 0 and odd and (odd.count(0) / len(odd)) > 0.20:
        return data.decode("utf-16-le", errors="replace")
    for encoding in ("utf-8", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")

def command(*args):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        return {"exit_code": result.returncode, "output": decode_command_output(result.stdout).strip()}
    except OSError as exc:
        return {"exit_code": None, "output": str(exc)}

repo = Path(os.environ["REPO_ROOT"])
data = {
    "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "os_release": Path("/etc/os-release").read_text(encoding="utf-8"),
    "wsl_distro": os.environ.get("WSL_DISTRO_NAME"),
    "wsl_version": command("wsl.exe", "--version"),
    "wsl_status": command("wsl.exe", "--status"),
    "wsl_distributions": command("wsl.exe", "--list", "--verbose"),
    "kernel": platform.release(),
    "architecture": platform.machine(),
    "systemd_status": os.environ.get("SYSTEMD_STATUS"),
    "repository_path": str(repo.resolve()),
    "repository_filesystem": os.environ.get("mount_type"),
    "git_version": command("git", "--version"),
    "git_head": command("git", "-C", str(repo), "rev-parse", "HEAD"),
    "git_branch": command("git", "-C", str(repo), "branch", "--show-current"),
    "git_safe_directories": command("git", "config", "--global", "--get-all", "safe.directory"),
    "python": sys.version.split()[0],
    "numpy": numpy.__version__,
    "scipy": scipy.__version__,
    "matplotlib": matplotlib.__version__,
    "pyyaml": yaml.__version__,
    "pip_freeze": command(str(repo / ".venv/bin/python"), "-m", "pip", "freeze"),
    "codex_version": command("codex", "--version"),
    "node": command("node", "--version"),
    "npm": command("npm", "--version"),
    "node_required_for_codex_install": False,
    "windows_codex_home_copied": False,
    "qualification_ref": os.environ.get("REF"),
}
Path(sys.argv[1]).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

cat <<EOF
Bootstrap complete.
Repository: $REPO_ROOT
Branch: $QUALIFICATION_REF
Codex: $(codex --version)
Python environment: $REPO_ROOT/.venv
Environment report: $artifacts/bootstrap/environment.json

Windows .codex was not copied. Sign in to Codex from this Linux environment before running qualify-core.sh.
EOF
