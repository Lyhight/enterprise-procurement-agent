from fastapi import APIRouter, HTTPException

from ...domain.models import Quotation, QuotationSubmission
from ..dependencies import audit_store, request_store

router = APIRouter(prefix="/api/v1/rfqs", tags=["供应商报价"])


@router.post("/{rfq_id}/quotation", response_model=Quotation, status_code=201)
def submit_rfq_quotation(rfq_id: str, payload: QuotationSubmission) -> Quotation:
    try:
        quotation = request_store.submit_quotation(rfq_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        "QUOTATION_RECEIVED",
        quotation.supplier_id,
        "quotation",
        quotation.quotation_id,
        {"request_id": quotation.request_id, "rfq_id": rfq_id},
    )
    return quotation

