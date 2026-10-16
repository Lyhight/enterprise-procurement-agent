from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.evaluation.runner import EvaluationRunner
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository


def test_baseline_evaluation_passes() -> None:
    settings = get_settings()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    report = EvaluationRunner(
        workflow, settings.project_root / "evals" / "cases.json"
    ).run()

    assert report.total == 6
    assert report.passed == report.total
    assert report.pass_rate == 1.0
