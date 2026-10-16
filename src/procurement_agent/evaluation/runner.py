from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..application.workflow import ProcurementWorkflow
from ..core.config import get_settings
from ..domain.models import PurchaseRequest
from ..infrastructure.knowledge import KnowledgeBase
from ..infrastructure.repositories import CsvRepository


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    category: str
    passed: bool
    checks: dict[str, bool]


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    passed: int
    pass_rate: float
    results: list[EvaluationResult]

    def as_dict(self) -> dict:
        return asdict(self)


class EvaluationRunner:
    def __init__(self, workflow: ProcurementWorkflow, cases_path: Path) -> None:
        self.workflow = workflow
        self.cases_path = cases_path

    def run(self) -> EvaluationReport:
        cases = json.loads(self.cases_path.read_text(encoding="utf-8"))
        results = [
            *(self._agent_case(case) for case in cases.get("agent_cases", [])),
            *(self._rag_case(case) for case in cases.get("rag_cases", [])),
        ]
        passed = sum(result.passed for result in results)
        return EvaluationReport(
            total=len(results),
            passed=passed,
            pass_rate=round(passed / len(results), 4) if results else 0.0,
            results=results,
        )

    def _agent_case(self, case: dict) -> EvaluationResult:
        workflow = self.workflow
        request_id = case["request_id"]
        if case.get("request"):
            request = PurchaseRequest.model_validate(case["request"])
            request_id = request.request_id
            workflow = ProcurementWorkflow(
                CsvRepository(
                    self.workflow.repository.data_dir,
                    extra_request_loader=lambda: [request],
                ),
                self.workflow.knowledge_base,
                planner=self.workflow.agent.planner,
            )
        result = workflow.analyze(request_id)
        trace_steps = {step.step for step in result.trace}
        plan_statuses = {
            step["step_id"]: step["status"] for step in result.execution_plan
        }
        checks: dict[str, bool] = {
            "grounding": bool(result.policy_evidence)
            if case.get("grounding_required", True)
            else True,
        }
        if "expected_approval_level" in case:
            checks["approval_level"] = (
                result.approval_level == case["expected_approval_level"]
            )
        if "minimum_recommendations" in case:
            checks["minimum_recommendations"] = (
                len(result.recommendations) >= case["minimum_recommendations"]
            )
        if "maximum_recommendations" in case:
            checks["maximum_recommendations"] = (
                len(result.recommendations) <= case["maximum_recommendations"]
            )
        if "expected_next_action" in case:
            checks["next_action"] = (
                result.next_action == case["expected_next_action"]
            )
        required_trace_steps = case.get("required_trace_steps") or [
            case["required_trace_step"]
        ]
        checks["trace"] = all(step in trace_steps for step in required_trace_steps)
        if case.get("expected_plan_statuses"):
            checks["plan_statuses"] = all(
                plan_statuses.get(step_id) == expected
                for step_id, expected in case["expected_plan_statuses"].items()
            )
        if case.get("warning_contains"):
            checks["warnings"] = all(
                any(fragment in warning for warning in result.warnings)
                for fragment in case["warning_contains"]
            )
        return EvaluationResult(case["name"], "agent", all(checks.values()), checks)

    def _rag_case(self, case: dict) -> EvaluationResult:
        evidence = self.workflow.knowledge_base.search(case["query"], case["top_k"])
        checks = {
            "source_hit": any(item.source == case["expected_source"] for item in evidence),
            "section_hit": any(item.section == case["expected_section"] for item in evidence),
            "non_empty": bool(evidence),
        }
        return EvaluationResult(case["name"], "rag", all(checks.values()), checks)


def main() -> None:
    settings = get_settings()
    workflow = ProcurementWorkflow(
        CsvRepository(settings.company_data_dir), KnowledgeBase(settings.documents_dir)
    )
    report = EvaluationRunner(workflow, settings.project_root / "evals" / "cases.json").run()
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.passed == report.total else 1)


if __name__ == "__main__":
    main()
