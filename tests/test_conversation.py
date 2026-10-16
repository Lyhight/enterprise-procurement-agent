from procurement_agent.application.conversation import ConversationService
from procurement_agent.domain.models import ConversationMessageRequest
from procurement_agent.infrastructure.persistence import ConversationStore, RequestStore


def test_multi_turn_conversation_creates_request(tmp_path) -> None:
    database_path = tmp_path / "conversation.db"
    conversations = ConversationStore(database_path)
    conversations.initialize()
    requests = RequestStore(database_path)
    requests.initialize()
    service = ConversationService(conversations, requests)

    state = service.start("E002", "研发部")
    state = service.reply(
        state.session_id,
        ConversationMessageRequest(text="需要采购20台GPU服务器"),
    )
    assert "budget" in state.draft.missing_fields
    state = service.reply(
        state.session_id,
        ConversationMessageRequest(
            text="预算125万元", required_date="2027-04-01", priority="HIGH"
        ),
    )
    assert state.status == "READY"
    assert state.draft.ready_to_submit is True

    request = service.submit(state.session_id)
    assert request.quantity == 20
    assert request.budget == 1250000
    assert conversations.get(state.session_id).status == "SUBMITTED"
