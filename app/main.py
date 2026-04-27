from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.settings import Settings, get_settings
from workflows import load_default_playbook
from workflows.orchestrator import WorkflowOrchestrator
from workflows.storage import WorkflowStorage

PUBLIC_DEMO_GET_PREFIXES = ("/demo", "/static")
PUBLIC_DEMO_GET_PATHS = {"/", "/healthz", "/favicon.ico"}
READ_ONLY_METHODS = {"GET", "HEAD"}


async def _public_demo_guard(request: Request, call_next):
    settings: Settings = request.app.state.settings
    if not settings.public_demo_mode:
        return await call_next(request)

    path = request.url.path
    read_only_public_path = (
        path in PUBLIC_DEMO_GET_PATHS
        or any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in PUBLIC_DEMO_GET_PREFIXES
        )
    )
    if request.method in READ_ONLY_METHODS and read_only_public_path:
        return await call_next(request)

    return Response(status_code=404)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url=None if resolved_settings.public_demo_mode else "/docs",
        redoc_url=None if resolved_settings.public_demo_mode else "/redoc",
        openapi_url=None if resolved_settings.public_demo_mode else "/openapi.json",
    )
    app.state.settings = resolved_settings
    app.state.storage = WorkflowStorage(resolved_settings.database_path)
    app.state.playbook = load_default_playbook()
    app.state.orchestrator = WorkflowOrchestrator(app.state.storage, app.state.playbook)

    static_path = Path(__file__).resolve().parent / "static"
    template_path = Path(__file__).resolve().parent / "templates"
    template_path.mkdir(parents=True, exist_ok=True)
    static_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    app.middleware("http")(_public_demo_guard)
    app.include_router(router)
    return app


app = create_app()
