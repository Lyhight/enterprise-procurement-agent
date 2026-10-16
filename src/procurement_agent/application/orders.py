from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ..domain.models import (
    AgentRunRecord,
    AwardDecisionRequest,
    GoodsReceipt,
    GoodsReceiptRequest,
    OrderStatusUpdate,
    PurchaseOrder,
    PurchaseOrderStatus,
    RunStatus,
)
from ..infrastructure.persistence import OrderStore


ALLOWED_TRANSITIONS = {
    PurchaseOrderStatus.DRAFT: {PurchaseOrderStatus.ISSUED, PurchaseOrderStatus.CANCELLED},
    PurchaseOrderStatus.ISSUED: {
        PurchaseOrderStatus.ACKNOWLEDGED,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.ACKNOWLEDGED: {
        PurchaseOrderStatus.IN_TRANSIT,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.IN_TRANSIT: {
        PurchaseOrderStatus.DELIVERED,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.DELIVERED: set(),
    PurchaseOrderStatus.CANCELLED: set(),
}


class OrderService:
    def __init__(self, store: OrderStore) -> None:
        self.store = store

    def award(self, run: AgentRunRecord, decision: AwardDecisionRequest) -> PurchaseOrder:
        if run.status is not RunStatus.COMPLETED or run.approval_decision not in {
            "APPROVED",
            "AUTO_APPROVED",
        }:
            raise ValueError("只有已批准的 Agent 运行可以执行定标。")
        selected = next(
            (
                item
                for item in run.result.recommendations
                if item.supplier_id == decision.supplier_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("定标供应商不在本次 Agent 推荐清单中。")
        if selected.quoted_total is None:
            raise ValueError("定标供应商尚无有效报价。")
        timestamp = datetime.now(UTC).isoformat()
        return self.store.create(
            PurchaseOrder(
                po_id=f"PO-{uuid4().hex[:12].upper()}",
                request_id=run.request_id,
                run_id=run.run_id,
                supplier_id=selected.supplier_id,
                supplier_name=selected.supplier_name,
                quantity=run.result.request.quantity,
                total_amount=selected.quoted_total,
                currency="CNY",
                expected_delivery_date=decision.expected_delivery_date,
                status=PurchaseOrderStatus.DRAFT,
                created_by=decision.decided_by,
                award_reason=decision.reason,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    def transition(self, po_id: str, update: OrderStatusUpdate) -> PurchaseOrder:
        current = self.store.get(po_id)
        if update.status not in ALLOWED_TRANSITIONS[current.status]:
            raise ValueError(
                f"订单状态不能从 {current.status.value} 变更为 {update.status.value}。"
            )
        return self.store.update_status(po_id, update.status, update.actor_id, update.note)

    def receive(self, po_id: str, payload: GoodsReceiptRequest) -> GoodsReceipt:
        order = self.store.get(po_id)
        if order.status is not PurchaseOrderStatus.IN_TRANSIT:
            raise ValueError("只有运输中的订单可以办理收货。")
        if payload.accepted_quantity + payload.rejected_quantity != payload.received_quantity:
            raise ValueError("合格数量与拒收数量之和必须等于本次收货数量。")
        previous_received = sum(item.received_quantity for item in self.store.receipts(po_id))
        if previous_received + payload.received_quantity > order.quantity:
            raise ValueError("累计收货数量不能超过订单数量。")
        receipt = self.store.add_receipt(po_id, payload)
        if previous_received + payload.received_quantity == order.quantity:
            self.store.update_status(
                po_id,
                PurchaseOrderStatus.DELIVERED,
                payload.receiver_id,
                "订单数量已全部收货",
            )
        return receipt
