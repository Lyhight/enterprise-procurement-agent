from decimal import Decimal

from fastapi import APIRouter

from ...domain.models import DashboardSummary, RunStatus
from ..dependencies import order_store, repository, run_store

router = APIRouter(prefix="/api/v1/dashboard", tags=["管理看板"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    orders = order_store.list()
    runs = run_store.list(10000)
    by_status: dict[str, int] = {}
    for order in orders:
        by_status[order.status.value] = by_status.get(order.status.value, 0) + 1
    return DashboardSummary(
        total_requests=len(repository.requests()),
        total_agent_runs=len(runs),
        pending_approvals=sum(run.status is RunStatus.AWAITING_APPROVAL for run in runs),
        total_orders=len(orders),
        orders_by_status=by_status,
        approved_order_value=sum((order.total_amount for order in orders), Decimal("0")),
    )
