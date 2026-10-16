from __future__ import annotations

from ..domain.models import (
    DecisionGuardrailReport,
    PolicyAssessment,
    PolicyEvidence,
    PurchaseRequest,
    Quotation,
    RequirementAssessment,
    Supplier,
    SupplierRecommendation,
)
from ..domain.policy import approval_level, policy_warnings
from ..domain.ruleset import EXCLUDED_AUTOMATION_RISK


class DecisionGuardrailError(RuntimeError):
    def __init__(self, report: DecisionGuardrailReport) -> None:
        self.report = report
        super().__init__(
            "Agent 最终决策安全校验失败：" + "；".join(report.violations)
        )


def validate_decision_state(state: dict) -> DecisionGuardrailReport:
    request = PurchaseRequest.model_validate(state["request"])
    requirement = RequirementAssessment.model_validate(
        state["requirement_assessment"]
    )
    suppliers = [
        Supplier.model_validate(item) for item in state.get("eligible_suppliers", [])
    ]
    quotations = [
        Quotation.model_validate(item) for item in state.get("quotations", [])
    ]
    recommendations = [
        SupplierRecommendation.model_validate(item)
        for item in state.get("recommendations", [])
    ]
    assessment = PolicyAssessment.model_validate(state["policy_assessment"])
    evidence = [
        PolicyEvidence.model_validate(item)
        for item in state.get("policy_evidence", [])
    ]

    violations: list[str] = []
    supplier_ids = [supplier.supplier_id for supplier in suppliers]
    supplier_id_set = set(supplier_ids)
    quotation_ids = [quote.quotation_id for quote in quotations]
    quotations_by_supplier: dict[str, list[Quotation]] = {}
    for quote in quotations:
        quotations_by_supplier.setdefault(quote.supplier_id, []).append(quote)
    recommendation_ids = [item.supplier_id for item in recommendations]

    supplier_scope_valid = all(
        supplier.category == request.category
        and supplier.qualified
        and supplier.risk_level.value != EXCLUDED_AUTOMATION_RISK
        for supplier in suppliers
    ) and len(supplier_ids) == len(supplier_id_set)
    if not supplier_scope_valid:
        violations.append("候选供应商存在品类、资质、风险或重复问题。")

    quotation_scope_valid = (
        len(quotation_ids) == len(set(quotation_ids))
        and all(
            quote.request_id == request.request_id
            and quote.supplier_id in supplier_id_set
            for quote in quotations
        )
    )
    if not quotation_scope_valid:
        violations.append("报价存在申请归属、供应商归属或重复问题。")

    recommendation_scope_valid = (
        len(recommendation_ids) == len(set(recommendation_ids))
        and set(recommendation_ids).issubset(supplier_id_set)
        and all(0 <= item.score <= 100 for item in recommendations)
    )
    if not recommendation_scope_valid:
        violations.append("推荐结果包含越权供应商、重复供应商或非法评分。")

    quoted_totals_valid = True
    for recommendation in recommendations:
        expected_totals = {
            quote.unit_price * request.quantity
            for quote in quotations_by_supplier.get(recommendation.supplier_id, [])
        }
        total_valid = (
            recommendation.quoted_total in expected_totals
            if expected_totals
            else recommendation.quoted_total is None
        )
        if not total_valid:
            quoted_totals_valid = False
            break
    if not quoted_totals_valid:
        violations.append("推荐总价与有效报价及采购数量不一致。")

    expected_warnings = policy_warnings(request, suppliers, quotations)
    policy_valid = (
        assessment.approval_level == approval_level(request.budget)
        and assessment.warnings == expected_warnings
        and _expected_route(suppliers, expected_warnings) == assessment.route
    )
    if not policy_valid:
        violations.append("审批等级、制度警告或流程路由与当前规则集不一致。")

    invalid_request_isolated = requirement.valid or (
        not suppliers and not quotations and not recommendations
    )
    if not invalid_request_isolated:
        violations.append("未通过需求校验的申请仍产生了自动寻源结果。")

    evidence_valid = bool(evidence) and all(
        item.source.strip() and item.section.strip() and item.content.strip()
        for item in evidence
    )
    if not evidence_valid:
        violations.append("最终决策缺少完整、可追溯的制度证据。")

    checks = {
        "supplier_scope": supplier_scope_valid,
        "quotation_scope": quotation_scope_valid,
        "recommendation_scope": recommendation_scope_valid,
        "quoted_totals": quoted_totals_valid,
        "policy_consistency": policy_valid,
        "invalid_request_isolation": invalid_request_isolated,
        "policy_evidence": evidence_valid,
    }
    return DecisionGuardrailReport(
        valid=not violations,
        checks=checks,
        violations=violations,
    )


def _expected_route(suppliers: list[Supplier], warnings: list[str]) -> str:
    if not suppliers:
        return "MANUAL_SOURCING"
    if warnings:
        return "HUMAN_REVIEW"
    return "SUBMIT_APPROVAL"
