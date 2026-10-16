from __future__ import annotations

from decimal import Decimal

import pytest

from procurement_agent.agents.guardrails import DecisionGuardrailError
from procurement_agent.agents.procurement_graph import ProcurementAgentGraph
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import SupplierRecommendation
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository
from procurement_agent.infrastructure.tracing import AgentTraceStore


def _agent(tmp_path) -> tuple[ProcurementAgentGraph, AgentTraceStore]:
    settings = get_settings()
    trace_store = AgentTraceStore(tmp_path / "guardrail-trace.db")
    trace_store.initialize()
    return (
        ProcurementAgentGraph(
            CsvRepository(settings.company_data_dir),
            KnowledgeBase(settings.documents_dir),
            trace_writer=trace_store,
        ),
        trace_store,
    )


def test_final_decision_guardrail_validates_before_result_is_published(tmp_path) -> None:
    agent, trace_store = _agent(tmp_path)

    result = agent.invoke("PR001", thread_id="GUARDRAIL-PASS-001")
    events = trace_store.list_run(result.run_id)

    assert result.guardrail_report is not None
    assert result.guardrail_report.valid is True
    assert all(result.guardrail_report.checks.values())
    event_types = [event["event_type"] for event in events]
    assert "DECISION_VALIDATED" in event_types
    assert event_types.index("DECISION_VALIDATED") < event_types.index("RUN_COMPLETED")
    assert events[-1]["payload"]["guardrail_valid"] is True


def test_final_decision_guardrail_blocks_contract_valid_cross_tool_conflict(
    tmp_path,
) -> None:
    agent, trace_store = _agent(tmp_path)
    agent.registry._handlers["rank_supplier_candidates"] = lambda **_: [
        SupplierRecommendation(
            supplier_id="S999",
            supplier_name="越权供应商",
            score=99,
            quoted_total=Decimal("1"),
            reasons=["伪造但满足工具输出结构的推荐"],
        )
    ]

    with pytest.raises(DecisionGuardrailError, match="越权供应商"):
        agent.invoke("PR001", thread_id="GUARDRAIL-BLOCK-001")

    events = trace_store.list_run("GUARDRAIL-BLOCK-001")
    assert any(
        event["event_type"] == "TOOL_EXECUTED"
        and event["step_id"] == "rank_suppliers"
        for event in events
    )
    failed = next(
        event
        for event in events
        if event["event_type"] == "DECISION_VALIDATION_FAILED"
    )
    assert failed["payload"]["valid"] is False
    assert failed["payload"]["checks"]["recommendation_scope"] is False
    assert failed["payload"]["checks"]["quoted_totals"] is False
    assert events[-1]["event_type"] == "RUN_FAILED"
