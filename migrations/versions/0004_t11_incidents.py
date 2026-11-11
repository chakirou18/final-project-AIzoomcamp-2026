"""Durable on-call episodes, operator grants and positive resolution invariant."""

from alembic import op

revision = "0004_t11_incidents"
down_revision = "0003_t07_controls"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""

CREATE TABLE incidents (
	id UUID NOT NULL,
	episode VARCHAR(64) NOT NULL,
	alert_name VARCHAR(80) NOT NULL,
	labels JSONB NOT NULL,
	alert_status VARCHAR(10) NOT NULL,
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
	first_seen TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	latest_seen TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	state VARCHAR(30) DEFAULT 'RECEIVED' NOT NULL,
	generation INTEGER,
	telemetry JSONB,
	diagnosis JSONB,
	verification JSONB,
	escalation_reason VARCHAR(80),
	resolved_at TIMESTAMP WITH TIME ZONE,
	closed_at TIMESTAMP WITH TIME ZONE,
	lease_token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    model_attempts INTEGER DEFAULT '0' NOT NULL,
    last_processed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_incident_state CHECK (state IN (
        'RECEIVED','DIAGNOSING','DIAGNOSED','ACTION_PENDING',
        'ACTION_IN_PROGRESS','VERIFYING','RESOLVED','ESCALATED')),
	CONSTRAINT ck_incident_alert_status CHECK (alert_status IN ('firing','resolved')),
	CONSTRAINT ck_incident_model_bound CHECK (model_attempts BETWEEN 0 AND 1),
	CONSTRAINT ck_incident_resolution CHECK ((state = 'RESOLVED') = (resolved_at IS NOT NULL)),
	UNIQUE (episode)
)

;

CREATE TABLE incident_events (
	id UUID NOT NULL,
	incident_id UUID NOT NULL,
	event_type VARCHAR(40) NOT NULL,
	evidence JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(incident_id) REFERENCES incidents (id)
)

;

CREATE TABLE incident_affected (
	incident_id UUID NOT NULL,
	outbox_id UUID NOT NULL,
	recipient_id UUID NOT NULL,
	PRIMARY KEY (incident_id, outbox_id),
	FOREIGN KEY(incident_id) REFERENCES incidents (id)
)

;

CREATE TABLE incident_grants (
	id UUID NOT NULL,
	incident_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	generation INTEGER NOT NULL,
	action VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_incident_grant_action CHECK (action = 'resume_notification_worker'),
	CONSTRAINT ck_incident_grant_bound CHECK (generation > 0 AND expires_at > created_at
        AND expires_at <= created_at + interval '5 minutes'),
	UNIQUE (incident_id),
	FOREIGN KEY(incident_id) REFERENCES incidents (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;

CREATE TABLE incident_actions (
	idempotency_key UUID NOT NULL,
	incident_id UUID NOT NULL,
	grant_id UUID NOT NULL,
	generation INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	success BOOLEAN,
	completed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (idempotency_key),
	UNIQUE (incident_id),
	FOREIGN KEY(incident_id) REFERENCES incidents (id),
	FOREIGN KEY(grant_id) REFERENCES incident_grants (id)
)

;
CREATE INDEX ix_incident_work ON incidents (state, lease_until);
CREATE INDEX ix_incident_event_order ON incident_events (incident_id, created_at, id);
    """)
    op.execute("""
        CREATE TRIGGER incident_event_immutable BEFORE UPDATE OR DELETE ON incident_events
            FOR EACH ROW EXECUTE FUNCTION reject_worker_audit_mutation();
        CREATE FUNCTION guard_incident_transition() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
          IF NEW.state <> OLD.state AND NOT (
            (OLD.state = 'RECEIVED' AND NEW.state IN ('DIAGNOSING','ESCALATED')) OR
            (OLD.state = 'DIAGNOSING' AND NEW.state IN ('DIAGNOSED','ESCALATED')) OR
            (OLD.state = 'DIAGNOSED' AND NEW.state IN ('ACTION_PENDING','ESCALATED')) OR
            (OLD.state = 'ACTION_PENDING' AND NEW.state IN ('ACTION_IN_PROGRESS','ESCALATED')) OR
            (OLD.state = 'ACTION_IN_PROGRESS' AND NEW.state IN ('VERIFYING','ESCALATED')) OR
            (OLD.state = 'VERIFYING' AND NEW.state IN ('RESOLVED','ESCALATED'))
          ) THEN RAISE EXCEPTION 'illegal incident transition'; END IF;
          IF NEW.state = 'RESOLVED' AND OLD.state <> 'RESOLVED' THEN
            IF NOT EXISTS (
                SELECT 1 FROM incident_actions a JOIN worker_resume_actions r
                  ON r.idempotency_key = a.idempotency_key
                JOIN incident_grants g ON g.id = a.grant_id
                WHERE a.incident_id = NEW.id AND r.incident_id = NEW.id
                  AND a.success AND r.success AND r.expected_generation = a.generation
                  AND g.generation = a.generation AND g.created_at <= r.recorded_at
                  AND g.expires_at > r.recorded_at
                  AND (g.revoked_at IS NULL OR g.revoked_at > r.recorded_at)
            ) OR NOT EXISTS (SELECT 1 FROM incident_affected WHERE incident_id = NEW.id)
              OR EXISTS (
                SELECT 1 FROM incident_affected a
                LEFT JOIN notification_outbox o ON o.id = a.outbox_id
                LEFT JOIN notifications n ON n.outbox_id = a.outbox_id
                WHERE a.incident_id = NEW.id AND
                  (o.id IS NULL OR o.delivered_at IS NULL OR o.status <> 'delivered'
                    OR n.id IS NULL OR n.recipient_id <> a.recipient_id
                    OR o.recipient_id <> a.recipient_id)
              ) OR NEW.verification IS NULL OR NEW.verification->>'ok' IS DISTINCT FROM 'true'
              THEN RAISE EXCEPTION 'positive action and delivery evidence required'; END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER incident_transition BEFORE UPDATE ON incidents
          FOR EACH ROW EXECUTE FUNCTION guard_incident_transition();
        REVOKE ALL ON FUNCTION guard_incident_transition() FROM PUBLIC;
    """)


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM incidents) THEN
                RAISE EXCEPTION 'preserve incident evidence before downgrade';
            END IF;
        END $$;
        DROP TABLE incident_actions;
        DROP TABLE incident_grants;
        DROP TABLE incident_affected;
        DROP TABLE incident_events;
        DROP TABLE incidents;
        DROP FUNCTION guard_incident_transition();
    """)
