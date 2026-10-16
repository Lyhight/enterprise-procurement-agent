from __future__ import annotations

from ..domain.models import AgentRunRecord, IntegrationJob, RunStatus
from ..infrastructure.integration_jobs import IntegrationJobStore
from ..infrastructure.persistence import RunStore
from .integrations import EnterpriseIntegrationService


class IntegrationWorker:
    def __init__(
        self,
        jobs: IntegrationJobStore,
        runs: RunStore,
        integrations: EnterpriseIntegrationService,
    ) -> None:
        self.jobs = jobs
        self.runs = runs
        self.integrations = integrations

    def run_once(self) -> IntegrationJob | None:
        job = self.jobs.claim_next()
        if job is None:
            return None
        try:
            run = self.runs.get(job.run_id)
            record = (
                self.integrations.submit_to_oa(run)
                if job.target == "OA"
                else self.integrations.sync_to_erp(run)
            )
            return self.jobs.succeed(job.job_id, record.integration_id)
        except Exception as exc:
            return self.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")


class IntegrationQueueService:
    def __init__(self, jobs: IntegrationJobStore, runs: RunStore) -> None:
        self.jobs = jobs
        self.runs = runs

    def enqueue(self, run_id: str, target: str) -> IntegrationJob:
        run = self.runs.get(run_id)
        normalized = target.upper()
        self._validate(run, normalized)
        return self.jobs.enqueue(run_id, normalized)

    @staticmethod
    def _validate(run: AgentRunRecord, target: str) -> None:
        if target == "OA" and run.status is not RunStatus.AWAITING_APPROVAL:
            raise ValueError("只有待审批的 Agent 运行可以加入 OA 任务队列。")
        if target == "ERP" and (
            run.status is not RunStatus.COMPLETED
            or run.approval_decision not in {"APPROVED", "AUTO_APPROVED"}
        ):
            raise ValueError("只有已批准的 Agent 运行可以加入 ERP 任务队列。")
        if target not in {"OA", "ERP"}:
            raise ValueError("集成任务 target 必须为 OA 或 ERP。")
