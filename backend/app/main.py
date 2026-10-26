import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint

from app.api.attachments import router as attachment_router
from app.api.chat import router as chat_router
from app.api.comparisons import router as comparison_router
from app.auth.service import AuthError, AuthService
from app.body_limit import BodyLimitMiddleware
from app.config import Settings
from app.db import create_database, migrate
from app.models import OwnerSession
from app.providers.chat import ChatProvider, MockChat, OpenRouter
from app.providers.mock import MockProvider, PreviewProvider, PreviewResult
from app.services.attachments import AttachmentService
from app.services.catalog import CatalogService
from app.services.comparisons import ComparisonService
from app.services.runs import RunService


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class LoginInfo(BaseModel):
    auth_mode: str
    requires_code: bool
    environment: str
    provider_mode: str


class LoginRequest(BaseModel):
    password: SecretStr = Field(default=SecretStr(""), max_length=1024)
    code: SecretStr = Field(default=SecretStr(""), max_length=128)


class SessionInfo(BaseModel):
    owner_id: str
    csrf_token: str
    expires_at: int
    environment: str
    provider_mode: str


class BootstrapInfo(BaseModel):
    environment: str
    provider_mode: str
    simulated: bool = True


class PreviewRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


def create_app(
    settings: Settings | None = None,
    static_dir: Path | None = None,
    clock: Callable[[], datetime] | None = None,
    chat_provider: ChatProvider | None = None,
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database(config)
        try:
            migrate(engine)
            app.state.auth = AuthService(engine, config, clock or (lambda: datetime.now(UTC)))
            selected = chat_provider or (
                MockChat() if config.provider_mode == "mock" else OpenRouter(config)
            )

            def now() -> int:
                return int((clock() if clock else datetime.now(UTC)).timestamp())

            app.state.catalog = CatalogService(engine, config, selected, now)
            app.state.attachments = AttachmentService(engine, config, now)
            app.state.attachments.collect()
            app.state.runs = RunService(
                engine, config, selected, app.state.catalog, now, app.state.attachments
            )
            app.state.comparisons = ComparisonService(app.state.runs)
            await app.state.runs.recover()

            async def maintain_attachments() -> None:
                while True:
                    await asyncio.sleep(3600)
                    try:
                        await asyncio.to_thread(app.state.attachments.collect)
                    except Exception:
                        logging.getLogger(__name__).warning("attachment_maintenance_failed")

            maintenance = asyncio.create_task(maintain_attachments())
            try:
                yield
            finally:
                maintenance.cancel()
                await asyncio.gather(maintenance, return_exceptions=True)
                await app.state.runs.stop()
        finally:
            engine.dispose()

    app = FastAPI(
        title="Lab chatbot",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        responses={
            status: {"model": ErrorEnvelope}
            for status in [401, 402, 403, 404, 409, 410, 413, 422, 429, 500, 503]
        },
    )
    provider: PreviewProvider = MockProvider()

    def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
        response = JSONResponse(
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
        if status == 429:
            response.headers["Retry-After"] = "300"
        return response

    app.add_middleware(BodyLimitMiddleware, upload_maximum=config.max_upload_total_bytes + 262144)

    @app.middleware("http")
    async def protection(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid4().hex
        try:
            path = request.url.path
            if path == "/api" or path.startswith("/api/"):
                auth: AuthService = app.state.auth
                if path == "/api/auth/login":
                    await run_in_threadpool(auth.verify_access, request)
                    auth.check_origin(request, required=request.method == "POST")
                elif path not in {"/api/health/live", "/api/health/ready"}:
                    request.state.owner_session = await run_in_threadpool(
                        auth.authenticate, request
                    )
            response = await call_next(request)
        except AuthError as exc:
            response = error(request, exc.status, exc.code, exc.message)
        except Exception:
            response = error(request, 500, "internal_error", "The request could not be completed.")
        response.headers.update(
            {
                "X-Request-ID": request.state.request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; "
                    "style-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'"
                ),
            }
        )
        if config.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
        return error(request, exc.status, exc.code, exc.message)

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

    def session_info(session: OwnerSession) -> SessionInfo:
        return SessionInfo(
            owner_id=session.owner_id,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
            environment=config.app_env,
            provider_mode=config.provider_mode,
        )

    @app.get("/api/health/live", response_model=Health)
    def live() -> Health:
        return Health()

    @app.get("/api/health/ready", response_model=Health)
    def ready(request: Request) -> Health:
        auth: AuthService = request.app.state.auth
        if not auth.ready():
            raise HTTPException(status_code=503)
        return Health()

    @app.get("/api/auth/login", response_model=LoginInfo)
    def login_info() -> LoginInfo:
        return LoginInfo(
            auth_mode=config.auth_mode,
            requires_code=config.auth_policy_file is not None,
            environment=config.app_env,
            provider_mode=config.provider_mode,
        )

    @app.post("/api/auth/login", response_model=SessionInfo)
    def login(body: LoginRequest, request: Request, response: Response) -> SessionInfo:
        auth: AuthService = request.app.state.auth
        token, session = auth.login(
            request, body.password.get_secret_value(), body.code.get_secret_value()
        )
        response.set_cookie(
            config.cookie_name,
            token,
            httponly=True,
            secure=config.production,
            samesite="lax",
            path="/",
            max_age=config.session_absolute_seconds,
        )
        return session_info(session)

    @app.get("/api/auth/session", response_model=SessionInfo)
    def current_session(request: Request) -> SessionInfo:
        return session_info(request.state.owner_session)

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request) -> Response:
        auth: AuthService = request.app.state.auth
        auth.logout(request.state.owner_session)
        response = Response(status_code=204)
        response.delete_cookie(
            config.cookie_name, path="/", secure=config.production, httponly=True, samesite="lax"
        )
        return response

    if not config.production and config.provider_mode == "mock":

        @app.get("/api/dev/bootstrap", response_model=BootstrapInfo)
        def bootstrap() -> BootstrapInfo:
            return BootstrapInfo(environment=config.app_env, provider_mode=config.provider_mode)

        @app.post("/api/dev/preview", response_model=PreviewResult)
        async def preview(body: PreviewRequest) -> PreviewResult:
            return await provider.preview(body.prompt)

    app.include_router(chat_router)
    app.include_router(attachment_router)
    app.include_router(comparison_router)

    @app.api_route(
        "/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"], include_in_schema=False
    )
    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
        include_in_schema=False,
    )
    def unknown_api(path: str = "") -> None:
        raise HTTPException(status_code=404)

    root = (static_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
    for private_path in [
        config.data_dir,
        config.auth_policy_file,
        config.auth_password_hash_file,
        config.openrouter_api_key_file,
    ]:
        if private_path and private_path.resolve().is_relative_to(root):
            raise ValueError("Private runtime paths must remain outside compiled static assets.")
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if not (root / "index.html").is_file():
            raise HTTPException(status_code=404)
        return FileResponse(root / "index.html")

    return app
