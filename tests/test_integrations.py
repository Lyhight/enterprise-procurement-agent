from procurement_agent.application.integrations import EnterpriseIntegrationService
from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import ApprovalDecisionRequest
from procurement_agent.infrastructure.integrations.mock_erp import MockErpGateway
from procurement_agent.infrastructure.integrations.mock_oa import MockOaGateway
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import IntegrationStore, RunStore
from procurement_agent.infrastructure.repositories import CsvRepository


def test_oa_and_erp_integrations_are_state_guarded_and_idempotent(tmp_path) -> None:
    settings = get_settings()
    repository = CsvRepository(settings.company_data_dir)
    result = ProcurementWorkflow(repository, KnowledgeBase(settings.documents_dir)).analyze("PR001")
    run_store = RunStore(tmp_path / "integrations.db")
    run_store.initialize()
    integration_store = IntegrationStore(tmp_path / "integrations.db")
    integration_store.initialize()
    service = EnterpriseIntegrationService(
        integration_store, MockOaGateway(), MockErpGateway()
    )

    run = run_store.create(result)
    oa_record = service.submit_to_oa(run)
    assert service.submit_to_oa(run).integration_id == oa_record.integration_id

    approved = run_store.decide(
        run.run_id,
        ApprovalDecisionRequest(decision="APPROVED", approver_id="E001"),
    )
    erp_record = service.sync_to_erp(approved)
    assert erp_record.system == "ERP-SAP"
    assert service.sync_to_erp(approved).integration_id == erp_record.integration_id
    assert len(integration_store.list()) == 2
