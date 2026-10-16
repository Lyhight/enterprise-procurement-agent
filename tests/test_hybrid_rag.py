from procurement_agent.infrastructure.rag import (
    HybridPolicyRetriever,
    LocalHashEmbedding,
    RetrievalDocument,
)


def test_hybrid_retriever_combines_bm25_and_vector_scores() -> None:
    documents = [
        RetrievalDocument("policy.md", "审批", "高风险供应商必须升级审批。"),
        RetrievalDocument("delivery.md", "交付", "紧急采购应核查交付周期。"),
    ]
    retriever = HybridPolicyRetriever(documents)

    rows = retriever.search("高风险供应商审批", limit=2)

    assert rows[0].document.section == "审批"
    assert rows[0].lexical_score > 0
    assert rows[0].vector_score > 0


def test_local_embedding_is_deterministic_and_normalized() -> None:
    embedding = LocalHashEmbedding(dimensions=64)
    first = embedding.embed("GPU 服务器采购")
    second = embedding.embed("GPU 服务器采购")

    assert first == second
    assert round(sum(value * value for value in first), 6) == 1.0
