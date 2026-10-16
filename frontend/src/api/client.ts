import type {
  AgentRunRecord,
  AgentExecution,
  AiRuntimeStatus,
  AuditEvent,
  DashboardSummary,
  IntakePayload,
  IntegrityReport,
  KnowledgeStatus,
  GoodsReceipt,
  ConversationState,
  IntegrationJob,
  IntegrationRecord,
  ParsedPurchaseDraft,
  PurchaseOrder,
  PurchaseRequest,
  Quotation,
  RfqRecord,
  TraceEvent
} from "../types/domain";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "procurement-agent-token";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  if (token.trim()) localStorage.setItem(TOKEN_KEY, token.trim());
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? JSON.stringify((detail as { detail: unknown }).detail)
        : `请求失败（${response.status}）`;
    throw new ApiError(response.status, message, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  dashboard: () => request<DashboardSummary>("/api/v1/dashboard/summary"),
  requests: () => request<PurchaseRequest[]>("/api/v1/requests"),
  runs: (limit = 50) => request<AgentRunRecord[]>(`/api/v1/agent/runs?limit=${limit}`),
  orders: () => request<PurchaseOrder[]>("/api/v1/orders"),
  audit: (limit = 100) => request<AuditEvent[]>(`/api/v1/audit/events?limit=${limit}`),
  aiStatus: () => request<AiRuntimeStatus>("/api/v1/system/ai"),
  knowledgeStatus: () => request<KnowledgeStatus>("/api/v1/knowledge/status"),
  parseIntake: (payload: IntakePayload) =>
    request<ParsedPurchaseDraft>("/api/v1/intake/parse", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  submitIntake: (payload: IntakePayload) =>
    request<PurchaseRequest>("/api/v1/intake/submit", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createRun: (requestId: string) =>
    request<AgentRunRecord>(
      `/api/v1/agent/runs?request_id=${encodeURIComponent(requestId)}`,
      { method: "POST" }
    ),
  createRfqs: (requestId: string) =>
    request<RfqRecord[]>(`/api/v1/requests/${encodeURIComponent(requestId)}/rfqs`, {
      method: "POST"
    }),
  rfqs: (requestId: string) =>
    request<RfqRecord[]>(`/api/v1/requests/${encodeURIComponent(requestId)}/rfqs`),
  quotations: (requestId: string) =>
    request<Quotation[]>(`/api/v1/requests/${encodeURIComponent(requestId)}/quotations`),
  approveRun: (
    runId: string,
    payload: { decision: "APPROVED" | "REJECTED"; approver_id: string; comment?: string }
  ) =>
    request<AgentRunRecord>(`/api/v1/agent/runs/${encodeURIComponent(runId)}/approval`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  trace: (executionId: string) =>
    request<TraceEvent[]>(`/api/v1/agent/runs/${encodeURIComponent(executionId)}/trace`),
  traceVerify: (executionId: string) =>
    request<IntegrityReport>(
      `/api/v1/agent/runs/${encodeURIComponent(executionId)}/trace/verify`
    ),
  provenanceVerify: (runId: string) =>
    request<IntegrityReport>(
      `/api/v1/agent/runs/${encodeURIComponent(runId)}/provenance/verify`
    ),
  createOrder: (payload: {
    run_id: string;
    supplier_id: string;
    decided_by: string;
    reason: string;
    expected_delivery_date: string;
  }) => request<PurchaseOrder>("/api/v1/orders", { method: "POST", body: JSON.stringify(payload) }),
  updateOrderStatus: (
    poId: string,
    payload: { status: string; actor_id: string; note?: string }
  ) => request<PurchaseOrder>(`/api/v1/orders/${encodeURIComponent(poId)}/status`, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  receiveOrder: (
    poId: string,
    payload: {
      received_quantity: number;
      accepted_quantity: number;
      rejected_quantity: number;
      receiver_id: string;
      note?: string;
    }
  ) => request<GoodsReceipt>(`/api/v1/orders/${encodeURIComponent(poId)}/receipts`, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  orderReceipts: (poId: string) =>
    request<GoodsReceipt[]>(`/api/v1/orders/${encodeURIComponent(poId)}/receipts`),
  submitQuotation: (rfqId: string, payload: {
    unit_price: number;
    currency: string;
    delivery_days: number;
    warranty_months: number;
    valid_until: string;
  }) => request<Quotation>(`/api/v1/rfqs/${encodeURIComponent(rfqId)}/quotation`, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  startConversation: (payload: { requester_id: string; department: string }) =>
    request<ConversationState>("/api/v1/conversations", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getConversation: (sessionId: string) =>
    request<ConversationState>(`/api/v1/conversations/${encodeURIComponent(sessionId)}`),
  sendConversationMessage: (sessionId: string, payload: {
    text: string;
    required_date?: string;
    priority?: "LOW" | "MEDIUM" | "HIGH";
  }) => request<ConversationState>(`/api/v1/conversations/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  submitConversation: (sessionId: string) =>
    request<PurchaseRequest>(`/api/v1/conversations/${encodeURIComponent(sessionId)}/submit`, {
      method: "POST"
    }),
  execution: (executionId: string) =>
    request<AgentExecution>(`/api/v1/agent/runs/${encodeURIComponent(executionId)}/execution`),
  cancelExecution: (executionId: string, reason: string) =>
    request(`/api/v1/agent/runs/${encodeURIComponent(executionId)}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  retryExecution: (executionId: string) =>
    request<AgentRunRecord>(`/api/v1/agent/runs/${encodeURIComponent(executionId)}/retry`, {
      method: "POST"
    }),
  integrationRecords: (limit = 100) =>
    request<IntegrationRecord[]>(`/api/v1/integrations/records?limit=${limit}`),
  integrationJobs: (limit = 100) =>
    request<IntegrationJob[]>(`/api/v1/integrations/jobs?limit=${limit}`),
  enqueueIntegration: (runId: string, target: "OA" | "ERP") =>
    request<IntegrationJob>(`/api/v1/integrations/jobs?run_id=${encodeURIComponent(runId)}&target=${target}`, {
      method: "POST"
    }),
  syncRun: (runId: string, target: "OA" | "ERP") =>
    request<IntegrationRecord>(`/api/v1/integrations/runs/${encodeURIComponent(runId)}/${target.toLowerCase()}`, {
      method: "POST"
    })
};

export function formatError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "发生未知错误";
}
