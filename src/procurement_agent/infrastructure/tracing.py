from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class AgentTraceStore:
    """Append-only event store for auditable Agent execution traces."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_trace_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    step_id TEXT,
                    status TEXT NOT NULL,
                    duration_ms REAL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(agent_trace_events)"
                ).fetchall()
            }
            if "previous_hash" not in columns:
                connection.execute(
                    "ALTER TABLE agent_trace_events ADD COLUMN previous_hash TEXT"
                )
            if "event_hash" not in columns:
                connection.execute(
                    "ALTER TABLE agent_trace_events ADD COLUMN event_hash TEXT"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_trace_heads (
                    run_id TEXT PRIMARY KEY,
                    head_hash TEXT NOT NULL,
                    event_count INTEGER NOT NULL
                )
                """
            )
            self._backfill_hash_chain(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_trace_run "
                "ON agent_trace_events(run_id, created_at)"
            )

    def record(
        self,
        run_id: str,
        request_id: str,
        event_type: str,
        status: str,
        payload: dict | None = None,
        *,
        step_id: str | None = None,
        duration_ms: float | None = None,
    ) -> dict:
        event = {
            "event_id": f"TRACE-{uuid4().hex[:16].upper()}",
            "run_id": run_id,
            "request_id": request_id,
            "event_type": event_type,
            "step_id": step_id,
            "status": status,
            "duration_ms": duration_ms,
            "payload": self._redact(payload or {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            head = connection.execute(
                "SELECT head_hash, event_count FROM agent_trace_heads WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            previous_hash = head[0] if head else ""
            event_count = head[1] if head else 0
            event["previous_hash"] = previous_hash
            event["event_hash"] = self._event_hash(event)
            connection.execute(
                """
                INSERT INTO agent_trace_events (
                    event_id, run_id, request_id, event_type, step_id, status,
                    duration_ms, payload_json, created_at, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["run_id"],
                    event["request_id"],
                    event["event_type"],
                    event["step_id"],
                    event["status"],
                    event["duration_ms"],
                    json.dumps(event["payload"], ensure_ascii=False),
                    event["created_at"],
                    event["previous_hash"],
                    event["event_hash"],
                ),
            )
            connection.execute(
                """
                INSERT INTO agent_trace_heads (run_id, head_hash, event_count)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    head_hash = excluded.head_hash,
                    event_count = excluded.event_count
                """,
                (run_id, event["event_hash"], event_count + 1),
            )
        return event

    def list_run(self, run_id: str) -> list[dict]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_trace_events WHERE run_id = ? "
                "ORDER BY rowid",
                (run_id,),
            ).fetchall()
        return [
            {
                "event_id": row[0],
                "run_id": row[1],
                "request_id": row[2],
                "event_type": row[3],
                "step_id": row[4],
                "status": row[5],
                "duration_ms": row[6],
                "payload": json.loads(row[7]),
                "created_at": row[8],
                "previous_hash": row[9],
                "event_hash": row[10],
            }
            for row in rows
        ]

    def verify_run(self, run_id: str) -> dict:
        """Verify the event chain and the separately maintained run head."""
        events = self.list_run(run_id)
        if not events:
            return {
                "run_id": run_id,
                "valid": False,
                "checked_events": 0,
                "total_events": 0,
                "head_hash": None,
                "broken_event_id": None,
                "reason": "TRACE_NOT_FOUND",
            }
        previous_hash = ""
        for index, event in enumerate(events):
            if event["previous_hash"] != previous_hash:
                return self._verification_failure(
                    run_id, events, index, event, "PREVIOUS_HASH_MISMATCH"
                )
            expected = self._event_hash(event)
            if event["event_hash"] != expected:
                return self._verification_failure(
                    run_id, events, index, event, "EVENT_HASH_MISMATCH"
                )
            previous_hash = event["event_hash"]
        with sqlite3.connect(self.database_path) as connection:
            head = connection.execute(
                "SELECT head_hash, event_count FROM agent_trace_heads WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if head is None or head[0] != previous_hash or head[1] != len(events):
            return {
                "run_id": run_id,
                "valid": False,
                "checked_events": len(events),
                "total_events": len(events),
                "head_hash": previous_hash,
                "broken_event_id": None,
                "reason": "HEAD_MISMATCH",
            }
        return {
            "run_id": run_id,
            "valid": True,
            "checked_events": len(events),
            "total_events": len(events),
            "head_hash": previous_hash,
            "broken_event_id": None,
            "reason": None,
        }

    def metrics(self) -> dict:
        """Aggregate durable Agent health metrics from the append-only timeline."""
        with sqlite3.connect(self.database_path) as connection:
            counts = dict(
                connection.execute(
                    "SELECT event_type, COUNT(*) FROM agent_trace_events "
                    "GROUP BY event_type"
                ).fetchall()
            )
            tool_statuses = dict(
                connection.execute(
                    "SELECT status, COUNT(*) FROM agent_trace_events "
                    "WHERE event_type = 'TOOL_EXECUTED' GROUP BY status"
                ).fetchall()
            )
            terminal_durations = [
                row[0]
                for row in connection.execute(
                    "SELECT duration_ms FROM agent_trace_events "
                    "WHERE event_type IN "
                    "('RUN_COMPLETED', 'RUN_FAILED', 'RUN_RESUME_COMPLETED', "
                    "'RUN_RESUME_FAILED', 'RUN_CANCELLED') "
                    "AND duration_ms IS NOT NULL"
                ).fetchall()
            ]
            planner_payloads = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT payload_json FROM agent_trace_events "
                    "WHERE event_type IN ('PLAN_CREATED', 'PLAN_REVISED')"
                ).fetchall()
            ]
        tool_total = sum(tool_statuses.values())
        tool_failures = tool_statuses.get("FAILED", 0)
        return {
            "runs_started": counts.get("RUN_STARTED", 0),
            "runs_completed": counts.get("RUN_COMPLETED", 0),
            "runs_failed": counts.get("RUN_FAILED", 0),
            "runs_cancelled": counts.get("RUN_CANCELLED", 0),
            "recoveries_completed": counts.get("RUN_RESUME_COMPLETED", 0),
            "recoveries_failed": counts.get("RUN_RESUME_FAILED", 0),
            "tool_calls": tool_total,
            "tool_failures": tool_failures,
            "tool_failure_rate": round(tool_failures / tool_total, 4)
            if tool_total
            else 0.0,
            "planner_fallback_decisions": sum(
                bool(payload.get("fallback_reason"))
                for payload in planner_payloads
            ),
            "average_terminal_duration_ms": round(
                sum(terminal_durations) / len(terminal_durations), 3
            )
            if terminal_durations
            else 0.0,
        }

    def prune_before(
        self,
        cutoff: datetime,
        *,
        preserve_failed_runs: bool = True,
        dry_run: bool = True,
    ) -> dict:
        """Remove complete old timelines while preserving active and failed runs."""
        cutoff_text = self._utc_iso(cutoff)
        terminal_types = {
            "RUN_COMPLETED",
            "RUN_FAILED",
            "RUN_RESUME_COMPLETED",
            "RUN_RESUME_FAILED",
            "RUN_CANCELLED",
        }
        failed_types = {"RUN_FAILED", "RUN_RESUME_FAILED"}
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT run_id, event_type, created_at FROM agent_trace_events "
                "ORDER BY rowid"
            ).fetchall()
            last_created: dict[str, str] = {}
            last_terminal: dict[str, str] = {}
            event_counts: dict[str, int] = {}
            for run_id, event_type, created_at in rows:
                last_created[run_id] = max(
                    last_created.get(run_id, created_at), created_at
                )
                event_counts[run_id] = event_counts.get(run_id, 0) + 1
                if event_type in terminal_types:
                    last_terminal[run_id] = event_type
            old_terminal_runs = {
                run_id
                for run_id, created_at in last_created.items()
                if created_at < cutoff_text and run_id in last_terminal
            }
            preserved_failed = {
                run_id
                for run_id in old_terminal_runs
                if last_terminal[run_id] in failed_types
            }
            removable = old_terminal_runs - (
                preserved_failed if preserve_failed_runs else set()
            )
            event_count = sum(event_counts[run_id] for run_id in removable)
            if removable and not dry_run:
                connection.executemany(
                    "DELETE FROM agent_trace_events WHERE run_id = ?",
                    [(run_id,) for run_id in removable],
                )
                connection.executemany(
                    "DELETE FROM agent_trace_heads WHERE run_id = ?",
                    [(run_id,) for run_id in removable],
                )
        return {
            "cutoff": cutoff_text,
            "dry_run": dry_run,
            "runs": len(removable),
            "events": event_count,
            "preserved_failed_runs": len(preserved_failed),
        }

    @staticmethod
    def _utc_iso(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("Retention cutoff must include timezone information.")
        return value.astimezone(timezone.utc).isoformat()

    @classmethod
    def _event_hash(cls, event: dict) -> str:
        canonical = {
            "event_id": event["event_id"],
            "run_id": event["run_id"],
            "request_id": event["request_id"],
            "event_type": event["event_type"],
            "step_id": event["step_id"],
            "status": event["status"],
            "duration_ms": event["duration_ms"],
            "payload": event["payload"],
            "created_at": event["created_at"],
            "previous_hash": event.get("previous_hash") or "",
        }
        serialized = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    @classmethod
    def _backfill_hash_chain(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT rowid, event_id, run_id, request_id, event_type, step_id,
                   status, duration_ms, payload_json, created_at,
                   previous_hash, event_hash
            FROM agent_trace_events ORDER BY rowid
            """
        ).fetchall()
        previous_by_run: dict[str, str] = {}
        counts: dict[str, int] = {}
        for row in rows:
            run_id = row[2]
            previous = previous_by_run.get(run_id, "")
            event = {
                "event_id": row[1],
                "run_id": run_id,
                "request_id": row[3],
                "event_type": row[4],
                "step_id": row[5],
                "status": row[6],
                "duration_ms": row[7],
                "payload": json.loads(row[8]),
                "created_at": row[9],
                "previous_hash": previous,
            }
            event_hash = row[11]
            if not event_hash:
                event_hash = cls._event_hash(event)
                connection.execute(
                    """
                    UPDATE agent_trace_events
                    SET previous_hash = ?, event_hash = ? WHERE rowid = ?
                    """,
                    (previous, event_hash, row[0]),
                )
            previous_by_run[run_id] = event_hash
            counts[run_id] = counts.get(run_id, 0) + 1
        for run_id, head_hash in previous_by_run.items():
            connection.execute(
                """
                INSERT INTO agent_trace_heads (run_id, head_hash, event_count)
                VALUES (?, ?, ?) ON CONFLICT(run_id) DO NOTHING
                """,
                (run_id, head_hash, counts[run_id]),
            )

    @staticmethod
    def _verification_failure(
        run_id: str,
        events: list[dict],
        index: int,
        event: dict,
        reason: str,
    ) -> dict:
        return {
            "run_id": run_id,
            "valid": False,
            "checked_events": index,
            "total_events": len(events),
            "head_hash": None,
            "broken_event_id": event["event_id"],
            "reason": reason,
        }

    @classmethod
    def _redact(cls, value):
        sensitive_keys = {
            "authorization",
            "token",
            "access_token",
            "api_key",
            "secret",
            "password",
        }
        if isinstance(value, dict):
            return {
                key: "***REDACTED***"
                if key.lower() in sensitive_keys
                else cls._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value
