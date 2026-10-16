from __future__ import annotations

from ...core.config import Settings
from .http_gateways import HttpErpGateway, HttpOaGateway
from .mock_erp import MockErpGateway
from .mock_oa import MockOaGateway


def build_integration_gateways(settings: Settings):
    if settings.integration_mode == "mock":
        return MockOaGateway(), MockErpGateway()
    if settings.integration_mode != "http":
        raise ValueError(f"不支持的 INTEGRATION_MODE: {settings.integration_mode}")
    if not all(
        (
            settings.oa_base_url,
            settings.oa_api_token,
            settings.erp_base_url,
            settings.erp_api_token,
        )
    ):
        raise ValueError("HTTP 集成模式缺少 OA/ERP 地址或 API Token。")
    return (
        HttpOaGateway(
            settings.oa_base_url,
            settings.oa_api_token,
            settings.integration_timeout_seconds,
        ),
        HttpErpGateway(
            settings.erp_base_url,
            settings.erp_api_token,
            settings.integration_timeout_seconds,
        ),
    )
