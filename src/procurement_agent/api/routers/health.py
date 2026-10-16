import sqlite3

from fastapi import APIRouter, HTTPException

from ...core.metrics import metrics
from ..dependencies import auth_service, knowledge_base, settings, trace_store

router = APIRouter(tags=["系统"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
def readiness() -> dict:
    checks = {
        "database": False,
        "knowledge_base": knowledge_base.document_count > 0,
        "authentication": (
            settings.app_env != "production"
            or (settings.auth_enabled and auth_service.configured)
        ),
    }
    try:
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = True
    except sqlite3.Error:
        pass
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@router.get("/metrics")
def application_metrics() -> dict:
    return {**metrics.snapshot(), "agent": trace_store.metrics()}

