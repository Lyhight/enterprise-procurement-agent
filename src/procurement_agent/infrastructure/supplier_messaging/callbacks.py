from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from pathlib import Path


class SupplierCallbackVerifier:
    def __init__(self, secret: str, tolerance_seconds: int = 300) -> None:
        if len(secret) < 16:
            raise ValueError("供应商回调密钥长度至少为 16 个字符。")
        self._secret = secret.encode("utf-8")
        self.tolerance_seconds = tolerance_seconds

    def verify(
        self,
        body: bytes,
        timestamp: str,
        signature: str,
        now: datetime | None = None,
    ) -> None:
        try:
            sent_at = int(timestamp)
        except ValueError as exc:
            raise PermissionError("回调时间戳格式无效。") from exc
        current = now or datetime.now(timezone.utc)
        if abs(int(current.timestamp()) - sent_at) > self.tolerance_seconds:
            raise PermissionError("回调已过期或时间偏差过大。")
        message = timestamp.encode("ascii") + b"." + body
        expected = hmac_new(self._secret, message, sha256).hexdigest()
        supplied = signature.removeprefix("sha256=")
        if not compare_digest(expected, supplied):
            raise PermissionError("回调签名无效。")


class SupplierCallbackStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS supplier_callback_events (
                    event_id TEXT PRIMARY KEY,
                    rfq_id TEXT NOT NULL,
                    quotation_id TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
                """
            )

    def find_quotation_id(self, event_id: str) -> str | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT quotation_id FROM supplier_callback_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row[0] if row else None

    def record(self, event_id: str, rfq_id: str, quotation_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO supplier_callback_events VALUES (?, ?, ?, ?)",
                (event_id, rfq_id, quotation_id, datetime.now(timezone.utc).isoformat()),
            )
