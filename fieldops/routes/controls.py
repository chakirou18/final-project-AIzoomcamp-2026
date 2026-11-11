"""Separate operator session and internal bearer authority; only fixed worker operations."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fieldops.auth import current_user, fault_simulation_enabled, require_csrf
from fieldops.control_schemas import (
    Dashboard,
    PauseRequest,
    ResumeRequest,
    ResumeResult,
    WorkerStatus,
)
from fieldops.models import User
from fieldops.schemas import ErrorResponse
from fieldops.services.controls import ControlService

router = APIRouter(
    tags=["operational controls"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 503)},
)
bearer = HTTPBearer(auto_error=False, scheme_name="RecoveryBearer")
Reader = Annotated[User, Depends(current_user)]
Writer = Annotated[User, Depends(require_csrf)]


def internal(
    request: Request, value: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)]
):
    configured = request.app.state.settings.recovery_secret
    expected = configured.get_secret_value() if configured else ""
    supplied = value.credentials if value else ""
    if len(expected) >= 32 and hmac.compare_digest(expected.encode(), supplied.encode()):
        return
    agent_secret = request.app.state.settings.oncall_secret
    agent_key = agent_secret.get_secret_value() if agent_secret else ""
    if len(agent_key) >= 32 and hmac.compare_digest(agent_key.encode(), supplied.encode()):
        request.state.oncall_agent_authenticated = True
        return
    raise HTTPException(401, "unauthenticated")


@router.get(
    "/api/v1/dashboard",
    response_model=Dashboard,
    description=(
        "Operator only; real PostgreSQL counts. Worker heartbeat is separate from API readiness."
    ),
)
def dashboard(request: Request, actor: Reader):
    return ControlService(request.app.state.engine).dashboard(actor.id)


@router.post(
    "/demo/worker/pause",
    response_model=WorkerStatus,
    dependencies=[Depends(fault_simulation_enabled)],
    description=(
        "Demo-only operator + CSRF. "
        "Acknowledges the committed gate after active transactions finish."
    ),
)
def pause(request: Request, command: PauseRequest, actor: Writer):
    return ControlService(request.app.state.engine).pause(actor.id, command)


@router.get(
    "/internal/worker/status",
    response_model=WorkerStatus,
    dependencies=[Depends(internal)],
    description="Recovery bearer only. No cookie, operator or webhook credential authority.",
)
def status(request: Request):
    return ControlService(request.app.state.engine).status()


@router.post(
    "/internal/worker/resume",
    response_model=ResumeResult,
    dependencies=[Depends(internal)],
    responses={409: {"model": ResumeResult | ErrorResponse}},
    description=(
        "One fixed action. Durable key binds incident and generation; "
        "replay returns the recorded result. No incident diagnosis is implemented."
    ),
)
def resume(request: Request, command: ResumeRequest):
    settings = request.app.state.settings
    result = ControlService(request.app.state.engine).resume(
        command,
        (
            settings.environment,
            settings.demo_mode,
            request.headers.get("x-fieldops-authorization", ""),
            getattr(request.state, "oncall_agent_authenticated", False),
        ),
    )
    return JSONResponse(
        status_code=200 if result.success else 409, content=result.model_dump(mode="json")
    )
