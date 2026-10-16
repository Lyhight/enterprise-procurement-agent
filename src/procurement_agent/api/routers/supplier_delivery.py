from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ...core.auth import AuthenticatedPrincipal
from ...domain.models import RfqDelivery, SupplierCallbackReceipt
from ..dependencies import (
    audit_store,
    rfq_delivery_service,
    rfq_delivery_store,
    supplier_callback_service,
)
from ..security import require_roles

router = APIRouter(prefix="/api/v1", tags=["供应商询价交付"])


@router.post(
    "/requests/{request_id}/rfq-deliveries",
    response_model=list[RfqDelivery],
    status_code=202,
)
def enqueue_rfq_deliveries(
    request_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> list[RfqDelivery]:
    try:
        deliveries = rfq_delivery_service.enqueue_request(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        "RFQ_DELIVERIES_ENQUEUED",
        principal.employee_id,
        "purchase_request",
        request_id,
        {"delivery_ids": [item.delivery_id for item in deliveries]},
    )
    return deliveries


@router.get(
    "/requests/{request_id}/rfq-deliveries",
    response_model=list[RfqDelivery],
)
def list_rfq_deliveries(
    request_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> list[RfqDelivery]:
    return rfq_delivery_store.list(request_id)


@router.post(
    "/supplier-callbacks/quotations/{rfq_id}",
    response_model=SupplierCallbackReceipt,
)
async def supplier_quotation_callback(
    rfq_id: str,
    request: Request,
    x_event_id: str = Header(alias="X-Event-ID"),
    x_timestamp: str = Header(alias="X-Timestamp"),
    x_signature: str = Header(alias="X-Signature"),
) -> SupplierCallbackReceipt:
    if supplier_callback_service is None:
        raise HTTPException(status_code=503, detail="供应商回调密钥尚未配置。")
    body = await request.body()
    try:
        receipt = supplier_callback_service.receive(
            x_event_id, rfq_id, body, x_timestamp, x_signature
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        "SUPPLIER_QUOTATION_CALLBACK",
        receipt.quotation.supplier_id,
        "quotation",
        receipt.quotation.quotation_id,
        {"event_id": x_event_id, "duplicate": receipt.duplicate},
    )
    return receipt
