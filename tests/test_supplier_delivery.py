import json
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new

import pytest

from procurement_agent.application.rfq_delivery import (
    RfqDeliveryService,
    RfqDeliveryWorker,
    SupplierQuotationCallbackService,
)
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import RfqDeliveryStatus, RiskLevel
from procurement_agent.infrastructure.persistence import RequestStore
from procurement_agent.infrastructure.repositories import CsvRepository
from procurement_agent.infrastructure.supplier_messaging import (
    MockSupplierGateway,
    RfqDeliveryStore,
    SupplierCallbackStore,
    SupplierCallbackVerifier,
)


def _setup(tmp_path):
    settings = get_settings()
    database = tmp_path / "supplier-delivery.db"
    requests = RequestStore(database)
    requests.initialize()
    repository = CsvRepository(settings.company_data_dir)
    request = repository.request_by_id("PR001")
    suppliers = [
        item
        for item in repository.suppliers()
        if item.category == request.category
        and item.qualified
        and item.risk_level is not RiskLevel.HIGH
    ]
    requests.create_rfqs(request, suppliers)
    deliveries = RfqDeliveryStore(database)
    deliveries.initialize()
    return database, requests, repository, deliveries


def test_rfq_delivery_queue_is_idempotent_and_marks_rfq_sent(tmp_path) -> None:
    _, requests, repository, deliveries = _setup(tmp_path)
    service = RfqDeliveryService(deliveries, requests, repository)

    first = service.enqueue_request("PR001")
    second = service.enqueue_request("PR001")
    sent = RfqDeliveryWorker(
        deliveries, requests, MockSupplierGateway()
    ).run_once()

    assert [item.delivery_id for item in first] == [item.delivery_id for item in second]
    assert sent.status is RfqDeliveryStatus.SENT
    assert requests.rfq_by_id(sent.rfq_id).status == "SENT"


def test_signed_supplier_callback_is_verified_and_idempotent(tmp_path) -> None:
    database, requests, _, _ = _setup(tmp_path)
    events = SupplierCallbackStore(database)
    events.initialize()
    secret = "supplier-callback-secret-value"
    verifier = SupplierCallbackVerifier(secret)
    service = SupplierQuotationCallbackService(verifier, events, requests)
    rfq = requests.list_rfqs("PR001")[0]
    body = json.dumps(
        {
            "unit_price": "56000",
            "currency": "CNY",
            "delivery_days": 20,
            "warranty_months": 36,
            "valid_until": "2027-02-01",
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac_new(
        secret.encode(), timestamp.encode() + b"." + body, sha256
    ).hexdigest()

    first = service.receive("EVT-001", rfq.rfq_id, body, timestamp, signature)
    duplicate = service.receive("EVT-001", rfq.rfq_id, body, timestamp, signature)

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert duplicate.quotation.quotation_id == first.quotation.quotation_id


def test_supplier_callback_rejects_invalid_signature(tmp_path) -> None:
    database, requests, _, _ = _setup(tmp_path)
    events = SupplierCallbackStore(database)
    events.initialize()
    service = SupplierQuotationCallbackService(
        SupplierCallbackVerifier("supplier-callback-secret-value"), events, requests
    )
    rfq = requests.list_rfqs("PR001")[0]

    with pytest.raises(PermissionError, match="签名无效"):
        service.receive(
            "EVT-002",
            rfq.rfq_id,
            b"{}",
            str(int(datetime.now(timezone.utc).timestamp())),
            "invalid",
        )
