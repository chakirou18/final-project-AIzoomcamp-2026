"""FastAPI foundation: process liveness and independent database readiness."""

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError, SQLAlchemyError, TimeoutError
from starlette.exceptions import HTTPException

from fieldops.auth import router as auth_router
from fieldops.contracts import document_session_boundaries, lifecycle_openapi
from fieldops.database import check_database, create_database_engine
from fieldops.logging import configure_logging
from fieldops.policy import DomainError
from fieldops.routes.controls import router as control_router
from fieldops.routes.interventions import router as intervention_router
from fieldops.routes.notifications import router as notification_router
from fieldops.schemas import ErrorResponse
from fieldops.settings import Settings
from fieldops.web import router as web_router
from fieldops.web import web_error

logger = logging.getLogger("fieldops.http")


def error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "fields": {}}},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        current_settings = settings if settings is not None else Settings()
        app.state.settings = current_settings
        configure_logging(current_settings.environment, current_settings.log_level)
        app.state.engine = create_database_engine(current_settings)
        logger.info("application_started")
        try:
            yield
        finally:
            app.state.engine.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title="FieldOps",
        version="0.1.0",
        lifespan=lifespan,
        responses={500: {"model": ErrorResponse}},
    )
    app.include_router(auth_router)
    app.include_router(intervention_router)
    app.include_router(notification_router)
    app.include_router(control_router)
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/app/login", status_code=303)

    original_openapi = app.openapi

    def documented_openapi():
        schema = document_session_boundaries(original_openapi())
        contracts = lifecycle_openapi()
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                contract = contracts["paths"].get(path, {}).get(method)
                if contract:
                    operation["description"] = contract["description"]
        return schema

    app.openapi = documented_openapi

    @app.get("/contracts/openapi.json", tags=["contracts"])
    def draft_contracts():
        schema = lifecycle_openapi()
        schema["info"]["title"] = "FieldOps lifecycle contracts"
        schema["x-implementation-status"] = "T04 lifecycle and T06 JSON inbox implemented"
        for operations in schema["paths"].values():
            for operation in operations.values():
                operation["x-implemented"] = True
        schema["info"]["description"] = (
            "Lifecycle and JSON inbox routes implemented; HTML workspace available at /app/login."
        )
        return schema

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, error: DomainError):
        if request.url.path.startswith("/app/"):
            return web_error(request, error.status_code, error.message)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "fields": error.fields,
                }
            },
        )

    @app.exception_handler(OperationalError)
    @app.exception_handler(TimeoutError)
    async def handle_database_error(request: Request, error):
        logger.warning("database_unavailable", extra={"error_type": type(error).__name__})
        if request.url.path.startswith("/app/"):
            return web_error(request, 503, "Database unavailable. Please try again shortly.")
        return error_response("database_unavailable", "Database operation unavailable", 503)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error):
        if request.url.path.startswith("/app/"):
            return web_error(request, 422, "Invalid request fields. Check the form and try again.")
        # Never echo invalid values, secrets or Pydantic exception context.
        fields = {}
        for item in error.errors():
            name = ".".join(str(part) for part in item["loc"])
            fields.setdefault(name, []).append("Invalid value")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request fields",
                    "fields": fields,
                }
            },
        )

    @app.middleware("http")
    async def request_logging(request: Request, call_next: Callable):
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            if request.url.path.startswith(
                ("/auth/", "/session", "/api/", "/app/", "/internal/", "/demo/")
            ):
                response.headers["Cache-Control"] = "no-store"
                response.headers["Vary"] = "Cookie"
            if request.url.path.startswith("/app/"):
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; "
                    "form-action 'self'; object-src 'none'"
                )
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["Referrer-Policy"] = "same-origin"
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "route": getattr(route, "path", "<unmatched>"),
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, error: HTTPException):
        if request.url.path.startswith("/app/"):
            messages = {
                401: "Your session is missing or expired. Choose a demo identity to continue.",
                403: "This action is not permitted. Check your identity and form token.",
                404: "This page or intervention is unavailable.",
                422: "Invalid request fields. Check the form and try again.",
            }
            return web_error(
                request,
                error.status_code,
                messages.get(error.status_code, "Request could not be processed."),
            )
        # Do not echo arbitrary exception detail, user input or query parameters.
        codes = {
            "unauthenticated",
            "forbidden",
            "csrf_failed",
            "not_found",
            "validation_error",
            "session_configuration_unavailable",
        }
        code = (
            error.detail
            if isinstance(error.detail, str) and error.detail in codes
            else "http_error"
        )
        return error_response(code, "Request could not be processed", error.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception):
        logger.error("unexpected_error", extra={"error_type": type(error).__name__})
        if request.url.path.startswith("/app/"):
            return web_error(request, 500, "An unexpected error occurred. Please try again.")
        return error_response("internal_error", "An unexpected error occurred", 500)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get(
        "/health/ready",
        tags=["health"],
        responses={503: {"description": "Database unavailable", "model": ErrorResponse}},
    )
    def ready(request: Request):
        try:
            check_database(request.app.state.engine)
        except SQLAlchemyError as error:
            logger.warning("database_unavailable", extra={"error_type": type(error).__name__})
            return error_response("database_unavailable", "Service is not ready", 503)
        return {"status": "ready"}

    return app


app = create_app()
