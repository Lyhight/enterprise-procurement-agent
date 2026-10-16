from __future__ import annotations

import json
import logging
import operator
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Annotated, Any, Callable, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from ..application.authorization import ToolPrincipal
from ..core.prompts import load_prompt
from ..domain.models import (
    AgentTraceStep,
    AnalysisResult,
    DecisionGuardrailReport,
    PolicyAssessment,
    PolicyEvidence,
    PurchaseRequest,
    Quotation,
    RequirementAssessment,
    Supplier,
    SupplierRecommendation,
)
from ..domain.ruleset import (
    PROCUREMENT_RULESET_FINGERPRINT,
    PROCUREMENT_RULESET_VERSION,
)
from ..infrastructure.knowledge import KnowledgeBase
from ..infrastructure.repositories import CsvRepository
from .core import (
    AgentExecutionCancelled,
    AgentExecutionDeadlineExceeded,
    LocalPlanAndExecutePlanner,
    PlanAndExecutePlanner,
    classify_tool_error,
)
from .provenance import (
    build_decision_provenance,
    build_source_evidence_manifest,
    canonical_hash,
)
from .guardrails import DecisionGuardrailError, validate_decision_state
from .tool_registry import ProcurementToolRegistry
from .tool_contracts import TOOL_CONTRACT_VERSION
from .tools import ProcurementToolbox

logger = logging.getLogger(__name__)


class MemoryReader(Protocol):
    def list(self, request_id: str, limit: int = 20) -> list: ...


class MemoryWriter(Protocol):
    def remember(
        self,
        thread_id: str,
        request_id: str,
        kind: str,
        content: str,
        metadata: dict | None = None,
    ) -> Any: ...

    def prune(self, request_id: str, keep_latest: int = 20) -> int: ...


class TraceWriter(Protocol):
    def record(
        self,
        run_id: str,
        request_id: str,
        event_type: str,
        status: str,
        payload: dict | None = None,
        *,
        step_id: str | None = None,
        duration_ms: float | None = None,
    ) -> dict: ...


class CancellationReader(Protocol):
    def find(self, execution_id: str) -> Any | None: ...


class ProcurementAgentState(TypedDict, total=False):
    run_id: str
    request_id: str
    run_started_at: str
    run_deadline_at: str
    plan_goal: str
    execution_plan: list[dict]
    current_step_id: str
    route: str
    request: dict
    requirement_assessment: dict
    eligible_suppliers: list[dict]
    quotations: list[dict]
    recommendations: list[dict]
    policy_assessment: dict
    policy_evidence: list[dict]
    last_error: str | None
    iterations: int
    tool_calls: Annotated[list[dict], operator.add]
    plan_revisions: Annotated[list[str], operator.add]
    planner_events: Annotated[list[dict], operator.add]
    long_term_memories: list[dict]
    cancelled: bool
    cancellation: dict
    guardrail_report: dict
    result: AnalysisResult


