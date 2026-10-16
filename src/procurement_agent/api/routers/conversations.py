from fastapi import APIRouter, HTTPException

from ...domain.models import (
    ConversationMessageRequest,
    ConversationStartRequest,
    ConversationState,
    PurchaseRequest,
)
from ..dependencies import audit_store, conversation_service

router = APIRouter(prefix="/api/v1/conversations", tags=["多轮需求澄清"])


@router.post("", response_model=ConversationState, status_code=201)
def start_conversation(payload: ConversationStartRequest) -> ConversationState:
    state = conversation_service.start(payload.requester_id, payload.department)
    audit_store.record(
        "CONVERSATION_STARTED", payload.requester_id, "conversation", state.session_id
    )
    return state


@router.get("/{session_id}", response_model=ConversationState)
def get_conversation(session_id: str) -> ConversationState:
    try:
        return conversation_service.conversations.get(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/messages", response_model=ConversationState)
def reply_to_conversation(
    session_id: str, payload: ConversationMessageRequest
) -> ConversationState:
    try:
        return conversation_service.reply(session_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{session_id}/submit", response_model=PurchaseRequest, status_code=201)
def submit_conversation(session_id: str) -> PurchaseRequest:
    try:
        request = conversation_service.submit(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        "CONVERSATION_SUBMITTED",
        request.requester_id,
        "purchase_request",
        request.request_id,
        {"session_id": session_id},
    )
    return request
