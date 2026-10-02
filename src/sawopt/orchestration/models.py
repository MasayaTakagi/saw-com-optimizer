"""Durable models used by the asynchronous run manager."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


RUN_STATES = (
    "CREATED",
    "STARTING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CALLBACK_PENDING",
    "CALLBACK_RUNNING",
    "REVIEW_WAITING",
    "REVIEWED",
    "CALLBACK_FAILED",
    "ORPHANED",
    "ORPHANED_CHILD",
)

CALLBACK_STATES = {
    "CALLBACK_PENDING",
    "CALLBACK_RUNNING",
    "REVIEWED",
    "CALLBACK_FAILED",
}


@dataclass(frozen=True)
class RunManifest:
    """Immutable description of one optimizer process and its review target."""

    schema_version: int
    run_id: str
    experiment_name: str
    created_at: str
    project_root: str
    run_dir: str
    command: list[str]
    config_path: str | None
    codex_session_id: str | None
    codex_model: str | None
    callback_enabled: bool
    review_after_completion: bool
    callback_timeout_minutes: float | None = 30.0
    codex_session_source: str | None = None
    optimizer_run_dir: str | None = None
    callback_preflight: dict[str, Any] | None = None
    experiment_metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.callback_timeout_minutes is not None and self.callback_timeout_minutes <= 0:
            raise ValueError("callback_timeout_minutes must be positive or None")
        if self.schema_version >= 2:
            if not self.optimizer_run_dir:
                raise ValueError("schema-v2 run manifest requires optimizer_run_dir")
            control_root = Path(self.run_dir).resolve()
            optimizer_root = Path(self.optimizer_run_dir).resolve()
            if optimizer_root == control_root:
                raise ValueError("optimizer_run_dir must be distinct from run_dir")
            try:
                optimizer_root.relative_to(control_root)
            except ValueError as exc:
                raise ValueError("optimizer_run_dir must be nested under run_dir") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def effective_optimizer_run_dir(self) -> str:
        """Study output path, falling back to the control root for old manifests."""
        return str(self.optimizer_run_dir or self.run_dir)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunManifest":
        required = {
            "run_id", "experiment_name", "created_at", "project_root",
            "run_dir", "command", "callback_enabled", "review_after_completion",
        }
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"run manifest is missing fields: {', '.join(missing)}")
        timeout_value = value.get("callback_timeout_minutes", 30.0)
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            run_id=str(value["run_id"]),
            experiment_name=str(value["experiment_name"]),
            created_at=str(value["created_at"]),
            project_root=str(value["project_root"]),
            run_dir=str(value["run_dir"]),
            command=[str(item) for item in value["command"]],
            config_path=None if value.get("config_path") is None else str(value["config_path"]),
            codex_session_id=(
                None if value.get("codex_session_id") in (None, "")
                else str(value["codex_session_id"])
            ),
            codex_model=None if value.get("codex_model") is None else str(value["codex_model"]),
            callback_enabled=bool(value["callback_enabled"]),
            review_after_completion=bool(value["review_after_completion"]),
            callback_timeout_minutes=None if timeout_value is None else float(timeout_value),
            codex_session_source=(
                None if value.get("codex_session_source") is None
                else str(value.get("codex_session_source"))
            ),
            optimizer_run_dir=(
                None if value.get("optimizer_run_dir") in (None, "")
                else str(value["optimizer_run_dir"])
            ),
            callback_preflight=(
                None if value.get("callback_preflight") is None
                else dict(value["callback_preflight"])
            ),
            experiment_metadata=(
                None if value.get("experiment_metadata") is None
                else dict(value["experiment_metadata"])
            ),
        )


@dataclass
class RunStatus:
    """Mutable state persisted separately from :class:`RunManifest`."""

    state: str
    updated_at: str
    worker_pid: int | None = None
    optimizer_pid: int | None = None
    exit_code: int | None = None
    callback_attempts: int = 0
    callback_completed: bool = False
    callback_exit_code: int | None = None
    callback_enabled: bool = False
    optimizer_state: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    callback_started_at: str | None = None
    callback_finished_at: str | None = None
    resume_count: int = 0
    last_attached_at: str | None = None
    session_checkpoint_path: str | None = None

    def __post_init__(self) -> None:
        if self.state not in RUN_STATES:
            raise ValueError(f"unknown run state: {self.state}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunStatus":
        fields = {
            "state", "updated_at", "worker_pid", "optimizer_pid", "exit_code",
            "callback_attempts", "callback_completed", "callback_exit_code",
            "callback_enabled", "optimizer_state", "error", "started_at",
            "finished_at", "callback_started_at", "callback_finished_at",
            "resume_count", "last_attached_at", "session_checkpoint_path",
        }
        return cls(**{key: value[key] for key in fields if key in value})
