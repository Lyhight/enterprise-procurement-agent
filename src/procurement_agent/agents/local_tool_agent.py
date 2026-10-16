from __future__ import annotations

import json

from ..application.authorization import ToolPrincipal
from ..domain.models import AgentAssistResponse, ToolInvocation
from .tool_registry import ProcurementToolRegistry


class LocalProcurementToolAgent:
    """Auditable local planner that executes only allow-listed read tools."""

    def __init__(self, registry: ProcurementToolRegistry) -> None:
        self.registry = registry
        self.principal = ToolPrincipal("LOCAL-AGENT", "SYSTEM_AGENT")

    def answer(
        self,
        request_id: str,
        question: str,
        principal: ToolPrincipal | None = None,
    ) -> AgentAssistResponse:
        active_principal = principal or self.principal
        traces: list[ToolInvocation] = []
        request = self._call(
            active_principal, traces, "get_purchase_request", {"request_id": request_id}
        )
        suppliers = self._call(
            active_principal,
            traces,
            "find_eligible_suppliers",
            {"category": request["category"]},
        )
        policy = self._call(
            active_principal,
            traces,
            "search_procurement_policy",
            {
                "query": f"{question} {request['category']} 采购审批 供应商风险",
                "limit": 4,
            },
        )
        supplier_names = "、".join(item["supplier_name"] for item in suppliers) or "无"
        evidence = "；".join(
            f"{item['source']}#{item['section']}" for item in policy
        ) or "未检索到直接制度依据"
        answer = (
            f"申请 {request_id} 采购 {request['product']}，数量 {request['quantity']}，"
            f"预算 {request['budget']} 元。合格候选供应商：{supplier_names}。"
            f"制度依据：{evidence}。具体推荐与审批等级应以正式分析工作流结果为准。"
        )
        return AgentAssistResponse(provider="local", answer=answer, tool_calls=traces)

    def _call(
        self,
        principal: ToolPrincipal,
        traces: list[ToolInvocation],
        name: str,
        arguments: dict,
    ) -> dict | list:
        output = self.registry.execute(principal, name, arguments)
        traces.append(
            ToolInvocation(
                name=name,
                arguments=arguments,
                output_preview=output[:500],
            )
        )
        return json.loads(output)
