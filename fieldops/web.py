"""Server-rendered adapters; domain services own authorization and transactions."""

import secrets
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from fieldops.auth import (
    LOGIN_CSRF,
    LoginRequest,
    activate,
    check_csrf,
    cookie_options,
    current_session,
    demo_enabled,
    personas,
    revoke,
    signed,
)
from fieldops.control_schemas import PauseRequest
from fieldops.policy import DomainError
from fieldops.schemas import (
    Assignment,
    InterventionCreate,
    InterventionEdit,
    InterventionFilters,
    Pagination,
    Priority,
    Status,
    Transition,
)
from fieldops.seed import persona_id
from fieldops.services.controls import ControlService
from fieldops.services.interventions import InterventionService
from fieldops.services.notifications import InboxService

router = APIRouter(prefix="/app", include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
Identity = Annotated[tuple, Depends(current_session)]


def render(request, template, session=None, status_code=200, **context):
    return templates.TemplateResponse(
        request=request,
        name=template + ".html",
        context={
            "user": session[1] if session else None,
            "csrf": session[0].csrf_token if session else "",
            "priorities": list(Priority),
            "statuses": list(Status),
            "errors": {},
            "values": {},
            "status_code": status_code,
            **context,
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Vary": "Cookie"},
    )


def web_error(request, status, message):
    return render(request, "error", status_code=status, message=message, standalone_error=True)


def redirect(path):
    return RedirectResponse(path, status_code=303)


async def fields(request):
    if request.headers.get("content-type", "").split(";")[0] != (
        "application/x-www-form-urlencoded"
    ):
        raise HTTPException(422, "validation_error")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(422, "validation_error")
    try:
        data = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=12)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "validation_error") from None
    if any(len(value) != 1 for value in data.values()):
        raise HTTPException(422, "validation_error")
    return {key: value[0] for key, value in data.items()}


def payload(model, data):
    data = dict(data)
    for name in ("expected_version", "expected_generation", "duration_seconds"):
        if name not in data:
            continue
        # HTML controls submit strings; the shared contract still checks the integer range.
        value = data[name]
        if not value.isascii() or not value.isdecimal() or len(value) > 18:
            raise DomainError(422, "validation_error", "Invalid version; reload this page")
        data[name] = int(value)
    if model is InterventionCreate and data.get("technician_id") == "":
        data.pop("technician_id")
    return model.model_validate(data)


def feedback(error):
    if isinstance(error, DomainError):
        return error.status_code, error.message, error.fields
    errors = {}
    hints = {
        "title": "Enter a title between 1 and 160 characters.",
        "site": "Enter a site between 1 and 250 characters.",
        "description": "Description must not exceed 4000 characters.",
        "priority": "Choose low, medium, high or urgent.",
        "technician_id": "Choose an active technician from the list.",
        "resolution": "Completion requires a nonblank resolution, up to 4000 characters.",
        "expected_version": "Invalid version. Reload the latest page before retrying.",
    }
    for item in error.errors():
        name = str(item["loc"][0]) if item["loc"] else "form"
        if name == "form" and error.title == "Transition":
            name = "resolution"
        errors.setdefault(name, []).append(hints.get(name, "Invalid or unexpected form field."))
    return 422, "Please correct the highlighted fields.", errors


@router.get("/login")
def login_page(request: Request):
    demo_enabled(request)
    token = secrets.token_urlsafe(32)
    response = render(request, "login", people=personas(request), login_csrf=token)
    response.set_cookie(LOGIN_CSRF, signed(request, token), max_age=600, **cookie_options(request))
    return response


@router.post("/login")
async def login(request: Request):
    data = await fields(request)
    csrf = data.pop("csrf_token", "")
    try:
        command = LoginRequest.model_validate(data)
    except ValidationError:
        raise HTTPException(422, "validation_error") from None
    response = redirect("/app/interventions")
    await run_in_threadpool(activate, request, response, command, csrf)
    return response


@router.post("/logout")
async def logout(request: Request, session: Identity):
    data = await fields(request)
    if set(data) != {"csrf_token"}:
        raise HTTPException(422, "validation_error")
    response = redirect("/app/login")
    await run_in_threadpool(revoke, request, response, session, data["csrf_token"])
    return response


def query(request, model):
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, "validation_error")
    try:
        return model.model_validate({k: v for k, v in request.query_params.items() if v != ""})
    except ValidationError:
        raise HTTPException(422, "validation_error") from None


def paging(request, page):
    def link(number):
        values = dict(request.query_params)
        values["page"] = number
        return request.url.path + "?" + urlencode(values)

    return {
        "first": link(1),
        "previous": link(page.page - 1) if page.page > 1 else None,
        "next": link(page.page + 1) if page.page * page.page_size < page.total else None,
    }


@router.get("/interventions")
def listing(request: Request, session: Identity):
    domain = InterventionService(request.app.state.engine)
    filters = query(request, InterventionFilters)
    page = domain.list(session[1].id, filters)
    technicians = domain.list_technicians(session[1].id) if session[1].role == "dispatcher" else []
    return render(
        request,
        "list",
        session,
        page=page,
        technicians=technicians,
        filters=filters,
        **paging(request, page),
    )


@router.get("/interventions/new")
def new(request: Request, session: Identity):
    technicians = InterventionService(request.app.state.engine).list_technicians(session[1].id)
    return render(request, "form", session, technicians=technicians, job=None)


