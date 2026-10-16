from __future__ import annotations

from typing import Any

import httpx

from ...domain.models import AgentRunRecord, ExternalOperationResult


class IntegrationGatewayError(RuntimeError):
    pass


class _HttpGateway:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not api_token:
            raise ValueError("HTTP 集成网关必须配置 base_url 和 api_token。")
        self._authorization = f"Bearer {api_token}"
        self.client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_token}"},
        )

    def _post(
        self, path: str, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        try:
            response = self.client.post(
                path,
                json=payload,
                headers={
                    "Authorization": self._authorization,
                    "Idempotency-Key": idempotency_key,
                },
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationGatewayError(f"外部系统调用失败: {exc}") from exc
        if not isinstance(body, dict) or not body.get("external_reference"):
            raise IntegrationGatewayError("外部系统响应缺少 external_reference。")
        return body


class HttpOaGateway(_HttpGateway):
    def create_approval(self, run: AgentRunRecord) -> ExternalOperationResult:
        payload = {
            "run_id": run.run_id,
            "request_id": run.request_id,
            "approval_level": run.approval_level,
            "amount": str(run.result.request.budget),
            "department": run.result.request.department,
            "requester_id": run.result.request.requester_id,
        }
        body = self._post(
            "/api/approvals", payload, f"OA:CREATE_APPROVAL:{run.run_id}"
        )
        return ExternalOperationResult(
            system="OA",
            action="CREATE_APPROVAL",
            status=str(body.get("status", "ACCEPTED")),
            external_reference=str(body["external_reference"]),
            payload=body.get("payload", payload),
        )


class HttpErpGateway(_HttpGateway):
    def create_purchase_order_draft(
        self, run: AgentRunRecord
    ) -> ExternalOperationResult:
        selected = run.result.recommendations[0] if run.result.recommendations else None
        payload = {
            "run_id": run.run_id,
            "request_id": run.request_id,
            "supplier_id": selected.supplier_id if selected else None,
            "quantity": run.result.request.quantity,
            "amount": (
                str(selected.quoted_total)
                if selected is not None and selected.quoted_total is not None
                else None
            ),
        }
        body = self._post(
            "/api/purchase-orders/drafts",
            payload,
            f"ERP:CREATE_PO_DRAFT:{run.run_id}",
        )
        return ExternalOperationResult(
            system="ERP-SAP",
            action="CREATE_PO_DRAFT",
            status=str(body.get("status", "ACCEPTED")),
            external_reference=str(body["external_reference"]),
            payload=body.get("payload", payload),
        )
