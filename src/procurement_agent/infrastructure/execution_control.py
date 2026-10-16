from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import ExecutionCancellation


class AgentExecutionControlStore:
    """Persistent cooperative cancellation signals for running Agent graphs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_execution_cancellations (
                    execution_id TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_at TEXT NOT NULL
                )
                """
            )

    def request_cancel(
        self, execution_id: str, reason: str, requested_by: str
    ) -> ExecutionCancellation:
        cancellation = ExecutionCancellation(
            execution_id=execution_id,
            reason=reason,
            requested_by=requested_by,
            requested_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_execution_cancellations (
                    execution_id, reason, requested_by, requested_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(execution_id) DO NOTHING
                """,
                (
                    cancellation.execution_id,
                    cancellation.reason,
                    cancellation.requested_by,
                    cancellation.requested_at,
                ),
            )
        return self.get(execution_id)

    def get(self, execution_id: str) -> ExecutionCancellation:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT execution_id, reason, requested_by, requested_at
                FROM agent_execution_cancellations
                WHERE execution_id = ?
                """,
                (execution_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"Agent 执行取消请求不存在: {execution_id}")
        return ExecutionCancellation(
            execution_id=row[0],
            reason=row[1],
            requested_by=row[2],
            requested_at=row[3],
        )

    def find(self, execution_id: str) -> ExecutionCancellation | None:
        try:
            return self.get(execution_id)
        except LookupError:
            return None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=30)
