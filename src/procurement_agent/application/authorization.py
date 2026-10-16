from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import Employee, PurchaseRequest


LEVEL_RANK = {"L1": 1, "L2": 2, "L3": 3}


@dataclass(frozen=True)
class ToolPrincipal:
    actor_id: str
    role: str


class ToolAccessPolicy:
    _permissions = {
        "SYSTEM_AGENT": {
            "get_purchase_request",
            "validate_purchase_request",
            "find_eligible_suppliers",
            "get_valid_quotations",
            "rank_supplier_candidates",
            "evaluate_procurement_policy",
            "search_procurement_policy",
        },
        "PROCUREMENT": {
            "get_purchase_request",
            "validate_purchase_request",
            "find_eligible_suppliers",
            "get_valid_quotations",
            "rank_supplier_candidates",
            "evaluate_procurement_policy",
            "search_procurement_policy",
        },
        "REQUESTER": {"get_purchase_request", "search_procurement_policy"},
    }

    def require(self, principal: ToolPrincipal, tool_name: str) -> None:
        if tool_name not in self._permissions.get(principal.role, set()):
            raise PermissionError(
                f"角色 {principal.role} 无权调用工具 {tool_name}。"
            )


def validate_approver(
    employee: Employee,
    request: PurchaseRequest,
    required_level: str,
) -> None:
    if employee.employee_id == request.requester_id:
        raise PermissionError("申请人与审批人不能是同一人。")
    if LEVEL_RANK.get(employee.approval_level, 0) < LEVEL_RANK.get(required_level, 99):
        raise PermissionError(
            f"审批人权限为 {employee.approval_level}，低于所需的 {required_level}。"
        )
