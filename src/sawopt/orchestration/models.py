"""Durable models used by the asynchronous run manager."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
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

CONTINUATION_MODES = {"disabled", "legacy_resume", "queue"}
CONTINUATION_STATES = {
    "DISABLED", "PENDING", "CLAIMED", "SENDER_ACCEPTED",
    "RECEIVER_CONFIRMED", "AMBIGUOUS",
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
    continuation_mode: str | None = None
    original_thread_id: str | None = None
    c2c_task_id: str | None = None
    plan_iteration: int | None = None
    next_expected_step: str | None = None
    delivery_sentinel: str | None = None
    queue_preflight: dict[str, Any] | None = None
    queue_timeout_seconds: float | None = 120.0

    def __post_init__(self) -> None:
        if self.callback_timeout_minutes is not None and self.callback_timeout_minutes <= 0:
            raise ValueError("callback_timeout_minutes must be positive or None")
        if self.queue_timeout_seconds is not None and self.queue_timeout_seconds <= 0:
            raise ValueError("queue_timeout_seconds must be positive or None")
        mode = self.continuation_mode
        if self.schema_version >= 3 and mode is None:
            raise ValueError(
                "schema-v3 run manifest requires an explicit continuation_mode"
            )
        if mode is None:
            mode = "legacy_resume" if self.callback_enabled else "disabled"
            object.__setattr__(self, "continuation_mode", mode)
        if mode not in CONTINUATION_MODES:
            raise ValueError(f"unknown continuation mode: {mode}")
        if mode == "queue":
            if self.schema_version < 3:
                raise ValueError("queue continuation requires schema version 3 or newer")
            from .codex_queue import validate_thread_id
            thread_id = validate_thread_id(self.original_thread_id or "")
            if thread_id != str(self.original_thread_id).lower():
                raise ValueError("queue manifest thread ID must use canonical lowercase UUID form")
            if not self.c2c_task_id or not self.c2c_task_id.strip():
                raise ValueError("queue manifest requires a C2C task ID")
            if len(self.c2c_task_id) > 80 or any(ord(ch) < 32 for ch in self.c2c_task_id):
                raise ValueError("queue manifest C2C task ID is invalid")
            if self.plan_iteration is None or int(self.plan_iteration) < 0:
                raise ValueError("queue manifest requires a non-negative PLAN iteration")
            if not self.next_expected_step or not self.next_expected_step.strip():
                raise ValueError("queue manifest requires NEXT_EXPECTED_STEP")
            if len(self.next_expected_step) > 512 or any(ord(ch) < 32 for ch in self.next_expected_step):
                raise ValueError("queue manifest NEXT_EXPECTED_STEP is invalid")
            if not self.delivery_sentinel or not re.fullmatch(r"[0-9a-f]{32}", self.delivery_sentinel):
                raise ValueError("queue manifest requires a 32-character delivery sentinel")
            if not self.queue_preflight or self.queue_preflight.get("status") != "PASS":
                raise ValueError("queue manifest requires a passing queue preflight")
            if self.queue_preflight.get("thread_id") != thread_id:
                raise ValueError("queue preflight thread ID does not match the manifest target")
            if not self.queue_preflight.get("codex_executable") or not self.queue_preflight.get("codex_version"):
                raise ValueError("queue preflight must pin the Codex executable and version")
            if not self.queue_preflight.get("explicit_thread") or not self.queue_preflight.get("explicit_message"):
                raise ValueError("queue preflight must confirm explicit --thread and --message")
            if self.queue_timeout_seconds is None:
                raise ValueError("queue mode requires a finite queue timeout")
            if self.callback_enabled:
                raise ValueError("queue manifests must not enable the legacy callback path")
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
            continuation_mode=(
                None if value.get("continuation_mode") is None
                else str(value.get("continuation_mode"))
            ),
            original_thread_id=(
                None if value.get("original_thread_id") is None
                else str(value.get("original_thread_id"))
            ),
            c2c_task_id=(
                None if value.get("c2c_task_id") is None
                else str(value.get("c2c_task_id"))
            ),
            plan_iteration=(
                None if value.get("plan_iteration") is None
                else int(value.get("plan_iteration"))
            ),
            next_expected_step=(
                None if value.get("next_expected_step") is None
                else str(value.get("next_expected_step"))
            ),
            delivery_sentinel=(
                None if value.get("delivery_sentinel") is None
                else str(value.get("delivery_sentinel"))
            ),
            queue_preflight=(
                None if value.get("queue_preflight") is None
                else dict(value.get("queue_preflight"))
            ),
            queue_timeout_seconds=(
                None if value.get("queue_timeout_seconds", 120.0) is None
                else float(value.get("queue_timeout_seconds", 120.0))
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
    continuation_mode: str = "disabled"
    continuation_state: str = "DISABLED"
    continuation_attempt_count: int = 0
    continuation_delivery_id: str | None = None
    continuation_claimed_at: str | None = None
    continuation_command_started_at: str | None = None
    continuation_exit_code: int | None = None
    continuation_acknowledged: bool | None = None
    continuation_error: str | None = None
    continuation_receiver_confirmed_at: str | None = None
    continuation_receiver_thread_id: str | None = None

    def __post_init__(self) -> None:
        if self.state not in RUN_STATES:
            raise ValueError(f"unknown run state: {self.state}")
        if self.continuation_state not in CONTINUATION_STATES:
            raise ValueError(f"unknown continuation state: {self.continuation_state}")

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
            "continuation_mode", "continuation_state", "continuation_attempt_count",
            "continuation_delivery_id", "continuation_claimed_at",
            "continuation_command_started_at", "continuation_exit_code",
            "continuation_acknowledged", "continuation_error",
            "continuation_receiver_confirmed_at", "continuation_receiver_thread_id",
        }
        continuation_mode = value.get("continuation_mode")
        if continuation_mode is None:
            continuation_mode = "legacy_resume" if value.get("callback_enabled") else "disabled"
        defaults = {
            "continuation_mode": continuation_mode,
            "continuation_state": (
                "PENDING" if continuation_mode in {"queue", "legacy_resume"} else "DISABLED"
            ),
        }
        data = {key: value[key] for key in fields if key in value}
        for key, default in defaults.items():
            data.setdefault(key, default)
        return cls(**data)
