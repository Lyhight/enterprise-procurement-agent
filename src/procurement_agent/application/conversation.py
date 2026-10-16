from __future__ import annotations

from .intake import RuleBasedDemandUnderstanding
from .ports.language_model import DemandUnderstanding
from ..domain.models import (
    ConversationMessageRequest,
    ConversationState,
    NaturalLanguageIntake,
    ParsedPurchaseDraft,
    PurchaseRequest,
)
from ..infrastructure.persistence import ConversationStore, RequestStore


FIELD_LABELS = {
    "product": "采购产品",
    "category": "采购品类",
    "quantity": "采购数量",
    "budget": "预算金额",
    "required_date": "要求到货日期",
}


class ConversationService:
    def __init__(
        self,
        conversations: ConversationStore,
        requests: RequestStore,
        understanding: DemandUnderstanding | None = None,
    ) -> None:
        self.conversations = conversations
        self.requests = requests
        self.understanding = understanding or RuleBasedDemandUnderstanding()

    def start(self, requester_id: str, department: str) -> ConversationState:
        draft = ParsedPurchaseDraft(
            requester_id=requester_id,
            department=department,
            product=None,
            category=None,
            quantity=None,
            budget=None,
            required_date=None,
            priority="MEDIUM",
            missing_fields=["product", "category", "quantity", "budget", "required_date"],
            ready_to_submit=False,
        )
        state = self.conversations.create(requester_id, department, draft)
        self.conversations.add_message(
            state.session_id,
            "assistant",
            "请描述需要采购的产品、数量、预算和要求到货日期。",
        )
        return self.conversations.get(state.session_id)

    def reply(self, session_id: str, message: ConversationMessageRequest) -> ConversationState:
        current = self.conversations.get(session_id)
        if current.status == "SUBMITTED":
            raise ValueError("该采购对话已经提交，不能继续修改。")
        parsed = self.understanding.extract(
            NaturalLanguageIntake(
                text=message.text,
                requester_id=current.requester_id,
                department=current.department,
                required_date=message.required_date,
                priority=message.priority or current.draft.priority,
            )
        )
        merged = _merge_draft(current.draft, parsed)
        self.conversations.add_message(session_id, "user", message.text)
        self.conversations.update_draft(session_id, merged)
        self.conversations.add_message(session_id, "assistant", _assistant_response(merged))
        return self.conversations.get(session_id)

    def submit(self, session_id: str) -> PurchaseRequest:
        state = self.conversations.get(session_id)
        if state.status == "SUBMITTED":
            raise ValueError("该采购对话已经提交。")
        if not state.draft.ready_to_submit:
            labels = "、".join(FIELD_LABELS[field] for field in state.draft.missing_fields)
            raise ValueError(f"采购需求尚不完整，仍缺少：{labels}。")
        request = self.requests.create(state.draft)
        self.conversations.mark_submitted(session_id)
        return request


def _merge_draft(current: ParsedPurchaseDraft, incoming: ParsedPurchaseDraft) -> ParsedPurchaseDraft:
    values = {
        "product": incoming.product or current.product,
        "category": incoming.category or current.category,
        "quantity": incoming.quantity or current.quantity,
        "budget": incoming.budget or current.budget,
        "required_date": incoming.required_date or current.required_date,
    }
    missing = [field for field, value in values.items() if value is None]
    return ParsedPurchaseDraft(
        requester_id=current.requester_id,
        department=current.department,
        **values,
        priority=incoming.priority or current.priority,
        missing_fields=missing,
        ready_to_submit=not missing,
    )


def _assistant_response(draft: ParsedPurchaseDraft) -> str:
    if draft.ready_to_submit:
        return "采购信息已经完整，可以提交生成正式采购申请。"
    labels = "、".join(FIELD_LABELS[field] for field in draft.missing_fields)
    return f"还需要补充：{labels}。"
