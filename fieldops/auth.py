"""Signed, database-revocable eight-hour demo sessions and CSRF boundaries."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from html import escape
from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import APIKeyCookie
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from fieldops.models import PersonaSession, User
from fieldops.schemas import Contract, ErrorResponse, PersonaResponse

router = APIRouter(
    tags=["demo sessions"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 500, 503)},
)
COOKIE = "fieldops_session"
LOGIN_CSRF = "fieldops_login_csrf"
cookie_scheme = APIKeyCookie(name=COOKIE, auto_error=False, scheme_name="PersonaSession")


class LoginRequest(Contract):
    persona_id: UUID
    operator_secret: SecretStr | None = None


class SessionResponse(Contract):
    persona: PersonaResponse
    csrf_token: str


class CSRFResponse(Contract):
    csrf_token: str


def key(request: Request) -> bytes:
    try:
        return request.app.state.settings.signing_key()
    except (ValueError, OSError):
        raise HTTPException(503, "session_configuration_unavailable") from None


def signature(request: Request, token: str) -> str:
    return hmac.new(key(request), token.encode(), hashlib.sha256).hexdigest()


def signed(request: Request, token: str) -> str:
    return token + "." + signature(request, token)


def verified(request: Request, value: str | None) -> str:
    if value is None or len(value) > 200:
        raise HTTPException(401, "unauthenticated")
    token, separator, mac = value.partition(".")
    if not separator or not hmac.compare_digest(signature(request, token).encode(), mac.encode()):
        raise HTTPException(401, "unauthenticated")
    return token


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_options(request: Request):
    # Hosted/nonlocal settings always require HTTPS; local HTTP is explicitly development-only.
    return dict(
        httponly=True,
        secure=request.app.state.settings.environment != "local" or request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def demo_enabled(request: Request):
    if not request.app.state.settings.demo_mode:
        raise HTTPException(404, "not_found")


def current_session(
    request: Request,
    session_cookie: Annotated[str | None, Security(cookie_scheme)] = None,
):
    token = verified(request, session_cookie)
    with Session(request.app.state.engine) as db:
        row = db.execute(
            select(PersonaSession, User)
            .join(User)
            .where(
                PersonaSession.token_digest == digest(token),
                PersonaSession.expires_at > func.now(),
                PersonaSession.created_at > func.now() - timedelta(hours=8),
                PersonaSession.revoked_at.is_(None),
                User.active.is_(True),
            )
        ).first()
        if row is None:
            raise HTTPException(401, "unauthenticated")
        return row


def current_user(session: Annotated[tuple, Depends(current_session)]) -> User:
    return session[1]


def check_csrf(request: Request, expected: str, supplied: str | None = None):
    value = supplied if supplied is not None else request.headers.get("X-CSRF-Token", "")
    if not value or not hmac.compare_digest(expected.encode(), value.encode()):
        raise HTTPException(403, "csrf_failed")


def require_csrf(request: Request, session: Annotated[tuple, Depends(current_session)]):
    check_csrf(request, session[0].csrf_token)
    return session[1]


@router.get("/auth/csrf", response_model=CSRFResponse, dependencies=[Depends(demo_enabled)])
def login_csrf(request: Request, response: Response):
    token = secrets.token_urlsafe(32)
    response.set_cookie(LOGIN_CSRF, signed(request, token), max_age=600, **cookie_options(request))
    return {"csrf_token": token}


@router.get(
    "/auth/personas", response_model=list[PersonaResponse], dependencies=[Depends(demo_enabled)]
)
def personas(request: Request):
    with Session(request.app.state.engine) as db:
        return list(
            db.scalars(
                select(User)
                .where(User.active.is_(True), User.role != "operator")
                .order_by(User.persona_key)
            )
        )


def activate(request: Request, response: Response, payload: LoginRequest, csrf: str | None = None):
    demo_enabled(request)
    try:
        expected = verified(request, request.cookies.get(LOGIN_CSRF))
    except HTTPException:
        raise HTTPException(403, "csrf_failed") from None
    check_csrf(request, expected, csrf)
    token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with Session(request.app.state.engine) as db, db.begin():
        user = db.get(User, payload.persona_id)
        if user is None or not user.active:
            raise HTTPException(403, "forbidden")
        if user.role == "operator":
            configured = request.app.state.settings.operator_secret
            supplied = payload.operator_secret
            if (
                configured is None
                or len(configured.get_secret_value()) < 32
                or supplied is None
                or not hmac.compare_digest(
                    configured.get_secret_value().encode(), supplied.get_secret_value().encode()
                )
            ):
                raise HTTPException(403, "forbidden")
        # Rotating identity revokes an existing valid session instead of leaving it active.
        old_cookie = request.cookies.get(COOKIE)
        if old_cookie:
            try:
                old = db.get(PersonaSession, digest(verified(request, old_cookie)))
            except HTTPException:
                old = None
            if old:
                old.revoked_at = func.now()
        db.add(
            PersonaSession(
                token_digest=digest(token),
                user_id=user.id,
                csrf_token=csrf_token,
                expires_at=func.now() + timedelta(hours=8),
            )
        )
        persona = PersonaResponse.model_validate(user)
    response.set_cookie(COOKIE, signed(request, token), max_age=28800, **cookie_options(request))
    response.delete_cookie(LOGIN_CSRF, **cookie_options(request))
    return SessionResponse(persona=persona, csrf_token=csrf_token)


@router.post("/auth/login", response_model=SessionResponse)
def login(request: Request, response: Response, payload: LoginRequest):
    return activate(request, response, payload)


@router.get("/auth/session", response_model=SessionResponse)
def session_info(session: Annotated[tuple, Depends(current_session)]):
    return SessionResponse(
        persona=PersonaResponse.model_validate(session[1]), csrf_token=session[0].csrf_token
    )


def revoke(request: Request, response: Response, session, csrf: str | None = None):
    check_csrf(request, session[0].csrf_token, csrf)
    with Session(request.app.state.engine) as db, db.begin():
        record = db.get(PersonaSession, session[0].token_digest)
        if record:
            record.revoked_at = func.now()
    response.delete_cookie(COOKIE, **cookie_options(request))


@router.post("/auth/logout", status_code=204)
def logout(request: Request, session: Annotated[tuple, Depends(current_session)]):
    response = Response(status_code=204)
    revoke(request, response, session)
    return response


async def form_fields(request: Request):
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(422, "validation_error")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(422, "validation_error")
    try:
        values = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=4)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "validation_error") from None
    if any(len(value) != 1 for value in values.values()):
        raise HTTPException(422, "validation_error")
    return {name: value[0] for name, value in values.items()}


@router.get("/session", response_class=HTMLResponse)
def html_session(session: Annotated[tuple, Depends(current_session)]):
    user = session[1]
    return HTMLResponse(
        "<p>" + escape(user.display_name) + '</p><form method="post" action="/session/logout">'
        '<input type="hidden" name="csrf_token" value="' + escape(session[0].csrf_token) + '">'
        "<button>Log out</button></form>"
    )


@router.post("/session/login", response_class=RedirectResponse, status_code=303)
async def html_login(request: Request):
    values = await form_fields(request)
    csrf = values.pop("csrf_token", "")
    response = RedirectResponse("/session", status_code=303)
    try:
        payload = LoginRequest.model_validate(values)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from None
    await run_in_threadpool(activate, request, response, payload, csrf)
    return response


@router.post("/session/logout", response_class=RedirectResponse, status_code=303)
async def html_logout(request: Request, session: Annotated[tuple, Depends(current_session)]):
    values = await form_fields(request)
    if set(values) != {"csrf_token"}:
        raise HTTPException(422, "validation_error")
    response = RedirectResponse("/session", status_code=303)
    await run_in_threadpool(revoke, request, response, session, values["csrf_token"])
    return response
