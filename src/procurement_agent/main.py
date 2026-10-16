"""ASGI entry point: uvicorn procurement_agent.main:app --reload."""

from .api.app import app, create_app

__all__ = ["app", "create_app"]

