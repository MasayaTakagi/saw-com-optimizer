"""Durable models used by the asynchronous run manager."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
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
REVIEW_EVIDENCE_STATES = {"PENDING", "EXPORTED", "PUBLISHED"}


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
    continuation_mode: str | None = None
    original_thread_id: str | None = None
    c2c_task_id: str | None = None  # schema-v3 compatibility only
    plan_iteration: int | None = None  # schema-v3 compatibility only
    next_expected_step: str | None = None
    delivery_sentinel: str | None = None
    queue_preflight: dict[str, Any] | None = None
    queue_timeout_seconds: float | None = 120.0
    review_stage: str | None = None
    review_contract_version: str | None = None
    review_output_dir: str | None = None
    review_spec_id: str | None = None
    review_spec_sha256: str | None = None
    review_spec: dict[str, Any] | None = None
    source_commit_sha: str | None = None
    source_branch: str | None = None
    study_type: str | None = None
    run_storage_policy: str | None = None
    persistent_run_root: str | None = None
    repository_root_at_launch: str | None = None
    source_worktree_at_launch: str | None = None

    def __post_init__(self) -> None:
        if self.callback_timeout_minutes is not None and self.callback_timeout_minutes <= 0:
            raise ValueError("callback_timeout_minutes must be positive or None")
        if self.queue_timeout_seconds is not None and self.queue_timeout_seconds <= 0:
            raise ValueError("queue_timeout_seconds must be positive or None")
        if self.schema_version not in {1, 2, 3, 4}:
            raise ValueError(f"unsupported run manifest schema version: {self.schema_version}")
        mode = self.continuation_mode
        if self.schema_version >= 3 and mode is None:
            raise ValueError("schema-v3+ run manifest requires an explicit continuation_mode")
        if mode is None:
            mode = "legacy_resume" if self.callback_enabled else "disabled"
            object.__setattr__(self, "continuation_mode", mode)
        if mode not in CONTINUATION_MODES:
            raise ValueError(f"unknown continuation mode: {mode}")
        if mode == "queue":
            from .codex_queue import validate_thread_id
            thread_id = validate_thread_id(self.original_thread_id or "")
            if thread_id != str(self.original_thread_id).lower():
                raise ValueError("queue manifest thread ID must use canonical lowercase UUID form")
            if not self.next_expected_step or len(self.next_expected_step) > 512:
                raise ValueError("queue manifest requires a bounded NEXT_EXPECTED_STEP")
            if not self.delivery_sentinel or not re.fullmatch(r"[0-9a-f]{32}", self.delivery_sentinel):
                raise ValueError("queue manifest requires a 32-character delivery sentinel")
            if not self.queue_preflight or self.queue_preflight.get("status") != "PASS":
                raise ValueError("queue manifest requires a passing queue preflight")
            if self.queue_preflight.get("thread_id") != thread_id:
                raise ValueError("queue preflight thread ID does not match manifest target")
            if (not self.queue_preflight.get("codex_executable")
                    or not self.queue_preflight.get("codex_version")
                    or not self.queue_preflight.get("explicit_thread")
                    or not self.queue_preflight.get("explicit_message")):
                raise ValueError("queue preflight must pin executable/version and explicit queue flags")
            if self.queue_timeout_seconds is None:
                raise ValueError("queue mode requires a finite sender timeout")
            if self.callback_enabled or self.codex_session_id is not None:
                raise ValueError("queue routing cannot use the legacy session callback identity")
            if self.schema_version == 4 and not self.review_after_completion:
                raise ValueError("schema-v4 queue runs require a post-completion publisher handoff")
            if self.schema_version == 3:
                if not self.c2c_task_id or self.plan_iteration is None or int(self.plan_iteration) < 0:
                    raise ValueError("historical schema-v3 queue manifests require C2C task/iteration fields")
            elif self.schema_version == 4:
                if not self.review_stage or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", self.review_stage):
                    raise ValueError("schema-v4 queue manifest requires a safe review_stage")
                if not self.review_contract_version or not self.review_spec_id or not self.review_spec:
                    raise ValueError("schema-v4 queue manifest requires frozen review contract/spec metadata")
                expected = f"reports/experiment_reviews/{self.review_stage}/{self.run_id}"
                if str(self.review_output_dir or "").replace("\\", "/").strip("/") != expected:
                    raise ValueError("schema-v4 review_output_dir must be canonical for stage and run")
        elif mode == "disabled":
            if self.callback_enabled or self.codex_session_id is not None:
                raise ValueError("disabled continuation cannot carry legacy callback identity")
        elif self.schema_version == 4:
            raise ValueError("new schema-v4 launches may not select legacy_resume")
        if self.schema_version == 4 and mode not in {"queue", "disabled"}:
            raise ValueError("schema-v4 supports only queue or disabled continuation")
        if self.schema_version == 4:
            if self.c2c_task_id is not None or self.plan_iteration is not None:
                raise ValueError("schema-v4 manifests must not contain C2C routing metadata")
            if not self.review_stage or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", self.review_stage):
                raise ValueError("schema-v4 manifest requires a safe review_stage")
            if not self.review_contract_version or not self.review_spec_id or not self.review_spec:
                raise ValueError("schema-v4 manifest requires frozen review contract/spec metadata")
            declared_spec_id = str(self.review_spec.get("spec_id", ""))
            if (declared_spec_id != self.review_spec_id
                    and not declared_spec_id.startswith(self.review_spec_id + "_")):
                raise ValueError("schema-v4 review spec ID differs from its frozen specification")
            study_types = self.review_spec.get("study_types", ())
            if self.study_type and study_types and self.study_type not in study_types:
                raise ValueError("schema-v4 review spec does not cover the declared study type")
            if not re.fullmatch(r"[0-9a-f]{64}", str(self.review_spec_sha256 or "")):
                raise ValueError("schema-v4 manifest requires review_spec_sha256")
            spec_hash = hashlib.sha256(json.dumps(
                self.review_spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest()
            if spec_hash != self.review_spec_sha256:
                raise ValueError("schema-v4 frozen review spec hash mismatch")
            expected = f"reports/experiment_reviews/{self.review_stage}/{self.run_id}"
            if str(self.review_output_dir or "").replace("\\", "/").strip("/") != expected:
                raise ValueError("schema-v4 review_output_dir must be canonical for stage and run")
            if mode == "disabled" and self.review_after_completion:
                raise ValueError("disabled continuation cannot request an automatic publisher handoff")
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
        storage_fields = (
            self.run_storage_policy, self.persistent_run_root,
            self.repository_root_at_launch, self.source_worktree_at_launch,
        )
        if any(value is not None for value in storage_fields):
            if not all(value is not None for value in storage_fields):
                raise ValueError("run storage provenance fields must be supplied together")
            if self.run_storage_policy != "external_persistent_v1":
                raise ValueError("unknown run storage policy")
            if not Path(str(self.persistent_run_root)).is_absolute():
                raise ValueError("persistent_run_root must be absolute")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if self.run_storage_policy is None:
            value.pop("run_storage_policy", None)
            value.pop("persistent_run_root", None)
            value.pop("repository_root_at_launch", None)
            value.pop("source_worktree_at_launch", None)
        if self.schema_version >= 4:
            value.pop("c2c_task_id", None)
            value.pop("plan_iteration", None)
        return value

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
            continuation_mode=(None if value.get("continuation_mode") is None
                               else str(value["continuation_mode"])),
            original_thread_id=None if value.get("original_thread_id") is None else str(value["original_thread_id"]),
            c2c_task_id=None if value.get("c2c_task_id") is None else str(value["c2c_task_id"]),
            plan_iteration=None if value.get("plan_iteration") is None else int(value["plan_iteration"]),
            next_expected_step=None if value.get("next_expected_step") is None else str(value["next_expected_step"]),
            delivery_sentinel=None if value.get("delivery_sentinel") is None else str(value["delivery_sentinel"]),
            queue_preflight=None if value.get("queue_preflight") is None else dict(value["queue_preflight"]),
            queue_timeout_seconds=(None if value.get("queue_timeout_seconds", 120.0) is None
                                   else float(value.get("queue_timeout_seconds", 120.0))),
            review_stage=None if value.get("review_stage") is None else str(value["review_stage"]),
            review_contract_version=None if value.get("review_contract_version") is None else str(value["review_contract_version"]),
            review_output_dir=None if value.get("review_output_dir") is None else str(value["review_output_dir"]),
            review_spec_id=None if value.get("review_spec_id") is None else str(value["review_spec_id"]),
            review_spec_sha256=None if value.get("review_spec_sha256") is None else str(value["review_spec_sha256"]),
            review_spec=None if value.get("review_spec") is None else dict(value["review_spec"]),
            source_commit_sha=None if value.get("source_commit_sha") is None else str(value["source_commit_sha"]),
            source_branch=None if value.get("source_branch") is None else str(value["source_branch"]),
            study_type=None if value.get("study_type") is None else str(value["study_type"]),
            run_storage_policy=(None if value.get("run_storage_policy") is None else str(value["run_storage_policy"])),
            persistent_run_root=(None if value.get("persistent_run_root") is None else str(value["persistent_run_root"])),
            repository_root_at_launch=(None if value.get("repository_root_at_launch") is None else str(value["repository_root_at_launch"])),
            source_worktree_at_launch=(None if value.get("source_worktree_at_launch") is None else str(value["source_worktree_at_launch"])),
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
    error_type: str | None = None
    error_message: str | None = None
    error_repr: str | None = None
    error_traceback_path: str | None = None
    failing_cell: dict[str, Any] | None = None
    last_durable_checkpoint_budget: int | None = None
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
    review_evidence_state: str = "PENDING"
    review_output_dir: str | None = None
    review_publication_branch: str | None = None
    review_publication_commit: str | None = None
    review_exported_at: str | None = None
    review_published_at: str | None = None

    def __post_init__(self) -> None:
        if self.state not in RUN_STATES:
            raise ValueError(f"unknown run state: {self.state}")
        if self.continuation_state not in CONTINUATION_STATES:
            raise ValueError(f"unknown continuation state: {self.continuation_state}")
        if self.review_evidence_state not in REVIEW_EVIDENCE_STATES:
            raise ValueError(f"unknown review evidence state: {self.review_evidence_state}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunStatus":
        fields = {
            "state", "updated_at", "worker_pid", "optimizer_pid", "exit_code",
            "callback_attempts", "callback_completed", "callback_exit_code",
            "callback_enabled", "optimizer_state", "error", "started_at",
            "error_type", "error_message", "error_repr", "error_traceback_path",
            "failing_cell", "last_durable_checkpoint_budget",
            "finished_at", "callback_started_at", "callback_finished_at",
            "resume_count", "last_attached_at", "session_checkpoint_path",
            "continuation_mode", "continuation_state", "continuation_attempt_count",
            "continuation_delivery_id", "continuation_claimed_at",
            "continuation_command_started_at", "continuation_exit_code",
            "continuation_acknowledged", "continuation_error",
            "continuation_receiver_confirmed_at", "continuation_receiver_thread_id",
            "review_evidence_state", "review_output_dir", "review_publication_branch",
            "review_publication_commit", "review_exported_at", "review_published_at",
        }
        return cls(**{key: value[key] for key in fields if key in value})
