from __future__ import annotations

import sqlite3
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..domain.models import (
    AgentRunRecord,
    AnalysisResult,
    ApprovalDecisionRequest,
    AuditEvent,
    ConversationMessageRecord,
    ConversationState,
    ExternalOperationResult,
    IntegrationRecord,
    GoodsReceipt,
    GoodsReceiptRequest,
    PurchaseOrder,
    PurchaseOrderStatus,
    ParsedPurchaseDraft,
    PurchaseRequest,
    Quotation,
    QuotationSubmission,
    RfqRecord,
    RunStatus,
    Supplier,
)


class RunStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_level TEXT NOT NULL,
                    approval_decision TEXT NOT NULL,
                    approver_id TEXT,
                    approval_comment TEXT,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS supplier_quotations (
                    quotation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    rfq_id TEXT NOT NULL UNIQUE,
                    supplier_id TEXT NOT NULL,
                    unit_price TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    delivery_days INTEGER NOT NULL,
                    warranty_months INTEGER NOT NULL,
                    valid_until TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, supplier_id)
                )
                """
            )

    def create(self, result: AnalysisResult) -> AgentRunRecord:
        needs_approval = result.approval_level in {"L2", "L3"} or bool(result.warnings)
        status = RunStatus.AWAITING_APPROVAL if needs_approval else RunStatus.COMPLETED
        decision = "PENDING" if needs_approval else "AUTO_APPROVED"
        timestamp = _now()
        run_id = f"RUN-{uuid4().hex[:12].upper()}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, request_id, status, approval_level, approval_decision,
                    result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.request.request_id,
                    status.value,
                    result.approval_level,
                    decision,
                    result.model_dump_json(),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(run_id)

    def get(self, run_id: str) -> AgentRunRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"Agent 运行记录不存在: {run_id}")
        return _row_to_record(row)

    def list(self, limit: int = 20) -> list[AgentRunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def decide(self, run_id: str, decision: ApprovalDecisionRequest) -> AgentRunRecord:
        current = self.get(run_id)
        if current.status is not RunStatus.AWAITING_APPROVAL:
            raise ValueError(f"运行记录当前状态为 {current.status.value}，不能重复审批。")
        status = RunStatus.COMPLETED if decision.decision == "APPROVED" else RunStatus.REJECTED
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET status = ?, approval_decision = ?, approver_id = ?,
                    approval_comment = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    status.value,
                    decision.decision,
                    decision.approver_id,
                    decision.comment,
                    _now(),
                    run_id,
                ),
            )
        return self.get(run_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


class RequestStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS purchase_requests (
                    request_id TEXT PRIMARY KEY,
                    requester_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    product TEXT NOT NULL,
                    category TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    budget TEXT NOT NULL,
                    required_date TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rfqs (
                    rfq_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    supplier_id TEXT NOT NULL,
                    supplier_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, supplier_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS supplier_quotations (
                    quotation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    rfq_id TEXT NOT NULL UNIQUE,
                    supplier_id TEXT NOT NULL,
                    unit_price TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    delivery_days INTEGER NOT NULL,
                    warranty_months INTEGER NOT NULL,
                    valid_until TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, supplier_id)
                )
                """
            )

    def create(self, draft: ParsedPurchaseDraft) -> PurchaseRequest:
        if not draft.ready_to_submit:
            raise ValueError(f"采购需求字段不完整: {', '.join(draft.missing_fields)}")
        request = PurchaseRequest(
            request_id=f"PR-{uuid4().hex[:10].upper()}",
            requester_id=draft.requester_id,
            department=draft.department,
            product=draft.product,
            category=draft.category,
            quantity=draft.quantity,
            budget=draft.budget,
            required_date=draft.required_date,
            priority=draft.priority,
            status="submitted",
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO purchase_requests (
                    request_id, requester_id, department, product, category,
                    quantity, budget, required_date, priority, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.requester_id,
                    request.department,
                    request.product,
                    request.category,
                    request.quantity,
                    str(request.budget),
                    request.required_date,
                    request.priority,
                    request.status,
                    _now(),
                ),
            )
        return request

    def list(self) -> list[PurchaseRequest]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM purchase_requests ORDER BY created_at DESC"
            ).fetchall()
        return [
            PurchaseRequest.model_validate(
                {
                    key: row[key]
                    for key in (
                        "request_id",
                        "requester_id",
                        "department",
                        "product",
                        "category",
                        "quantity",
                        "budget",
                        "required_date",
                        "priority",
                        "status",
                    )
                }
            )
            for row in rows
        ]

    def create_rfqs(self, request: PurchaseRequest, suppliers: list[Supplier]) -> list[RfqRecord]:
        timestamp = _now()
        with self._connect() as connection:
            for supplier in suppliers:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO rfqs (
                        rfq_id, request_id, supplier_id, supplier_name, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"RFQ-{uuid4().hex[:10].upper()}",
                        request.request_id,
                        supplier.supplier_id,
                        supplier.supplier_name,
                        "CREATED",
                        timestamp,
                    ),
                )
        return self.list_rfqs(request.request_id)

    def list_rfqs(self, request_id: str) -> list[RfqRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM rfqs WHERE request_id = ? ORDER BY created_at, supplier_id",
                (request_id,),
            ).fetchall()
        return [RfqRecord.model_validate(dict(row)) for row in rows]

    def rfq_by_id(self, rfq_id: str) -> RfqRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM rfqs WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"询价单不存在: {rfq_id}")
        return RfqRecord.model_validate(dict(row))

    def mark_rfq_sent(self, rfq_id: str) -> RfqRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE rfqs SET status = 'SENT' WHERE rfq_id = ? AND status = 'CREATED'",
                (rfq_id,),
            )
        if cursor.rowcount == 0:
            rfq = self.rfq_by_id(rfq_id)
            if rfq.status not in {"SENT", "QUOTED"}:
                raise ValueError(f"询价单状态不能标记为已发送: {rfq.status}")
            return rfq
        return self.rfq_by_id(rfq_id)

    def submit_quotation(self, rfq_id: str, payload: QuotationSubmission) -> Quotation:
        with self._connect() as connection:
            rfq = connection.execute(
                "SELECT * FROM rfqs WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()
            if rfq is None:
                raise LookupError(f"询价单不存在: {rfq_id}")
            existing = connection.execute(
                "SELECT * FROM supplier_quotations WHERE rfq_id = ?", (rfq_id,)
            ).fetchone()
            if existing is not None:
                raise ValueError(f"询价单 {rfq_id} 已提交报价，不能重复提交。")
            quotation_id = f"Q-{uuid4().hex[:10].upper()}"
            connection.execute(
                """
                INSERT INTO supplier_quotations (
                    quotation_id, request_id, rfq_id, supplier_id, unit_price,
                    currency, delivery_days, warranty_months, valid_until, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quotation_id,
                    rfq["request_id"],
                    rfq_id,
                    rfq["supplier_id"],
                    str(payload.unit_price),
                    payload.currency,
                    payload.delivery_days,
                    payload.warranty_months,
                    payload.valid_until,
                    _now(),
                ),
            )
            connection.execute(
                "UPDATE rfqs SET status = 'QUOTED' WHERE rfq_id = ?", (rfq_id,)
            )
        return self.quotation_by_id(quotation_id)

    def quotations(self) -> list[Quotation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM supplier_quotations ORDER BY created_at DESC"
            ).fetchall()
        return [_quotation_from_row(row) for row in rows]

    def quotations_for_request(self, request_id: str) -> list[Quotation]:
        return [quote for quote in self.quotations() if quote.request_id == request_id]

    def quotation_by_id(self, quotation_id: str) -> Quotation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM supplier_quotations WHERE quotation_id = ?", (quotation_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"报价不存在: {quotation_id}")
        return _quotation_from_row(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


class AuditStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        action: str,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        details: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"EVT-{uuid4().hex[:12].upper()}",
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            created_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, action, actor_id, resource_type, resource_id,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.action,
                    event.actor_id,
                    event.resource_type,
                    event.resource_id,
                    json.dumps(event.details, ensure_ascii=False),
                    event.created_at,
                ),
            )
        return event

    def list(self, limit: int = 100) -> list[AuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            AuditEvent(
                event_id=row["event_id"],
                action=row["action"],
                actor_id=row["actor_id"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                details=json.loads(row["details_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


class ConversationStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS procurement_conversations (
                    session_id TEXT PRIMARY KEY,
                    requester_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    status TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES procurement_conversations(session_id)
                )
                """
            )

    def create(self, requester_id: str, department: str, draft: ParsedPurchaseDraft) -> ConversationState:
        timestamp = _now()
        session_id = f"CHAT-{uuid4().hex[:12].upper()}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO procurement_conversations (
                    session_id, requester_id, department, status, draft_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    requester_id,
                    department,
                    "COLLECTING",
                    draft.model_dump_json(),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(session_id)

    def get(self, session_id: str) -> ConversationState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM procurement_conversations WHERE session_id = ?", (session_id,)
            ).fetchone()
            messages = connection.execute(
                """
                SELECT message_id, role, content, created_at
                FROM conversation_messages
                WHERE session_id = ? ORDER BY created_at, rowid
                """,
                (session_id,),
            ).fetchall()
        if row is None:
            raise LookupError(f"采购对话不存在: {session_id}")
        return ConversationState(
            session_id=row["session_id"],
            requester_id=row["requester_id"],
            department=row["department"],
            status=row["status"],
            draft=ParsedPurchaseDraft.model_validate_json(row["draft_json"]),
            messages=[ConversationMessageRecord.model_validate(dict(item)) for item in messages],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.get(session_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_messages (
                    message_id, session_id, role, content, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (f"MSG-{uuid4().hex[:12].upper()}", session_id, role, content, _now()),
            )

    def update_draft(self, session_id: str, draft: ParsedPurchaseDraft) -> ConversationState:
        status = "READY" if draft.ready_to_submit else "COLLECTING"
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE procurement_conversations
                SET draft_json = ?, status = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (draft.model_dump_json(), status, _now(), session_id),
            )
        if cursor.rowcount == 0:
            raise LookupError(f"采购对话不存在: {session_id}")
        return self.get(session_id)

    def mark_submitted(self, session_id: str) -> ConversationState:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE procurement_conversations
                SET status = 'SUBMITTED', updated_at = ?
                WHERE session_id = ?
                """,
                (_now(), session_id),
            )
        if cursor.rowcount == 0:
            raise LookupError(f"采购对话不存在: {session_id}")
        return self.get(session_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


class IntegrationStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_records (
                    integration_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    system TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_reference TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(resource_id, system, action)
                )
                """
            )

    def save(
        self,
        resource_type: str,
        resource_id: str,
        result: ExternalOperationResult,
    ) -> IntegrationRecord:
        existing = self.find(resource_id, result.system, result.action)
        if existing is not None:
            return existing
        record = IntegrationRecord(
            integration_id=f"INT-{uuid4().hex[:12].upper()}",
            resource_type=resource_type,
            resource_id=resource_id,
            **result.model_dump(),
            created_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO integration_records (
                    integration_id, resource_type, resource_id, system, action,
                    status, external_reference, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.integration_id,
                    record.resource_type,
                    record.resource_id,
                    record.system,
                    record.action,
                    record.status,
                    record.external_reference,
                    json.dumps(record.payload, ensure_ascii=False),
                    record.created_at,
                ),
            )
        return record

    def find(self, resource_id: str, system: str, action: str) -> IntegrationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM integration_records
                WHERE resource_id = ? AND system = ? AND action = ?
                """,
                (resource_id, system, action),
            ).fetchone()
        return _integration_from_row(row) if row is not None else None

    def list(self, limit: int = 100) -> list[IntegrationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM integration_records ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_integration_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


class OrderStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS purchase_orders (
                    po_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    supplier_id TEXT NOT NULL,
                    supplier_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    total_amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    expected_delivery_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    award_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_events (
                    event_id TEXT PRIMARY KEY,
                    po_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS goods_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    po_id TEXT NOT NULL,
                    received_quantity INTEGER NOT NULL,
                    accepted_quantity INTEGER NOT NULL,
                    rejected_quantity INTEGER NOT NULL,
                    receiver_id TEXT NOT NULL,
                    note TEXT,
                    received_at TEXT NOT NULL
                )
                """
            )

    def create(self, order: PurchaseOrder) -> PurchaseOrder:
        existing = self.find_by_run(order.run_id)
        if existing is not None:
            return existing
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO purchase_orders (
                    po_id, request_id, run_id, supplier_id, supplier_name,
                    quantity, total_amount, currency, expected_delivery_date,
                    status, created_by, award_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.po_id, order.request_id, order.run_id, order.supplier_id,
                    order.supplier_name, order.quantity, str(order.total_amount),
                    order.currency, order.expected_delivery_date, order.status.value,
                    order.created_by, order.award_reason, order.created_at, order.updated_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO order_events (
                    event_id, po_id, from_status, to_status, actor_id, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"OEV-{uuid4().hex[:12].upper()}", order.po_id, None,
                    order.status.value, order.created_by, "采购定标并创建订单草稿",
                    order.created_at,
                ),
            )
        return self.get(order.po_id)

    def get(self, po_id: str) -> PurchaseOrder:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM purchase_orders WHERE po_id = ?", (po_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"采购订单不存在: {po_id}")
        return _order_from_row(row)

    def find_by_run(self, run_id: str) -> PurchaseOrder | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM purchase_orders WHERE run_id = ?", (run_id,)
            ).fetchone()
        return _order_from_row(row) if row is not None else None

    def list(self) -> list[PurchaseOrder]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM purchase_orders ORDER BY created_at DESC"
            ).fetchall()
        return [_order_from_row(row) for row in rows]

    def update_status(
        self, po_id: str, status: PurchaseOrderStatus, actor_id: str, note: str | None
    ) -> PurchaseOrder:
        current = self.get(po_id)
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE purchase_orders SET status = ?, updated_at = ? WHERE po_id = ?",
                (status.value, timestamp, po_id),
            )
            connection.execute(
                """
                INSERT INTO order_events (
                    event_id, po_id, from_status, to_status, actor_id, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"OEV-{uuid4().hex[:12].upper()}", po_id, current.status.value,
                    status.value, actor_id, note, timestamp,
                ),
            )
        return self.get(po_id)

    def add_receipt(self, po_id: str, payload: GoodsReceiptRequest) -> GoodsReceipt:
        self.get(po_id)
        receipt = GoodsReceipt(
            receipt_id=f"GR-{uuid4().hex[:12].upper()}",
            po_id=po_id,
            received_quantity=payload.received_quantity,
            accepted_quantity=payload.accepted_quantity,
            rejected_quantity=payload.rejected_quantity,
            receiver_id=payload.receiver_id,
            note=payload.note,
            received_at=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO goods_receipts (
                    receipt_id, po_id, received_quantity, accepted_quantity,
                    rejected_quantity, receiver_id, note, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_id, receipt.po_id, receipt.received_quantity,
                    receipt.accepted_quantity, receipt.rejected_quantity,
                    receipt.receiver_id, receipt.note, receipt.received_at,
                ),
            )
        return receipt

    def receipts(self, po_id: str) -> list[GoodsReceipt]:
        self.get(po_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM goods_receipts WHERE po_id = ? ORDER BY received_at",
                (po_id,),
            ).fetchall()
        return [GoodsReceipt.model_validate(dict(row)) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _quotation_from_row(row: sqlite3.Row) -> Quotation:
    return Quotation(
        quotation_id=row["quotation_id"],
        request_id=row["request_id"],
        supplier_id=row["supplier_id"],
        unit_price=row["unit_price"],
        currency=row["currency"],
        delivery_days=row["delivery_days"],
        warranty_months=row["warranty_months"],
        valid_until=row["valid_until"],
    )


def _integration_from_row(row: sqlite3.Row) -> IntegrationRecord:
    return IntegrationRecord(
        integration_id=row["integration_id"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        system=row["system"],
        action=row["action"],
        status=row["status"],
        external_reference=row["external_reference"],
        payload=json.loads(row["payload_json"]),
        created_at=row["created_at"],
    )


def _order_from_row(row: sqlite3.Row) -> PurchaseOrder:
    return PurchaseOrder(
        po_id=row["po_id"], request_id=row["request_id"], run_id=row["run_id"],
        supplier_id=row["supplier_id"], supplier_name=row["supplier_name"],
        quantity=row["quantity"], total_amount=row["total_amount"],
        currency=row["currency"], expected_delivery_date=row["expected_delivery_date"],
        status=row["status"], created_by=row["created_by"],
        award_reason=row["award_reason"], created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_record(row: sqlite3.Row) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=row["run_id"],
        request_id=row["request_id"],
        status=row["status"],
        approval_level=row["approval_level"],
        approval_decision=row["approval_decision"],
        approver_id=row["approver_id"],
        approval_comment=row["approval_comment"],
        result=AnalysisResult.model_validate_json(row["result_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
