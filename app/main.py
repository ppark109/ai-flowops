from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from app.routes import router
from app.settings import Settings, get_settings
from workflows.orchestrator import WorkflowOrchestrator


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
    )
    app.state.settings = resolved_settings
    app.state.orchestrator = WorkflowOrchestrator(resolved_settings.database_file)
    app.state.templates = Jinja2Templates(directory=Path("app/templates"))
    app.mount("/static", StaticFiles(directory=Path("app/static"), html=True), name="static")

    app.include_router(router)

    @app.on_event("shutdown")
    def _close() -> None:
        app.state.orchestrator.close()

    return app


app = create_app()
