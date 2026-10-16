"""Run an end-to-end procurement workflow against the local API application."""

import os

os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault(
    "AUTH_TOKENS",
    "smoke-procurement-token|E001|PROCUREMENT;smoke-warehouse-token|E004|WAREHOUSE",
)

from fastapi.testclient import TestClient

from procurement_agent.main import app


def main() -> None:
    client = TestClient(
        app, headers={"Authorization": "Bearer smoke-procurement-token"}
    )
    conversation = client.post(
        "/api/v1/conversations",
        json={"requester_id": "E002", "department": "研发部"},
    ).json()
    session_id = conversation["session_id"]
    client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"text": "采购12台GPU服务器"},
    ).raise_for_status()
    ready = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={
            "text": "预算75万元",
            "required_date": "2027-03-01",
            "priority": "HIGH",
        },
    )
    ready.raise_for_status()
    request_response = client.post(f"/api/v1/conversations/{session_id}/submit")
    request_response.raise_for_status()
    request = request_response.json()
    request_id = request["request_id"]
    rfqs = client.post(f"/api/v1/requests/{request_id}/rfqs").json()
    for index, (rfq, price) in enumerate(zip(rfqs[:3], [58000, 55000, 56500], strict=True)):
        response = client.post(
            f"/api/v1/rfqs/{rfq['rfq_id']}/quotation",
            json={
                "unit_price": price,
                "currency": "CNY",
                "delivery_days": 18 + index,
                "warranty_months": 36,
                "valid_until": "2027-02-15",
            },
        )
        response.raise_for_status()

    run_response = client.post("/api/v1/agent/runs", params={"request_id": request_id})
    run_response.raise_for_status()
    run = run_response.json()
    run_id = run["run_id"]
    oa = client.post(f"/api/v1/integrations/runs/{run_id}/oa")
    oa.raise_for_status()
    denied = client.post(
        f"/api/v1/agent/runs/{run_id}/approval",
        json={"decision": "APPROVED", "approver_id": "E002", "comment": "本人审批"},
    )
    approved = client.post(
        f"/api/v1/agent/runs/{run_id}/approval",
        json={
            "decision": "APPROVED",
            "approver_id": "E001",
            "comment": "技术、预算和三家报价已复核",
        },
    )
    approved.raise_for_status()
    erp = client.post(f"/api/v1/integrations/runs/{run_id}/erp")
    erp.raise_for_status()
    selected = run["result"]["recommendations"][0]
    order = client.post(
        "/api/v1/orders",
        json={
            "run_id": run_id,
            "supplier_id": selected["supplier_id"],
            "decided_by": "E001",
            "reason": "综合评分最高且报价符合预算",
            "expected_delivery_date": "2027-03-01",
        },
    )
    order.raise_for_status()
    po_id = order.json()["po_id"]
    for status in ("ISSUED", "ACKNOWLEDGED", "IN_TRANSIT"):
        transition = client.post(
            f"/api/v1/orders/{po_id}/status",
            json={"status": status, "actor_id": "E001"},
        )
        transition.raise_for_status()
    receipt = client.post(
        f"/api/v1/orders/{po_id}/receipts",
        headers={"Authorization": "Bearer smoke-warehouse-token"},
        json={
            "received_quantity": 12,
            "accepted_quantity": 12,
            "rejected_quantity": 0,
            "receiver_id": "E004",
            "note": "设备数量与外观验收通过",
        },
    )
    receipt.raise_for_status()
    delivered = client.get(f"/api/v1/orders/{po_id}").json()
    dashboard = client.get("/api/v1/dashboard/summary").json()
    audit_events = client.get("/api/v1/audit/events", params={"limit": 20}).json()
    quotations = client.get(f"/api/v1/requests/{request_id}/quotations").json()
    top = run["result"]["recommendations"][0]

    print(f"CONVERSATION {session_id} {ready.json()['status']}")
    print(f"REQUEST {request_id}")
    print(f"QUOTES {len(quotations)}")
    print(f"TOP {top['supplier_name']} {top['quoted_total']}")
    print(f"WARNINGS {run['result']['warnings']}")
    print(f"SELF_APPROVAL {denied.status_code} {denied.json()['detail']}")
    print(f"APPROVAL {approved.status_code} {approved.json()['status']}")
    print(f"OA {oa.json()['external_reference']}")
    print(f"ERP {erp.json()['external_reference']}")
    print(f"ORDER {po_id} {delivered['status']}")
    print(f"DASHBOARD {dashboard['total_orders']} {dashboard['approved_order_value']}")
    print(f"AUDIT_EVENTS {len(audit_events)} {audit_events[0]['action']}")


if __name__ == "__main__":
    main()
