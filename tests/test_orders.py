from procurement_agent.application.orders import OrderService
from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import (
    ApprovalDecisionRequest,
    AwardDecisionRequest,
    GoodsReceiptRequest,
    OrderStatusUpdate,
    PurchaseOrderStatus,
)
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.persistence import OrderStore, RunStore
from procurement_agent.infrastructure.repositories import CsvRepository


def test_award_order_transitions_and_receipt(tmp_path) -> None:
    settings = get_settings()
    repository = CsvRepository(settings.company_data_dir)
    result = ProcurementWorkflow(repository, KnowledgeBase(settings.documents_dir)).analyze("PR001")
    run_store = RunStore(tmp_path / "orders.db")
    run_store.initialize()
    run = run_store.create(result)
    run = run_store.decide(
        run.run_id,
        ApprovalDecisionRequest(decision="APPROVED", approver_id="E001"),
    )
    order_store = OrderStore(tmp_path / "orders.db")
    order_store.initialize()
    service = OrderService(order_store)
    selected = next(item for item in result.recommendations if item.quoted_total is not None)
    order = service.award(
        run,
        AwardDecisionRequest(
            run_id=run.run_id,
            supplier_id=selected.supplier_id,
            decided_by="E001",
            reason="综合评分与报价符合要求",
            expected_delivery_date="2027-05-01",
        ),
    )
    for status in (
        PurchaseOrderStatus.ISSUED,
        PurchaseOrderStatus.ACKNOWLEDGED,
        PurchaseOrderStatus.IN_TRANSIT,
    ):
        order = service.transition(
            order.po_id, OrderStatusUpdate(status=status, actor_id="E001")
        )
    service.receive(
        order.po_id,
        GoodsReceiptRequest(
            received_quantity=20,
            accepted_quantity=20,
            rejected_quantity=0,
            receiver_id="E004",
        ),
    )
    assert order_store.get(order.po_id).status is PurchaseOrderStatus.DELIVERED
    assert len(order_store.receipts(order.po_id)) == 1
