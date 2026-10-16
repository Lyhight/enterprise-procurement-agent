from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ...core.auth import BearerTokenAuth
from ...core.config import Settings


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authenticate every business API request when production auth is enabled."""

    def __init__(
        self, app, settings: Settings, auth_service: BearerTokenAuth
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.auth_service = auth_service

    async def dispatch(self, request: Request, call_next):
        is_supplier_callback = request.url.path.startswith(
            "/api/v1/supplier-callbacks/"
        )
        if (
            not self.settings.auth_enabled
            or not request.url.path.startswith("/api/v1")
            or is_supplier_callback
        ):
            return await call_next(request)
        if not self.auth_service.configured:
            return JSONResponse(
                {"detail": "API 身份认证已启用但没有配置凭证。"}, status_code=503
            )
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse({"detail": "缺少 Bearer 凭证。"}, status_code=401)
        try:
            request.state.principal = self.auth_service.authenticate(token)
        except PermissionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)
        return await call_next(request)
