from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.knowledge import KnowledgeBase


def test_search_returns_policy_source() -> None:
    knowledge = KnowledgeBase(get_settings().documents_dir)
    results = knowledge.search("超过十万元需要几家报价")

    assert knowledge.document_count == 2
    assert knowledge.chunk_count == 3
    assert results
    assert results[0].source == "procurement_policy.md"


def test_empty_query_returns_no_results() -> None:
    knowledge = KnowledgeBase(get_settings().documents_dir)
    assert knowledge.search("  ") == []
