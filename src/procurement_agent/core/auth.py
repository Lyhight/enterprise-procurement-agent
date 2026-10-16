from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    employee_id: str
    role: str


class BearerTokenAuth:
    """Environment-backed bearer authentication storing only token digests."""

    def __init__(self, encoded_credentials: str) -> None:
        self._credentials: list[tuple[str, AuthenticatedPrincipal]] = []
        for entry in encoded_credentials.split(";"):
            if not entry.strip():
                continue
            parts = [part.strip() for part in entry.split("|")]
            if len(parts) != 3 or not all(parts):
                raise ValueError(
                    "AUTH_TOKENS 格式必须为 token|employee_id|role，多个凭证用分号分隔。"
                )
            token, employee_id, role = parts
            self._credentials.append(
                (self._digest(token), AuthenticatedPrincipal(employee_id, role.upper()))
            )

    @property
    def configured(self) -> bool:
        return bool(self._credentials)

    def authenticate(self, token: str) -> AuthenticatedPrincipal:
        candidate = self._digest(token)
        for digest, principal in self._credentials:
            if compare_digest(candidate, digest):
                return principal
        raise PermissionError("Bearer 凭证无效。")

    @staticmethod
    def _digest(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()


def require_actor_identity(
    principal: AuthenticatedPrincipal, claimed_employee_id: str
) -> None:
    if principal.employee_id != claimed_employee_id:
        raise PermissionError("认证身份与请求中的操作人不一致。")
