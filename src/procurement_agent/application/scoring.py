from __future__ import annotations

from decimal import Decimal

from ..domain.models import PurchaseRequest, Quotation, Supplier, SupplierRecommendation
from ..domain.ruleset import (
    EXPERIENCE_POINTS_PER_YEAR,
    EXPERIENCE_SCORE_CAP,
    MISSING_QUOTE_PRICE_SCORE,
    RISK_SCORES,
    SCORING_WEIGHTS,
)


def rank_suppliers(
    request: PurchaseRequest,
    suppliers: list[Supplier],
    quotations: list[Quotation],
) -> list[SupplierRecommendation]:
    quote_by_supplier = {quote.supplier_id: quote for quote in quotations}
    totals = {
        supplier_id: quote.unit_price * request.quantity
        for supplier_id, quote in quote_by_supplier.items()
    }
    quoted_totals = list(totals.values())
    low = min(quoted_totals) if quoted_totals else None
    high = max(quoted_totals) if quoted_totals else None

    recommendations: list[SupplierRecommendation] = []
    for supplier in suppliers:
        price_score = _price_score(totals.get(supplier.supplier_id), low, high)
        experience_score = min(
            supplier.cooperation_year * EXPERIENCE_POINTS_PER_YEAR,
            EXPERIENCE_SCORE_CAP,
        )
        risk_score = RISK_SCORES[supplier.risk_level.value]
        score = (
            Decimal(str(supplier.rating)) * SCORING_WEIGHTS["rating"]
            + Decimal(str(supplier.delivery_score)) * SCORING_WEIGHTS["delivery"]
            + Decimal(str(price_score)) * SCORING_WEIGHTS["price"]
            + Decimal(str(risk_score)) * SCORING_WEIGHTS["risk"]
            + Decimal(str(experience_score)) * SCORING_WEIGHTS["experience"]
        )
        reasons = [
            f"供应商综合评分 {supplier.rating:.0f}/100",
            f"交付评分 {supplier.delivery_score:.0f}/100",
            f"风险等级 {supplier.risk_level.value}",
        ]
        total = totals.get(supplier.supplier_id)
        if total is None:
            reasons.append("暂无有效报价，价格项按中性分计算")
        elif total <= request.budget:
            reasons.append("报价总额在预算内")
        else:
            reasons.append("报价总额超过申请预算")

        recommendations.append(
            SupplierRecommendation(
                supplier_id=supplier.supplier_id,
                supplier_name=supplier.supplier_name,
                score=round(float(score), 2),
                quoted_total=total,
                reasons=reasons,
            )
        )
    return sorted(recommendations, key=lambda item: item.score, reverse=True)


def _price_score(total: Decimal | None, low: Decimal | None, high: Decimal | None) -> float:
    if total is None:
        return float(MISSING_QUOTE_PRICE_SCORE)
    if low == high:
        return 100.0
    assert low is not None and high is not None
    return float(100 * (high - total) / (high - low))

