"""Synthetic persona seed; IDs are stable public identifiers, never credentials."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldops.models import User

PERSONAS = (
    ("demo-manager", "Synthetic Dispatcher", "dispatcher"),
    ("demo-technician-a", "Synthetic Technician A", "technician"),
    ("demo-technician-b", "Synthetic Technician B", "technician"),
    ("demo-operator", "Synthetic Operator", "operator"),
)


def persona_id(key: str):
    return uuid5(NAMESPACE_URL, "https://fieldops.invalid/personas/" + key)


def seed_personas(session: Session) -> None:
    # Never reactivate or overwrite an identity changed by an administrator.
    for key, name, role in PERSONAS:
        session.execute(
            insert(User)
            .values(
                id=persona_id(key),
                persona_key=key,
                display_name=name,
                role=role,
                active=True,
            )
            .on_conflict_do_nothing(index_elements=["persona_key"])
        )
