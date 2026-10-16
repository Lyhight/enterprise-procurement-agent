"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..core.logging import configure_logging
from ..core.auth import BearerTokenAuth
from ..core.config import Settings
from .dependencies import auth_service, settings
from .middleware.authentication import AuthenticationMiddleware
from .middleware.request_context import RequestContextMiddleware

from .routers import (
    agent_assist,
    agent_sessions,
    audit,
    conversations,
    dashboard,
    health,
    intake,
    integrations,
    knowledge,
    orders,
    quotations,
    requests,
    runs,
    supplier_delivery,
    system,
)


def create_app(
    settings_override: Settings | None = None,
    auth_service_override: BearerTokenAuth | None = None,
) -> FastAPI:
    app_settings = settings_override or settings
    app_auth_service = auth_service_override or auth_service
    configure_logging(app_settings.log_level)
    application = FastAPI(
        title="Enterprise Procurement Intelligence Agent",
        version=__version__,
        description="企业采购需求、询价比价、合规审批与审计 API",
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        AuthenticationMiddleware,
        settings=app_settings,
        auth_service=app_auth_service,
    )
    if app_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(app_settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    application.include_router(health.router)
    application.include_router(knowledge.router)
    application.include_router(intake.router)
    application.include_router(conversations.router)
    application.include_router(requests.router)
    application.include_router(quotations.router)
    application.include_router(runs.router)
    application.include_router(agent_assist.router)
    application.include_router(agent_sessions.router)
    application.include_router(supplier_delivery.router)
    application.include_router(integrations.router)
    application.include_router(orders.router)
    application.include_router(dashboard.router)
    application.include_router(system.router)
    application.include_router(audit.router)
    frontend_dist = app_settings.project_root / "frontend" / "dist"
    if frontend_dist.is_dir():
        application.mount(
            "/app",
            StaticFiles(directory=frontend_dist, html=True),
            name="procurement-console",
        )

        @application.get("/", include_in_schema=False)
        def frontend_redirect() -> RedirectResponse:
            return RedirectResponse(url="/app/")
    return application


app = create_app()

