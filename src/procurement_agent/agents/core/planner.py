from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


PlanStepStatus = Literal["PENDING", "COMPLETED", "SKIPPED", "FAILED"]


@dataclass
class PlanStep:
    step_id: str
    objective: str
    tool_name: str
    rationale: str
    status: PlanStepStatus = "PENDING"
    attempts: int = 0
    error: str | None = None
    error_category: str | None = None
    retryable: bool | None = None


@dataclass
class ExecutionPlan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    planner_source: str = "local_plan_and_execute"
    fallback_reason: str | None = None
    model_attempted: bool = False


@dataclass(frozen=True)
class ReplanDecision:
    action: Literal["execute", "finalize", "abort"]
    rationale: str
    next_step_id: str | None = None
    skip_step_ids: tuple[str, ...] = ()
    retry_step_id: str | None = None
    revision: str | None = None
    planner_source: str = "local_plan_and_execute"
    fallback_reason: str | None = None
    model_attempted: bool = False


class PlanAndExecutePlanner(Protocol):
    provider: str

    def create_plan(self, request_id: str) -> ExecutionPlan: ...

    def replan(self, state: dict) -> ReplanDecision: ...


class LocalPlanAndExecutePlanner:
    """Creates a complete plan and revises it after every tool observation."""

    provider = "local_plan_and_execute"

    def __init__(self, max_step_attempts: int = 2) -> None:
        self.max_step_attempts = max_step_attempts

    def create_plan(self, request_id: str) -> ExecutionPlan:
        return ExecutionPlan(
            goal=f"对采购申请 {request_id} 完成供应商推荐、制度检查和审批建议",
            steps=[
                PlanStep(
                    step_id="load_request",
                    objective="读取采购申请的真实业务字段",
                    tool_name="get_purchase_request",
                    rationale="先取得采购申请事实，禁止根据编号猜测需求。",
                ),
                PlanStep(
                    step_id="validate_request",
                    objective="校验申请人、部门、状态和需求字段",
                    tool_name="validate_purchase_request",
                    rationale="不完整或来源不可信的需求不能进入自动供应商推荐。",
                ),
                PlanStep(
                    step_id="screen_suppliers",
                    objective="筛选合格且风险可接受的候选供应商",
                    tool_name="find_eligible_suppliers",
                    rationale="供应商资格和风险是进入比价环节的前置条件。",
                ),
                PlanStep(
                    step_id="collect_quotations",
                    objective="读取候选供应商的有效报价",
                    tool_name="get_valid_quotations",
                    rationale="价格评分必须建立在候选供应商的有效报价上。",
                ),
                PlanStep(
                    step_id="rank_suppliers",
                    objective="使用确定性多维规则计算供应商排名",
                    tool_name="rank_supplier_candidates",
                    rationale="推荐结果必须由可审计的评分工具生成，而不是模型主观判断。",
                ),
                PlanStep(
                    step_id="check_policy",
                    objective="执行审批等级和采购合规规则检查",
                    tool_name="evaluate_procurement_policy",
                    rationale="流程路由必须由确定性制度规则决定。",
                ),
                PlanStep(
                    step_id="retrieve_policy",
                    objective="检索与当前采购相关的企业制度",
                    tool_name="search_procurement_policy",
                    rationale="审批和风险结论必须附带可追溯的制度证据。",
                ),
            ],
        )

    def replan(self, state: dict) -> ReplanDecision:
        steps = state["execution_plan"]
        failed = next((step for step in steps if step["status"] == "FAILED"), None)
        if failed is not None:
            if failed.get("retryable") and failed["attempts"] < self.max_step_attempts:
                return ReplanDecision(
                    action="execute",
                    next_step_id=failed["step_id"],
                    retry_step_id=failed["step_id"],
                    rationale="工具执行失败且仍有重试额度，修订计划后重试当前步骤。",
                    revision=f"重试步骤 {failed['step_id']}：{failed.get('error') or '未知错误'}",
                )
            if not failed.get("retryable"):
                return ReplanDecision(
                    action="abort",
                    rationale=(
                        f"步骤 {failed['step_id']} 发生不可重试的"
                        f" {failed.get('error_category') or 'INTERNAL'} 错误，"
                        "停止自动决策并保留现场。"
                    ),
                )
            return ReplanDecision(
                action="abort",
                rationale=f"步骤 {failed['step_id']} 连续失败，停止自动决策并保留现场。",
            )

        invalid_requirement = (
            state.get("requirement_assessment") is not None
            and not state["requirement_assessment"]["valid"]
        )
        invalid_skip_ids = [
            step["step_id"]
            for step in steps
            if step["step_id"]
            in {"screen_suppliers", "collect_quotations", "rank_suppliers"}
            and step["status"] == "PENDING"
        ]
        if invalid_requirement and invalid_skip_ids:
            next_step = next(
                (
                    step
                    for step in steps
                    if step["status"] == "PENDING"
                    and step["step_id"] not in invalid_skip_ids
                ),
                None,
            )
            return ReplanDecision(
                action="execute" if next_step else "finalize",
                next_step_id=next_step["step_id"] if next_step else None,
                skip_step_ids=tuple(invalid_skip_ids),
                rationale="采购需求校验未通过，禁止继续自动寻源和供应商推荐。",
                revision=(
                    "需求校验失败，跳过供应商筛选、报价和排名，"
                    "保留制度检查并转交申请人修正。"
                ),
            )

        quotation_step = next(
            (step for step in steps if step["step_id"] == "collect_quotations"), None
        )
        ranking_step = next(
            (step for step in steps if step["step_id"] == "rank_suppliers"), None
        )
        if (
            "eligible_suppliers" in state
            and not state["eligible_suppliers"]
            and quotation_step is not None
            and quotation_step["status"] == "PENDING"
        ):
            skipped_ids = ["collect_quotations"]
            if ranking_step is not None and ranking_step["status"] == "PENDING":
                skipped_ids.append("rank_suppliers")
            next_step = next(
                (
                    step
                    for step in steps
                    if step["status"] == "PENDING"
                    and step["step_id"] not in skipped_ids
                ),
                None,
            )
            return ReplanDecision(
                action="execute" if next_step else "finalize",
                next_step_id=next_step["step_id"] if next_step else None,
                skip_step_ids=tuple(skipped_ids),
                rationale="没有合格候选供应商，报价步骤已无执行条件。",
                revision=(
                    "没有合格供应商，跳过 collect_quotations 和 rank_suppliers，"
                    "继续执行合规检查并转入人工扩展寻源。"
                ),
            )

        pending = next((step for step in steps if step["status"] == "PENDING"), None)
        if pending is not None:
            return ReplanDecision(
                action="execute",
                next_step_id=pending["step_id"],
                rationale=f"步骤 {pending['step_id']} 的前置事实已经满足，继续执行计划。",
            )
        return ReplanDecision(
            action="finalize",
            rationale="计划中的必要步骤均已完成或有依据地跳过，可以生成决策。",
        )
