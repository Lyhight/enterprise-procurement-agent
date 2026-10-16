from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..tool_contracts import ToolContractError


ToolErrorCategory = Literal[
    "TRANSIENT",
    "BUDGET",
    "CANCELLATION",
    "CONTRACT",
    "AUTHORIZATION",
    "NOT_FOUND",
    "INVALID_INPUT",
    "INTERNAL",
]


class AgentExecutionDeadlineExceeded(TimeoutError):
    """Raised when an Agent run exceeds its configured wall-clock budget."""


class AgentExecutionCancelled(RuntimeError):
    """Raised after a durable Agent cancellation request is observed."""


@dataclass(frozen=True)
class ToolErrorClassification:
    category: ToolErrorCategory
    retryable: bool


def classify_tool_error(exc: Exception) -> ToolErrorClassification:
    """Classify failures conservatively so deterministic errors fail fast."""
    if isinstance(exc, AgentExecutionDeadlineExceeded):
        return ToolErrorClassification("BUDGET", False)
    if isinstance(exc, AgentExecutionCancelled):
        return ToolErrorClassification("CANCELLATION", False)
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ToolErrorClassification("TRANSIENT", True)
    if isinstance(exc, ToolContractError):
        return ToolErrorClassification("CONTRACT", False)
    if isinstance(exc, PermissionError):
        return ToolErrorClassification("AUTHORIZATION", False)
    if isinstance(exc, LookupError):
        return ToolErrorClassification("NOT_FOUND", False)
    if isinstance(exc, (TypeError, ValueError)):
        return ToolErrorClassification("INVALID_INPUT", False)
    return ToolErrorClassification("INTERNAL", False)
