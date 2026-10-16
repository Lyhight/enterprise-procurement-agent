from __future__ import annotations

from copy import deepcopy
from typing import Any

from .security import ContextSecurityReport, ContextSecurityScanner


class ProcurementContextManager:
    """Builds a bounded, redacted context payload for planner calls."""

    _sensitive_keys = {
        "api_key",
        "authorization",
        "password",
        "secret",
        "signature",
        "token",
    }

    def __init__(
        self,
        max_tool_observations: int = 4,
        max_memories: int = 5,
        max_observation_chars: int = 600,
        max_memory_chars: int = 400,
        max_plan_revisions: int = 5,
        max_list_items: int = 3,
        max_scalar_chars: int = 300,
        security_scanner: ContextSecurityScanner | None = None,
    ) -> None:
        self.max_tool_observations = max_tool_observations
        self.max_memories = max_memories
        self.max_observation_chars = max_observation_chars
        self.max_memory_chars = max_memory_chars
        self.max_plan_revisions = max_plan_revisions
        self.max_list_items = max_list_items
        self.max_scalar_chars = max_scalar_chars
        self.security_scanner = security_scanner or ContextSecurityScanner()

    def build_replan_context(self, state: dict) -> dict:
        tool_calls = deepcopy(state.get("tool_calls", [])[-self.max_tool_observations :])
        for call in tool_calls:
            if "observation" in call:
                call["observation"] = str(call["observation"])[
                    : self.max_observation_chars
                ]
            if "arguments" in call:
                call["arguments"] = self._compact(call["arguments"])
        memories = []
        for memory in state.get("long_term_memories", [])[-self.max_memories :]:
            memories.append(
                {
                    "kind": memory.get("kind"),
                    "content": str(memory.get("content", ""))[: self.max_memory_chars],
                    "metadata": self._compact(memory.get("metadata", {})),
                    "created_at": memory.get("created_at"),
                }
            )
        recent_revisions = state.get("plan_revisions", [])[
            -self.max_plan_revisions :
        ]
        context = {
            "run_id": state.get("run_id"),
            "goal": state.get("plan_goal"),
            "request": self._compact(state.get("request")),
            "steps": [
                {
                    "step_id": step.get("step_id"),
                    "status": step.get("status"),
                    "attempts": step.get("attempts"),
                    "error": str(step.get("error"))[: self.max_scalar_chars]
                    if step.get("error")
                    else None,
                    "error_category": step.get("error_category"),
                    "retryable": step.get("retryable"),
                }
                for step in state.get("execution_plan", [])
            ],
            "recent_tool_observations": tool_calls,
            "plan_revisions": [
                str(revision)[: self.max_scalar_chars]
                for revision in recent_revisions
            ],
            "facts_available": {
                "request": "request" in state,
                "requirement_valid": (
                    state.get("requirement_assessment") or {}
                ).get("valid"),
                "eligible_suppliers": len(state.get("eligible_suppliers", [])),
                "quotations": len(state.get("quotations", [])),
                "recommendations": len(state.get("recommendations", [])),
                "policy_evidence": len(state.get("policy_evidence", [])),
            },
            "long_term_memories": memories,
            "context_stats": {
                "total_tool_calls": len(state.get("tool_calls", [])),
                "included_tool_calls": len(tool_calls),
                "total_memories": len(state.get("long_term_memories", [])),
                "included_memories": len(memories),
            },
            "trust_boundary": {
                "classification": "UNTRUSTED_BUSINESS_DATA",
                "may_supply_instructions": False,
            },
        }
        return self._redact(context)

    def assess_security(self, context: dict) -> ContextSecurityReport:
        return self.security_scanner.scan(context)

    def _compact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._compact(item)
                for key, item in list(value.items())[:20]
            }
        if isinstance(value, list):
            compacted = [
                self._compact(item) for item in value[: self.max_list_items]
            ]
            if len(value) > self.max_list_items:
                compacted.append({"omitted_items": len(value) - self.max_list_items})
            return compacted
        if isinstance(value, str):
            return value[: self.max_scalar_chars]
        return value

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED]"
                    if key.lower() in self._sensitive_keys
                    else self._redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value
