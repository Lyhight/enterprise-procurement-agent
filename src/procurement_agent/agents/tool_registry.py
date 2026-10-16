from __future__ import annotations

import json
from typing import Any, Callable

from ..application.authorization import ToolAccessPolicy, ToolPrincipal
from .tools import ProcurementToolbox
from .tool_contracts import TOOL_CONTRACTS


class ProcurementToolRegistry:
    """Allow-listed dispatch boundary for agent-originated read operations."""

    def __init__(
        self, toolbox: ProcurementToolbox, access_policy: ToolAccessPolicy | None = None
    ) -> None:
        self.access_policy = access_policy or ToolAccessPolicy()
        self._handlers: dict[str, Callable[..., Any]] = {
            "get_purchase_request": toolbox.get_purchase_request,
            "validate_purchase_request": toolbox.validate_purchase_request,
            "find_eligible_suppliers": toolbox.find_eligible_suppliers,
            "get_valid_quotations": toolbox.get_valid_quotations,
            "rank_supplier_candidates": toolbox.rank_supplier_candidates,
            "evaluate_procurement_policy": toolbox.evaluate_procurement_policy,
            "search_procurement_policy": toolbox.search_policy,
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def execute(self, principal: ToolPrincipal, name: str, arguments: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"不允许调用工具: {name}")
        self.access_policy.require(principal, name)
        contract = TOOL_CONTRACTS[name]
        validated_arguments = contract.validate_arguments(name, arguments)
        result = handler(**validated_arguments)
        if hasattr(result, "model_dump"):
            payload = result.model_dump(mode="json")
        elif isinstance(result, list):
            payload = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        else:
            payload = result
        validated_payload = contract.validate_output(name, payload)
        return json.dumps(validated_payload, ensure_ascii=False)
