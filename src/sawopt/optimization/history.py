"""Buffered JSONL history writing."""
from __future__ import annotations

import json
import time
from pathlib import Path


class HistoryBuffer:
    def __init__(self, path, flush_every=100):
        self.file = Path(path).open("a", encoding="utf-8")
        self.flush_every = max(1, int(flush_every))
        self.pending = []
        self.io_time_s = 0.0

    def write(self, record):
        self.pending.append(json.dumps(record, allow_nan=False) + "\n")
        if len(self.pending) >= self.flush_every:
            self.flush()

    def flush(self):
        started = time.time()
        if self.pending:
            self.file.writelines(self.pending)
            self.pending.clear()
        self.file.flush()
        self.io_time_s += time.time() - started

    def close(self):
        self.flush()
        self.file.close()


__all__ = ["HistoryBuffer"]
