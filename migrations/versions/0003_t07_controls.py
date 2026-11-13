"""Persistent notification-worker gate, heartbeat and append-only control results."""

from alembic import op

revision = "0003_t07_controls"
down_revision = "0002_t03_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE worker_control (
            key varchar(40) PRIMARY KEY,
            paused boolean NOT NULL DEFAULT false,
            generation integer NOT NULL DEFAULT 0,
            effective_at timestamptz, expires_at timestamptz, last_pause_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_control_singleton CHECK (key = 'notification-worker'),
            CONSTRAINT ck_control_generation CHECK (generation >= 0),
            CONSTRAINT ck_control_pause CHECK (
                (paused AND generation > 0 AND effective_at IS NOT NULL AND expires_at IS NOT NULL
                 AND expires_at > effective_at
                 AND expires_at <= effective_at + interval '10 minutes')
                OR (NOT paused AND effective_at IS NULL AND expires_at IS NULL))
        );
        INSERT INTO worker_control(key) VALUES ('notification-worker');
        CREATE TABLE worker_heartbeats (
            instance_id uuid PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(),
            last_seen timestamptz NOT NULL DEFAULT now(), observed_generation integer NOT NULL,
            observed_paused boolean NOT NULL,
            CONSTRAINT ck_heartbeat_generation CHECK (observed_generation >= 0)
        );
        CREATE INDEX ix_heartbeat_last_seen ON worker_heartbeats(last_seen);
        CREATE TABLE worker_control_audit (
            id uuid PRIMARY KEY, event_type varchar(30) NOT NULL, generation integer NOT NULL,
            actor_id uuid REFERENCES users(id), principal varchar(20) NOT NULL,
            outcome varchar(40) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_control_event CHECK (event_type IN ('pause','resume','auto_expired')),
            CONSTRAINT ck_audit_generation CHECK (generation >= 0),
            CONSTRAINT ck_control_principal CHECK (principal IN ('operator','agent','system'))
        );
        CREATE TABLE worker_resume_actions (
            idempotency_key uuid PRIMARY KEY, incident_id uuid NOT NULL,
            expected_generation integer NOT NULL, generation integer NOT NULL,
            outcome varchar(40) NOT NULL, success boolean NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_action_generation CHECK (expected_generation >= 1 AND generation >= 0),
            CONSTRAINT ck_action_outcome CHECK (
                (success AND outcome = 'resumed') OR
                (NOT success AND outcome IN ('generation_mismatch','not_paused')))
        );
        CREATE FUNCTION reject_worker_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'worker control records are append-only'; END $$;
        CREATE TRIGGER worker_audit_immutable BEFORE UPDATE OR DELETE ON worker_control_audit
            FOR EACH ROW EXECUTE FUNCTION reject_worker_audit_mutation();
        CREATE TRIGGER worker_action_immutable BEFORE UPDATE OR DELETE ON worker_resume_actions
            FOR EACH ROW EXECUTE FUNCTION reject_worker_audit_mutation();
    """)


def downgrade():
    op.execute("""
        DROP TABLE worker_resume_actions;
        DROP TABLE worker_control_audit;
        DROP FUNCTION reject_worker_audit_mutation();
        DROP TABLE worker_heartbeats;
        DROP TABLE worker_control;
    """)
