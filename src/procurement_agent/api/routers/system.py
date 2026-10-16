from fastapi import APIRouter

from ...domain.models import AiRuntimeStatus
from ..dependencies import demand_understanding, settings

router = APIRouter(prefix="/api/v1/system", tags=["系统配置"])


@router.get("/ai", response_model=AiRuntimeStatus)
def ai_runtime_status() -> AiRuntimeStatus:
    enabled = demand_understanding.provider == "openai"
    return AiRuntimeStatus(
        provider=demand_understanding.provider,
        model=demand_understanding.model,
        enabled=enabled,
        fallback=settings.llm_provider == "openai" and not enabled,
    )
