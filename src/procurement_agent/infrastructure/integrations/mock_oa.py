from uuid import uuid4

from ...domain.models import AgentRunRecord, ExternalOperationResult


class MockOaGateway:
    """Local OA adapter used until a real enterprise endpoint is configured."""

    def create_approval(self, run: AgentRunRecord) -> ExternalOperationResult:
        return ExternalOperationResult(
            system="OA",
            action="CREATE_APPROVAL",
            status="ACCEPTED",
            external_reference=f"OA-{uuid4().hex[:10].upper()}",
            payload={
                "run_id": run.run_id,
                "request_id": run.request_id,
                "approval_level": run.approval_level,
                "amount": str(run.result.request.budget),
            },
        )
