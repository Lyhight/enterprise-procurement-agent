from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from ...application.authorization import validate_approver
from ...agents.core import AgentExecutionCancelled
from ...agents.provenance import verify_decision_provenance
from ...domain.models import (
    AgentExecutionView,
    AgentRunRecord,
    ApprovalDecisionRequest,
    ExecutionCancellation,
    ExecutionCancelRequest,
    TraceIntegrityReport,
    DecisionProvenanceReport,
)
from ...core.auth import AuthenticatedPrincipal, require_actor_identity
from ..dependencies import (
    audit_store,
    execution_control_store,
    repository,
    run_store,
    trace_store,
    workflow,
)
from ..security import require_roles

router = APIRouter(prefix="/api/v1/agent/runs", tags=["Agent 运行与审批"])


@router.post("", response_model=AgentRunRecord, status_code=201)
def create_agent_run(
    request_id: str,
    execution_id: str | None = Query(
        default=None,
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> AgentRunRecord:
    stable_execution_id = execution_id or f"RUN-{uuid4().hex[:12].upper()}"
    try:
        run = run_store.create(
            workflow.analyze(request_id, execution_id=stable_execution_id)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AgentExecutionCancelled as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "execution_id": stable_execution_id,
                "message": str(exc),
                "cancelled": True,
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "execution_id": stable_execution_id,
                "message": str(exc),
                "recoverable": True,
            },
        ) from exc
    audit_store.record(
        "AGENT_RUN_CREATED", principal.employee_id, "agent_run", run.run_id,
        {"request_id": request_id}
    )
    return run


@router.get("", response_model=list[AgentRunRecord])
def list_agent_runs(
    limit: int = Query(default=20, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE", "MANAGER")),
) -> list[AgentRunRecord]:
    return run_store.list(limit)


@router.get("/{run_id}", response_model=AgentRunRecord)
def get_agent_run(
    run_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE", "MANAGER")),
) -> AgentRunRecord:
    try:
        return run_store.get(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/trace", response_model=list[dict])
def get_agent_run_trace(
    run_id: str,
    principal: AuthenticatedPrincipal = Depends(
        require_roles("PROCUREMENT", "FINANCE", "MANAGER")
    ),
) -> list[dict]:
    """Return the append-only execution timeline for an existing Agent run."""
    events = trace_store.list_run(run_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"Agent 执行不存在: {run_id}")
    return events


@router.get("/{run_id}/trace/verify", response_model=TraceIntegrityReport)
def verify_agent_run_trace(
    run_id: str,
    principal: AuthenticatedPrincipal = Depends(
        require_roles("PROCUREMENT", "FINANCE", "MANAGER")
    ),
) -> TraceIntegrityReport:
    report = trace_store.verify_run(run_id)
    if report["reason"] == "TRACE_NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Agent 执行不存在: {run_id}")
    return TraceIntegrityReport.model_validate(report)


@router.get("/{run_id}/provenance/verify", response_model=DecisionProvenanceReport)
def verify_agent_run_provenance(
    run_id: str,
    principal: AuthenticatedPrincipal = Depends(
        require_roles("PROCUREMENT", "FINANCE", "MANAGER")
    ),
) -> DecisionProvenanceReport:
    try:
        run = run_store.get(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    trace_events = trace_store.list_run(run.result.run_id or run_id)
    trace_report = trace_store.verify_run(run.result.run_id or run_id)
    return verify_decision_provenance(
        run.result,
        trace_events=trace_events,
        trace_integrity_valid=trace_report["valid"],
    )


@router.get("/{execution_id}/execution", response_model=AgentExecutionView)
def get_agent_execution(
    execution_id: str,
    principal: AuthenticatedPrincipal = Depends(
        require_roles("PROCUREMENT", "FINANCE", "MANAGER")
    ),
) -> AgentExecutionView:
    try:
        return workflow.execution(execution_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{execution_id}/cancel", response_model=ExecutionCancellation)
def cancel_agent_execution(
    execution_id: str,
    payload: ExecutionCancelRequest,
    principal: AuthenticatedPrincipal = Depends(
        require_roles("PROCUREMENT", "MANAGER")
    ),
) -> ExecutionCancellation:
    try:
        current = workflow.execution(execution_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if current.status in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(
            status_code=409,
            detail=f"Agent 执行当前状态为 {current.status}，不能取消。",
        )
    cancellation = execution_control_store.request_cancel(
        execution_id, payload.reason, principal.employee_id
    )
    audit_store.record(
        "AGENT_EXECUTION_CANCEL_REQUESTED",
        principal.employee_id,
        "agent_execution",
        execution_id,
        {"reason": payload.reason},
    )
    return cancellation


@router.post("/{execution_id}/retry", response_model=AgentRunRecord)
def retry_agent_execution(
    execution_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> AgentRunRecord:
    try:
        result = workflow.retry_execution(execution_id)
        run = run_store.create(result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audit_store.record(
        "AGENT_EXECUTION_RECOVERED",
        principal.employee_id,
        "agent_execution",
        execution_id,
        {"request_id": result.request.request_id},
    )
    return run


@router.post("/{run_id}/approval", response_model=AgentRunRecord)
def decide_agent_run(
    run_id: str,
    payload: ApprovalDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE", "MANAGER")),
) -> AgentRunRecord:
    try:
        require_actor_identity(principal, payload.approver_id)
        current = run_store.get(run_id)
        approver = repository.employee_by_id(payload.approver_id)
        validate_approver(approver, current.result.request, current.approval_level)
        decided = run_store.decide(run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        f"RUN_{payload.decision}",
        payload.approver_id,
        "agent_run",
        run_id,
        {"comment": payload.comment},
    )
    return decided

