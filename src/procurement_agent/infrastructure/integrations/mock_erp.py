from uuid import uuid4

from ...domain.models import AgentRunRecord, ExternalOperationResult


class MockErpGateway:
    """Local ERP adapter used until SAP credentials and mappings are available."""

    def create_purchase_order_draft(self, run: AgentRunRecord) -> ExternalOperationResult:
        selected = run.result.recommendations[0] if run.result.recommendations else None
        return ExternalOperationResult(
            system="ERP-SAP",
            action="CREATE_PO_DRAFT",
            status="ACCEPTED",
            external_reference=f"ERP-{uuid4().hex[:10].upper()}",
            payload={
                "run_id": run.run_id,
                "request_id": run.request_id,
                "supplier_id": selected.supplier_id if selected else None,
                "amount": str(selected.quoted_total) if selected and selected.quoted_total else None,
            },
        )
