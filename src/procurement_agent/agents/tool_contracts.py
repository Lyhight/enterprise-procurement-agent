from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ..domain.models import (
    PolicyAssessment,
    PolicyEvidence,
    PurchaseRequest,
    Quotation,
    RequirementAssessment,
    Supplier,
    SupplierRecommendation,
)


TOOL_CONTRACT_VERSION = "1.0.0"


class ToolContractError(ValueError):
    """Raised when a tool crosses the Agent boundary with invalid data."""

    def __init__(self, tool_name: str, phase: str, detail: str) -> None:
        self.tool_name = tool_name
        self.phase = phase
        self.detail = detail
        super().__init__(f"工具 {tool_name} 的{phase}契约校验失败：{detail}")


class _StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequestLookupArguments(_StrictArguments):
    request_id: str = Field(min_length=1, max_length=100)


class RequestValidationArguments(_StrictArguments):
    request: PurchaseRequest


class SupplierSearchArguments(_StrictArguments):
    category: str = Field(min_length=1, max_length=100)


class QuotationLookupArguments(_StrictArguments):
    request_id: str = Field(min_length=1, max_length=100)
    supplier_ids: set[str] = Field(min_length=1, max_length=100)


class SupplierDecisionArguments(_StrictArguments):
    request: PurchaseRequest
    suppliers: list[Supplier] = Field(max_length=100)
    quotations: list[Quotation] = Field(max_length=500)


class PolicySearchArguments(_StrictArguments):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=4, ge=1, le=10)


def _safe_validation_detail(exc: ValidationError) -> str:
    details = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(item) for item in error["loc"]) or "root"
        details.append(f"{location}: {error['msg']}")
    return "; ".join(details)[:1000]


@dataclass(frozen=True)
class ToolContract:
    arguments_model: type[BaseModel]
    output_adapter: TypeAdapter

    def validate_arguments(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        try:
            validated = self.arguments_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolContractError(
                tool_name, "输入", _safe_validation_detail(exc)
            ) from exc
        return validated.model_dump(mode="python")

    def validate_output(self, tool_name: str, payload: Any) -> Any:
        try:
            validated = self.output_adapter.validate_python(payload)
        except ValidationError as exc:
            raise ToolContractError(
                tool_name, "输出", _safe_validation_detail(exc)
            ) from exc
        return self.output_adapter.dump_python(validated, mode="json")


TOOL_CONTRACTS: dict[str, ToolContract] = {
    "get_purchase_request": ToolContract(
        RequestLookupArguments, TypeAdapter(PurchaseRequest)
    ),
    "validate_purchase_request": ToolContract(
        RequestValidationArguments, TypeAdapter(RequirementAssessment)
    ),
    "find_eligible_suppliers": ToolContract(
        SupplierSearchArguments, TypeAdapter(list[Supplier])
    ),
    "get_valid_quotations": ToolContract(
        QuotationLookupArguments, TypeAdapter(list[Quotation])
    ),
    "rank_supplier_candidates": ToolContract(
        SupplierDecisionArguments, TypeAdapter(list[SupplierRecommendation])
    ),
    "evaluate_procurement_policy": ToolContract(
        SupplierDecisionArguments, TypeAdapter(PolicyAssessment)
    ),
    "search_procurement_policy": ToolContract(
        PolicySearchArguments, TypeAdapter(list[PolicyEvidence])
    ),
}