def form_page(request, session, identifier=None, values=None, error=None):
    domain = InterventionService(request.app.state.engine)
    technicians = domain.list_technicians(session[1].id)
    job = domain.detail(session[1].id, identifier) if identifier else None
    status, message, errors = feedback(error) if error else (200, None, {})
    return render(
        request,
        "form",
        session,
        status_code=status,
        job=job,
        technicians=technicians,
        values=values if values is not None else (job.model_dump() if job else {}),
        message=message,
        errors=errors,
    )


@router.get("/interventions/{identifier}/edit")
def edit_page(identifier: UUID, request: Request, session: Identity):
    return form_page(request, session, identifier)


@router.post("/interventions/new")
async def create(request: Request, session: Identity):
    data = await fields(request)
    check_csrf(request, session[0].csrf_token, data.pop("csrf_token", ""))
    domain = InterventionService(request.app.state.engine)
    try:
        command = payload(InterventionCreate, data)
        job = await run_in_threadpool(domain.create, session[1].id, command)
    except (ValidationError, DomainError) as error:
        return await run_in_threadpool(form_page, request, session, None, data, error)
    return redirect(f"/app/interventions/{job.id}?notice=created")


@router.post("/interventions/{identifier}/edit")
async def edit(identifier: UUID, request: Request, session: Identity):
    data = await fields(request)
    check_csrf(request, session[0].csrf_token, data.pop("csrf_token", ""))
    domain = InterventionService(request.app.state.engine)
    try:
        command = payload(InterventionEdit, data)
        job = await run_in_threadpool(domain.edit, session[1].id, identifier, command)
    except (ValidationError, DomainError) as error:
        return await run_in_threadpool(form_page, request, session, identifier, data, error)
    return redirect(f"/app/interventions/{job.id}?notice=updated")


def detail_page(request, session, identifier, error=None, values=None):
    domain = InterventionService(request.app.state.engine)
    job = domain.detail(session[1].id, identifier)
    try:
        history_page = Pagination.model_validate(
            {
                key: request.query_params[key]
                for key in ("page", "page_size")
                if key in request.query_params
            }
        )
    except ValidationError:
        raise HTTPException(422, "validation_error") from None
    history = domain.list_history(session[1].id, identifier, history_page)
    technicians = domain.list_technicians(session[1].id) if session[1].role == "dispatcher" else []
    status, message, errors = feedback(error) if error else (200, None, {})
    notices = {"created": "Intervention created.", "updated": "Changes saved."}
    return render(
        request,
        "detail",
        session,
        status_code=status,
        job=job,
        history=history,
        technicians=technicians,
        message=message,
        errors=errors,
        notice=notices.get(request.query_params.get("notice")),
        reload_url=f"/app/interventions/{identifier}",
        values=values or {},
        **paging(request, history),
    )


@router.get("/interventions/{identifier}")
def detail(identifier: UUID, request: Request, session: Identity):
    return detail_page(request, session, identifier)


@router.post("/interventions/{identifier}/{action}")
async def command(identifier: UUID, action: str, request: Request, session: Identity):
    data = await fields(request)
    check_csrf(request, session[0].csrf_token, data.pop("csrf_token", ""))
    domain = InterventionService(request.app.state.engine)
    if action not in {"assignment", "transition"}:
        raise HTTPException(404, "not_found")
    try:
        model = Assignment if action == "assignment" else Transition
        operation = domain.assign if action == "assignment" else domain.transition
        await run_in_threadpool(operation, session[1].id, identifier, payload(model, data))
    except (ValidationError, DomainError) as error:
        return await run_in_threadpool(detail_page, request, session, identifier, error, data)
    return redirect(f"/app/interventions/{identifier}?notice=updated")


@router.get("/inbox")
def inbox(request: Request, session: Identity):
    page = InboxService(request.app.state.engine).list(session[1].id, query(request, Pagination))
    return render(request, "inbox", session, page=page, **paging(request, page))


@router.post("/inbox/{identifier}/read")
async def read(identifier: UUID, request: Request, session: Identity):
    data = await fields(request)
    check_csrf(request, session[0].csrf_token, data.pop("csrf_token", ""))
    if data:
        raise HTTPException(422, "validation_error")
    await run_in_threadpool(
        InboxService(request.app.state.engine).mark_read, session[1].id, identifier
    )
    return redirect("/app/inbox")


@router.get("/operator")
def operator_login_page(request: Request):
    demo_enabled(request)
    token = secrets.token_urlsafe(32)
    response = render(request, "operator", login_csrf=token)
    response.set_cookie(LOGIN_CSRF, signed(request, token), max_age=600, **cookie_options(request))
    return response


@router.post("/operator/login")
async def operator_login(request: Request):
    data = await fields(request)
    csrf = data.pop("csrf_token", "")
    if set(data) != {"operator_secret"}:
        raise HTTPException(422, "validation_error")
    command = LoginRequest(persona_id=persona_id("demo-operator"), **data)
    response = redirect("/app/dashboard")
    await run_in_threadpool(activate, request, response, command, csrf)
    return response


@router.get("/dashboard")
def dashboard_page(request: Request, session: Identity):
    data = ControlService(request.app.state.engine).dashboard(session[1].id)
    return render(
        request, "dashboard", session, data=data, demo_mode=request.app.state.settings.demo_mode
    )


@router.post("/worker/pause")
async def pause_worker(request: Request, session: Identity):
    demo_enabled(request)
    data = await fields(request)
    check_csrf(request, session[0].csrf_token, data.pop("csrf_token", ""))
    try:
        command = payload(PauseRequest, data)
    except ValidationError:
        raise HTTPException(422, "validation_error") from None
    await run_in_threadpool(ControlService(request.app.state.engine).pause, session[1].id, command)
    return redirect("/app/dashboard")
