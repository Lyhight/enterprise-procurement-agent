from __future__ import annotations

from typing import Any

from ..agents.procurement_graph import ProcurementAgentGraph
from ..agents.core import PlanAndExecutePlanner
from ..agents.local_tool_agent import LocalProcurementToolAgent
from ..agents.tool_registry import ProcurementToolRegistry
from ..infrastructure.knowledge import KnowledgeBase
from ..domain.models import AgentExecutionView, AnalysisResult
from ..infrastructure.repositories import CsvRepository


class ProcurementWorkflow:
    def __init__(
        self,
        repository: CsvRepository,
        knowledge_base: KnowledgeBase,
        planner: PlanAndExecutePlanner | None = None,
        memory_reader: Any | None = None,
        memory_writer: Any | None = None,
        checkpointer: Any | None = None,
        trace_writer: Any | None = None,
        max_iterations: int = 10,
        max_runtime_seconds: float = 30.0,
        cancellation_reader: Any | None = None,
    ) -> None:
        self.repository = repository
        self.knowledge_base = knowledge_base
        self.agent = ProcurementAgentGraph(
            repository,
            knowledge_base,
            planner=planner,
            memory_reader=memory_reader,
            memory_writer=memory_writer,
            checkpointer=checkpointer,
            trace_writer=trace_writer,
            max_iterations=max_iterations,
            max_runtime_seconds=max_runtime_seconds,
            cancellation_reader=cancellation_reader,
        )
        self.tool_agent = LocalProcurementToolAgent(
            ProcurementToolRegistry(self.agent.toolbox)
        )

    @property
    def steps(self) -> tuple[str, ...]:
        return self.agent.step_names

    @property
    def tool_names(self) -> tuple[str, ...]:
        return self.agent.tool_names

    @property
    def prompt_version(self) -> str:
        return self.agent.system_prompt.version

    @property
    def execution_nodes(self) -> tuple[str, ...]:
        return self.agent.execution_nodes

    @property
    def planning_mode(self) -> str:
        return self.agent.planner.provider

    def analyze(
        self, request_id: str, execution_id: str | None = None
    ) -> AnalysisResult:
        return self.agent.invoke(request_id, thread_id=execution_id)

    def execution(self, execution_id: str) -> AgentExecutionView:
        state = self.agent.get_execution_state(execution_id)
        plan = state.get("execution_plan", [])
        if state.get("cancelled"):
            status = "CANCELLED"
        elif state.get("result") is not None:
            status = "COMPLETED"
        elif any(step.get("status") == "FAILED" for step in plan):
            status = "FAILED"
        else:
            status = "RUNNING"
        return AgentExecutionView(
            execution_id=state.get("run_id", execution_id),
            request_id=state["request_id"],
            status=status,
            current_step_id=state.get("current_step_id"),
            iterations=state.get("iterations", 0),
            execution_plan=[
                {
                    "step_id": step.get("step_id"),
                    "objective": step.get("objective"),
                    "tool_name": step.get("tool_name"),
                    "status": step.get("status"),
                    "attempts": step.get("attempts", 0),
                    "error_category": step.get("error_category"),
                    "retryable": step.get("retryable"),
                    "error": str(step.get("error"))[:500]
                    if step.get("error")
                    else None,
                }
                for step in plan
            ],
            last_error=(str(state.get("last_error"))[:500] if state.get("last_error") else None),
        )

    def retry_execution(self, execution_id: str) -> AnalysisResult:
        return self.agent.retry_failed_execution(execution_id)

    def answer_with_tools(self, request_id: str, question: str, principal=None):
        return self.tool_agent.answer(request_id, question, principal)

