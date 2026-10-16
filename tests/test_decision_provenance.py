from decimal import Decimal

from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.agents.procurement_graph import ProcurementAgentGraph
from procurement_agent.agents.provenance import verify_decision_provenance
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import Quotation
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository
from procurement_agent.infrastructure.tracing import AgentTraceStore
from procurement_agent.domain.ruleset import (
    PROCUREMENT_RULESET_FINGERPRINT,
    PROCUREMENT_RULESET_VERSION,
)


def test_decision_and_tool_fingerprints_are_stable_and_data_sensitive() -> None:
    settings = get_settings()
    knowledge = KnowledgeBase(settings.documents_dir)
    baseline = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), knowledge
    )

    first = baseline.analyze("PR001")
    repeated = baseline.analyze("PR001")

    assert first.provenance is not None
    assert repeated.provenance is not None
    assert first.provenance == repeated.provenance
    assert first.provenance.system_prompt_version == "1.0.0"
    assert first.provenance.tool_contract_version == "1.0.0"
    assert first.provenance.ruleset_version == PROCUREMENT_RULESET_VERSION
    assert first.provenance.ruleset_fingerprint == PROCUREMENT_RULESET_FINGERPRINT
    assert len(first.provenance.source_fingerprint) == 64
    assert len(first.provenance.decision_fingerprint) == 64
    assert all(len(call["arguments_hash"]) == 64 for call in first.tool_calls)
    assert all(len(call["output_hash"]) == 64 for call in first.tool_calls)
    assert all(
        call["tool_contract_version"] == "1.0.0" for call in first.tool_calls
    )
    verification = verify_decision_provenance(first)
    assert verification.valid is True
    assert verification.decision_fingerprint_valid is True
    assert verification.source_fingerprint_valid is True
    assert verification.trace_evidence_valid is None
    assert verification.ruleset_current is True

    tampered = first.model_copy(update={"warnings": ["审计后被修改"]})
    tampered_verification = verify_decision_provenance(tampered)
    assert tampered_verification.valid is False
    assert tampered_verification.decision_fingerprint_valid is False

    additional_quote = Quotation(
        quotation_id="Q-PROVENANCE",
        request_id="PR001",
        supplier_id="S001",
        unit_price=Decimal("61000"),
        currency="CNY",
        delivery_days=15,
        warranty_months=36,
        valid_until="2099-12-31",
    )
    changed = ProcurementWorkflow(
        CsvRepository(
            settings.company_data_dir,
            extra_quotation_loader=lambda: [additional_quote],
        ),
        knowledge,
    ).analyze("PR001")

    assert changed.provenance is not None
    assert changed.provenance.source_fingerprint != (
        first.provenance.source_fingerprint
    )
    assert changed.provenance.decision_fingerprint != (
        first.provenance.decision_fingerprint
    )


def test_provenance_replays_source_manifest_against_tamper_evident_trace(
    tmp_path,
) -> None:
    settings = get_settings()
    traces = AgentTraceStore(tmp_path / "provenance-replay.db")
    traces.initialize()
    agent = ProcurementAgentGraph(
        CsvRepository(settings.company_data_dir),
        KnowledgeBase(settings.documents_dir),
        trace_writer=traces,
    )
    result = agent.invoke("PR001", thread_id="PROVENANCE-REPLAY-001")
    events = traces.list_run(result.run_id)

    report = verify_decision_provenance(
        result,
        trace_events=events,
        trace_integrity_valid=traces.verify_run(result.run_id)["valid"],
    )

    assert report.valid is True
    assert report.source_fingerprint_valid is True
    assert report.trace_evidence_valid is True
    assert report.trace_integrity_valid is True
    assert report.missing_evidence == []

    tampered_result = result.model_copy(deep=True)
    source_call = next(
        call
        for call in tampered_result.tool_calls
        if call["name"] == "get_valid_quotations"
    )
    source_call["output_hash"] = "0" * 64
    result_report = verify_decision_provenance(tampered_result)
    assert result_report.valid is False
    assert result_report.source_fingerprint_valid is False
    assert result_report.decision_fingerprint_valid is False

    tampered_events = [dict(event) for event in events]
    quote_event = next(
        event
        for event in tampered_events
        if event["event_type"] == "TOOL_EXECUTED"
        and event["payload"]["tool_name"] == "get_valid_quotations"
    )
    quote_event["payload"] = dict(quote_event["payload"])
    quote_event["payload"]["output_hash"] = "f" * 64
    trace_report = verify_decision_provenance(
        result,
        trace_events=tampered_events,
        trace_integrity_valid=False,
    )
    assert trace_report.valid is False
    assert trace_report.trace_evidence_valid is False
    assert trace_report.trace_integrity_valid is False
