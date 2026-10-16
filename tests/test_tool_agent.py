import pytest

from procurement_agent.application.workflow import ProcurementWorkflow
from procurement_agent.application.authorization import ToolPrincipal
from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.repositories import CsvRepository


def _workflow() -> ProcurementWorkflow:
    settings = get_settings()
    return ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )


def test_local_agent_executes_allow_listed_tools_with_trace() -> None:
    response = _workflow().answer_with_tools("PR001", "有哪些供应商和制度风险？")

    assert response.provider == "local"
    assert [call.name for call in response.tool_calls] == [
        "get_purchase_request",
        "find_eligible_suppliers",
        "search_procurement_policy",
    ]
    assert "GPU服务器" in response.answer
    assert "procurement_policy.md" in response.answer


def test_tool_registry_rejects_unknown_tool() -> None:
    workflow = _workflow()
    with pytest.raises(ValueError, match="不允许调用工具"):
        workflow.tool_agent.registry.execute(
            ToolPrincipal("SYSTEM", "SYSTEM_AGENT"), "delete_supplier", {}
        )


def test_tool_registry_enforces_role_permissions() -> None:
    workflow = _workflow()
    with pytest.raises(PermissionError, match="无权调用"):
        workflow.tool_agent.registry.execute(
            ToolPrincipal("E002", "REQUESTER"),
            "find_eligible_suppliers",
            {"category": "服务器"},
        )
