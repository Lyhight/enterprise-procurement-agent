from __future__ import annotations

import csv
from pathlib import Path
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from ..domain.models import Employee, PurchaseRequest, Quotation, Supplier

ModelT = TypeVar("ModelT", bound=BaseModel)


class CsvRepository:
    def __init__(
        self,
        data_dir: Path,
        extra_request_loader: Callable[[], list[PurchaseRequest]] | None = None,
        extra_quotation_loader: Callable[[], list[Quotation]] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.extra_request_loader = extra_request_loader
        self.extra_quotation_loader = extra_quotation_loader

    def _load(self, filename: str, model: type[ModelT]) -> list[ModelT]:
        path = self.data_dir / filename
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [model.model_validate(row) for row in csv.DictReader(handle)]

    def suppliers(self) -> list[Supplier]:
        return self._load("suppliers.csv", Supplier)

    def employees(self) -> list[Employee]:
        return self._load("employees.csv", Employee)

    def requests(self) -> list[PurchaseRequest]:
        requests = self._load("purchase_request.csv", PurchaseRequest)
        if self.extra_request_loader is not None:
            requests.extend(self.extra_request_loader())
        return requests

    def quotations(self) -> list[Quotation]:
        quotations = self._load("quotation.csv", Quotation)
        if self.extra_quotation_loader is not None:
            quotations.extend(self.extra_quotation_loader())
        return quotations

    def request_by_id(self, request_id: str) -> PurchaseRequest:
        for request in self.requests():
            if request.request_id == request_id:
                return request
        raise LookupError(f"采购申请不存在: {request_id}")

    def employee_by_id(self, employee_id: str) -> Employee:
        for employee in self.employees():
            if employee.employee_id == employee_id:
                return employee
        raise LookupError(f"员工不存在: {employee_id}")

