from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository


def test_pr001_returns_ranked_suppliers() -> None:
    settings = get_settings()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    result = workflow.analyze("PR001")

    assert result.approval_level == "L3"
    assert len(result.recommendations) == 4
    assert result.recommendations[0].score >= result.recommendations[-1].score
    assert result.policy_evidence
    assert [step.step for step in result.trace] == list(workflow.steps)
    assert result.next_action == "提交审批"


def test_pr002_requires_review_for_insufficient_quotes() -> None:
    settings = get_settings()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    result = workflow.analyze("PR002")

    assert result.approval_level == "L2"
    assert result.warnings
    assert result.next_action == "采购专员人工复核"

