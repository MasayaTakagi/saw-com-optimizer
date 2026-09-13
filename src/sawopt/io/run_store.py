"""Run-directory initialization and manifest creation."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

from .serialization import save


def initialize(out, cfg):
    """Create or validate a run manifest using the historical contract."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    package_root = Path(__file__).parents[1]
    source_hash = hashlib.sha256(b"".join(
        p.relative_to(package_root).as_posix().encode() + p.read_bytes()
        for p in sorted(package_root.rglob("*.py"))
    )).hexdigest()
    fingerprint = hashlib.sha256((json.dumps(cfg, sort_keys=True) + source_hash).encode()).hexdigest()
    if (out / "manifest.json").exists():
        old = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if old["fingerprint"] != fingerprint:
            raise ValueError("Run config mismatch: use a new run directory")
    else:
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        save(out / "manifest.json", dict(
            fingerprint=fingerprint,
            source_hash=source_hash,
            config=cfg,
            git_commit=commit,
            python=sys.version,
            versions={x: importlib.metadata.version(x) for x in ["numpy", "scipy", "matplotlib", "PyYAML"]},
            rounding="floor(x+0.5)",
            limitations=[
                "Hypothetical COM; far-off-synchronous extrapolation is unvalidated",
                "Seed-level restart, not exact DE population continuation",
            ],
        ))
    return out


__all__ = ["initialize"]
