from procurement_agent.application.integration_worker import (
    IntegrationQueueService,
    IntegrationWorker,
)
from procurement_agent.application.integrations import EnterpriseIntegrationService
from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import IntegrationJobStatus
from procurement_agent.infrastructure.integration_jobs import IntegrationJobStore
from procurement_agent.infrastructure.integrations.mock_erp import MockErpGateway
from procurement_agent.infrastructure.integrations.mock_oa import MockOaGateway
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import IntegrationStore, RunStore
from procurement_agent.infrastructure.repositories import CsvRepository


def _services(tmp_path, oa_gateway=None):
    settings = get_settings()
    database = tmp_path / "jobs.db"
    run_store = RunStore(database)
    run_store.initialize()
    integration_store = IntegrationStore(database)
    integration_store.initialize()
    job_store = IntegrationJobStore(database)
    job_store.initialize()
    integration_service = EnterpriseIntegrationService(
        integration_store,
        oa_gateway or MockOaGateway(),
        MockErpGateway(),
    )
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    run = run_store.create(workflow.analyze("PR001"))
    return run, run_store, job_store, integration_service


def test_integration_queue_is_idempotent_and_worker_completes_job(tmp_path) -> None:
    run, run_store, jobs, integrations = _services(tmp_path)
    queue = IntegrationQueueService(jobs, run_store)

    first = queue.enqueue(run.run_id, "OA")
    second = queue.enqueue(run.run_id, "OA")
    completed = IntegrationWorker(jobs, run_store, integrations).run_once()

    assert first.job_id == second.job_id
    assert completed.status is IntegrationJobStatus.SUCCEEDED
    assert completed.attempts == 1
    assert completed.integration_id is not None


def test_failed_job_is_retried_then_dead_lettered(tmp_path) -> None:
    class FailingOaGateway:
        def create_approval(self, run):
            raise RuntimeError("temporary OA outage")

    run, run_store, jobs, integrations = _services(tmp_path, FailingOaGateway())
    job = jobs.enqueue(run.run_id, "OA", max_attempts=1)

    failed = IntegrationWorker(jobs, run_store, integrations).run_once()

    assert failed.job_id == job.job_id
    assert failed.status is IntegrationJobStatus.FAILED
    assert "temporary OA outage" in failed.last_error