class ProcurementAgentGraph:
    """Plan-and-Execute agent that replans after every observed tool result."""

    step_names = (
        "load_request",
        "validate_request",
        "screen_suppliers",
        "collect_quotations",
        "rank_suppliers",
        "check_policy",
        "retrieve_policy",
        "validate_decision",
        "finalize",
    )
    execution_nodes = (
        "create_plan",
        "execute_step",
        "replan",
        "validate_decision",
        "finalize",
        "cancel",
        "abort",
    )

    def __init__(
        self,
        repository: CsvRepository,
        knowledge_base: KnowledgeBase,
        planner: PlanAndExecutePlanner | None = None,
        max_iterations: int = 10,
        max_runtime_seconds: float = 30.0,
        checkpointer: Any | None = None,
        memory_reader: MemoryReader | None = None,
        memory_writer: MemoryWriter | None = None,
        trace_writer: TraceWriter | None = None,
        clock: Callable[[], datetime] | None = None,
        cancellation_reader: CancellationReader | None = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations 必须大于 0。")
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds 必须大于 0。")
        self.repository = repository
        self.knowledge_base = knowledge_base
        self.toolbox = ProcurementToolbox(repository, knowledge_base)
        self.registry = ProcurementToolRegistry(self.toolbox)
        self.principal = ToolPrincipal("PROCUREMENT-AGENT", "SYSTEM_AGENT")
        self.planner = planner or LocalPlanAndExecutePlanner()
        self.max_iterations = max_iterations
        self.max_runtime_seconds = max_runtime_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.checkpointer = checkpointer
        self.memory_reader = memory_reader
        self.memory_writer = memory_writer
        self.trace_writer = trace_writer
        self.cancellation_reader = cancellation_reader
        self.system_prompt = load_prompt("system.md")
        self.graph = self._build_graph()

    @property
    def tool_names(self) -> tuple[str, ...]:
        return self.registry.names

    def invoke(self, request_id: str, thread_id: str | None = None) -> AnalysisResult:
        run_id = thread_id or f"RUN-{uuid4().hex[:12].upper()}"
        run_started_clock = perf_counter()
        run_started_at = self._utc_now()
        run_deadline_at = run_started_at + timedelta(seconds=self.max_runtime_seconds)
        config = None
        if self.checkpointer is not None:
            thread_id = thread_id or run_id
            config = self._config(thread_id)
            existing = self.graph.get_state(config)
            if existing.values:
                existing_result = existing.values.get("result")
                if existing_result is not None:
                    return AnalysisResult.model_validate(existing_result)
                raise ValueError(
                    f"Agent 执行 ID 已存在且尚未完成: {thread_id}；"
                    "请查询执行状态或使用恢复接口。"
                )
        memories = self._load_memories(request_id)
        self._write_trace(
            run_id,
            request_id,
            "RUN_STARTED",
            "RUNNING",
            {
                "planner_provider": self.planner.provider,
                "max_iterations": self.max_iterations,
                "max_runtime_seconds": self.max_runtime_seconds,
                "deadline_at": run_deadline_at.isoformat(),
            },
        )
        try:
            state = self.graph.invoke(
                {
                    "run_id": run_id,
                    "request_id": request_id,
                    "run_started_at": run_started_at.isoformat(),
                    "run_deadline_at": run_deadline_at.isoformat(),
                    "iterations": 0,
                    "tool_calls": [],
                    "plan_revisions": [],
                    "planner_events": [],
                    "long_term_memories": memories,
                },
                config,
            )
            if state.get("cancelled"):
                cancellation = state.get("cancellation", {})
                raise AgentExecutionCancelled(
                    f"Agent 执行已取消：{cancellation.get('reason') or '未提供原因'}"
                )
        except AgentExecutionCancelled as exc:
            cancellation = self._cancellation(run_id)
            self._write_trace(
                run_id,
                request_id,
                "RUN_CANCELLED",
                "CANCELLED",
                {
                    "error_type": type(exc).__name__,
                    "reason": cancellation.get("reason") if cancellation else str(exc),
                    "requested_by": (
                        cancellation.get("requested_by") if cancellation else None
                    ),
                    "requested_at": (
                        cancellation.get("requested_at") if cancellation else None
                    ),
                },
                duration_ms=round((perf_counter() - run_started_clock) * 1000, 3),
            )
            raise
        except Exception as exc:
            self._write_trace(
                run_id,
                request_id,
                "RUN_FAILED",
                "FAILED",
                {"error_type": type(exc).__name__, "error": str(exc)[:1000]},
                duration_ms=round((perf_counter() - run_started_clock) * 1000, 3),
            )
            raise
        result = state["result"]
        self._remember_result(run_id, result)
        self._write_trace(
            run_id,
            request_id,
            "RUN_COMPLETED",
            "COMPLETED",
            {
                "next_action": result.next_action,
                "source_fingerprint": (
                    result.provenance.source_fingerprint
                    if result.provenance
                    else None
                ),
                "decision_fingerprint": (
                    result.provenance.decision_fingerprint
                    if result.provenance
                    else None
                ),
                "planner_fallback_count": result.planner_fallback_count,
                "planner_model_attempt_count": result.planner_model_attempt_count,
                "planner_model_failure_count": result.planner_model_failure_count,
                "guardrail_valid": (
                    result.guardrail_report.valid
                    if result.guardrail_report
                    else False
                ),
            },
            duration_ms=round((perf_counter() - run_started_clock) * 1000, 3),
        )
        return result

    def get_execution_state(self, thread_id: str) -> dict:
        if self.checkpointer is None:
            raise RuntimeError("当前 Agent 未配置持久化 checkpointer。")
        snapshot = self.graph.get_state(self._config(thread_id))
        if not snapshot.values:
            raise LookupError(f"Agent 执行线程不存在: {thread_id}")
        return dict(snapshot.values)

    def retry_failed_execution(self, thread_id: str) -> AnalysisResult:
        """Resume a durable run after an operator has fixed a transient tool failure."""
        if self.checkpointer is None:
            raise RuntimeError("当前 Agent 未配置持久化 checkpointer。")
        config = self._config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            raise LookupError(f"Agent 执行线程不存在: {thread_id}")
        state = dict(snapshot.values)
        plan = [dict(step) for step in state["execution_plan"]]
        failed = [step for step in plan if step["status"] == "FAILED"]
        if len(failed) != 1:
            raise ValueError("执行线程当前不存在唯一的失败步骤，不能执行恢复。")
        failed_step = failed[0]
        run_id = state.get("run_id", thread_id)
        request_id = state["request_id"]
        if self._cancellation(run_id):
            raise ValueError("已取消的 Agent 执行不能恢复，请创建新的 execution_id。")
        resume_started_clock = perf_counter()
        resume_started_at = self._utc_now()
        resume_deadline_at = resume_started_at + timedelta(
            seconds=self.max_runtime_seconds
        )
        self._write_trace(
            run_id,
            request_id,
            "RUN_RESUME_STARTED",
            "RUNNING",
            {
                "failed_step_id": failed_step["step_id"],
                "max_runtime_seconds": self.max_runtime_seconds,
                "deadline_at": resume_deadline_at.isoformat(),
            },
            step_id=failed_step["step_id"],
        )
        failed_step["status"] = "PENDING"
        failed_step["attempts"] = 0
        failed_step["error"] = None
        failed_step["error_category"] = None
        failed_step["retryable"] = None
        try:
            self.graph.update_state(
                config,
                {
                    "execution_plan": plan,
                    "current_step_id": failed_step["step_id"],
                    "route": "execute",
                    "last_error": None,
                    "run_started_at": resume_started_at.isoformat(),
                    "run_deadline_at": resume_deadline_at.isoformat(),
                },
                as_node="replan",
            )
            resumed = self.graph.invoke(None, config)
        except Exception as exc:
            self._write_trace(
                run_id,
                request_id,
                "RUN_RESUME_FAILED",
                "FAILED",
                {"error_type": type(exc).__name__, "error": str(exc)[:1000]},
                step_id=failed_step["step_id"],
                duration_ms=round(
                    (perf_counter() - resume_started_clock) * 1000, 3
                ),
            )
            raise
        result = resumed["result"]
        self._remember_result(run_id, result)
        self._write_trace(
            run_id,
            request_id,
            "RUN_RESUME_COMPLETED",
            "COMPLETED",
            {
                "next_action": result.next_action,
                "planner_fallback_count": result.planner_fallback_count,
                "planner_model_attempt_count": result.planner_model_attempt_count,
                "planner_model_failure_count": result.planner_model_failure_count,
            },
            step_id=failed_step["step_id"],
            duration_ms=round((perf_counter() - resume_started_clock) * 1000, 3),
        )
        return result

    def _build_graph(self):
        builder = StateGraph(ProcurementAgentState)
        builder.add_node("create_plan", self._create_plan)
        builder.add_node("execute_step", self._execute_step)
        builder.add_node("replan", self._replan)
        builder.add_node("validate_decision", self._validate_decision)
        builder.add_node("finalize", self._finalize)
        builder.add_node("cancel", self._cancel)
        builder.add_node("abort", self._abort)
        builder.add_edge(START, "create_plan")
        builder.add_edge("create_plan", "execute_step")
        builder.add_edge("execute_step", "replan")
        builder.add_conditional_edges(
            "replan",
            self._route_replan,
            {
                "execute": "execute_step",
                "finalize": "validate_decision",
                "cancel": "cancel",
                "abort": "abort",
            },
        )
        builder.add_edge("validate_decision", "finalize")
        builder.add_edge("finalize", END)
        builder.add_edge("cancel", END)
        builder.add_edge("abort", END)
        return builder.compile(checkpointer=self.checkpointer)

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def _create_plan(self, state: ProcurementAgentState) -> dict:
        self._raise_if_cancelled(state, "create_plan")
        self._ensure_within_budget(state, "create_plan")
        plan = self.planner.create_plan(state["request_id"])
        self._ensure_within_budget(state, "create_plan")
        if not plan.steps:
            raise RuntimeError("Agent 规划器返回了空执行计划。")
        update = {
            "plan_goal": plan.goal,
            "execution_plan": [asdict(step) for step in plan.steps],
            "current_step_id": plan.steps[0].step_id,
            "planner_events": [
                {
                    "phase": "create_plan",
                    "source": plan.planner_source,
                    "fallback_reason": plan.fallback_reason,
                    "model_attempted": plan.model_attempted,
                }
            ],
        }
        self._write_trace(
            state["run_id"],
            state["request_id"],
            "PLAN_CREATED",
            "COMPLETED",
            {
                "goal": plan.goal,
                "steps": [step.step_id for step in plan.steps],
                "planner_source": plan.planner_source,
                "fallback_reason": plan.fallback_reason,
                "model_attempted": plan.model_attempted,
            },
        )
        return update

    def _execute_step(self, state: ProcurementAgentState) -> dict:
        iteration = state.get("iterations", 0) + 1
        if iteration > self.max_iterations:
            raise RuntimeError(
                f"Agent 超过最大执行轮次 {self.max_iterations}，已安全终止。"
            )

        plan = [dict(step) for step in state["execution_plan"]]
        step = next(
            (item for item in plan if item["step_id"] == state["current_step_id"]),
            None,
        )
        if step is None:
            raise RuntimeError(f"执行计划中不存在步骤 {state['current_step_id']}。")
        step["attempts"] += 1
        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        arguments: dict = {}
        arguments_hash: str | None = None

        try:
            self._raise_if_cancelled(state, step["step_id"])
            self._ensure_within_budget(state, step["step_id"])
            arguments = self._tool_arguments(step["tool_name"], state)
            arguments_hash = canonical_hash(arguments)
            output = self.registry.execute(
                self.principal, step["tool_name"], arguments
            )
            self._raise_if_cancelled(state, step["step_id"])
            self._ensure_within_budget(state, step["step_id"])
            parsed = json.loads(output)
            output_hash = canonical_hash(parsed)
            step["status"] = "COMPLETED"
            step["error"] = None
            step["error_category"] = None
            step["retryable"] = None
            completed_at = datetime.now(timezone.utc)
            duration_ms = round((perf_counter() - started_clock) * 1000, 3)
            update: dict = {
                "execution_plan": plan,
                "iterations": iteration,
                "last_error": None,
                "tool_calls": [
                    {
                        "iteration": iteration,
                        "step_id": step["step_id"],
                        "name": step["tool_name"],
                        "arguments": arguments,
                        "arguments_hash": arguments_hash,
                        "output_hash": output_hash,
                        "tool_contract_version": TOOL_CONTRACT_VERSION,
                        "rationale": step["rationale"],
                        "observation": output[:1000],
                        "status": "COMPLETED",
                        "started_at": started_at.isoformat(),
                        "completed_at": completed_at.isoformat(),
                        "duration_ms": duration_ms,
                        "error_type": None,
                    }
                ],
            }
            field_by_tool = {
                "get_purchase_request": "request",
                "validate_purchase_request": "requirement_assessment",
                "find_eligible_suppliers": "eligible_suppliers",
                "get_valid_quotations": "quotations",
                "rank_supplier_candidates": "recommendations",
                "evaluate_procurement_policy": "policy_assessment",
                "search_procurement_policy": "policy_evidence",
            }
            field = field_by_tool.get(step["tool_name"])
            if field is None:
                raise ValueError(f"Agent 收到未映射的工具结果: {step['tool_name']}")
            update[field] = parsed
            if step["tool_name"] == "get_purchase_request":
                update["long_term_memories"] = self._load_memories(
                    state["request_id"], parsed
                )
            self._write_trace(
                state["run_id"],
                state["request_id"],
                "TOOL_EXECUTED",
                "COMPLETED",
                {
                    "tool_name": step["tool_name"],
                    "arguments": arguments,
                    "arguments_hash": arguments_hash,
                    "output_hash": output_hash,
                    "tool_contract_version": TOOL_CONTRACT_VERSION,
                    "observation": output[:1000],
                },
                step_id=step["step_id"],
                duration_ms=duration_ms,
            )
            return update
        except Exception as exc:
            classification = classify_tool_error(exc)
            step["status"] = "FAILED"
            step["error"] = str(exc)
            step["error_category"] = classification.category
            step["retryable"] = classification.retryable
            completed_at = datetime.now(timezone.utc)
            duration_ms = round((perf_counter() - started_clock) * 1000, 3)
            update = {
                "execution_plan": plan,
                "iterations": iteration,
                "last_error": str(exc),
                "tool_calls": [
                    {
                        "iteration": iteration,
                        "step_id": step["step_id"],
                        "name": step["tool_name"],
                        "arguments": arguments,
                        "arguments_hash": arguments_hash,
                        "output_hash": None,
                        "tool_contract_version": TOOL_CONTRACT_VERSION,
                        "rationale": step["rationale"],
                        "observation": str(exc)[:1000],
                        "status": "FAILED",
                        "started_at": started_at.isoformat(),
                        "completed_at": completed_at.isoformat(),
                        "duration_ms": duration_ms,
                        "error_type": type(exc).__name__,
                        "error_category": classification.category,
                        "retryable": classification.retryable,
                    }
                ],
            }
            self._write_trace(
                state["run_id"],
                state["request_id"],
                "TOOL_EXECUTED",
                "FAILED",
                {
                    "tool_name": step["tool_name"],
                    "arguments": arguments,
                    "arguments_hash": arguments_hash,
                    "output_hash": None,
                    "tool_contract_version": TOOL_CONTRACT_VERSION,
                    "error_type": type(exc).__name__,
                    "error_category": classification.category,
                    "retryable": classification.retryable,
                    "error": str(exc)[:1000],
                },
                step_id=step["step_id"],
                duration_ms=duration_ms,
            )
            return update

    def _replan(self, state: ProcurementAgentState) -> dict:
        cancellation = self._cancellation(state["run_id"])
        if cancellation:
            self._write_trace(
                state["run_id"],
                state["request_id"],
                "CANCELLATION_OBSERVED",
                "CANCELLED",
                cancellation,
                step_id=state.get("current_step_id"),
            )
            return {
                "route": "cancel",
                "cancelled": True,
                "cancellation": cancellation,
            }
        self._ensure_within_budget(state, "replan")
        decision = self.planner.replan(state)
        self._ensure_within_budget(state, "replan")
        plan = [dict(step) for step in state["execution_plan"]]
        for step in plan:
            if step["step_id"] in decision.skip_step_ids:
                step["status"] = "SKIPPED"
            if step["step_id"] == decision.retry_step_id:
                step["status"] = "PENDING"
        update: dict = {
            "execution_plan": plan,
            "route": decision.action,
            "planner_events": [
                {
                    "phase": "replan",
                    "source": decision.planner_source,
                    "fallback_reason": decision.fallback_reason,
                    "model_attempted": decision.model_attempted,
                }
            ],
        }
        if decision.next_step_id is not None:
            update["current_step_id"] = decision.next_step_id
        if decision.revision is not None:
            update["plan_revisions"] = [decision.revision]
        self._write_trace(
            state["run_id"],
            state["request_id"],
            "PLAN_REVISED",
            "COMPLETED",
            {
                "action": decision.action,
                "next_step_id": decision.next_step_id,
                "skip_step_ids": list(decision.skip_step_ids),
                "rationale": decision.rationale,
                "revision": decision.revision,
                "planner_source": decision.planner_source,
                "fallback_reason": decision.fallback_reason,
                "model_attempted": decision.model_attempted,
            },
        )
        return update

    @staticmethod
    def _route_replan(state: ProcurementAgentState) -> str:
        return state["route"]

    @staticmethod
    def _tool_arguments(tool_name: str, state: ProcurementAgentState) -> dict:
        if tool_name == "get_purchase_request":
            return {"request_id": state["request_id"]}
        if tool_name == "find_eligible_suppliers":
            return {"category": state["request"]["category"]}
        if tool_name == "validate_purchase_request":
            return {"request": state["request"]}
        if tool_name == "get_valid_quotations":
            return {
                "request_id": state["request_id"],
                "supplier_ids": [
                    item["supplier_id"] for item in state["eligible_suppliers"]
                ],
            }
        if tool_name == "rank_supplier_candidates":
            return {
                "request": state["request"],
                "suppliers": state.get("eligible_suppliers", []),
                "quotations": state.get("quotations", []),
            }
        if tool_name == "evaluate_procurement_policy":
            return {
                "request": state["request"],
                "suppliers": state.get("eligible_suppliers", []),
                "quotations": state.get("quotations", []),
            }
        if tool_name == "search_procurement_policy":
            request = state["request"]
            return {
                "query": (
                    f"{request['category']} 采购金额 审批等级 三家报价 "
                    "合格供应商 风险"
                ),
                "limit": 4,
            }
        raise ValueError(f"计划引用了未注册的采购工具: {tool_name}")

    def _validate_decision(self, state: ProcurementAgentState) -> dict:
        self._raise_if_cancelled(state, "validate_decision")
        self._ensure_within_budget(state, "validate_decision")
        report = validate_decision_state(state)
        payload = report.model_dump(mode="json")
        self._write_trace(
            state["run_id"],
            state["request_id"],
            "DECISION_VALIDATED" if report.valid else "DECISION_VALIDATION_FAILED",
            "COMPLETED" if report.valid else "FAILED",
            payload,
            step_id="validate_decision",
        )
        if not report.valid:
            raise DecisionGuardrailError(report)
        return {"guardrail_report": payload}

    def _finalize(self, state: ProcurementAgentState) -> dict:
        self._raise_if_cancelled(state, "finalize")
        self._ensure_within_budget(state, "finalize")
        request = PurchaseRequest.model_validate(state["request"])
        suppliers = [
            Supplier.model_validate(item) for item in state.get("eligible_suppliers", [])
        ]
        quotations = [
            Quotation.model_validate(item) for item in state.get("quotations", [])
        ]
        evidence = [
            PolicyEvidence.model_validate(item)
            for item in state.get("policy_evidence", [])
        ]
        recommendations = [
            SupplierRecommendation.model_validate(item)
            for item in state.get("recommendations", [])
        ]
        requirement = RequirementAssessment.model_validate(
            state["requirement_assessment"]
        )
        assessment = PolicyAssessment.model_validate(state["policy_assessment"])
        guardrail_report = DecisionGuardrailReport.model_validate(
            state["guardrail_report"]
        )
        warnings = [*requirement.issues, *assessment.warnings]
        level = assessment.approval_level
        next_action = assessment.next_action
        if not requirement.valid:
            next_action = requirement.next_action or "申请人补充或修正采购需求"
            review_step = AgentTraceStep(
                step="requirement_review",
                status="waiting",
                summary="采购需求校验未通过，已停止自动寻源并退回申请人修正",
            )
        elif assessment.route == "MANUAL_SOURCING":
            review_step = AgentTraceStep(
                step="manual_review",
                status="waiting",
                summary="没有可推荐供应商，已路由至人工寻源分支",
            )
        elif assessment.route == "HUMAN_REVIEW":
            review_step = AgentTraceStep(
                step="human_review",
                status="waiting",
                summary="制度检查存在警告，已路由至人工复核分支",
            )
        else:
            review_step = None
        plan_status = {
            step["step_id"]: step["status"].lower()
            for step in state["execution_plan"]
        }

        def summary(step_id: str, completed: str, skipped: str) -> str:
            return skipped if plan_status.get(step_id) == "skipped" else completed

        trace = [
            AgentTraceStep(
                step="load_request",
                status=plan_status.get("load_request", "completed"),
                summary=f"已通过工具加载采购申请 {request.request_id}",
            ),
            AgentTraceStep(
                step="validate_request",
                status=plan_status.get("validate_request", "completed"),
                summary=(
                    "采购需求校验通过"
                    if requirement.valid
                    else f"采购需求校验发现 {len(requirement.issues)} 项问题"
                ),
            ),
            AgentTraceStep(
                step="screen_suppliers",
                status=plan_status.get("screen_suppliers", "completed"),
                summary=summary(
                    "screen_suppliers",
                    f"工具筛得 {len(suppliers)} 家合格供应商",
                    "因需求校验未通过，已跳过供应商筛选",
                ),
            ),
            AgentTraceStep(
                step="collect_quotations",
                status=plan_status.get("collect_quotations", "completed"),
                summary=summary(
                    "collect_quotations",
                    f"工具取得 {len(quotations)} 份有效报价",
                    "前置条件不满足，已跳过报价读取",
                ),
            ),
            AgentTraceStep(
                step="rank_suppliers",
                status=plan_status.get("rank_suppliers", "completed"),
                summary=summary(
                    "rank_suppliers",
                    (
                        f"完成多维评分，当前首选：{recommendations[0].supplier_name}"
                        if recommendations
                        else "完成多维评分，无可推荐供应商"
                    ),
                    "前置条件不满足，已跳过供应商评分",
                ),
            ),
            AgentTraceStep(
                step="check_policy",
                status=plan_status.get("check_policy", "completed"),
                summary=f"审批等级 {level}，发现 {len(warnings)} 项需关注问题",
            ),
        ]
        if review_step:
            trace.append(review_step)
        trace.extend(
            [
                AgentTraceStep(
                    step="retrieve_policy",
                    status=plan_status.get("retrieve_policy", "completed"),
                    summary=f"工具检索到 {len(evidence)} 条制度依据",
                ),
                AgentTraceStep(
                    step="validate_decision",
                    summary="最终决策安全校验通过",
                ),
                AgentTraceStep(step="finalize", summary=f"决策完成，下一步：{next_action}"),
            ]
        )
        provenance = build_decision_provenance(
            source_facts=build_source_evidence_manifest(state["tool_calls"]),
            decision={
                "approval_level": level,
                "recommendations": recommendations,
                "warnings": warnings,
                "next_action": next_action,
                "plan_status": plan_status,
                "guardrail_report": guardrail_report,
            },
            system_prompt_version=self.system_prompt.version,
            planner_provider=self.planner.provider,
            tool_contract_version=TOOL_CONTRACT_VERSION,
            ruleset_version=PROCUREMENT_RULESET_VERSION,
            ruleset_fingerprint=PROCUREMENT_RULESET_FINGERPRINT,
        )
        result = AnalysisResult(
            request=request,
            approval_level=level,
            recommendations=recommendations,
            warnings=warnings,
            policy_evidence=evidence,
            trace=trace,
            next_action=next_action,
            agent_iterations=state["iterations"],
            tool_calls=state["tool_calls"],
            execution_plan=state["execution_plan"],
            plan_revisions=state.get("plan_revisions", []),
            run_id=state.get("run_id"),
            planner_provider=self.planner.provider,
            planner_events=state.get("planner_events", []),
            planner_fallback_count=sum(
                1
                for event in state.get("planner_events", [])
                if event.get("fallback_reason")
            ),
            planner_model_attempt_count=sum(
                1
                for event in state.get("planner_events", [])
                if event.get("model_attempted")
            ),
            planner_model_failure_count=sum(
                1
                for event in state.get("planner_events", [])
                if event.get("model_attempted")
                and event.get("fallback_reason")
            ),
            provenance=provenance,
            guardrail_report=guardrail_report,
        )
        return {"result": result}

    def _utc_now(self) -> datetime:
        current = self.clock()
        if current.tzinfo is None:
            raise ValueError("Agent clock 必须返回带时区的时间。")
        return current.astimezone(timezone.utc)

    def _ensure_within_budget(self, state: ProcurementAgentState, phase: str) -> None:
        deadline_text = state.get("run_deadline_at")
        if not deadline_text:
            return
        deadline = datetime.fromisoformat(deadline_text).astimezone(timezone.utc)
        if self._utc_now() >= deadline:
            raise AgentExecutionDeadlineExceeded(
                f"Agent 执行超过 {self.max_runtime_seconds:g} 秒预算，"
                f"已在 {phase} 阶段安全终止。"
            )

    def _cancellation(self, run_id: str) -> dict | None:
        if self.cancellation_reader is None:
            return None
        cancellation = self.cancellation_reader.find(run_id)
        if cancellation is None:
            return None
        if hasattr(cancellation, "model_dump"):
            return cancellation.model_dump(mode="json")
        return dict(cancellation)

    def _raise_if_cancelled(self, state: ProcurementAgentState, phase: str) -> None:
        cancellation = self._cancellation(state["run_id"])
        if cancellation:
            raise AgentExecutionCancelled(
                f"Agent 执行已在 {phase} 阶段取消：{cancellation['reason']}"
            )

    @staticmethod
    def _cancel(state: ProcurementAgentState) -> dict:
        return {
            "cancelled": True,
            "cancellation": state.get("cancellation", {}),
        }

    def _load_memories(
        self, request_id: str, request: dict | None = None
    ) -> list[dict]:
        """Load exact-request and business-relevant memories for the planner."""
        if self.memory_reader is None:
            return []
        if hasattr(self.memory_reader, "search"):
            memories = self.memory_reader.search(
                request_id=request_id,
                category=request.get("category") if request else None,
                department=request.get("department") if request else None,
                limit=5,
            )
        else:
            memories = self.memory_reader.list(request_id, limit=5)
        return [
            memory.model_dump() if hasattr(memory, "model_dump") else dict(memory)
            for memory in memories
        ]

    def _remember_result(self, run_id: str, result: AnalysisResult) -> None:
        if self.memory_writer is None:
            return
        request = result.request
        metadata = {
            "run_id": run_id,
            "approval_level": result.approval_level,
            "category": request.category,
            "department": request.department,
            "warnings": result.warnings,
            "recommended_supplier_id": (
                result.recommendations[0].supplier_id
                if result.recommendations
                else None
            ),
            "planner_provider": result.planner_provider,
            "planner_fallback_count": result.planner_fallback_count,
            "planner_model_attempt_count": result.planner_model_attempt_count,
            "planner_model_failure_count": result.planner_model_failure_count,
            "source_fingerprint": (
                result.provenance.source_fingerprint if result.provenance else None
            ),
            "decision_fingerprint": (
                result.provenance.decision_fingerprint if result.provenance else None
            ),
        }
        try:
            memory = self.memory_writer.remember(
                run_id,
                request.request_id,
                "analysis",
                result.next_action,
                metadata,
            )
            pruned = self.memory_writer.prune(request.request_id, keep_latest=20)
            self._write_trace(
                run_id,
                request.request_id,
                "MEMORY_STORED",
                "COMPLETED",
                {
                    "memory_id": getattr(memory, "memory_id", None),
                    "kind": "analysis",
                    "pruned": pruned,
                },
            )
        except Exception as exc:
            logger.exception("Unable to persist agent long-term memory")
            self._write_trace(
                run_id,
                request.request_id,
                "MEMORY_STORE_FAILED",
                "FAILED",
                {"error_type": type(exc).__name__, "error": str(exc)[:500]},
            )

    def _write_trace(
        self,
        run_id: str,
        request_id: str,
        event_type: str,
        status: str,
        payload: dict | None = None,
        *,
        step_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Persist observability without allowing telemetry failure to stop work."""
        if self.trace_writer is None:
            return
        try:
            self.trace_writer.record(
                run_id,
                request_id,
                event_type,
                status,
                payload,
                step_id=step_id,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception("Unable to persist agent trace event %s", event_type)

    @staticmethod
    def _abort(state: ProcurementAgentState) -> dict:
        failed = next(
            step for step in state["execution_plan"] if step["status"] == "FAILED"
        )
        raise RuntimeError(
            f"Agent 执行步骤 {failed['step_id']} 失败，已终止自动决策："
            f"{failed.get('error') or state.get('last_error') or '未知错误'}"
        )
