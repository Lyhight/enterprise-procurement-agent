from fastapi import APIRouter, Depends, HTTPException

from ...application.authorization import validate_approver
from ...core.auth import AuthenticatedPrincipal, require_actor_identity
from ...domain.models import (
    AwardDecisionRequest,
    GoodsReceipt,
    GoodsReceiptRequest,
    OrderStatusUpdate,
    PurchaseOrder,
)
from ..dependencies import audit_store, order_service, order_store, repository, run_store
from ..security import require_roles

router = APIRouter(prefix="/api/v1/orders", tags=["采购订单与收货"])


@router.post("", response_model=PurchaseOrder, status_code=201)
def award_and_create_order(
    payload: AwardDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "MANAGER")),
) -> PurchaseOrder:
    try:
        require_actor_identity(principal, payload.decided_by)
        run = run_store.get(payload.run_id)
        employee = repository.employee_by_id(payload.decided_by)
        validate_approver(employee, run.result.request, "L2")
        order = order_service.award(run, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record("ORDER_CREATED", payload.decided_by, "purchase_order", order.po_id)
    return order


@router.get("", response_model=list[PurchaseOrder])
def list_orders() -> list[PurchaseOrder]:
    return order_store.list()


@router.get("/{po_id}", response_model=PurchaseOrder)
def get_order(po_id: str) -> PurchaseOrder:
    try:
        return order_store.get(po_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{po_id}/status", response_model=PurchaseOrder)
def update_order_status(
    po_id: str,
    payload: OrderStatusUpdate,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "WAREHOUSE")),
) -> PurchaseOrder:
    try:
        require_actor_identity(principal, payload.actor_id)
        repository.employee_by_id(payload.actor_id)
        order = order_service.transition(po_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        "ORDER_STATUS_CHANGED",
        payload.actor_id,
        "purchase_order",
        po_id,
        {"status": order.status.value, "note": payload.note},
    )
    return order


@router.post("/{po_id}/receipts", response_model=GoodsReceipt, status_code=201)
def receive_order(
    po_id: str,
    payload: GoodsReceiptRequest,
    principal: AuthenticatedPrincipal = Depends(require_roles("WAREHOUSE")),
) -> GoodsReceipt:
    try:
        require_actor_identity(principal, payload.receiver_id)
        repository.employee_by_id(payload.receiver_id)
        receipt = order_service.receive(po_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record("GOODS_RECEIVED", payload.receiver_id, "purchase_order", po_id)
    return receipt


@router.get("/{po_id}/receipts", response_model=list[GoodsReceipt])
def list_order_receipts(po_id: str) -> list[GoodsReceipt]:
    try:
        return order_store.receipts(po_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
