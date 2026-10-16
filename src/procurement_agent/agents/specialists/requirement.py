from __future__ import annotations

from datetime import date

from ...domain.models import Employee, PurchaseRequest, RequirementAssessment
from ...domain.ruleset import PROCESSABLE_REQUEST_STATUSES


class RequirementSpecialist:
    """Validates whether a request is trustworthy enough for automated analysis."""

    _processable_statuses = PROCESSABLE_REQUEST_STATUSES

    def assess(
        self,
        request: PurchaseRequest,
        requester: Employee | None,
    ) -> RequirementAssessment:
        issues: list[str] = []
        requester_verified = requester is not None
        if requester is None:
            issues.append("申请人员工编号不存在。")
        elif requester.department != request.department:
            issues.append("申请部门与员工所属部门不一致。")
        if request.status.lower() not in self._processable_statuses:
            issues.append(f"申请状态 {request.status} 不允许进入自动采购分析。")
        if not request.product.strip() or not request.category.strip():
            issues.append("产品或采购品类为空。")
        try:
            date.fromisoformat(request.required_date)
        except ValueError:
            issues.append("要求交付日期不是有效的 ISO 日期。")
        return RequirementAssessment(
            valid=not issues,
            requester_verified=requester_verified,
            issues=issues,
            next_action="申请人补充或修正采购需求" if issues else None,
        )
