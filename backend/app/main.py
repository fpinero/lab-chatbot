from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.config import Settings
from app.providers.mock import MockProvider, PreviewProvider, PreviewResult


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class BootstrapInfo(BaseModel):
    environment: str
    provider_mode: str
    simulated: bool = True


class PreviewRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None, static_dir: Path | None = None) -> FastAPI:
    config = settings or Settings()
    app = FastAPI(title="Lab chatbot", docs_url=None, redoc_url=None, openapi_url=None)
    provider: PreviewProvider = MockProvider()

    @app.middleware("http")
    async def request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", ""),
                    "retryable": False,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(
            request,
            exc.status_code,
            "not_found" if exc.status_code == 404 else "request_rejected",
            "Resource not found." if exc.status_code == 404 else "Request rejected.",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, 422, "invalid_request", "Check the request fields.")

    @app.get("/api/health/live", response_model=Health)
    @app.get("/api/health/ready", response_model=Health)
    async def health() -> Health:
        return Health()

    @app.get("/api/dev/bootstrap", response_model=BootstrapInfo)
    async def bootstrap() -> BootstrapInfo:
        return BootstrapInfo(environment=config.app_env, provider_mode=config.provider_mode)

    @app.post("/api/dev/preview", response_model=PreviewResult)
    async def preview(body: PreviewRequest) -> PreviewResult:
        return await provider.preview(body.prompt)

    # API routing must remain ahead of the SPA fallback, including unknown API paths.
    @app.api_route(
        "/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"], include_in_schema=False
    )
    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
        include_in_schema=False,
    )
    async def unknown_api(path: str = "") -> None:
        raise HTTPException(status_code=404)

    root = (static_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if not (root / "index.html").is_file():
            raise HTTPException(status_code=404)
        return FileResponse(root / "index.html")

    return app


app = create_app()
