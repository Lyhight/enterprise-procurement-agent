from fastapi import APIRouter, Query

from ...domain.models import AgentCapabilities, PolicyEvidence
from ...agents.tool_contracts import TOOL_CONTRACT_VERSION
from ...domain.ruleset import (
    PROCUREMENT_RULESET_FINGERPRINT,
    PROCUREMENT_RULESET_VERSION,
)
from ..dependencies import knowledge_base, workflow

router = APIRouter(prefix="/api/v1", tags=["知识库"])


@router.get("/knowledge/status")
def knowledge_status() -> dict[str, int | str]:
    return {
        "documents": knowledge_base.document_count,
        "chunks": knowledge_base.chunk_count,
        "retrieval_mode": knowledge_base.retrieval_mode,
    }


@router.get("/knowledge/search", response_model=list[PolicyEvidence])
def search_knowledge(
    query: str = Query(min_length=2, description="采购制度问题"),
    limit: int = Query(default=3, ge=1, le=10),
) -> list[PolicyEvidence]:
    return knowledge_base.search(query, limit)


@router.get("/agent/steps")
def agent_steps() -> dict[str, list[str]]:
    return {"steps": list(workflow.steps)}


@router.get("/agent/capabilities", response_model=AgentCapabilities)
def agent_capabilities() -> AgentCapabilities:
    return AgentCapabilities(
        graph_steps=list(workflow.steps),
        execution_graph=list(workflow.execution_nodes),
        tools=list(workflow.tool_names),
        system_prompt_version=workflow.prompt_version,
        supports_conditional_routing=True,
        supports_iterative_tool_loop=True,
        planning_mode=workflow.planning_mode,
        max_iterations=workflow.agent.max_iterations,
        max_runtime_seconds=workflow.agent.max_runtime_seconds,
        supports_durable_sessions=True,
        supports_human_interrupt=True,
        supports_long_term_memory=True,
        supports_planner_fallback=True,
        supports_planner_fallback_trace=True,
        supports_tool_contract_validation=True,
        supports_execution_cancellation=True,
        supports_tamper_evident_trace=True,
        supports_decision_provenance=True,
        supports_provenance_replay=True,
        supports_final_decision_guardrails=True,
        supports_context_injection_defense=True,
        tool_contract_version=TOOL_CONTRACT_VERSION,
        ruleset_version=PROCUREMENT_RULESET_VERSION,
        ruleset_fingerprint=PROCUREMENT_RULESET_FINGERPRINT,
        retrieval_mode=knowledge_base.retrieval_mode,
    )

