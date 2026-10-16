from __future__ import annotations

from .ports.integrations import ApprovalGateway, ErpGateway
from ..domain.models import AgentRunRecord, IntegrationRecord, RunStatus
from ..infrastructure.persistence import IntegrationStore


class EnterpriseIntegrationService:
    def __init__(
        self,
        store: IntegrationStore,
        approval_gateway: ApprovalGateway,
        erp_gateway: ErpGateway,
    ) -> None:
        self.store = store
        self.approval_gateway = approval_gateway
        self.erp_gateway = erp_gateway

    def submit_to_oa(self, run: AgentRunRecord) -> IntegrationRecord:
        if run.status is not RunStatus.AWAITING_APPROVAL:
            raise ValueError("只有待审批的 Agent 运行可以提交至 OA。")
        existing = self.store.find(run.run_id, "OA", "CREATE_APPROVAL")
        if existing is not None:
            return existing
        return self.store.save("agent_run", run.run_id, self.approval_gateway.create_approval(run))

    def sync_to_erp(self, run: AgentRunRecord) -> IntegrationRecord:
        if run.status is not RunStatus.COMPLETED or run.approval_decision not in {
            "APPROVED",
            "AUTO_APPROVED",
        }:
            raise ValueError("只有已批准的 Agent 运行可以同步至 ERP。")
        existing = self.store.find(run.run_id, "ERP-SAP", "CREATE_PO_DRAFT")
        if existing is not None:
            return existing
        return self.store.save(
            "agent_run", run.run_id, self.erp_gateway.create_purchase_order_draft(run)
        )
