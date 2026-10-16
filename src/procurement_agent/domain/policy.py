"""Deterministic procurement policies."""

from __future__ import annotations

from decimal import Decimal

from .models import PurchaseRequest, Quotation, Supplier
from .ruleset import (
    L1_MAX_AMOUNT,
    L2_MAX_AMOUNT,
    MIN_ELIGIBLE_SUPPLIERS,
    MIN_QUOTES_ABOVE_L1,
)


def approval_level(amount: Decimal) -> str:
    if amount <= L1_MAX_AMOUNT:
        return "L1"
    if amount <= L2_MAX_AMOUNT:
        return "L2"
    return "L3"


def policy_warnings(
    request: PurchaseRequest,
    eligible_suppliers: list[Supplier],
    quotations: list[Quotation],
) -> list[str]:
    warnings: list[str] = []
    if request.budget > L1_MAX_AMOUNT and len(quotations) < MIN_QUOTES_ABOVE_L1:
        warnings.append("采购金额超过10万元，但当前有效报价不足三家。")
    if len(eligible_suppliers) < MIN_ELIGIBLE_SUPPLIERS:
        warnings.append("符合自动推荐条件的供应商不足两家，需要人工扩展寻源。")
    return warnings

