from fastapi import APIRouter, Depends, HTTPException

from ...application.authorization import validate_approver
from ...domain.models import AgentSessionDecision, AgentSessionView
from ...core.auth import AuthenticatedPrincipal, require_actor_identity
from ..dependencies import audit_store, interactive_agent, repository
from ..security import require_roles

router = APIRouter(prefix="/api/v1/agent/sessions", tags=["持久化 Agent 会话"])


@router.post("", response_model=AgentSessionView, status_code=201)
def start_agent_session(
    request_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> AgentSessionView:
    try:
        session = interactive_agent.start(request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_store.record(
        "AGENT_THREAD_STARTED", principal.employee_id, "agent_thread", session.thread_id,
        {"request_id": request_id},
    )
    return session


@router.get("/{thread_id}", response_model=AgentSessionView)
def get_agent_session(
    thread_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE", "MANAGER")),
) -> AgentSessionView:
    try:
        return interactive_agent.get(thread_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{thread_id}/resume", response_model=AgentSessionView)
def resume_agent_session(
    thread_id: str,
    payload: AgentSessionDecision,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE", "MANAGER")),
) -> AgentSessionView:
    try:
        require_actor_identity(principal, payload.approver_id)
        current = interactive_agent.get(thread_id)
        if current.status != "WAITING_FOR_APPROVAL" or current.result is None:
            raise ValueError("Agent 线程当前没有等待处理的人工审批。")
        employee = repository.employee_by_id(payload.approver_id)
        validate_approver(
            employee, current.result.request, current.result.approval_level
        )
        resumed = interactive_agent.resume(thread_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        f"AGENT_THREAD_{payload.decision}", payload.approver_id,
        "agent_thread", thread_id, {"comment": payload.comment},
    )
    return resumed
