from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.settings import Settings, get_settings
from workflows import load_default_playbook
from workflows.orchestrator import WorkflowOrchestrator
from workflows.storage import WorkflowStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title=resolved_settings.app_name, version=resolved_settings.app_version)
    app.state.settings = resolved_settings
    app.state.storage = WorkflowStorage(resolved_settings.database_path)
    app.state.playbook = load_default_playbook()
    app.state.orchestrator = WorkflowOrchestrator(app.state.storage, app.state.playbook)

    static_path = Path(__file__).resolve().parent / "static"
    template_path = Path(__file__).resolve().parent / "templates"
    template_path.mkdir(parents=True, exist_ok=True)
    static_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    app.include_router(router)
    return app


app = create_app()
