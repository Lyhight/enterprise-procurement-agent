from procurement_agent.agents.interactive_graph import InteractiveProcurementAgent
from procurement_agent.agents.procurement_graph import ProcurementAgentGraph
from procurement_agent.core.config import get_settings
from procurement_agent.domain.models import AgentSessionDecision
from procurement_agent.infrastructure.knowledge import KnowledgeBase
from procurement_agent.infrastructure.memory import AgentMemoryStore
from procurement_agent.infrastructure.repositories import CsvRepository


def _agent(database_path):
    settings = get_settings()
    base_agent = ProcurementAgentGraph(
        CsvRepository(settings.company_data_dir),
        KnowledgeBase(settings.documents_dir),
    )
    return InteractiveProcurementAgent(base_agent, database_path)


def test_agent_session_interrupts_and_resumes_with_durable_state(tmp_path) -> None:
    agent = _agent(tmp_path / "agent-checkpoints.db")

    waiting = agent.start("PR001")

    assert waiting.status == "WAITING_FOR_APPROVAL"
    assert waiting.pending_action["type"] == "procurement_approval"
    assert waiting.result is not None
    assert waiting.result.request.request_id == "PR001"
    assert waiting.result.run_id == f"{waiting.thread_id}:analysis"

    completed = agent.resume(
        waiting.thread_id,
        AgentSessionDecision(
            decision="APPROVED",
            approver_id="E001",
            comment="预算与供应商建议已复核。",
        ),
    )

    assert completed.status == "COMPLETED"
    assert completed.pending_action is None
    assert completed.decision["decision"] == "APPROVED"
    assert agent.get(waiting.thread_id).status == "COMPLETED"


def test_agent_session_can_be_rejected(tmp_path) -> None:
    agent = _agent(tmp_path / "agent-checkpoints.db")
    waiting = agent.start("PR001")

    rejected = agent.resume(
        waiting.thread_id,
        AgentSessionDecision(
            decision="REJECTED",
            approver_id="E001",
            comment="需求信息不足。",
        ),
    )

    assert rejected.status == "REJECTED"
    assert rejected.decision["comment"] == "需求信息不足。"


def test_agent_reuses_internal_long_term_decision_memory(tmp_path) -> None:
    database_path = tmp_path / "agent-checkpoints.db"
    memory_store = AgentMemoryStore(database_path)
    memory_store.initialize()
    settings = get_settings()
    agent = InteractiveProcurementAgent(
        ProcurementAgentGraph(
            CsvRepository(settings.company_data_dir),
            KnowledgeBase(settings.documents_dir),
        ),
        database_path,
        memory_store,
    )
    first = agent.start("PR001")
    agent.resume(
        first.thread_id,
        AgentSessionDecision(
            decision="REJECTED", approver_id="E001", comment="需要补充技术参数。"
        ),
    )

    second = agent.start("PR001")

    previous = second.pending_action["previous_decisions"]
    assert previous[0]["kind"] == "approval_decision"
    assert previous[0]["content"] == "需要补充技术参数。"
    assert previous[0]["metadata"]["category"] == "服务器"
    assert previous[0]["metadata"]["department"] == "研发部"


def test_long_term_memory_supports_dedup_relevance_and_lifecycle(tmp_path) -> None:
    store = AgentMemoryStore(tmp_path / "memory.db")
    store.initialize()
    metadata = {"category": "服务器", "department": "研发部"}
    first = store.remember("T-1", "PR001", "analysis", "首选低风险供应商", metadata)
    duplicate = store.remember(
        "T-2", "PR001", "analysis", "首选低风险供应商", metadata
    )
    related = store.remember(
        "T-3",
        "PR-OLDER",
        "approval_decision",
        "同类服务器采购需补充技术参数",
        metadata,
    )
    unrelated = store.remember(
        "T-4",
        "PR-OFFICE",
        "analysis",
        "办公设备采购记录",
        {"category": "办公设备", "department": "行政部"},
    )

    memories = store.search(
        request_id="PR001", category="服务器", department="研发部", limit=10
    )

    assert duplicate.memory_id == first.memory_id
    assert [memory.memory_id for memory in memories[:2]] == [
        first.memory_id,
        related.memory_id,
    ]
    assert unrelated.memory_id not in {memory.memory_id for memory in memories}
    assert store.forget(related.memory_id) is True
    assert store.forget(related.memory_id) is False

    store.remember("T-5", "PR001", "analysis", "第二条", metadata)
    store.remember("T-6", "PR001", "analysis", "第三条", metadata)
    assert store.prune("PR001", keep_latest=1) == 2
    assert len(store.list("PR001")) == 1
