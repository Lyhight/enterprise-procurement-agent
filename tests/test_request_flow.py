from procurement_agent.application.intake import parse_intake
from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import NaturalLanguageIntake, RiskLevel
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import RequestStore
from procurement_agent.infrastructure.repositories import CsvRepository


def test_intake_submission_can_run_agent_and_create_rfqs(tmp_path) -> None:
    settings = get_settings()
    store = RequestStore(tmp_path / "flow.db")
    store.initialize()
    repository = CsvRepository(settings.company_data_dir, store.list)
    workflow = ProcurementWorkflow(repository, KnowledgeBase(settings.documents_dir))
    draft = parse_intake(
        NaturalLanguageIntake(
            text="新项目采购10台GPU服务器，预算60万元",
            requester_id="E002",
            department="研发部",
            required_date="2027-01-20",
            priority="HIGH",
        )
    )

    request = store.create(draft)
    result = workflow.analyze(request.request_id)
    eligible = [
        supplier
        for supplier in repository.suppliers()
        if supplier.category == request.category
        and supplier.qualified
        and supplier.risk_level is not RiskLevel.HIGH
    ]
    rfqs = store.create_rfqs(request, eligible)

    assert result.request.request_id == request.request_id
    assert result.approval_level == "L2"
    assert len(rfqs) == 4
    assert store.create_rfqs(request, eligible) == rfqs
