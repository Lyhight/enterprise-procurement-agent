from __future__ import annotations

from typing import Protocol

from ...domain.models import AgentRunRecord, ExternalOperationResult


class ApprovalGateway(Protocol):
    def create_approval(self, run: AgentRunRecord) -> ExternalOperationResult: ...


class ErpGateway(Protocol):
    def create_purchase_order_draft(self, run: AgentRunRecord) -> ExternalOperationResult: ...
