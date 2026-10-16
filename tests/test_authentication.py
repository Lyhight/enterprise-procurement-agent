import pytest
from dataclasses import replace
from fastapi.testclient import TestClient

from procurement_agent.core.auth import (
    AuthenticatedPrincipal,
    BearerTokenAuth,
    require_actor_identity,
)
from procurement_agent.core.config import get_settings
from procurement_agent.main import create_app


@pytest.fixture
def auth_app():
    tokens = (
        "long-random-procurement-token|E001|PROCUREMENT;"
        "long-random-requester-token|E002|REQUESTER"
    )
    application = create_app(
        settings_override=replace(
            get_settings(), auth_enabled=True, auth_tokens=tokens
        ),
        auth_service_override=BearerTokenAuth(tokens),
    )
    yield application


def test_bearer_tokens_authenticate_without_storing_plaintext() -> None:
    service = BearerTokenAuth(
        "long-random-procurement-token|E001|PROCUREMENT;"
        "long-random-requester-token|E002|REQUESTER"
    )

    principal = service.authenticate("long-random-procurement-token")

    assert principal.employee_id == "E001"
    assert principal.role == "PROCUREMENT"
    assert "long-random-procurement-token" not in repr(service._credentials)
    with pytest.raises(PermissionError, match="无效"):
        service.authenticate("wrong-token")


def test_protected_agent_tool_endpoint_binds_authenticated_actor(auth_app) -> None:
    response = TestClient(auth_app).post(
        "/api/v1/agent/assist",
        params={"request_id": "PR001", "question": "供应商和制度依据是什么？"},
        headers={"Authorization": "Bearer long-random-procurement-token"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "local"
    assert len(response.json()["tool_calls"]) == 3


def test_protected_agent_tool_endpoint_rejects_wrong_role(auth_app) -> None:
    response = TestClient(auth_app).post(
        "/api/v1/agent/assist",
        params={"request_id": "PR001", "question": "给出供应商列表"},
        headers={"Authorization": "Bearer long-random-requester-token"},
    )

    assert response.status_code == 403


def test_authenticated_actor_cannot_impersonate_another_employee() -> None:
    with pytest.raises(PermissionError, match="不一致"):
        require_actor_identity(
            AuthenticatedPrincipal("E001", "PROCUREMENT"), "E003"
        )
