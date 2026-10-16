from __future__ import annotations

import re
from decimal import Decimal

from ..domain.models import NaturalLanguageIntake, ParsedPurchaseDraft


PRODUCT_RULES = (
    (re.compile(r"gpu\s*服务器", re.IGNORECASE), "GPU服务器", "服务器"),
    (re.compile(r"服务器", re.IGNORECASE), "服务器", "服务器"),
    (re.compile(r"plc\s*控制设备", re.IGNORECASE), "PLC控制设备", "工业设备"),
    (re.compile(r"plc", re.IGNORECASE), "PLC控制设备", "工业设备"),
    (re.compile(r"交换机"), "网络交换机", "网络设备"),
    (re.compile(r"工控机"), "工业计算机", "工业计算机"),
    (re.compile(r"传感器"), "工业传感器", "传感器"),
)


def parse_intake(payload: NaturalLanguageIntake) -> ParsedPurchaseDraft:
    product, category = _parse_product(payload.text)
    quantity = _parse_quantity(payload.text)
    budget = _parse_budget(payload.text)
    missing_fields = [
        name
        for name, value in (
            ("product", product),
            ("category", category),
            ("quantity", quantity),
            ("budget", budget),
            ("required_date", payload.required_date),
        )
        if value is None
    ]
    return ParsedPurchaseDraft(
        requester_id=payload.requester_id,
        department=payload.department,
        product=product,
        category=category,
        quantity=quantity,
        budget=budget,
        required_date=payload.required_date,
        priority=payload.priority,
        missing_fields=missing_fields,
        ready_to_submit=not missing_fields,
    )


class RuleBasedDemandUnderstanding:
    provider = "local"
    model = None

    def extract(self, payload: NaturalLanguageIntake) -> ParsedPurchaseDraft:
        return parse_intake(payload)


def _parse_product(text: str) -> tuple[str | None, str | None]:
    for pattern, product, category in PRODUCT_RULES:
        if pattern.search(text):
            return product, category
    return None, None


def _parse_quantity(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:台|套|个|件|只|组|批)", text)
    return int(match.group(1)) if match else None


def _parse_budget(text: str) -> Decimal | None:
    match = re.search(
        r"(?:预算|金额|不超过)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(万元|万|元)", text
    )
    if not match:
        return None
    amount = Decimal(match.group(1))
    return amount * Decimal("10000") if match.group(2) in {"万", "万元"} else amount
