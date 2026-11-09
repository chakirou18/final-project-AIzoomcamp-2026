"""Executable contract validation without a database or business endpoints."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from fieldops.contracts import lifecycle_openapi
from fieldops.main import create_app
from fieldops.schemas import (
    Assignment,
    InterventionCreate,
    InterventionEdit,
    Pagination,
    Transition,
)
from fieldops.seed import persona_id


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "site": "x"},
        {"title": " ", "site": "x"},
        {"title": "x" * 161, "site": "x"},
        {"title": "x", "site": " "},
        {"title": "x", "site": "x" * 251},
        {"title": "x", "site": "x", "priority": "critical"},
        {"title": "x", "site": "x", "description": "x" * 4001},
        {"title": "x", "site": "x", "status": "completed"},
        {"title": "x", "site": "x", "technician_id": "bad-uuid"},
    ],
)
def test_invalid_create(payload):
    with pytest.raises(ValidationError):
        InterventionCreate.model_validate(payload)


def test_create_defaults_and_normalization():
    value = InterventionCreate(title=" Synthetic ", site=" Site ")
    assert (value.title, value.site, value.priority, value.description) == (
        "Synthetic",
        "Site",
        "medium",
        "",
    )
    assert value.technician_id is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"expected_version": 0, "title": "x"},
        {"expected_version": True, "title": "x"},
        {"expected_version": "1", "title": "x"},
        {"expected_version": 1},
        {"expected_version": 1, "title": None},
        {"expected_version": 1, "technician_id": str(uuid4())},
    ],
)
def test_edit_rejects_invalid_or_server_owned_fields(payload):
    with pytest.raises(ValidationError):
        InterventionEdit.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"target_status": "completed", "expected_version": 1},
        {"target_status": "completed", "expected_version": 1, "resolution": " "},
        {"target_status": "open", "expected_version": 1},
        {"target_status": "assigned", "expected_version": 1},
        {"target_status": "in_progress", "expected_version": 1, "resolution": "x"},
    ],
)
def test_transition_contract(payload):
    with pytest.raises(ValidationError):
        Transition.model_validate(payload)


def test_valid_commands():
    assert Assignment(technician_id=uuid4(), expected_version=1).expected_version == 1
    assert InterventionEdit(expected_version=1, description="").description == ""
    assert (
        Transition(target_status="completed", expected_version=2, resolution="Fixed").resolution
        == "Fixed"
    )


@pytest.mark.parametrize("payload", [{"page": 0}, {"page_size": 0}, {"page_size": 101}])
def test_pagination_bounds(payload):
    with pytest.raises(ValidationError):
        Pagination.model_validate(payload)


def test_openapi_has_versions_errors_security_and_no_live_workflows():
    document = lifecycle_openapi()
    assert document["x-implementation-status"] == "contracts-only"
    create = document["paths"]["/api/v1/interventions"]["post"]
    assert "201" in create["responses"]
    for path in document["paths"].values():
        for method, operation in path.items():
            assert not operation["x-implemented"]
            assert {"401", "403", "404", "409", "422", "503"} <= operation["responses"].keys()
            if method in {"post", "patch"}:
                assert operation["security"] == [{"PersonaSession": [], "CSRFToken": []}]
    assert not any(
        path.startswith("/api/v1/interventions") for path in create_app().openapi()["paths"]
    )
    schemas = document["components"]["schemas"]
    assert "expected_version" in schemas["Assignment"]["required"]
    assert schemas["InterventionCreate"]["additionalProperties"] is False
    assert persona_id("demo-manager") != persona_id("demo-technician-a")


def test_nonlocal_seed_requires_explicit_opt_in():
    from fieldops.bootstrap import seed
    from fieldops.settings import Settings

    value = Settings(environment="production", db_password="synthetic-only", db_password_file=None)
    with pytest.raises(ValueError, match="explicit"):
        seed(value)


def test_nonlocal_all_does_not_seed(monkeypatch):
    from unittest.mock import Mock

    from fieldops import bootstrap
    from fieldops.settings import Settings

    value = Settings(environment="production", db_password="synthetic-only", db_password_file=None)
    migrate = Mock()
    seed = Mock()
    monkeypatch.setattr(bootstrap, "Settings", lambda: value)
    monkeypatch.setattr(bootstrap, "migrate", migrate)
    monkeypatch.setattr(bootstrap, "seed", seed)
    monkeypatch.setattr("sys.argv", ["bootstrap", "all"])
    bootstrap.main()
    migrate.assert_called_once_with(value)
    seed.assert_not_called()
