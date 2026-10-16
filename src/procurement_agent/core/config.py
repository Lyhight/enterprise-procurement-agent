"""Project configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    llm_provider: str = "local"
    openai_model: str = "gpt-6-astra"
    openai_api_key: str | None = None
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    database_path_override: str | None = None
    cors_origins: tuple[str, ...] = ()
    auth_enabled: bool = False
    auth_tokens: str = ""
    integration_mode: str = "mock"
    oa_base_url: str | None = None
    oa_api_token: str | None = None
    erp_base_url: str | None = None
    erp_api_token: str | None = None
    integration_timeout_seconds: float = 10.0
    supplier_delivery_mode: str = "mock"
    supplier_gateway_url: str | None = None
    supplier_gateway_token: str | None = None
    supplier_callback_secret: str | None = None
    supplier_callback_tolerance_seconds: int = 300
    agent_max_iterations: int = 10
    agent_max_runtime_seconds: float = 30.0

    @property
    def company_data_dir(self) -> Path:
        return self.project_root / "data" / "raw" / "company"

    @property
    def documents_dir(self) -> Path:
        return self.project_root / "data" / "raw" / "documents"

    @property
    def database_path(self) -> Path:
        if self.database_path_override:
            return Path(self.database_path_override).expanduser().resolve()
        return self.project_root / "data" / "processed" / "procurement.db"


def get_settings() -> Settings:
    configured_root = os.getenv("PROJECT_ROOT")
    project_root = (
        Path(configured_root).expanduser().resolve()
        if configured_root
        else Path(__file__).resolve().parents[3]
    )
    return Settings(
        project_root=project_root,
        llm_provider=os.getenv("LLM_PROVIDER", "local").lower(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-6-astra"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        database_path_override=os.getenv("DATABASE_PATH"),
        cors_origins=tuple(
            item.strip()
            for item in os.getenv("CORS_ORIGINS", "").split(",")
            if item.strip()
        ),
        auth_enabled=os.getenv("AUTH_ENABLED", "false").lower() in {"1", "true", "yes"},
        auth_tokens=os.getenv("AUTH_TOKENS", ""),
        integration_mode=os.getenv("INTEGRATION_MODE", "mock").lower(),
        oa_base_url=os.getenv("OA_BASE_URL"),
        oa_api_token=os.getenv("OA_API_TOKEN"),
        erp_base_url=os.getenv("ERP_BASE_URL"),
        erp_api_token=os.getenv("ERP_API_TOKEN"),
        integration_timeout_seconds=float(
            os.getenv("INTEGRATION_TIMEOUT_SECONDS", "10")
        ),
        supplier_delivery_mode=os.getenv("SUPPLIER_DELIVERY_MODE", "mock").lower(),
        supplier_gateway_url=os.getenv("SUPPLIER_GATEWAY_URL"),
        supplier_gateway_token=os.getenv("SUPPLIER_GATEWAY_TOKEN"),
        supplier_callback_secret=os.getenv("SUPPLIER_CALLBACK_SECRET"),
        supplier_callback_tolerance_seconds=int(
            os.getenv("SUPPLIER_CALLBACK_TOLERANCE_SECONDS", "300")
        ),
        agent_max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "10")),
        agent_max_runtime_seconds=float(
            os.getenv("AGENT_MAX_RUNTIME_SECONDS", "30")
        ),
    )

