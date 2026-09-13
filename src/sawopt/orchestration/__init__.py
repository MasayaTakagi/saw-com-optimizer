"""Asynchronous run orchestration for long-running optimizer jobs.

The orchestration package owns process lifetime, durable run state, and the
optional Codex review callback.  COM and optimizer modules remain unaware of
Codex and can still be run synchronously through the existing entry points.
"""

from .models import (
    CALLBACK_STATES,
    RUN_STATES,
    RunManifest,
    RunStatus,
)

__all__ = [
    "CALLBACK_STATES",
    "RUN_STATES",
    "RunManifest",
    "RunStatus",
]
