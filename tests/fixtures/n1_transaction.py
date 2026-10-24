"""Test-owned N1 transaction seam; never imported by the product CLI."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator, Mapping

from sawopt.io.cli_config import load_synthetic_config
from sawopt.io.experiment_store import ExperimentRun, create_experiment_run

BASE_SOURCE_SHA = "63f837b14ba12be6fe4299b1e1759d423f655da2"
AUTHORIZATION_REFERENCE = "https://github.com/MasayaTakagi/saw-com-optimizer/issues/96#issuecomment-6380953524"
JOURNAL_NAME = "n1-test-journal.sqlite3"
_JOURNAL_SCHEMA_VERSION = 1
_SCHEMA = {
    "runs": """CREATE TABLE runs (
        run_id TEXT PRIMARY KEY,
        request_json TEXT NOT NULL,
        request_sha256 TEXT NOT NULL,
        current_attempt_id TEXT NOT NULL,
        attempt_generation INTEGER NOT NULL CHECK(attempt_generation >= 1),
        state TEXT NOT NULL CHECK(state IN ('READY','RUNNING','CHECKPOINT_INTENT','CHECKPOINTED','AMBIGUOUS','CLOSED','EXPORT_INTENT','EXPORT_READY')),
        checkpoint_intent_json TEXT,
        checkpoint_receipt_json TEXT,
        export_intent_json TEXT,
        export_receipt_json TEXT
    )""",
    "attempts": """CREATE TABLE attempts (
        attempt_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        generation INTEGER NOT NULL CHECK(generation >= 1),
        predecessor_attempt_id TEXT,
        state TEXT NOT NULL CHECK(state IN ('CREATED','CLAIMED','CHECKPOINTED','SUPERSEDED')),
        UNIQUE(run_id,generation)
    )""",
    "evaluations": """CREATE TABLE evaluations (
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        cell_id TEXT NOT NULL,
        result_key TEXT NOT NULL,
        candidate_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('CLAIMED','COMMITTED')),
        claim_attempt_id TEXT NOT NULL,
        result_json TEXT,
        result_sha256 TEXT,
        PRIMARY KEY(run_id,cell_id,result_key)
    )""",
}


class N1RecoveryError(RuntimeError):
    """Fail-closed test-journal state or identity error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def evaluation_result_key(request: Mapping[str, Any], cell_id: str, candidate: list[float]) -> str:
    return digest({
        "run_id": request["run_id"], "cell_id": cell_id,
        "candidate": candidate, "model_sha256": request["model_sha256"],
        "search_grid_sha256": request["search_grid_sha256"],
    })


def _safe_test_root(path: Path, *, raw_run: Path | None = None) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise N1RecoveryError("TEST_ROOT_UNSAFE", "test journal root must be an explicit absolute path")
    candidate = path.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise N1RecoveryError("TEST_ROOT_UNSAFE", "test journal path may not contain symlinks")
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or not resolved.is_dir():
        raise N1RecoveryError("TEST_ROOT_UNSAFE", "test journal root identity is unresolved")
    info = os.stat(resolved)
    if not hasattr(os, "getuid") or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise N1RecoveryError("TEST_ROOT_UNSAFE", "test journal root must be private and user-owned")
    repository = Path(__file__).resolve().parents[2]
    if resolved.is_relative_to(repository):
        raise N1RecoveryError("TEST_ROOT_UNSAFE", "test journal root may not be inside a repository")
    try:
        from sawopt.io.experiment_store import _discover_worktree_roots

        if any(resolved.is_relative_to(worktree) for worktree in _discover_worktree_roots(repository)):
            raise N1RecoveryError("TEST_ROOT_UNSAFE", "test journal root may not alias a registered worktree")
    except N1RecoveryError:
        raise
    except Exception as exc:
        raise N1RecoveryError("TEST_ROOT_UNSAFE", "cannot establish repository/worktree exclusions") from exc
    if raw_run is not None:
        raw = raw_run.resolve(strict=True)
        raw_root = raw.parents[2]
        if any(
            resolved.is_relative_to(protected) or protected.is_relative_to(resolved)
            for protected in (raw, raw_root)
        ):
            raise N1RecoveryError("TEST_ROOT_UNSAFE", "journal and the complete R5 data-root tree must be separate")
    return resolved


