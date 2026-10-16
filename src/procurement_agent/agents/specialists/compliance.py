from __future__ import annotations

from ...domain.models import PolicyAssessment, PurchaseRequest, Quotation, Supplier
from ...domain.policy import approval_level, policy_warnings


class ComplianceSpecialist:
    """Owns approval thresholds, policy warnings and guarded workflow routing."""

    def assess(
        self,
        request: PurchaseRequest,
        suppliers: list[Supplier],
        quotations: list[Quotation],
    ) -> PolicyAssessment:
        warnings = policy_warnings(request, suppliers, quotations)
        if not suppliers:
            route = "MANUAL_SOURCING"
            next_action = "采购专员扩展寻源"
        elif warnings:
            route = "HUMAN_REVIEW"
            next_action = "采购专员人工复核"
        else:
            route = "SUBMIT_APPROVAL"
            next_action = "提交审批"
        return PolicyAssessment(
            approval_level=approval_level(request.budget),
            warnings=warnings,
            route=route,
            next_action=next_action,
        )
