from __future__ import annotations

import json

from pydantic import ValidationError

from ..domain.models import (
    QuotationSubmission,
    RfqDelivery,
    SupplierCallbackReceipt,
)
from ..infrastructure.persistence import RequestStore
from ..infrastructure.repositories import CsvRepository
from ..infrastructure.supplier_messaging.callbacks import (
    SupplierCallbackStore,
    SupplierCallbackVerifier,
)
from ..infrastructure.supplier_messaging.store import RfqDeliveryStore


class RfqDeliveryService:
    def __init__(
        self,
        deliveries: RfqDeliveryStore,
        requests: RequestStore,
        repository: CsvRepository,
    ) -> None:
        self.deliveries = deliveries
        self.requests = requests
        self.repository = repository

    def enqueue_request(self, request_id: str) -> list[RfqDelivery]:
        request = self.repository.request_by_id(request_id)
        rfqs = self.requests.list_rfqs(request_id)
        if not rfqs:
            raise ValueError("采购申请尚未创建询价单。")
        return [
            self.deliveries.enqueue(
                rfq.rfq_id,
                request_id,
                rfq.supplier_id,
                {
                    "rfq_id": rfq.rfq_id,
                    "request_id": request_id,
                    "supplier_id": rfq.supplier_id,
                    "product": request.product,
                    "quantity": request.quantity,
                    "required_date": request.required_date,
                },
            )
            for rfq in rfqs
        ]


class RfqDeliveryWorker:
    def __init__(self, store: RfqDeliveryStore, requests: RequestStore, gateway) -> None:
        self.store = store
        self.requests = requests
        self.gateway = gateway

    def run_once(self) -> RfqDelivery | None:
        delivery = self.store.claim_next()
        if delivery is None:
            return None
        try:
            result = self.gateway.send_rfq(
                delivery.payload, f"RFQ:SEND:{delivery.rfq_id}"
            )
            self.requests.mark_rfq_sent(delivery.rfq_id)
            return self.store.sent(delivery.delivery_id, result.external_reference)
        except Exception as exc:
            return self.store.fail(
                delivery.delivery_id, f"{type(exc).__name__}: {exc}"
            )


class SupplierQuotationCallbackService:
    def __init__(
        self,
        verifier: SupplierCallbackVerifier,
        events: SupplierCallbackStore,
        requests: RequestStore,
    ) -> None:
        self.verifier = verifier
        self.events = events
        self.requests = requests

    def receive(
        self,
        event_id: str,
        rfq_id: str,
        body: bytes,
        timestamp: str,
        signature: str,
    ) -> SupplierCallbackReceipt:
        self.verifier.verify(body, timestamp, signature)
        existing_id = self.events.find_quotation_id(event_id)
        if existing_id:
            return SupplierCallbackReceipt(
                event_id=event_id,
                quotation=self.requests.quotation_by_id(existing_id),
                duplicate=True,
            )
        try:
            payload = QuotationSubmission.model_validate(json.loads(body))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"报价回调数据无效: {exc}") from exc
        quotation = self.requests.submit_quotation(rfq_id, payload)
        self.events.record(event_id, rfq_id, quotation.quotation_id)
        return SupplierCallbackReceipt(event_id=event_id, quotation=quotation)
