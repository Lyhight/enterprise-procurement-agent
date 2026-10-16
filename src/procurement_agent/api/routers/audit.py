from fastapi import APIRouter, Query

from ...domain.models import AuditEvent
from ..dependencies import audit_store

router = APIRouter(prefix="/api/v1/audit", tags=["审计"])


@router.get("/events", response_model=list[AuditEvent])
def list_audit_events(limit: int = Query(default=100, ge=1, le=500)) -> list[AuditEvent]:
    return audit_store.list(limit)

