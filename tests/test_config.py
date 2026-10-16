from dataclasses import replace

from procurement_agent import __version__
from procurement_agent.api.app import create_app
from procurement_agent.core.config import get_settings


def test_project_root_can_be_explicitly_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))

    settings = get_settings()

    assert settings.project_root == tmp_path.resolve()
    assert settings.company_data_dir == tmp_path.resolve() / "data" / "raw" / "company"


def test_api_version_matches_package_version(tmp_path) -> None:
    settings = get_settings()
    app = create_app(settings_override=replace(settings, project_root=tmp_path))

    assert app.version == __version__
