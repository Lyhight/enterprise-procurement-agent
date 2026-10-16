import json
import sqlite3

from procurement_agent.infrastructure.tracing import AgentTraceStore


def test_trace_hash_chain_detects_event_tampering_and_tail_deletion(tmp_path) -> None:
    database = tmp_path / "trace-integrity.db"
    store = AgentTraceStore(database)
    store.initialize()
    first = store.record("RUN-CHAIN", "PR001", "RUN_STARTED", "RUNNING")
    second = store.record(
        "RUN-CHAIN", "PR001", "PLAN_CREATED", "COMPLETED", {"steps": ["load"]}
    )
    third = store.record("RUN-CHAIN", "PR001", "RUN_COMPLETED", "COMPLETED")

    report = store.verify_run("RUN-CHAIN")

    assert report["valid"] is True
    assert report["checked_events"] == 3
    assert report["head_hash"] == third["event_hash"]
    events = store.list_run("RUN-CHAIN")
    assert events[0]["previous_hash"] == ""
    assert events[1]["previous_hash"] == first["event_hash"]

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_trace_events SET payload_json = ? WHERE event_id = ?",
            (json.dumps({"steps": ["tampered"]}), second["event_id"]),
        )
    tampered = store.verify_run("RUN-CHAIN")
    assert tampered["valid"] is False
    assert tampered["broken_event_id"] == second["event_id"]
    assert tampered["reason"] == "EVENT_HASH_MISMATCH"

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_trace_events SET payload_json = ? WHERE event_id = ?",
            (json.dumps({"steps": ["load"]}), second["event_id"]),
        )
        connection.execute(
            "DELETE FROM agent_trace_events WHERE event_id = ?",
            (third["event_id"],),
        )
    truncated = store.verify_run("RUN-CHAIN")
    assert truncated["valid"] is False
    assert truncated["reason"] == "HEAD_MISMATCH"


def test_trace_store_backfills_legacy_events_once(tmp_path) -> None:
    database = tmp_path / "legacy-trace.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE agent_trace_events (
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
        connection.executemany(
            "INSERT INTO agent_trace_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "LEGACY-1",
                    "RUN-LEGACY",
                    "PR001",
                    "RUN_STARTED",
                    None,
                    "RUNNING",
                    None,
                    "{}",
                    "2026-01-01T00:00:00+00:00",
                ),
                (
                    "LEGACY-2",
                    "RUN-LEGACY",
                    "PR001",
                    "RUN_COMPLETED",
                    None,
                    "COMPLETED",
                    1.0,
                    "{}",
                    "2026-01-01T00:00:01+00:00",
                ),
            ],
        )

    store = AgentTraceStore(database)
    store.initialize()
    first_report = store.verify_run("RUN-LEGACY")
    store.initialize()
    second_report = store.verify_run("RUN-LEGACY")

    assert first_report["valid"] is True
    assert second_report == first_report
    assert first_report["checked_events"] == 2
