import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from procurement_agent.agents.core import AgentExecutionCancelled
from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.execution_control import (
    AgentExecutionControlStore,
)
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository
from procurement_agent.infrastructure.tracing import AgentTraceStore


def test_cancellation_request_is_persistent_and_idempotent(tmp_path) -> None:
    store = AgentExecutionControlStore(tmp_path / "control.db")
    store.initialize()

    first = store.request_cancel("EXEC-1", "用户停止运行", "E001")
    repeated = store.request_cancel("EXEC-1", "覆盖原因", "E999")

    assert first == repeated
    assert repeated.reason == "用户停止运行"
    assert repeated.requested_by == "E001"
    assert store.find("UNKNOWN") is None


def test_running_agent_observes_cancellation_and_preserves_checkpoint(tmp_path) -> None:
    settings = get_settings()
    database_path = tmp_path / "cancel-agent.db"
    controls = AgentExecutionControlStore(database_path)
    controls.initialize()
    traces = AgentTraceStore(database_path)
    traces.initialize()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir),
        KnowledgeBase(settings.documents_dir),
        checkpointer=SqliteSaver(
            sqlite3.connect(database_path, check_same_thread=False)
        ),
        trace_writer=traces,
        cancellation_reader=controls,
    )
    execution_id = "EXEC-CANCELLED-001"
    original_handler = workflow.agent.registry._handlers["get_purchase_request"]
    calls = 0

    def cancelling_request_service(request_id: str):
        nonlocal calls
        calls += 1
        result = original_handler(request_id)
        controls.request_cancel(execution_id, "操作员终止本次分析", "E001")
        return result

    workflow.agent.registry._handlers[
        "get_purchase_request"
    ] = cancelling_request_service

    with pytest.raises(AgentExecutionCancelled, match="操作员终止"):
        workflow.analyze("PR001", execution_id=execution_id)

    assert calls == 1
    execution = workflow.execution(execution_id)
    assert execution.status == "CANCELLED"
    assert execution.execution_plan[0]["status"] == "FAILED"
    assert execution.execution_plan[0]["error_category"] == "CANCELLATION"
    assert execution.execution_plan[0]["retryable"] is False
    event_types = [event["event_type"] for event in traces.list_run(execution_id)]
    assert "CANCELLATION_OBSERVED" in event_types
    assert event_types[-1] == "RUN_CANCELLED"
    assert "RUN_FAILED" not in event_types
    metrics = traces.metrics()
    assert metrics["runs_cancelled"] == 1
    assert metrics["runs_failed"] == 0

    with pytest.raises(ValueError, match="已取消"):
        workflow.retry_execution(execution_id)
