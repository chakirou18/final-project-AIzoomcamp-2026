"""T03 audit: reject whitespace-only required text in PostgreSQL.

Keep 0001_t03 unchanged for existing local databases. Never rewrite invalid data;
constraint validation fails closed and requires an explicit repair decision.
"""

from alembic import op

revision = "0002_t03_review"
down_revision = "0001_t03"
branch_labels = None
depends_on = None

RULES = (
    (
        "users",
        "ck_user_name",
        "display_name ~ '[^[:space:]]'",
        "length(trim(display_name)) BETWEEN 1 AND 120",
    ),
    (
        "interventions",
        "ck_intervention_title",
        "title ~ '[^[:space:]]'",
        "length(trim(title)) BETWEEN 1 AND 160",
    ),
    (
        "interventions",
        "ck_intervention_site",
        "site ~ '[^[:space:]]'",
        "length(trim(site)) BETWEEN 1 AND 250",
    ),
    (
        "interventions",
        "ck_intervention_completion",
        "status <> 'completed' OR (resolution IS NOT NULL AND resolution ~ '[^[:space:]]')",
        "status <> 'completed' OR (resolution IS NOT NULL AND length(trim(resolution)) > 0)",
    ),
)


def upgrade():
    for table, name, corrected, _original in RULES:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, corrected)


def downgrade():
    for table, name, _corrected, original in reversed(RULES):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, original)
