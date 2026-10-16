"""Procurement domain models."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Supplier(BaseModel):
    supplier_id: str
    supplier_name: str
    category: str
    rating: float = Field(ge=0, le=100)
    delivery_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    cooperation_year: int = Field(ge=0)
    qualified: bool


class Employee(BaseModel):
    employee_id: str
    name: str
    department: str
    position: str
    approval_level: str


class PurchaseRequest(BaseModel):
    request_id: str
    requester_id: str
    department: str
    product: str
    category: str
    quantity: int = Field(gt=0)
    budget: Decimal = Field(gt=0)
    required_date: str
    priority: str
    status: str


class RequirementAssessment(BaseModel):
    valid: bool
    requester_verified: bool
    issues: list[str]
    next_action: str | None = None


class Quotation(BaseModel):
    quotation_id: str
    request_id: str
    supplier_id: str
    unit_price: Decimal = Field(gt=0)
    currency: str
    delivery_days: int = Field(gt=0)
    warranty_months: int = Field(ge=0)
    valid_until: str


class SupplierRecommendation(BaseModel):
    supplier_id: str
    supplier_name: str
    score: float
    quoted_total: Decimal | None
    reasons: list[str]


class PolicyAssessment(BaseModel):
    approval_level: str
    warnings: list[str]
    route: Literal["SUBMIT_APPROVAL", "HUMAN_REVIEW", "MANUAL_SOURCING"]
    next_action: str


class PolicyEvidence(BaseModel):
    source: str
    section: str
    content: str
    score: float


class AgentTraceStep(BaseModel):
    step: str
    status: str = "completed"
    summary: str


class AgentDecisionProvenance(BaseModel):
    system_prompt_version: str
    planner_provider: str
    tool_contract_version: str
    ruleset_version: str = "unversioned"
    ruleset_fingerprint: str = ""
    source_fingerprint: str
    decision_fingerprint: str


class DecisionGuardrailReport(BaseModel):
    valid: bool
    checks: dict[str, bool]
    violations: list[str]


class DecisionProvenanceReport(BaseModel):
    valid: bool
    decision_fingerprint_valid: bool
    source_fingerprint_valid: bool = False
    trace_evidence_valid: bool | None = None
    trace_integrity_valid: bool | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    prompt_version_current: bool
    tool_contract_version_current: bool
    ruleset_current: bool
    recorded_ruleset_version: str
    current_ruleset_version: str
    recorded_ruleset_fingerprint: str
    current_ruleset_fingerprint: str


class AnalysisResult(BaseModel):
    request: PurchaseRequest
    approval_level: str
    recommendations: list[SupplierRecommendation]
    warnings: list[str]
    policy_evidence: list[PolicyEvidence]
    trace: list[AgentTraceStep]
    next_action: str
    agent_iterations: int = 0
    tool_calls: list[dict] = Field(default_factory=list)
    execution_plan: list[dict] = Field(default_factory=list)
    plan_revisions: list[str] = Field(default_factory=list)
    run_id: str | None = None
    planner_provider: str = "local_plan_and_execute"
    planner_events: list[dict] = Field(default_factory=list)
    planner_fallback_count: int = 0
    planner_model_attempt_count: int = 0
    planner_model_failure_count: int = 0
    provenance: AgentDecisionProvenance | None = None
    guardrail_report: DecisionGuardrailReport | None = None


class NaturalLanguageIntake(BaseModel):
    text: str = Field(min_length=2)
    requester_id: str = Field(min_length=2)
    department: str = Field(min_length=2)
    required_date: str | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class ParsedPurchaseDraft(BaseModel):
    requester_id: str
    department: str
    product: str | None
    category: str | None
    quantity: int | None
    budget: Decimal | None
    required_date: str | None
    priority: str
    missing_fields: list[str]
    ready_to_submit: bool


class RunStatus(StrEnum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class AgentRunRecord(BaseModel):
    run_id: str
    request_id: str
    status: RunStatus
    approval_level: str
    approval_decision: str
    approver_id: str | None = None
    approval_comment: str | None = None
    result: AnalysisResult
    created_at: str
    updated_at: str


class AgentExecutionView(BaseModel):
    execution_id: str
    request_id: str
    status: Literal["RUNNING", "FAILED", "COMPLETED", "CANCELLED"]
    current_step_id: str | None = None
    iterations: int
    execution_plan: list[dict]
    last_error: str | None = None


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    approver_id: str = Field(min_length=2)
    comment: str | None = Field(default=None, max_length=1000)


class ExecutionCancelRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


class ExecutionCancellation(BaseModel):
    execution_id: str
    reason: str
    requested_by: str
    requested_at: str


class TraceIntegrityReport(BaseModel):
    run_id: str
    valid: bool
    checked_events: int
    total_events: int
    head_hash: str | None
    broken_event_id: str | None
    reason: str | None


class RfqRecord(BaseModel):
    rfq_id: str
    request_id: str
    supplier_id: str
    supplier_name: str
    status: str
    created_at: str


class QuotationSubmission(BaseModel):
    unit_price: Decimal = Field(gt=0)
    currency: str = "CNY"
    delivery_days: int = Field(gt=0)
    warranty_months: int = Field(ge=0)
    valid_until: str


class AuditEvent(BaseModel):
    event_id: str
    action: str
    actor_id: str
    resource_type: str
    resource_id: str
    details: dict
    created_at: str


class ConversationStartRequest(BaseModel):
    requester_id: str = Field(min_length=2)
    department: str = Field(min_length=2)


class ConversationMessageRequest(BaseModel):
    text: str = Field(min_length=1)
    required_date: str | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH"] | None = None


class ConversationMessageRecord(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ConversationState(BaseModel):
    session_id: str
    requester_id: str
    department: str
    status: str
    draft: ParsedPurchaseDraft
    messages: list[ConversationMessageRecord]
    created_at: str
    updated_at: str


class ExternalOperationResult(BaseModel):
    system: str
    action: str
    status: str
    external_reference: str
    payload: dict


class IntegrationRecord(ExternalOperationResult):
    integration_id: str
    resource_type: str
    resource_id: str
    created_at: str


class PurchaseOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class AwardDecisionRequest(BaseModel):
    run_id: str
    supplier_id: str
    decided_by: str
    reason: str = Field(min_length=2, max_length=1000)
    expected_delivery_date: str


class PurchaseOrder(BaseModel):
    po_id: str
    request_id: str
    run_id: str
    supplier_id: str
    supplier_name: str
    quantity: int
    total_amount: Decimal
    currency: str
    expected_delivery_date: str
    status: PurchaseOrderStatus
    created_by: str
    award_reason: str
    created_at: str
    updated_at: str


class OrderStatusUpdate(BaseModel):
    status: PurchaseOrderStatus
    actor_id: str = Field(min_length=2)
    note: str | None = Field(default=None, max_length=1000)


class GoodsReceiptRequest(BaseModel):
    received_quantity: int = Field(gt=0)
    accepted_quantity: int = Field(ge=0)
    rejected_quantity: int = Field(ge=0)
    receiver_id: str = Field(min_length=2)
    note: str | None = Field(default=None, max_length=1000)


class GoodsReceipt(BaseModel):
    receipt_id: str
    po_id: str
    received_quantity: int
    accepted_quantity: int
    rejected_quantity: int
    receiver_id: str
    note: str | None
    received_at: str


class DashboardSummary(BaseModel):
    total_requests: int
    total_agent_runs: int
    pending_approvals: int
    total_orders: int
    orders_by_status: dict[str, int]
    approved_order_value: Decimal


class DemandExtraction(BaseModel):
    product: str | None
    category: str | None
    quantity: int | None
    budget: Decimal | None
    required_date: str | None
    priority: Literal["LOW", "MEDIUM", "HIGH"] | None


class AiRuntimeStatus(BaseModel):
    provider: str
    model: str | None
    enabled: bool
    fallback: bool


class AgentCapabilities(BaseModel):
    graph_steps: list[str]
    execution_graph: list[str]
    tools: list[str]
    system_prompt_version: str
    supports_conditional_routing: bool
    supports_iterative_tool_loop: bool
    planning_mode: str
    max_iterations: int
    max_runtime_seconds: float
    supports_durable_sessions: bool
    supports_human_interrupt: bool
    supports_long_term_memory: bool
    supports_planner_fallback: bool
    supports_planner_fallback_trace: bool
    supports_tool_contract_validation: bool
    supports_execution_cancellation: bool
    supports_tamper_evident_trace: bool
    supports_decision_provenance: bool
    supports_provenance_replay: bool
    supports_final_decision_guardrails: bool
    supports_context_injection_defense: bool
    tool_contract_version: str
    ruleset_version: str
    ruleset_fingerprint: str
    retrieval_mode: str


class AgentSessionDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    approver_id: str = Field(min_length=2)
    comment: str | None = Field(default=None, max_length=1000)


class AgentSessionView(BaseModel):
    thread_id: str
    request_id: str
    status: str
    result: AnalysisResult | None
    pending_action: dict | None
    decision: dict | None


class AgentMemory(BaseModel):
    memory_id: str
    thread_id: str
    request_id: str
    kind: str
    content: str
    metadata: dict
    created_at: str


class ToolInvocation(BaseModel):
    name: str
    arguments: dict
    output_preview: str


class AgentAssistResponse(BaseModel):
    provider: str
    answer: str
    tool_calls: list[ToolInvocation]


class IntegrationJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY = "RETRY"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IntegrationJob(BaseModel):
    job_id: str
    run_id: str
    target: Literal["OA", "ERP"]
    status: IntegrationJobStatus
    attempts: int
    max_attempts: int
    next_attempt_at: str
    last_error: str | None
    integration_id: str | None
    created_at: str
    updated_at: str


class RfqDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY = "RETRY"
    SENT = "SENT"
    FAILED = "FAILED"


class RfqDelivery(BaseModel):
    delivery_id: str
    rfq_id: str
    request_id: str
    supplier_id: str
    status: RfqDeliveryStatus
    attempts: int
    max_attempts: int
    next_attempt_at: str
    external_reference: str | None
    last_error: str | None
    payload: dict
    created_at: str
    updated_at: str


class SupplierDeliveryResult(BaseModel):
    status: str
    external_reference: str


class SupplierCallbackReceipt(BaseModel):
    event_id: str
    quotation: Quotation
    duplicate: bool = False

