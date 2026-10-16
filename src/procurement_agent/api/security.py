from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.auth import AuthenticatedPrincipal
from .dependencies import auth_service, settings

bearer = HTTPBearer(auto_error=False)


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthenticatedPrincipal:
    middleware_principal = getattr(request.state, "principal", None)
    if middleware_principal is not None:
        return middleware_principal
    if not settings.auth_enabled or not auth_service.configured:
        raise HTTPException(status_code=503, detail="API 身份认证尚未配置。")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="缺少 Bearer 凭证。")
    try:
        return auth_service.authenticate(credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_roles(*allowed_roles: str) -> Callable:
    allowed = {role.upper() for role in allowed_roles}

    def dependency(
        principal: AuthenticatedPrincipal = Depends(current_principal),
    ) -> AuthenticatedPrincipal:
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="当前身份无权执行该操作。")
        return principal

    return dependency
