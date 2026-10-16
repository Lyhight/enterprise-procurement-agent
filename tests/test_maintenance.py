import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from procurement_agent.application.maintenance import AgentDataMaintenance
from procurement_agent.infrastructure.memory import AgentMemoryStore
from procurement_agent.infrastructure.tracing import AgentTraceStore


def test_agent_data_retention_previews_and_preserves_failures(tmp_path) -> None:
    database = tmp_path / "maintenance.db"
    traces = AgentTraceStore(database)
    memories = AgentMemoryStore(database)
    traces.initialize()
    memories.initialize()
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    old = (now - timedelta(days=120)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()

    traces.record("RUN-OLD-OK", "PR001", "RUN_STARTED", "RUNNING")
    traces.record("RUN-OLD-OK", "PR001", "RUN_COMPLETED", "COMPLETED")
    traces.record("RUN-OLD-FAILED", "PR001", "RUN_STARTED", "RUNNING")
    traces.record("RUN-OLD-FAILED", "PR001", "RUN_FAILED", "FAILED")
    traces.record("RUN-OLD-ACTIVE", "PR001", "RUN_STARTED", "RUNNING")
    traces.record("RUN-RECENT", "PR001", "RUN_STARTED", "RUNNING")
    traces.record("RUN-RECENT", "PR001", "RUN_COMPLETED", "COMPLETED")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_trace_events SET created_at = ? "
            "WHERE run_id LIKE 'RUN-OLD-%'",
            (old,),
        )
        connection.execute(
            "UPDATE agent_trace_events SET created_at = ? WHERE run_id = ?",
            (recent, "RUN-RECENT"),
        )

    old_analysis = memories.remember("T1", "PR001", "analysis", "old analysis")
    old_approval = memories.remember(
        "T2", "PR001", "approval_decision", "old approval"
    )
    recent_analysis = memories.remember(
        "T3", "PR002", "analysis", "recent analysis"
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_memories SET created_at = ? WHERE memory_id IN (?, ?)",
            (old, old_analysis.memory_id, old_approval.memory_id),
        )
        connection.execute(
            "UPDATE agent_memories SET created_at = ? WHERE memory_id = ?",
            (recent, recent_analysis.memory_id),
        )

    maintenance = AgentDataMaintenance(traces, memories)
    preview = maintenance.run(
        trace_days=30, memory_days=30, dry_run=True, now=now
    )

    assert preview["trace"] == {
        "cutoff": (now - timedelta(days=30)).isoformat(),
        "dry_run": True,
        "runs": 1,
        "events": 2,
        "preserved_failed_runs": 1,
    }
    assert preview["memory"]["memories"] == 1
    assert preview["memory"]["preserved_memories"] == 1
    assert len(traces.list_run("RUN-OLD-OK")) == 2
    assert len(memories.list("PR001")) == 2

    applied = maintenance.run(
        trace_days=30, memory_days=30, dry_run=False, now=now
    )

    assert applied["trace"]["runs"] == 1
    assert traces.list_run("RUN-OLD-OK") == []
    assert len(traces.list_run("RUN-OLD-FAILED")) == 2
    assert len(traces.list_run("RUN-OLD-ACTIVE")) == 1
    assert len(traces.list_run("RUN-RECENT")) == 2
    remaining_memory_ids = {
        memory.memory_id for memory in memories.list("PR001")
    }
    assert old_analysis.memory_id not in remaining_memory_ids
    assert old_approval.memory_id in remaining_memory_ids
    assert memories.list("PR002")[0].memory_id == recent_analysis.memory_id


def test_agent_data_retention_rejects_invalid_configuration(tmp_path) -> None:
    database = tmp_path / "maintenance.db"
    traces = AgentTraceStore(database)
    memories = AgentMemoryStore(database)
    traces.initialize()
    memories.initialize()

    with pytest.raises(ValueError, match="positive"):
        AgentDataMaintenance(traces, memories).run(trace_days=0)
