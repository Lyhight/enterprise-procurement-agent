import pytest

from procurement_agent.agents.procurement_graph import ProcurementAgentGraph
from procurement_agent.agents.tool_contracts import ToolContractError
from procurement_agent.agents.tool_registry import ProcurementToolRegistry
from procurement_agent.agents.tools import ProcurementToolbox
from procurement_agent.application.authorization import ToolPrincipal
from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository
from procurement_agent.infrastructure.tracing import AgentTraceStore


def _registry() -> ProcurementToolRegistry:
    settings = get_settings()
    return ProcurementToolRegistry(
        ProcurementToolbox(
            CsvRepository(settings.company_data_dir),
            KnowledgeBase(settings.documents_dir),
        )
    )


def test_tool_contract_rejects_unknown_arguments_before_dispatch() -> None:
    registry = _registry()
    dispatched = False

    def handler(request_id: str):
        nonlocal dispatched
        dispatched = True
        return {}

    registry._handlers["get_purchase_request"] = handler

    with pytest.raises(ToolContractError, match="输入契约校验失败"):
        registry.execute(
            ToolPrincipal("E001", "PROCUREMENT"),
            "get_purchase_request",
            {"request_id": "PR001", "unsafe_extra": "ignored-before"},
        )

    assert dispatched is False


def test_tool_contract_rejects_malformed_output() -> None:
    registry = _registry()
    registry._handlers["get_purchase_request"] = lambda request_id: {
        "request_id": request_id
    }

    with pytest.raises(ToolContractError, match="输出契约校验失败") as caught:
        registry.execute(
            ToolPrincipal("E001", "PROCUREMENT"),
            "get_purchase_request",
            {"request_id": "PR001"},
        )

    assert "requester_id" in str(caught.value)


def test_contract_failure_fails_fast_and_is_preserved_in_trace(tmp_path) -> None:
    settings = get_settings()
    trace_store = AgentTraceStore(tmp_path / "contract-trace.db")
    trace_store.initialize()
    agent = ProcurementAgentGraph(
        CsvRepository(settings.company_data_dir),
        KnowledgeBase(settings.documents_dir),
        trace_writer=trace_store,
    )
    agent.registry._handlers["get_purchase_request"] = lambda request_id: {
        "request_id": request_id
    }

    with pytest.raises(RuntimeError, match="load_request"):
        agent.invoke("PR001", thread_id="EXEC-CONTRACT-FAILURE")

    failed_calls = [
        event
        for event in trace_store.list_run("EXEC-CONTRACT-FAILURE")
        if event["event_type"] == "TOOL_EXECUTED" and event["status"] == "FAILED"
    ]
    assert len(failed_calls) == 1
    assert all(
        event["payload"]["error_type"] == "ToolContractError"
        for event in failed_calls
    )
    assert failed_calls[0]["payload"]["error_category"] == "CONTRACT"
    assert failed_calls[0]["payload"]["retryable"] is False
    assert trace_store.list_run("EXEC-CONTRACT-FAILURE")[-1]["event_type"] == (
        "RUN_FAILED"
    )
