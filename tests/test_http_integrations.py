import httpx

from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.integrations.http_gateways import (
    HttpErpGateway,
    HttpOaGateway,
)
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import RunStore
from procurement_agent.infrastructure.repositories import CsvRepository


def _pending_run(tmp_path):
    settings = get_settings()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    store = RunStore(tmp_path / "http-gateway.db")
    store.initialize()
    return store.create(workflow.analyze("PR001"))


def test_http_oa_gateway_sends_idempotency_key_and_maps_response(tmp_path) -> None:
    run = _pending_run(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Idempotency-Key"] == f"OA:CREATE_APPROVAL:{run.run_id}"
        assert request.headers["Authorization"] == "Bearer oa-secret"
        return httpx.Response(
            202,
            json={
                "status": "ACCEPTED",
                "external_reference": "OA-REMOTE-001",
                "payload": {"workflow": "procurement"},
            },
        )

    client = httpx.Client(
        base_url="https://oa.example.test",
        transport=httpx.MockTransport(handler),
    )
    result = HttpOaGateway(
        "https://oa.example.test", "oa-secret", client=client
    ).create_approval(run)

    assert result.external_reference == "OA-REMOTE-001"
    assert result.payload["workflow"] == "procurement"


def test_http_erp_gateway_uses_stable_idempotency_key(tmp_path) -> None:
    run = _pending_run(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Idempotency-Key"] == f"ERP:CREATE_PO_DRAFT:{run.run_id}"
        return httpx.Response(
            201,
            json={"external_reference": "ERP-DRAFT-001", "status": "ACCEPTED"},
        )

    client = httpx.Client(
        base_url="https://erp.example.test",
        transport=httpx.MockTransport(handler),
    )
    result = HttpErpGateway(
        "https://erp.example.test", "erp-secret", client=client
    ).create_purchase_order_draft(run)

    assert result.external_reference == "ERP-DRAFT-001"
