from __future__ import annotations

from ...core.config import Settings
from .gateways import HttpSupplierGateway, MockSupplierGateway


def build_supplier_gateway(settings: Settings):
    if settings.supplier_delivery_mode == "mock":
        return MockSupplierGateway()
    if settings.supplier_delivery_mode != "http":
        raise ValueError(
            f"不支持的 SUPPLIER_DELIVERY_MODE: {settings.supplier_delivery_mode}"
        )
    if not settings.supplier_gateway_url or not settings.supplier_gateway_token:
        raise ValueError("供应商 HTTP 发送模式缺少地址或 API Token。")
    return HttpSupplierGateway(
        settings.supplier_gateway_url,
        settings.supplier_gateway_token,
        settings.integration_timeout_seconds,
    )
