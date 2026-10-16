from __future__ import annotations

from ...application.scoring import rank_suppliers
from ...domain.models import (
    PurchaseRequest,
    Quotation,
    Supplier,
    SupplierRecommendation,
)
from ...domain.ruleset import EXCLUDED_AUTOMATION_RISK


class SupplierSpecialist:
    """Owns supplier qualification and deterministic recommendation logic."""

    def eligible(self, suppliers: list[Supplier], category: str) -> list[Supplier]:
        return [
            supplier
            for supplier in suppliers
            if supplier.category == category
            and supplier.qualified
            and supplier.risk_level.value != EXCLUDED_AUTOMATION_RISK
        ]

    def rank(
        self,
        request: PurchaseRequest,
        suppliers: list[Supplier],
        quotations: list[Quotation],
    ) -> list[SupplierRecommendation]:
        return rank_suppliers(request, suppliers, quotations)
