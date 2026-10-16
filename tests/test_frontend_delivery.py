from dataclasses import replace

from fastapi.testclient import TestClient

from procurement_agent.api.app import create_app
from procurement_agent.core.config import get_settings


def test_built_frontend_is_mounted_without_shadowing_api_or_docs(tmp_path) -> None:
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>Procurement Console</title>", encoding="utf-8"
    )
    app = create_app(
        settings_override=replace(
            get_settings(),
            project_root=tmp_path,
            app_env="development",
            auth_enabled=False,
            auth_tokens="",
        )
    )
    client = TestClient(app)

    root = client.get("/", follow_redirects=False)
    console = client.get("/app/")

    assert root.status_code in {302, 307}
    assert root.headers["location"] == "/app/"
    assert console.status_code == 200
    assert "Procurement Console" in console.text
    assert client.get("/docs").status_code == 200
    assert client.get("/api/v1/agent/capabilities").status_code == 200
