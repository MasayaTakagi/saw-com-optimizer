"""Stable JSON serialization used by run artifacts."""
from __future__ import annotations

import json
from pathlib import Path


def save(path, data):
    """Atomically write a JSON-serializable run artifact."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    tmp.replace(path)


__all__ = ["save"]
