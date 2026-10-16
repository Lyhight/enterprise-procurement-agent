from typing import Protocol

from ...domain.models import NaturalLanguageIntake, ParsedPurchaseDraft


class DemandUnderstanding(Protocol):
    provider: str
    model: str | None

    def extract(self, payload: NaturalLanguageIntake) -> ParsedPurchaseDraft: ...
