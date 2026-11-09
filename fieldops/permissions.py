"""Deny-by-default persona scope helpers shared by future HTML/JSON services."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select

from fieldops.models import Intervention, Notification, User


def require_role(user: User, *roles: str) -> None:
    if not user.active or user.role not in roles:
        raise HTTPException(403, "forbidden")


def intervention_scope(statement: Select, user: User) -> Select:
    require_role(user, "dispatcher", "technician")
    if user.role == "technician":
        statement = statement.where(Intervention.technician_id == user.id)
    return statement


def inbox_scope(statement: Select, user: User) -> Select:
    require_role(user, "technician")
    return statement.where(Notification.recipient_id == user.id)


def require_intervention_access(user: User, technician_id: UUID | None) -> None:
    require_role(user, "dispatcher", "technician")
    if user.role == "technician" and technician_id != user.id:
        raise HTTPException(403, "forbidden")
