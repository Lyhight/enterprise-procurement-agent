from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..domain.models import AgentMemory


class AgentMemoryStore:
    """Durable internal memory for decisions that inform later agent runs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memories (
                    memory_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_memories_request "
                "ON agent_memories(request_id, created_at DESC)"
            )

    def remember(
        self,
        thread_id: str,
        request_id: str,
        kind: str,
        content: str,
        metadata: dict | None = None,
    ) -> AgentMemory:
        normalized_metadata = metadata or {}
        with sqlite3.connect(self.database_path) as connection:
            existing = connection.execute(
                "SELECT * FROM agent_memories "
                "WHERE request_id = ? AND kind = ? AND content = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (request_id, kind, content),
            ).fetchone()
        if existing is not None and json.loads(existing[5]) == normalized_metadata:
            return self._from_row(existing)
        memory = AgentMemory(
            memory_id=f"MEM-{uuid4().hex[:12].upper()}",
            thread_id=thread_id,
            request_id=request_id,
            kind=kind,
            content=content,
            metadata=normalized_metadata,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO agent_memories VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    memory.memory_id,
                    memory.thread_id,
                    memory.request_id,
                    memory.kind,
                    memory.content,
                    json.dumps(memory.metadata, ensure_ascii=False),
                    memory.created_at,
                ),
            )
        return memory

    def list(self, request_id: str, limit: int = 20) -> list[AgentMemory]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_memories WHERE request_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (request_id, limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def search(
        self,
        *,
        request_id: str | None = None,
        category: str | None = None,
        department: str | None = None,
        kinds: set[str] | None = None,
        limit: int = 20,
    ) -> list[AgentMemory]:
        """Return relevant memories using auditable metadata and recency scoring."""
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_memories ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        ranked: list[tuple[int, int, AgentMemory]] = []
        for recency_index, row in enumerate(rows):
            memory = self._from_row(row)
            if kinds and memory.kind not in kinds:
                continue
            score = 0
            if request_id and memory.request_id == request_id:
                score += 100
            if category and memory.metadata.get("category") == category:
                score += 30
            if department and memory.metadata.get("department") == department:
                score += 20
            if not any((request_id, category, department)):
                score = 1
            if score:
                ranked.append((score, -recency_index, memory))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [memory for _, _, memory in ranked[:limit]]

    def forget(self, memory_id: str) -> bool:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "DELETE FROM agent_memories WHERE memory_id = ?", (memory_id,)
            )
        return cursor.rowcount > 0

    def prune(self, request_id: str, keep_latest: int = 20) -> int:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT memory_id FROM agent_memories WHERE request_id = ? "
                "ORDER BY created_at DESC",
                (request_id,),
            ).fetchall()
            stale_ids = [row[0] for row in rows[max(keep_latest, 0) :]]
            if stale_ids:
                connection.executemany(
                    "DELETE FROM agent_memories WHERE memory_id = ?",
                    [(memory_id,) for memory_id in stale_ids],
                )
        return len(stale_ids)

    def prune_before(
        self,
        cutoff: datetime,
        *,
        preserve_kinds: set[str] | None = None,
        dry_run: bool = True,
    ) -> dict:
        """Apply time retention without deleting protected decision memories."""
        if cutoff.tzinfo is None:
            raise ValueError("Retention cutoff must include timezone information.")
        cutoff_text = cutoff.astimezone(timezone.utc).isoformat()
        protected = preserve_kinds or set()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT memory_id, kind FROM agent_memories WHERE created_at < ?",
                (cutoff_text,),
            ).fetchall()
            removable = [
                memory_id for memory_id, kind in rows if kind not in protected
            ]
            preserved = len(rows) - len(removable)
            if removable and not dry_run:
                connection.executemany(
                    "DELETE FROM agent_memories WHERE memory_id = ?",
                    [(memory_id,) for memory_id in removable],
                )
        return {
            "cutoff": cutoff_text,
            "dry_run": dry_run,
            "memories": len(removable),
            "preserved_memories": preserved,
        }

    @staticmethod
    def _from_row(row) -> AgentMemory:
        return AgentMemory(
            memory_id=row[0],
            thread_id=row[1],
            request_id=row[2],
            kind=row[3],
            content=row[4],
            metadata=json.loads(row[5]),
            created_at=row[6],
        )
