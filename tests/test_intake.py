from decimal import Decimal

from procurement_agent.application.intake import parse_intake
from procurement_agent.domain.models import NaturalLanguageIntake


def test_parse_complete_natural_language_request() -> None:
    draft = parse_intake(
        NaturalLanguageIntake(
            text="研发项目需要采购20台GPU服务器，预算125万元",
            requester_id="E002",
            department="研发部",
            required_date="2026-12-20",
            priority="HIGH",
        )
    )

    assert draft.product == "GPU服务器"
    assert draft.category == "服务器"
    assert draft.quantity == 20
    assert draft.budget == Decimal("1250000")
    assert draft.ready_to_submit is True


def test_parse_reports_missing_fields() -> None:
    draft = parse_intake(
        NaturalLanguageIntake(text="需要买一些设备", requester_id="E002", department="研发部")
    )
    assert draft.ready_to_submit is False
    assert "budget" in draft.missing_fields
