import pytest

from procurement_agent.application.authorization import validate_approver
from procurement_agent.core.config import get_settings
from procurement_agent.infrastructure.repositories import CsvRepository


def test_approver_requires_sufficient_level_and_separation() -> None:
    repository = CsvRepository(get_settings().company_data_dir)
    request = repository.request_by_id("PR001")

    validate_approver(repository.employee_by_id("E001"), request, "L3")
    with pytest.raises(PermissionError, match="低于"):
        validate_approver(repository.employee_by_id("E005"), request, "L3")
    with pytest.raises(PermissionError, match="不能是同一人"):
        validate_approver(repository.employee_by_id("E002"), request, "L1")
