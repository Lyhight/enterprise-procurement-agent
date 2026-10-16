from __future__ import annotations

from uuid import uuid4

import httpx

from ...domain.models import SupplierDeliveryResult


class SupplierGatewayError(RuntimeError):
    pass


class MockSupplierGateway:
    def send_rfq(self, payload: dict, idempotency_key: str) -> SupplierDeliveryResult:
        return SupplierDeliveryResult(
            status="ACCEPTED",
            external_reference=f"SUP-{uuid4().hex[:12].upper()}",
        )


class HttpSupplierGateway:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not api_token:
            raise ValueError("供应商 HTTP 网关必须配置地址和 API Token。")
        self._authorization = f"Bearer {api_token}"
        self.client = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds
        )

    def send_rfq(self, payload: dict, idempotency_key: str) -> SupplierDeliveryResult:
        try:
            response = self.client.post(
                "/api/rfqs",
                json=payload,
                headers={
                    "Authorization": self._authorization,
                    "Idempotency-Key": idempotency_key,
                },
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SupplierGatewayError(f"发送询价失败: {exc}") from exc
        if not isinstance(body, dict) or not body.get("external_reference"):
            raise SupplierGatewayError("供应商网关响应缺少 external_reference。")
        return SupplierDeliveryResult(
            status=str(body.get("status", "ACCEPTED")),
            external_reference=str(body["external_reference"]),
        )
