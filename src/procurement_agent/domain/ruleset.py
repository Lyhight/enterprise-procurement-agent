from __future__ import annotations

import hashlib
import json
from decimal import Decimal


PROCUREMENT_RULESET_VERSION = "1.0.0"

L1_MAX_AMOUNT = Decimal("100000")
L2_MAX_AMOUNT = Decimal("1000000")
MIN_QUOTES_ABOVE_L1 = 3
MIN_ELIGIBLE_SUPPLIERS = 2
PROCESSABLE_REQUEST_STATUSES = frozenset({"pending", "submitted"})
EXCLUDED_AUTOMATION_RISK = "HIGH"

SCORING_WEIGHTS = {
    "rating": Decimal("0.30"),
    "delivery": Decimal("0.25"),
    "price": Decimal("0.25"),
    "risk": Decimal("0.15"),
    "experience": Decimal("0.05"),
}
RISK_SCORES = {"LOW": 100, "MEDIUM": 65, "HIGH": 0}
EXPERIENCE_POINTS_PER_YEAR = 10
EXPERIENCE_SCORE_CAP = 100
MISSING_QUOTE_PRICE_SCORE = 50


def ruleset_manifest() -> dict:
    return {
        "version": PROCUREMENT_RULESET_VERSION,
        "approval": {
            "l1_max_amount": str(L1_MAX_AMOUNT),
            "l2_max_amount": str(L2_MAX_AMOUNT),
        },
        "sourcing": {
            "min_quotes_above_l1": MIN_QUOTES_ABOVE_L1,
            "min_eligible_suppliers": MIN_ELIGIBLE_SUPPLIERS,
            "excluded_automation_risk": EXCLUDED_AUTOMATION_RISK,
            "processable_request_statuses": sorted(PROCESSABLE_REQUEST_STATUSES),
        },
        "scoring": {
            "weights": {key: str(value) for key, value in SCORING_WEIGHTS.items()},
            "risk_scores": RISK_SCORES,
            "experience_points_per_year": EXPERIENCE_POINTS_PER_YEAR,
            "experience_score_cap": EXPERIENCE_SCORE_CAP,
            "missing_quote_price_score": MISSING_QUOTE_PRICE_SCORE,
        },
    }


def ruleset_fingerprint() -> str:
    payload = json.dumps(
        ruleset_manifest(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


PROCUREMENT_RULESET_FINGERPRINT = ruleset_fingerprint()
