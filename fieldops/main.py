"""FastAPI foundation: process liveness and independent database readiness."""

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from fieldops.database import check_database, create_database_engine
from fieldops.logging import configure_logging
from fieldops.settings import Settings

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
        configure_logging(current_settings.environment, current_settings.log_level)
        app.state.engine = create_database_engine(current_settings)
        logger.info("application_started")
        try:
            yield
        finally:
            app.state.engine.dispose()
            logger.info("application_stopped")

    app = FastAPI(title="FieldOps", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_logging(request: Request, call_next: Callable):
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
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
        # Do not echo arbitrary exception detail, user input or query parameters.
        return error_response("http_error", "Request could not be processed", error.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception):
        logger.error("unexpected_error", extra={"error_type": type(error).__name__})
        return error_response("internal_error", "An unexpected error occurred", 500)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get(
        "/health/ready", tags=["health"], responses={503: {"description": "Database unavailable"}}
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
