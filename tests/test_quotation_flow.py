from decimal import Decimal

import pytest

from procurement_agent.application.intake import parse_intake
from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import NaturalLanguageIntake, QuotationSubmission, RiskLevel
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import AuditStore, RequestStore
from procurement_agent.infrastructure.repositories import CsvRepository


def test_quotations_feed_back_into_agent_ranking_and_audit(tmp_path) -> None:
    settings = get_settings()
    database_path = tmp_path / "quote.db"
    store = RequestStore(database_path)
    store.initialize()
    audit = AuditStore(database_path)
    audit.initialize()
    repository = CsvRepository(settings.company_data_dir, store.list, store.quotations)
    draft = parse_intake(
        NaturalLanguageIntake(
            text="采购10台GPU服务器，预算60万元",
            requester_id="E002",
            department="研发部",
            required_date="2027-02-01",
        )
    )
    request = store.create(draft)
    suppliers = [
        supplier
        for supplier in repository.suppliers()
        if supplier.category == request.category
        and supplier.qualified
        and supplier.risk_level is not RiskLevel.HIGH
    ]
    rfqs = store.create_rfqs(request, suppliers)
    prices = [Decimal("58000"), Decimal("55000"), Decimal("57000")]
    for rfq, price in zip(rfqs[:3], prices, strict=True):
        quotation = store.submit_quotation(
            rfq.rfq_id,
            QuotationSubmission(
                unit_price=price,
                delivery_days=20,
                warranty_months=36,
                valid_until="2027-01-31",
            ),
        )
        audit.record("QUOTATION_RECEIVED", quotation.supplier_id, "quotation", quotation.quotation_id)

    result = ProcurementWorkflow(repository, KnowledgeBase(settings.documents_dir)).analyze(
        request.request_id
    )
    assert len(store.quotations_for_request(request.request_id)) == 3
    assert result.warnings == []
    assert result.recommendations[0].quoted_total is not None
    assert len(audit.list()) == 3
    with pytest.raises(ValueError, match="不能重复提交"):
        store.submit_quotation(
            rfqs[0].rfq_id,
            QuotationSubmission(
                unit_price=Decimal("1"),
                delivery_days=1,
                warranty_months=1,
                valid_until="2027-01-31",
            ),
        )
