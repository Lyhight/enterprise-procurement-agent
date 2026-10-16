from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from ...domain.models import RfqDelivery, RfqDeliveryStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RfqDeliveryStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rfq_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    rfq_id TEXT NOT NULL UNIQUE,
                    request_id TEXT NOT NULL,
                    supplier_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    external_reference TEXT,
                    last_error TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def enqueue(self, rfq_id: str, request_id: str, supplier_id: str, payload: dict) -> RfqDelivery:
        existing = self.find_by_rfq(rfq_id)
        if existing:
            return existing
        timestamp = _now()
        delivery = RfqDelivery(
            delivery_id=f"DEL-{uuid4().hex[:12].upper()}",
            rfq_id=rfq_id,
            request_id=request_id,
            supplier_id=supplier_id,
            status=RfqDeliveryStatus.PENDING,
            attempts=0,
            max_attempts=5,
            next_attempt_at=timestamp,
            external_reference=None,
            last_error=None,
            payload=payload,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO rfq_deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._values(delivery),
                )
        except sqlite3.IntegrityError:
            existing = self.find_by_rfq(rfq_id)
            if existing is None:
                raise
            return existing
        return delivery

    def claim_next(self) -> RfqDelivery | None:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM rfq_deliveries WHERE status IN ('PENDING','RETRY') "
                "AND next_attempt_at <= ? ORDER BY created_at LIMIT 1",
                (timestamp,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                "UPDATE rfq_deliveries SET status='RUNNING', attempts=attempts+1, "
                "updated_at=? WHERE delivery_id=?",
                (timestamp, row["delivery_id"]),
            )
            connection.commit()
        return self.get(row["delivery_id"])

    def sent(self, delivery_id: str, external_reference: str) -> RfqDelivery:
        with self._connect() as connection:
            connection.execute(
                "UPDATE rfq_deliveries SET status='SENT', external_reference=?, "
                "last_error=NULL, updated_at=? WHERE delivery_id=?",
                (external_reference, _now(), delivery_id),
            )
        return self.get(delivery_id)

    def fail(self, delivery_id: str, error: str) -> RfqDelivery:
        current = self.get(delivery_id)
        status = (
            RfqDeliveryStatus.FAILED
            if current.attempts >= current.max_attempts
            else RfqDeliveryStatus.RETRY
        )
        delay = min(30 * 2 ** max(current.attempts - 1, 0), 3600)
        next_attempt = (
            datetime.now(timezone.utc) + timedelta(seconds=delay)
        ).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE rfq_deliveries SET status=?, next_attempt_at=?, last_error=?, "
                "updated_at=? WHERE delivery_id=?",
                (status.value, next_attempt, error[:2000], _now(), delivery_id),
            )
        return self.get(delivery_id)

    def get(self, delivery_id: str) -> RfqDelivery:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM rfq_deliveries WHERE delivery_id=?", (delivery_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"询价发送任务不存在: {delivery_id}")
        return self._from_row(row)

    def find_by_rfq(self, rfq_id: str) -> RfqDelivery | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM rfq_deliveries WHERE rfq_id=?", (rfq_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self, request_id: str | None = None) -> list[RfqDelivery]:
        query = "SELECT * FROM rfq_deliveries"
        params: tuple = ()
        if request_id:
            query += " WHERE request_id=?"
            params = (request_id,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RfqDelivery:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return RfqDelivery(**data)

    @staticmethod
    def _values(item: RfqDelivery) -> tuple:
        data = item.model_dump(mode="json")
        return (
            data["delivery_id"], data["rfq_id"], data["request_id"],
            data["supplier_id"], data["status"], data["attempts"],
            data["max_attempts"], data["next_attempt_at"],
            data["external_reference"], data["last_error"],
            json.dumps(data["payload"], ensure_ascii=False),
            data["created_at"], data["updated_at"],
        )
