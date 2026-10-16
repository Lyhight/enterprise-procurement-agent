from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from ..core.prompts import load_prompt
from ..domain.models import (
    AgentDecisionProvenance,
    AnalysisResult,
    DecisionProvenanceReport,
)
from ..domain.ruleset import (
    PROCUREMENT_RULESET_FINGERPRINT,
    PROCUREMENT_RULESET_VERSION,
)
from .tool_contracts import TOOL_CONTRACT_VERSION


SOURCE_EVIDENCE_TOOLS = (
    "get_purchase_request",
    "find_eligible_suppliers",
    "get_valid_quotations",
    "search_procurement_policy",
)


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_source_evidence_manifest(tool_calls: list[dict]) -> list[dict]:
    """Build the stable evidence manifest used by result and Trace verification."""
    completed: dict[str, dict] = {}
    for call in tool_calls:
        name = call.get("name") or call.get("tool_name")
        if name not in SOURCE_EVIDENCE_TOOLS or call.get("status") != "COMPLETED":
            continue
        completed[name] = {
            "tool_name": name,
            "arguments_hash": call.get("arguments_hash"),
            "output_hash": call.get("output_hash"),
            "tool_contract_version": call.get("tool_contract_version"),
        }
    return [completed[name] for name in SOURCE_EVIDENCE_TOOLS if name in completed]


def source_evidence_from_trace(events: list[dict]) -> list[dict]:
    calls = []
    for event in events:
        if event.get("event_type") != "TOOL_EXECUTED":
            continue
        payload = event.get("payload", {})
        calls.append(
            {
                "tool_name": payload.get("tool_name"),
                "arguments_hash": payload.get("arguments_hash"),
                "output_hash": payload.get("output_hash"),
                "tool_contract_version": payload.get("tool_contract_version"),
                "status": event.get("status"),
            }
        )
    return build_source_evidence_manifest(calls)


def build_decision_provenance(
    *,
    source_facts: dict,
    decision: dict,
    system_prompt_version: str,
    planner_provider: str,
    tool_contract_version: str,
    ruleset_version: str,
    ruleset_fingerprint: str,
) -> AgentDecisionProvenance:
    source_fingerprint = canonical_hash(source_facts)
    decision_fingerprint = canonical_hash(
        {
            "source_fingerprint": source_fingerprint,
            "decision": decision,
            "system_prompt_version": system_prompt_version,
            "planner_provider": planner_provider,
            "tool_contract_version": tool_contract_version,
            "ruleset_version": ruleset_version,
            "ruleset_fingerprint": ruleset_fingerprint,
        }
    )
    return AgentDecisionProvenance(
        system_prompt_version=system_prompt_version,
        planner_provider=planner_provider,
        tool_contract_version=tool_contract_version,
        ruleset_version=ruleset_version,
        ruleset_fingerprint=ruleset_fingerprint,
        source_fingerprint=source_fingerprint,
        decision_fingerprint=decision_fingerprint,
    )


def verify_decision_provenance(
    result: AnalysisResult,
    *,
    trace_events: list[dict] | None = None,
    trace_integrity_valid: bool | None = None,
) -> DecisionProvenanceReport:
    provenance = result.provenance
    if provenance is None:
        return DecisionProvenanceReport(
            valid=False,
            decision_fingerprint_valid=False,
            source_fingerprint_valid=False,
            trace_evidence_valid=(False if trace_events is not None else None),
            trace_integrity_valid=trace_integrity_valid,
            missing_evidence=[],
            prompt_version_current=False,
            tool_contract_version_current=False,
            ruleset_current=False,
            recorded_ruleset_version="unversioned",
            current_ruleset_version=PROCUREMENT_RULESET_VERSION,
            recorded_ruleset_fingerprint="",
            current_ruleset_fingerprint=PROCUREMENT_RULESET_FINGERPRINT,
        )
    evidence_manifest = build_source_evidence_manifest(result.tool_calls)
    expected_tools = {
        step.get("tool_name")
        for step in result.execution_plan
        if step.get("status") == "COMPLETED"
        and step.get("tool_name") in SOURCE_EVIDENCE_TOOLS
    }
    actual_tools = {item["tool_name"] for item in evidence_manifest}
    missing_evidence = sorted(expected_tools - actual_tools)
    recomputed_source_fingerprint = canonical_hash(evidence_manifest)
    source_fingerprint_valid = (
        not missing_evidence
        and recomputed_source_fingerprint == provenance.source_fingerprint
    )
    trace_evidence_valid = None
    if trace_events is not None:
        trace_evidence_valid = (
            source_evidence_from_trace(trace_events) == evidence_manifest
            and not missing_evidence
        )
    decision = {
        "approval_level": result.approval_level,
        "recommendations": result.recommendations,
        "warnings": result.warnings,
        "next_action": result.next_action,
        "plan_status": {
            step.get("step_id"): (
                str(step.get("status")).lower()
                if step.get("status") is not None
                else None
            )
            for step in result.execution_plan
        },
        "guardrail_report": result.guardrail_report,
    }
    expected = canonical_hash(
        {
            "source_fingerprint": recomputed_source_fingerprint,
            "decision": decision,
            "system_prompt_version": provenance.system_prompt_version,
            "planner_provider": provenance.planner_provider,
            "tool_contract_version": provenance.tool_contract_version,
            "ruleset_version": provenance.ruleset_version,
            "ruleset_fingerprint": provenance.ruleset_fingerprint,
        }
    )
    fingerprint_valid = expected == provenance.decision_fingerprint
    prompt_current = provenance.system_prompt_version == load_prompt("system.md").version
    contract_current = provenance.tool_contract_version == TOOL_CONTRACT_VERSION
    ruleset_current = (
        provenance.ruleset_version == PROCUREMENT_RULESET_VERSION
        and provenance.ruleset_fingerprint == PROCUREMENT_RULESET_FINGERPRINT
    )
    return DecisionProvenanceReport(
        valid=(
            fingerprint_valid
            and source_fingerprint_valid
            and (trace_evidence_valid is not False)
            and (trace_integrity_valid is not False)
            and prompt_current
            and contract_current
            and ruleset_current
        ),
        decision_fingerprint_valid=fingerprint_valid,
        source_fingerprint_valid=source_fingerprint_valid,
        trace_evidence_valid=trace_evidence_valid,
        trace_integrity_valid=trace_integrity_valid,
        missing_evidence=missing_evidence,
        prompt_version_current=prompt_current,
        tool_contract_version_current=contract_current,
        ruleset_current=ruleset_current,
        recorded_ruleset_version=provenance.ruleset_version,
        current_ruleset_version=PROCUREMENT_RULESET_VERSION,
        recorded_ruleset_fingerprint=provenance.ruleset_fingerprint,
        current_ruleset_fingerprint=PROCUREMENT_RULESET_FINGERPRINT,
    )


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
