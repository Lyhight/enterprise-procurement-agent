from __future__ import annotations

from ...domain.models import DemandExtraction, NaturalLanguageIntake, ParsedPurchaseDraft


class OpenAIDemandUnderstanding:
    provider = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self.model = model
        self.client = OpenAI(api_key=api_key)

    def extract(self, payload: NaturalLanguageIntake) -> ParsedPurchaseDraft:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "从中文采购描述中提取字段。只提取用户明确提供的信息；"
                        "不确定的字段必须返回 null。预算统一换算为人民币元。"
                    ),
                },
                {"role": "user", "content": payload.text},
            ],
            text_format=DemandExtraction,
        )
        extracted = response.output_parsed
        if extracted is None:
            raise RuntimeError("大模型没有返回可解析的采购需求结构。")
        values = {
            "product": extracted.product,
            "category": extracted.category,
            "quantity": extracted.quantity,
            "budget": extracted.budget,
            "required_date": payload.required_date or extracted.required_date,
        }
        missing = [field for field, value in values.items() if value is None]
        return ParsedPurchaseDraft(
            requester_id=payload.requester_id,
            department=payload.department,
            **values,
            priority=payload.priority or extracted.priority or "MEDIUM",
            missing_fields=missing,
            ready_to_submit=not missing,
        )
