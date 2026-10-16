from decimal import Decimal

from procurement_agent.domain.policy import approval_level


def test_approval_boundaries() -> None:
    assert approval_level(Decimal("100000")) == "L1"
    assert approval_level(Decimal("100000.01")) == "L2"
    assert approval_level(Decimal("1000000")) == "L2"
    assert approval_level(Decimal("1000000.01")) == "L3"

