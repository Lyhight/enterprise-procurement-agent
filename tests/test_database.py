from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import ApprovalDecisionRequest, RunStatus
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import RunStore
from procurement_agent.infrastructure.repositories import CsvRepository


def test_run_can_pause_and_resume_through_approval(tmp_path) -> None:
    settings = get_settings()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    store = RunStore(tmp_path / "test.db")
    store.initialize()

    created = store.create(workflow.analyze("PR001"))
    assert created.status is RunStatus.AWAITING_APPROVAL
    assert store.get(created.run_id).approval_decision == "PENDING"

    approved = store.decide(
        created.run_id,
        ApprovalDecisionRequest(
            decision="APPROVED", approver_id="E001", comment="预算与技术方案已复核"
        ),
    )
    assert approved.status is RunStatus.COMPLETED
    assert approved.approver_id == "E001"
