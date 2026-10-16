from fastapi import APIRouter, HTTPException

from ...domain.models import NaturalLanguageIntake, ParsedPurchaseDraft, PurchaseRequest
from ..dependencies import audit_store, demand_understanding, request_store

router = APIRouter(prefix="/api/v1/intake", tags=["需求录入"])


@router.post("/parse", response_model=ParsedPurchaseDraft)
def parse_purchase_intake(payload: NaturalLanguageIntake) -> ParsedPurchaseDraft:
    return demand_understanding.extract(payload)


@router.post("/submit", response_model=PurchaseRequest, status_code=201)
def submit_purchase_intake(payload: NaturalLanguageIntake) -> PurchaseRequest:
    draft = demand_understanding.extract(payload)
    if not draft.ready_to_submit:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "采购需求信息不完整，请补充缺失字段后重新提交。",
                "missing_fields": draft.missing_fields,
                "draft": draft.model_dump(mode="json"),
            },
        )
    request = request_store.create(draft)
    audit_store.record(
        "REQUEST_SUBMITTED", payload.requester_id, "purchase_request", request.request_id
    )
    return request

