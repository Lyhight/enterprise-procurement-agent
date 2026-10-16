from fastapi import APIRouter, Depends, HTTPException

from ...application.authorization import ToolPrincipal
from ...core.auth import AuthenticatedPrincipal
from ...domain.models import AgentAssistResponse
from ..dependencies import audit_store, workflow
from ..security import require_roles

router = APIRouter(prefix="/api/v1/agent", tags=["受保护的 Agent 工具调用"])


@router.post("/assist", response_model=AgentAssistResponse)
def assist(
    request_id: str,
    question: str,
    principal: AuthenticatedPrincipal = Depends(require_roles("PROCUREMENT")),
) -> AgentAssistResponse:
    try:
        response = workflow.answer_with_tools(
            request_id,
            question,
            ToolPrincipal(principal.employee_id, principal.role),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_store.record(
        "AGENT_TOOL_ASSIST",
        principal.employee_id,
        "purchase_request",
        request_id,
        {"tools": [item.name for item in response.tool_calls]},
    )
    return response
