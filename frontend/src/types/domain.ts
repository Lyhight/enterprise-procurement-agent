export type RunStatus = "AWAITING_APPROVAL" | "COMPLETED" | "REJECTED";

export interface DashboardSummary {
  total_requests: number;
  total_agent_runs: number;
  pending_approvals: number;
  total_orders: number;
  orders_by_status: Record<string, number>;
  approved_order_value: string | number;
}

export interface PurchaseRequest {
  request_id: string;
  requester_id: string;
  department: string;
  product: string;
  category: string;
  quantity: number;
  budget: string | number;
  required_date: string;
  priority: string;
  status: string;
}

export interface SupplierRecommendation {
  supplier_id: string;
  supplier_name: string;
  score: number;
  quoted_total: string | number | null;
  reasons: string[];
}

export interface PolicyEvidence {
  source: string;
  section: string;
  content: string;
  score: number;
}

export interface AgentTraceStep {
  step: string;
  status: string;
  summary: string;
}

export interface GuardrailReport {
  valid: boolean;
  checks: Record<string, boolean>;
  violations: string[];
}

export interface AnalysisResult {
  request: PurchaseRequest;
  approval_level: string;
  recommendations: SupplierRecommendation[];
  warnings: string[];
  policy_evidence: PolicyEvidence[];
  trace: AgentTraceStep[];
  next_action: string;
  agent_iterations: number;
  run_id: string | null;
  planner_provider: string;
  planner_fallback_count: number;
  execution_plan: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
  guardrail_report: GuardrailReport | null;
}

export interface AgentRunRecord {
  run_id: string;
  request_id: string;
  status: RunStatus;
  approval_level: string;
  approval_decision: string;
  approver_id: string | null;
  approval_comment: string | null;
  result: AnalysisResult;
  created_at: string;
  updated_at: string;
}

export interface ParsedPurchaseDraft {
  requester_id: string;
  department: string;
  product: string | null;
  category: string | null;
  quantity: number | null;
  budget: string | number | null;
  required_date: string | null;
  priority: string;
  missing_fields: string[];
  ready_to_submit: boolean;
}

export interface IntakePayload {
  text: string;
  requester_id: string;
  department: string;
  required_date?: string;
  priority: "LOW" | "MEDIUM" | "HIGH";
}

export interface PurchaseOrder {
  po_id: string;
  request_id: string;
  run_id: string;
  supplier_id: string;
  supplier_name: string;
  quantity: number;
  total_amount: string | number;
  currency: string;
  expected_delivery_date: string;
  status: string;
  created_by: string;
  award_reason: string;
  created_at: string;
  updated_at: string;
}

export interface RfqRecord {
  rfq_id: string;
  request_id: string;
  supplier_id: string;
  supplier_name: string;
  status: string;
  created_at: string;
}

export interface Quotation {
  quotation_id: string;
  request_id: string;
  supplier_id: string;
  unit_price: string | number;
  currency: string;
  delivery_days: number;
  warranty_months: number;
  valid_until: string;
}

export interface GoodsReceipt {
  receipt_id: string;
  po_id: string;
  received_quantity: number;
  accepted_quantity: number;
  rejected_quantity: number;
  receiver_id: string;
  note: string | null;
  received_at: string;
}

export interface ConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationState {
  session_id: string;
  requester_id: string;
  department: string;
  status: string;
  draft: ParsedPurchaseDraft;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}

export interface IntegrationRecord {
  integration_id: string;
  system: string;
  action: string;
  status: string;
  external_reference: string;
  resource_type: string;
  resource_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface IntegrationJob {
  job_id: string;
  run_id: string;
  target: "OA" | "ERP";
  status: "PENDING" | "RUNNING" | "RETRY" | "SUCCEEDED" | "FAILED";
  attempts: number;
  max_attempts: number;
  next_attempt_at: string;
  last_error: string | null;
  integration_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentExecution {
  execution_id: string;
  request_id: string;
  status: "RUNNING" | "FAILED" | "COMPLETED" | "CANCELLED";
  current_step_id: string | null;
  iterations: number;
  execution_plan: Array<Record<string, unknown>>;
  last_error: string | null;
}

export interface ExecutionCancellation {
  execution_id: string;
  reason: string;
  requested_by: string;
  requested_at: string;
}

export interface AuditEvent {
  event_id: string;
  action: string;
  actor_id: string;
  resource_type: string;
  resource_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface TraceEvent {
  event_id: string;
  event_type: string;
  step_id: string | null;
  status: string;
  duration_ms: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface IntegrityReport {
  valid: boolean;
  reason?: string | null;
  [key: string]: unknown;
}

export interface AiRuntimeStatus {
  provider: string;
  model: string | null;
  enabled: boolean;
  fallback: boolean;
}

export interface KnowledgeStatus {
  documents: number;
  chunks: number;
  retrieval_mode: string;
}