class N1RecoveryJournal:
    """A tiny fresh-root WAL journal exclusively for deterministic N1 fixtures."""

    def __init__(
        self, root: str | os.PathLike[str], *, raw_run: str | os.PathLike[str] | None = None,
        create: bool = True,
    ):
        self.root = _safe_test_root(Path(root), raw_run=Path(raw_run) if raw_run is not None else None)
        self.path = self.root / JOURNAL_NAME
        if create:
            with os.scandir(self.root) as entries:
                if next(entries, None) is not None:
                    raise N1RecoveryError("TEST_ROOT_UNSAFE", "N1 journal initialization requires a fresh empty root")
            if self.path.exists() or self.path.is_symlink():
                raise N1RecoveryError("TEST_ROOT_UNSAFE", "N1 journal path already exists; use a fresh test root")
            self._initialize()
        else:
            self._validate_existing()

    @classmethod
    def open_existing(
        cls, root: str | os.PathLike[str], *, raw_run: str | os.PathLike[str],
    ) -> "N1RecoveryJournal":
        return cls(root, raw_run=raw_run, create=False)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        old_umask = os.umask(0o077)
        try:
            with contextlib.closing(self._connect()) as connection:
                mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(mode).lower() != "wal":
                    raise N1RecoveryError("JOURNAL_UNAVAILABLE", "test journal refused WAL mode")
                connection.execute("BEGIN IMMEDIATE")
                for sql in _SCHEMA.values():
                    connection.execute(sql)
                connection.execute(f"PRAGMA user_version={_JOURNAL_SCHEMA_VERSION}")
                connection.commit()
            os.chmod(self.path, 0o600)
        except Exception:
            if self.path.exists():
                self.path.unlink()
            raise
        finally:
            os.umask(old_umask)

    def _validate_existing(self) -> None:
        try:
            entries = set(os.listdir(self.root))
            allowed = {JOURNAL_NAME, JOURNAL_NAME + "-wal", JOURNAL_NAME + "-shm"}
            if JOURNAL_NAME not in entries or entries - allowed:
                raise N1RecoveryError("JOURNAL_CORRUPT", "existing test-journal root has an unexpected file set")
            for name in entries:
                info = os.lstat(self.root / name)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) & 0o077):
                    raise N1RecoveryError("TEST_ROOT_UNSAFE", "existing journal artifacts must be private regular files")
            uri = self.path.as_uri() + "?mode=ro"
            with contextlib.closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.execute("PRAGMA query_only=ON")
                if str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal":
                    raise N1RecoveryError("JOURNAL_SCHEMA_UNKNOWN", "existing test journal is not WAL")
                self._validate_schema(connection)
        except N1RecoveryError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise N1RecoveryError("JOURNAL_CORRUPT", "cannot validate existing test journal") from exc

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = {
            (row[0], row[1]) for row in connection.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'",
            )
        }
        if version != _JOURNAL_SCHEMA_VERSION or objects != {("table", name) for name in _SCHEMA}:
            raise N1RecoveryError("JOURNAL_SCHEMA_UNKNOWN", "test-journal schema identity is unsupported")
        for table, expected_sql in _SCHEMA.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone()
            if row is None or " ".join(row[0].split()) != " ".join(expected_sql.split()):
                raise N1RecoveryError("JOURNAL_SCHEMA_UNKNOWN", "test-journal table definition changed")

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            self._validate_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def register(self, request: Mapping[str, Any], *, attempt_id: str | None = None) -> str:
        value = dict(request)
        if value.get("authorization_test_only") is not True:
            raise N1RecoveryError("IDENTITY_MISMATCH", "N1 request must be explicitly test-authorized")
        if value.get("authorization_reference") != AUTHORIZATION_REFERENCE:
            raise N1RecoveryError("IDENTITY_MISMATCH", "N1 request must cite the exact owner authorization")
        run_id = value.get("run_id")
        if not isinstance(run_id, str) or re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", run_id) is None:
            raise N1RecoveryError("IDENTITY_MISMATCH", "N1 run_id must be the exact R5 run identity")
        attempt_id = attempt_id or uuid.uuid4().hex
        if attempt_id == run_id or re.fullmatch(r"[0-9a-f]{32}", attempt_id) is None:
            raise N1RecoveryError("IDENTITY_MISMATCH", "attempt_id must be distinct from run_id")
        request_json = canonical_json(value)
        request_sha = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        with self._transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,1,'READY',NULL,NULL,NULL,NULL)",
                    (run_id, request_json, request_sha, attempt_id),
                )
                connection.execute(
                    "INSERT INTO attempts VALUES (?,?,1,NULL,'CREATED')", (attempt_id, run_id),
                )
            except sqlite3.IntegrityError as exc:
                raise N1RecoveryError("DUPLICATE_RUN", "run or attempt identity already exists") from exc
        return attempt_id

    def identity(self, run_id: str) -> dict[str, Any]:
        with contextlib.closing(self._connect()) as connection:
            row = connection.execute("SELECT request_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise N1RecoveryError("TASK_NOT_FOUND", "N1 run identity is absent")
        return json.loads(row[0])

    def _run(self, connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise N1RecoveryError("TASK_NOT_FOUND", "N1 run identity is absent")
        if hashlib.sha256(row["request_json"].encode("utf-8")).hexdigest() != row["request_sha256"]:
            raise N1RecoveryError("JOURNAL_CORRUPT", "frozen N1 identity hash does not match")
        return row

    def claim_attempt(self, run_id: str, attempt_id: str) -> None:
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["current_attempt_id"] != attempt_id or row["state"] not in {"READY", "RUNNING"}:
                raise N1RecoveryError("ATTEMPT_MISMATCH", "attempt is not the current claimable N1 attempt")
            cursor = connection.execute(
                "UPDATE attempts SET state='CLAIMED' WHERE attempt_id=? AND run_id=? AND state='CREATED'",
                (attempt_id, run_id),
            )
            if cursor.rowcount != 1:
                raise N1RecoveryError("DUPLICATE_CLAIM", "attempt claim is already committed")
            connection.execute("UPDATE runs SET state='RUNNING' WHERE run_id=?", (run_id,))

    def claim_evaluation(self, run_id: str, attempt_id: str, cell_id: str, result_key: str, candidate: list[float]) -> None:
        if (not isinstance(candidate, list) or len(candidate) != 1
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(float(value)) for value in candidate)):
            raise N1RecoveryError("IDENTITY_MISMATCH", "FE candidate must be one finite synthetic scalar")
        candidate = [float(value) for value in candidate]
        candidate_json = canonical_json(candidate)
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            request = json.loads(row["request_json"])
            if (cell_id not in {cell["cell_id"] for cell in request["expected_cells"]}
                    or result_key != evaluation_result_key(request, cell_id, candidate)):
                raise N1RecoveryError("IDENTITY_MISMATCH", "FE key/candidate does not match frozen run identity")
            attempt = connection.execute(
                "SELECT state FROM attempts WHERE attempt_id=? AND run_id=?", (attempt_id, run_id),
            ).fetchone()
            if (row["state"] != "RUNNING" or row["current_attempt_id"] != attempt_id
                    or attempt is None or attempt["state"] != "CLAIMED"):
                raise N1RecoveryError("ATTEMPT_MISMATCH", "FE claim is not fenced by the current attempt")
            existing = connection.execute(
                "SELECT state FROM evaluations WHERE run_id=? AND cell_id=? AND result_key=?",
                (run_id, cell_id, result_key),
            ).fetchone()
            if existing is not None:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "FE key is already claimed or committed; no retry")
            connection.execute(
                "INSERT INTO evaluations VALUES (?,?,?,?,'CLAIMED',?,NULL,NULL)",
                (run_id, cell_id, result_key, candidate_json, attempt_id),
            )

    def commit_evaluation(
        self, run_id: str, attempt_id: str, cell_id: str, result_key: str,
        result: Mapping[str, Any], *, fail_before_commit: bool = False,
    ) -> None:
        result_value = dict(result)
        supplied_candidate = result_value.get("candidate_vector")
        if (not isinstance(supplied_candidate, list) or len(supplied_candidate) != 1
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(float(value)) for value in supplied_candidate)):
            raise N1RecoveryError("IDENTITY_MISMATCH", "result must identify its finite synthetic candidate")
        result_json = canonical_json(result_value)
        result_sha = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["state"] != "RUNNING" or row["current_attempt_id"] != attempt_id:
                raise N1RecoveryError("ATTEMPT_MISMATCH", "result commit is not fenced by the current attempt")
            claimed = connection.execute(
                "SELECT candidate_json FROM evaluations WHERE run_id=? AND cell_id=? AND result_key=? "
                "AND claim_attempt_id=? AND state='CLAIMED'",
                (run_id, cell_id, result_key, attempt_id),
            ).fetchone()
            if claimed is None:
                raise N1RecoveryError("DUPLICATE_RESULT", "result commit was absent, stale, or already committed")
            normalized_candidate = canonical_json([float(value) for value in supplied_candidate])
            if normalized_candidate != claimed[0]:
                raise N1RecoveryError("IDENTITY_MISMATCH", "result candidate differs from its fenced FE claim")
            cursor = connection.execute(
                "UPDATE evaluations SET state='COMMITTED',result_json=?,result_sha256=? "
                "WHERE run_id=? AND cell_id=? AND result_key=? AND claim_attempt_id=? AND state='CLAIMED'",
                (result_json, result_sha, run_id, cell_id, result_key, attempt_id),
            )
            if cursor.rowcount != 1:
                raise N1RecoveryError("DUPLICATE_RESULT", "result commit was absent, stale, or already committed")
            if fail_before_commit:
                raise OSError("injected SQLite transaction interruption before commit")

    def _results(self, connection: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
        run = self._run(connection, run_id)
        request = json.loads(run["request_json"])
        rows = connection.execute(
            "SELECT cell_id,result_key,candidate_json,state,result_json,result_sha256 "
            "FROM evaluations WHERE run_id=? ORDER BY cell_id,result_key", (run_id,),
        ).fetchall()
        result = []
        for cell_id, key, candidate_json, state, result_json, result_sha in rows:
            candidate = json.loads(candidate_json)
            try:
                value = json.loads(result_json) if result_json is not None else None
                result_candidate = value.get("candidate_vector") if isinstance(value, dict) else None
                normalized_result_candidate = (
                    canonical_json([float(item) for item in result_candidate])
                    if isinstance(result_candidate, list) and len(result_candidate) == 1
                    and all(not isinstance(item, bool) and isinstance(item, (int, float))
                            and math.isfinite(float(item)) for item in result_candidate)
                    else None
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                normalized_result_candidate = None
                value = None
            if (not isinstance(candidate, list) or len(candidate) != 1
                    or any(isinstance(item, bool) or not isinstance(item, (int, float))
                           or not math.isfinite(float(item)) for item in candidate)
                    or state != "COMMITTED" or result_json is None
                    or hashlib.sha256(result_json.encode("utf-8")).hexdigest() != result_sha
                    or key != evaluation_result_key(request, cell_id, candidate)
                    or normalized_result_candidate != canonical_json([float(item) for item in candidate])):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "uncommitted, corrupt, or mis-keyed evaluator result blocks recovery")
            result.append({
                "cell_id": cell_id, "result_key": key, "candidate": candidate,
                "result": value, "result_sha256": result_sha,
            })
        return result

    def checkpoint_intent(self, run_id: str, attempt_id: str, optimizer_state: Mapping[str, Any]) -> dict[str, Any]:
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["state"] != "RUNNING" or row["current_attempt_id"] != attempt_id:
                raise N1RecoveryError("ATTEMPT_MISMATCH", "checkpoint intent is not owned by the current attempt")
            results = self._results(connection, run_id)
            request = json.loads(row["request_json"])
            if len(results) != optimizer_state.get("unique_evaluations"):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "result journal and optimizer unique-FE count disagree")
            receipt = {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "attempt_generation": row["attempt_generation"],
                "identity_sha256": row["request_sha256"],
                "optimizer_state_sha256": digest(dict(optimizer_state)),
                "result_keys": [item["result_key"] for item in results],
                "result_keys_sha256": digest([item["result_key"] for item in results]),
                "result_count": len(results),
                "unique_evaluations": int(optimizer_state.get("unique_evaluations", -1)),
                "proposals_total": int(optimizer_state.get("proposals_total", -1)),
                "duplicate_count": int(optimizer_state.get("duplicate_count", -1)),
                "cache_hits": int(optimizer_state.get("cache_hits", -1)),
                "budget": request["budget"],
                "requested_unique_budget": request["requested_unique_budget"],
                "hard_max_budget": request["hard_max_budget"],
            }
            if (receipt["unique_evaluations"] > receipt["budget"]
                    or receipt["unique_evaluations"] > receipt["requested_unique_budget"]
                    or receipt["unique_evaluations"] > receipt["hard_max_budget"]):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "optimizer state exceeds frozen synthetic budget")
            connection.execute(
                "UPDATE runs SET state='CHECKPOINT_INTENT',checkpoint_intent_json=? WHERE run_id=?",
                (canonical_json(receipt), run_id),
            )
            return receipt

    def _commit_checkpoint(
        self, run_id: str, receipt: Mapping[str, Any], checkpoint_sha256: str,
    ) -> None:
        saved = dict(receipt)
        saved["checkpoint_sha256"] = checkpoint_sha256
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["state"] != "CHECKPOINT_INTENT" or row["checkpoint_intent_json"] != canonical_json(dict(receipt)):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint receipt has no exact durable intent")
            attempt = connection.execute(
                "UPDATE attempts SET state='CHECKPOINTED' WHERE attempt_id=? AND run_id=? AND state='CLAIMED'",
                (receipt["attempt_id"], run_id),
            )
            task = connection.execute(
                "UPDATE runs SET state='CHECKPOINTED',checkpoint_receipt_json=? "
                "WHERE run_id=? AND current_attempt_id=? AND state='CHECKPOINT_INTENT'",
                (canonical_json(saved), run_id, receipt["attempt_id"]),
            )
            if attempt.rowcount != 1 or task.rowcount != 1:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint attempt/task receipt did not commit together")

    def reconcile_checkpoint(
        self, run_id: str, payload: Mapping[str, Any], checkpoint_sha256: str,
    ) -> dict[str, Any]:
        """Accept a lost checkpoint ACK only when exact intent and file state match."""
        with contextlib.closing(self._connect()) as connection:
            row = self._run(connection, run_id)
            if row["state"] != "CHECKPOINT_INTENT" or row["checkpoint_intent_json"] is None:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint has no pending durable intent")
            receipt = json.loads(row["checkpoint_intent_json"])
            optimizer_state = {key: value for key, value in payload.items() if key != "extra_state"}
            extra = payload.get("extra_state")
            if (not isinstance(extra, Mapping)
                    or extra.get("n1_receipt") != receipt
                    or digest(optimizer_state) != receipt["optimizer_state_sha256"]
                    or digest(dict(payload)) != checkpoint_sha256
                    or optimizer_state.get("unique_evaluations") != receipt["result_count"]
                    or optimizer_state.get("unique_evaluations", receipt["budget"] + 1) > receipt["budget"]
                    or optimizer_state.get("unique_evaluations", receipt["requested_unique_budget"] + 1) > receipt["requested_unique_budget"]
                    or optimizer_state.get("unique_evaluations", receipt["hard_max_budget"] + 1) > receipt["hard_max_budget"]
                    or optimizer_state.get("proposals_total") != receipt["proposals_total"]
                    or optimizer_state.get("duplicate_count") != receipt["duplicate_count"]
                    or optimizer_state.get("cache_hits") != receipt["cache_hits"]):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint does not match its durable intent")
            results = self._results(connection, run_id)
            keys = [item["result_key"] for item in results]
            if keys != receipt["result_keys"] or digest(keys) != receipt["result_keys_sha256"]:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint result keys do not reconcile")
            cache_versions = optimizer_state.get("cache_frequency_versions", [])
            cache_values = optimizer_state.get("cache", [])
            cached_by_candidate = {canonical_json(item[0]): item[1] for item in cache_values}
            if (len(cache_versions) != receipt["result_count"] or len(cache_values) != receipt["result_count"]
                    or any(cached_by_candidate.get(canonical_json(item["candidate"])) != item["result"]
                           for item in results)):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint optimizer cache does not reconcile")
        self._commit_checkpoint(run_id, receipt, checkpoint_sha256)
        return self.verify_checkpoint(run_id, payload)

    def verify_checkpoint(self, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        with contextlib.closing(self._connect()) as connection:
            row = self._run(connection, run_id)
            expected_json = row["checkpoint_receipt_json"]
            if row["state"] != "CHECKPOINTED" or expected_json is None:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "run has no committed checkpoint receipt")
            receipt = json.loads(expected_json)
            request = json.loads(row["request_json"])
            if digest(dict(payload)) != receipt["checkpoint_sha256"]:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint file hash differs from its committed receipt")
            expected_state_sha = receipt["optimizer_state_sha256"]
            optimizer_state = {key: value for key, value in payload.items() if key != "extra_state"}
            extra = payload.get("extra_state")
            if not isinstance(extra, Mapping) or extra.get("n1_receipt") != {
                key: value for key, value in receipt.items() if key != "checkpoint_sha256"
            }:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint receipt identity differs from the journal")
            if digest(optimizer_state) != expected_state_sha:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "optimizer state hash differs from checkpoint receipt")
            if optimizer_state.get("unique_evaluations") != receipt["result_count"]:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint FE count differs from committed result count")
            if (optimizer_state.get("unique_evaluations", request["budget"] + 1) > request["budget"]
                    or optimizer_state.get("unique_evaluations", request["requested_unique_budget"] + 1) > request["requested_unique_budget"]
                    or optimizer_state.get("unique_evaluations", request["hard_max_budget"] + 1) > request["hard_max_budget"]
                    or receipt.get("requested_unique_budget") != request["requested_unique_budget"]
                    or receipt.get("hard_max_budget") != request["hard_max_budget"]):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "checkpoint exceeds frozen budget")
            results = self._results(connection, run_id)
            keys = [item["result_key"] for item in results]
            if keys != receipt["result_keys"] or digest(keys) != receipt["result_keys_sha256"]:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "result journal and checkpoint key roster disagree")
            cache_versions = optimizer_state.get("cache_frequency_versions", [])
            cache_values = optimizer_state.get("cache", [])
            if len(cache_versions) != receipt["result_count"] or len(cache_values) != receipt["result_count"]:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "optimizer cache and result journal counts disagree")
            cached_by_candidate = {canonical_json(item[0]): item[1] for item in cache_values}
            for item in results:
                if cached_by_candidate.get(canonical_json(item["candidate"])) != item["result"]:
                    raise N1RecoveryError("RECOVERY_AMBIGUOUS", "optimizer cache result differs from durable journal")
            if (optimizer_state.get("proposals_total") != receipt["proposals_total"]
                    or optimizer_state.get("duplicate_count") != receipt["duplicate_count"]
                    or optimizer_state.get("cache_hits") != receipt["cache_hits"]):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "optimizer counters differ from checkpoint receipt")
            return receipt

    def resume(
        self, run_id: str, expected_attempt_id: str, identity: Mapping[str, Any],
        checkpoint_payload: Mapping[str, Any] | None = None,
    ) -> str:
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if digest(dict(identity)) != row["request_sha256"]:
                raise N1RecoveryError("IDENTITY_MISMATCH", "resume request differs from frozen run identity")
            if row["state"] != "CHECKPOINTED" or row["current_attempt_id"] != expected_attempt_id:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "resume requires the exact checkpointed predecessor")
            if checkpoint_payload is None:
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "resume requires the exact validated checkpoint payload")
            receipt = json.loads(row["checkpoint_receipt_json"] or "null")
            if (digest(dict(checkpoint_payload)) != receipt.get("checkpoint_sha256")
                    or not isinstance(checkpoint_payload.get("extra_state"), Mapping)
                    or checkpoint_payload["extra_state"].get("n1_receipt") != {
                        key: value for key, value in receipt.items() if key != "checkpoint_sha256"
                    }
                    or digest({key: value for key, value in checkpoint_payload.items() if key != "extra_state"})
                    != receipt.get("optimizer_state_sha256")):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "resume checkpoint does not match its committed receipt")
            results = self._results(connection, run_id)
            if len(results) != receipt.get("result_count") or [item["result_key"] for item in results] != receipt.get("result_keys"):
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "durable results do not reconcile to the checkpoint")
            generation = row["attempt_generation"] + 1
            successor = uuid.uuid4().hex
            connection.execute(
                "UPDATE attempts SET state='SUPERSEDED' WHERE attempt_id=? AND run_id=? AND state='CHECKPOINTED'",
                (expected_attempt_id, run_id),
            )
            connection.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,'CREATED')",
                (successor, run_id, generation, expected_attempt_id),
            )
            connection.execute(
                "UPDATE runs SET current_attempt_id=?,attempt_generation=?,state='READY',checkpoint_intent_json=NULL "
                "WHERE run_id=? AND current_attempt_id=?",
                (successor, generation, run_id, expected_attempt_id),
            )
            return successor

    def mark_ambiguous(self, run_id: str) -> None:
        with self._transaction() as connection:
            self._run(connection, run_id)
            connection.execute("UPDATE runs SET state='AMBIGUOUS' WHERE run_id=?", (run_id,))

    def close_raw_run(self, run_id: str) -> None:
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["state"] != "CHECKPOINTED":
                raise N1RecoveryError("RECOVERY_AMBIGUOUS", "raw run can close only from a checkpointed state")
            connection.execute("UPDATE runs SET state='CLOSED' WHERE run_id=?", (run_id,))

    def begin_export(self, run_id: str, raw_manifest_sha256: str) -> None:
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["state"] != "CLOSED":
                raise N1RecoveryError("EXPORT_NOT_READY", "only a closed R5 run may export review evidence")
            if re.fullmatch(r"[0-9a-f]{64}", raw_manifest_sha256) is None:
                raise N1RecoveryError("IDENTITY_MISMATCH", "raw R5 manifest identity must be a SHA-256 digest")
            request = json.loads(row["request_json"])
            intent = {
                "run_id": run_id, "experiment_id": request["experiment_id"],
                "request_sha256": row["request_sha256"],
                "raw_manifest_sha256": raw_manifest_sha256,
            }
            connection.execute(
                "UPDATE runs SET state='EXPORT_INTENT',export_intent_json=? WHERE run_id=?",
                (canonical_json(intent), run_id),
            )

    def acknowledge_export(
        self, run_id: str, package_sha256: str, *, observed_run_id: str,
        raw_manifest_sha256: str, package_status: str, observed_experiment_id: str,
    ) -> None:
        """Record caller-verified local package identity after matching durable intent."""
        with self._transaction() as connection:
            row = self._run(connection, run_id)
            if row["state"] != "EXPORT_INTENT":
                raise N1RecoveryError("EXPORT_ACK_UNKNOWN", "review export has no durable intent")
            intent = json.loads(row["export_intent_json"])
            if (observed_run_id != run_id or observed_experiment_id != intent["experiment_id"]
                    or raw_manifest_sha256 != intent["raw_manifest_sha256"]
                    or package_status != "READY_FOR_REVIEW"
                    or re.fullmatch(r"[0-9a-f]{64}", package_sha256) is None):
                raise N1RecoveryError("EXPORT_ACK_UNKNOWN", "review export identity cannot be reconciled")
            receipt = {
                **intent, "package_sha256": package_sha256,
                "status": "READY_FOR_REVIEW", "accepted": False,
            }
            connection.execute(
                "UPDATE runs SET state='EXPORT_READY',export_receipt_json=? WHERE run_id=?",
                (canonical_json(receipt), run_id),
            )

    def run_state(self, run_id: str) -> str:
        with contextlib.closing(self._connect()) as connection:
            row = self._run(connection, run_id)
        return str(row["state"])

    def export_intent(self, run_id: str) -> dict[str, Any] | None:
        with contextlib.closing(self._connect()) as connection:
            row = self._run(connection, run_id)
        return None if row["export_intent_json"] is None else json.loads(row["export_intent_json"])

    def export_receipt(self, run_id: str) -> dict[str, Any] | None:
        with contextlib.closing(self._connect()) as connection:
            row = connection.execute("SELECT export_receipt_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return None if row is None or row[0] is None else json.loads(row[0])


def fixture_request(raw_run: ExperimentRun, config: Mapping[str, Any]) -> dict[str, Any]:
    cells = [{
        "cell_id": "n1-synthetic", "topology": config["design"]["name"],
        "method": config["optimizer"]["name"], "seed": config["seed"],
    }]
    return {
        "schema_version": 1,
        "run_id": raw_run.run_id,
        "experiment_id": raw_run.experiment_id,
        "authorization_reference": AUTHORIZATION_REFERENCE,
        "authorization_test_only": True,
        "execution_source_sha": BASE_SOURCE_SHA,
        "effective_config_sha256": digest(config),
        "model_sha256": digest(config["model"]),
        "search_grid_sha256": digest(config["search_grid"]),
        "validation_grid_sha256": digest(config["validation_grid"]),
        "expected_cells": cells,
        "expected_cells_sha256": digest(cells),
        "topology": config["design"]["name"],
        "design_bounds": list(config["design"]["bounds"]),
        "optimizer": "lshade",
        "optimizer_state_version": 4,
        "rng": {"bit_generator": "PCG64", "seed": config["seed"]},
        "budget": config["search_fe_limit"],
        "requested_unique_budget": config["search_fe_limit"],
        "hard_max_budget": config["search_fe_limit"],
        "validation_point_limit": len(config["validation_grid"]["points"]),
        "runtime": {
            "python_implementation": platform.python_implementation(),
            "python_version": list(sys.version_info[:3]),
            "platform": platform.platform(),
        },
    }


def new_fixture(tmp_path: Path):
    """Create one fresh external R5 fixture and isolated N1 journal."""
    config = load_synthetic_config(Path(__file__).resolve().parents[2] / "configs/examples/r6_synthetic_smoke.yaml")
    data_root = tmp_path / "external-raw"
    repository = tmp_path / "review-repository"
    journal_root = tmp_path / "journal"
    repository.mkdir(mode=0o700)
    journal_root.mkdir(mode=0o700)
    cell = {
        "cell_id": "n1-synthetic", "topology": config["design"]["name"],
        "method": config["optimizer"]["name"], "seed": config["seed"],
    }
    raw_run = create_experiment_run(
        config["experiment_id"], effective_config=config,
        scientific_inputs={
            "model": config["model"], "search_grid": config["search_grid"],
            "validation_grid": config["validation_grid"],
        },
        expected_cells=[cell], source_sha=BASE_SOURCE_SHA,
        search_fe_limit=config["search_fe_limit"],
        validation_point_limit=len(config["validation_grid"]["points"]),
        required_free_bytes=1, review_context=config["review_context"],
        data_root=data_root, method=config["optimizer"]["name"], topology=config["design"]["name"],
    )
    journal = N1RecoveryJournal(journal_root, raw_run=raw_run.path)
    request = fixture_request(raw_run, config)
    attempt_id = journal.register(request)
    return config, raw_run, repository, journal, request, attempt_id
