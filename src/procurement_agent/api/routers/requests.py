from fastapi import APIRouter, HTTPException

from ...domain.models import AnalysisResult, PurchaseRequest, Quotation, RfqRecord, RiskLevel
from ..dependencies import audit_store, repository, request_store, workflow

router = APIRouter(prefix="/api/v1/requests", tags=["采购申请与询价"])


@router.get("", response_model=list[PurchaseRequest])
def list_requests() -> list[PurchaseRequest]:
    return repository.requests()


@router.get("/{request_id}/analysis", response_model=AnalysisResult)
def analyze_request(request_id: str) -> AnalysisResult:
    try:
        return workflow.analyze(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{request_id}/rfqs", response_model=list[RfqRecord], status_code=201)
def create_request_rfqs(request_id: str) -> list[RfqRecord]:
    try:
        request = repository.request_by_id(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    suppliers = [
        supplier
        for supplier in repository.suppliers()
        if supplier.category == request.category
        and supplier.qualified
        and supplier.risk_level is not RiskLevel.HIGH
    ]
    if not suppliers:
        raise HTTPException(status_code=409, detail="没有符合品类和风险要求的合格供应商。")
    rfqs = request_store.create_rfqs(request, suppliers)
    audit_store.record(
        "RFQS_CREATED",
        request.requester_id,
        "purchase_request",
        request.request_id,
        {"count": len(rfqs)},
    )
    return rfqs


@router.get("/{request_id}/rfqs", response_model=list[RfqRecord])
def list_request_rfqs(request_id: str) -> list[RfqRecord]:
    _require_request(request_id)
    return request_store.list_rfqs(request_id)


@router.get("/{request_id}/quotations", response_model=list[Quotation])
def list_request_quotations(request_id: str) -> list[Quotation]:
    _require_request(request_id)
    return [quote for quote in repository.quotations() if quote.request_id == request_id]


def _require_request(request_id: str) -> PurchaseRequest:
    try:
        return repository.request_by_id(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


