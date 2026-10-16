from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.auth import AuthenticatedPrincipal
from ...domain.models import IntegrationJob, IntegrationRecord
from ..dependencies import (
    audit_store,
    integration_job_store,
    integration_queue,
    integration_service,
    integration_store,
    run_store,
)
from ..security import require_roles

router = APIRouter(prefix="/api/v1/integrations", tags=["OA 与 ERP 集成"])


@router.post("/runs/{run_id}/oa", response_model=IntegrationRecord)
def submit_run_to_oa(
    run_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> IntegrationRecord:
    try:
        record = integration_service.submit_to_oa(run_store.get(run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record("OA_SUBMITTED", principal.employee_id, "agent_run", run_id)
    return record


@router.post("/runs/{run_id}/erp", response_model=IntegrationRecord)
def sync_run_to_erp(
    run_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> IntegrationRecord:
    try:
        record = integration_service.sync_to_erp(run_store.get(run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record("ERP_SYNCED", principal.employee_id, "agent_run", run_id)
    return record


@router.get("/records", response_model=list[IntegrationRecord])
def list_integration_records(
    limit: int = Query(default=100, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE")),
) -> list[IntegrationRecord]:
    return integration_store.list(limit)


@router.post("/jobs", response_model=IntegrationJob, status_code=202)
def enqueue_integration_job(
    run_id: str,
    target: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> IntegrationJob:
    try:
        job = integration_queue.enqueue(run_id, target)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_store.record(
        "INTEGRATION_JOB_ENQUEUED",
        principal.employee_id,
        "integration_job",
        job.job_id,
        {"run_id": run_id, "target": job.target},
    )
    return job


@router.get("/jobs", response_model=list[IntegrationJob])
def list_integration_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE")),
) -> list[IntegrationJob]:
    return integration_job_store.list(limit)


@router.get("/jobs/{job_id}", response_model=IntegrationJob)
def get_integration_job(
    job_id: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT", "FINANCE")),
) -> IntegrationJob:
    try:
        return integration_job_store.get(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
