from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..domain.models import AgentSessionDecision, AgentSessionView, AnalysisResult
from ..infrastructure.memory import AgentMemoryStore
from .procurement_graph import ProcurementAgentGraph


class InteractiveAgentState(TypedDict, total=False):
    request_id: str
    execution_thread_id: str
    analysis: dict
    decision: dict
    session_status: str


class InteractiveProcurementAgent:
    """Durable human-in-the-loop wrapper around the procurement analysis graph."""

    def __init__(
        self,
        agent: ProcurementAgentGraph,
        database_path: Path,
        memory_store: AgentMemoryStore | None = None,
    ) -> None:
        self.agent = agent
        self.memory_store = memory_store
        self.connection = sqlite3.connect(database_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self.connection)
        self.graph = self._build_graph()

    def start(self, request_id: str) -> AgentSessionView:
        thread_id = f"THREAD-{uuid4().hex[:12].upper()}"
        self.graph.invoke(
            {
                "request_id": request_id,
                "execution_thread_id": f"{thread_id}:analysis",
                "session_status": "RUNNING",
            },
            self._config(thread_id),
        )
        session = self.get(thread_id)
        if self.memory_store and session.result:
            self.memory_store.remember(
                thread_id,
                request_id,
                "analysis",
                session.result.next_action,
                {
                    "run_id": session.result.run_id,
                    "approval_level": session.result.approval_level,
                    "category": session.result.request.category,
                    "department": session.result.request.department,
                    "warnings": session.result.warnings,
                    "recommended_supplier_id": (
                        session.result.recommendations[0].supplier_id
                        if session.result.recommendations
                        else None
                    ),
                },
            )
            self.memory_store.prune(request_id, keep_latest=20)
        return session

    def resume(
        self, thread_id: str, decision: AgentSessionDecision
    ) -> AgentSessionView:
        current = self.get(thread_id)
        self.graph.invoke(Command(resume=decision.model_dump()), self._config(thread_id))
        session = self.get(thread_id)
        if self.memory_store:
            request = current.result.request if current.result else None
            metadata = decision.model_dump(mode="json")
            if request is not None:
                metadata.update(
                    {
                        "category": request.category,
                        "department": request.department,
                        "approval_level": current.result.approval_level,
                    }
                )
            self.memory_store.remember(
                thread_id,
                current.request_id,
                "approval_decision",
                decision.comment or decision.decision,
                metadata,
            )
            self.memory_store.prune(current.request_id, keep_latest=20)
        return session

    def get(self, thread_id: str) -> AgentSessionView:
        snapshot = self.graph.get_state(self._config(thread_id))
        values = snapshot.values or {}
        if not values:
            raise LookupError(f"Agent 线程不存在: {thread_id}")
        pending = snapshot.interrupts[0].value if snapshot.interrupts else None
        result = (
            AnalysisResult.model_validate(values["analysis"])
            if values.get("analysis")
            else None
        )
        return AgentSessionView(
            thread_id=thread_id,
            request_id=values["request_id"],
            status="WAITING_FOR_APPROVAL" if pending else values.get("session_status", "RUNNING"),
            result=result,
            pending_action=pending,
            decision=values.get("decision"),
        )

    def _build_graph(self):
        builder = StateGraph(InteractiveAgentState)
        builder.add_node("analyze", self._analyze)
        builder.add_node("approval_gate", self._approval_gate)
        builder.add_node("complete", self._complete)
        builder.add_edge(START, "analyze")
        builder.add_edge("analyze", "approval_gate")
        builder.add_edge("approval_gate", "complete")
        builder.add_edge("complete", END)
        return builder.compile(checkpointer=self.checkpointer)

    def _analyze(self, state: InteractiveAgentState) -> dict:
        result = self.agent.invoke(
            state["request_id"],
            thread_id=state.get("execution_thread_id"),
        )
        return {"analysis": result.model_dump(mode="json")}

    def _approval_gate(self, state: InteractiveAgentState) -> dict:
        result = AnalysisResult.model_validate(state["analysis"])
        if result.approval_level == "L1" and not result.warnings:
            return {
                "decision": {"decision": "AUTO_APPROVED", "approver_id": "SYSTEM"}
            }
        previous_decisions = []
        if self.memory_store:
            previous_decisions = [
                memory.model_dump(mode="json")
                for memory in self.memory_store.search(
                    request_id=result.request.request_id,
                    category=result.request.category,
                    department=result.request.department,
                    kinds={"approval_decision"},
                    limit=5,
                )
            ]
        decision = interrupt(
            {
                "type": "procurement_approval",
                "request_id": result.request.request_id,
                "approval_level": result.approval_level,
                "warnings": result.warnings,
                "recommended_supplier": (
                    result.recommendations[0].supplier_name
                    if result.recommendations
                    else None
                ),
                "previous_decisions": previous_decisions,
            }
        )
        return {"decision": decision}

    def _complete(self, state: InteractiveAgentState) -> dict:
        status = (
            "COMPLETED"
            if state["decision"]["decision"] in {"APPROVED", "AUTO_APPROVED"}
            else "REJECTED"
        )
        return {"session_status": status}

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}
