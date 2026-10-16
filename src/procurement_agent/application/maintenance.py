from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..infrastructure.memory import AgentMemoryStore
from ..infrastructure.tracing import AgentTraceStore


class AgentDataMaintenance:
    """Coordinates safe retention for Agent traces and long-term memories."""

    def __init__(
        self, traces: AgentTraceStore, memories: AgentMemoryStore
    ) -> None:
        self.traces = traces
        self.memories = memories

    def run(
        self,
        *,
        trace_days: int = 90,
        memory_days: int = 365,
        preserve_failed_runs: bool = True,
        preserve_approval_memories: bool = True,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> dict:
        if trace_days < 1 or memory_days < 1:
            raise ValueError("Retention days must be positive integers.")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Maintenance time must include timezone information.")
        current = current.astimezone(timezone.utc)
        return {
            "dry_run": dry_run,
            "trace": self.traces.prune_before(
                current - timedelta(days=trace_days),
                preserve_failed_runs=preserve_failed_runs,
                dry_run=dry_run,
            ),
            "memory": self.memories.prune_before(
                current - timedelta(days=memory_days),
                preserve_kinds={"approval_decision"}
                if preserve_approval_memories
                else set(),
                dry_run=dry_run,
            ),
        }
