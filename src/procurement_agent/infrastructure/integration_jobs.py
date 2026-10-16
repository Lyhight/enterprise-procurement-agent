from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from ..domain.models import IntegrationJob, IntegrationJobStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntegrationJobStore:
    """SQLite-backed at-least-once queue with atomic claiming and retry state."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    integration_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, target)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_integration_jobs_due "
                "ON integration_jobs(status, next_attempt_at)"
            )

    def enqueue(
        self, run_id: str, target: str, max_attempts: int = 5
    ) -> IntegrationJob:
        normalized = target.upper()
        if normalized not in {"OA", "ERP"}:
            raise ValueError("集成任务 target 必须为 OA 或 ERP。")
        if max_attempts < 1:
            raise ValueError("max_attempts 必须大于 0。")
        existing = self.find(run_id, normalized)
        if existing is not None:
            return existing
        timestamp = _now()
        job = IntegrationJob(
            job_id=f"JOB-{uuid4().hex[:12].upper()}",
            run_id=run_id,
            target=normalized,
            status=IntegrationJobStatus.PENDING,
            attempts=0,
            max_attempts=max_attempts,
            next_attempt_at=timestamp,
            last_error=None,
            integration_id=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO integration_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._values(job),
                )
        except sqlite3.IntegrityError:
            existing = self.find(run_id, normalized)
            if existing is None:
                raise
            return existing
        return job

    def claim_next(self) -> IntegrationJob | None:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM integration_jobs
                WHERE status IN ('PENDING', 'RETRY') AND next_attempt_at <= ?
                ORDER BY created_at ASC LIMIT 1
                """,
                (timestamp,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE integration_jobs
                SET status = 'RUNNING', attempts = attempts + 1, updated_at = ?
                WHERE job_id = ?
                """,
                (timestamp, row["job_id"]),
            )
            connection.commit()
        return self.get(row["job_id"])

    def succeed(self, job_id: str, integration_id: str) -> IntegrationJob:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE integration_jobs
                SET status = 'SUCCEEDED', integration_id = ?, last_error = NULL,
                    updated_at = ? WHERE job_id = ?
                """,
                (integration_id, _now(), job_id),
            )
        return self.get(job_id)

    def fail(self, job_id: str, error: str) -> IntegrationJob:
        job = self.get(job_id)
        exhausted = job.attempts >= job.max_attempts
        status = IntegrationJobStatus.FAILED if exhausted else IntegrationJobStatus.RETRY
        delay_seconds = min(2 ** max(job.attempts - 1, 0) * 30, 3600)
        next_attempt = (
            datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        ).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE integration_jobs
                SET status = ?, next_attempt_at = ?, last_error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status.value, next_attempt, error[:2000], _now(), job_id),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> IntegrationJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM integration_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"集成任务不存在: {job_id}")
        return self._from_row(row)

    def find(self, run_id: str, target: str) -> IntegrationJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM integration_jobs WHERE run_id = ? AND target = ?",
                (run_id, target),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def list(self, limit: int = 100) -> list[IntegrationJob]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM integration_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> IntegrationJob:
        return IntegrationJob(**dict(row))

    @staticmethod
    def _values(job: IntegrationJob) -> tuple:
        data = job.model_dump(mode="json")
        return tuple(data[field] for field in (
            "job_id", "run_id", "target", "status", "attempts", "max_attempts",
            "next_attempt_at", "last_error", "integration_id", "created_at", "updated_at"
        ))
