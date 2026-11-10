"""Web-owned persisted queue metrics: database outage is never a healthy empty queue."""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, HistogramMetricFamily
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

BUCKETS = (0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, float("inf"))


class DatabaseMetrics:
    def __init__(self, engine):
        self.engine = engine

    def collect(self):
        try:
            with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as db:
                rows = db.execute(
                    text("SELECT status, count(*) FROM notification_outbox GROUP BY status")
                ).all()
                counts = dict(rows)
                age = db.scalar(
                    text(
                        "SELECT COALESCE(GREATEST(0, EXTRACT(EPOCH FROM "
                        "(clock_timestamp()-min(created_at)))),0) FROM notification_outbox "
                        "WHERE status IN ('pending','processing','failed')"
                    )
                )
                heartbeat = db.scalar(
                    text(
                        "SELECT COALESCE(EXTRACT(EPOCH FROM max(last_seen)),0) "
                        "FROM worker_heartbeats"
                    )
                )
                paused = db.scalar(
                    text("SELECT paused FROM worker_control WHERE key='notification-worker'")
                )
                # Fixed buckets; persisted distribution survives worker/web restarts.
                bucket_sql = ", ".join(
                    f"count(*) FILTER (WHERE seconds <= {bound}) AS b{index}"
                    for index, bound in enumerate(BUCKETS[:-1])
                )
                latency = db.execute(
                    text(
                        "SELECT count(*) AS total, COALESCE(sum(seconds),0) AS sum, "
                        + bucket_sql
                        + " FROM (SELECT GREATEST(0, EXTRACT(EPOCH FROM "
                        "(delivered_at-created_at))) AS seconds FROM notification_outbox "
                        "WHERE status='delivered') AS latencies"
                    )
                ).one()
        except SQLAlchemyError:
            yield GaugeMetricFamily(
                "fieldops_metrics_database_up",
                "1 when the complete queue snapshot is available",
                value=0,
            )
            return  # Deliberately omit unavailable queue/worker metrics; do not emit false zeroes.
        yield GaugeMetricFamily(
            "fieldops_metrics_database_up",
            "1 when the complete queue snapshot is available",
            value=1,
        )
        yield GaugeMetricFamily(
            "fieldops_notifications_undelivered",
            "Pending + processing + failed events",
            value=sum(counts.get(s, 0) for s in ("pending", "processing", "failed")),
        )
        yield GaugeMetricFamily(
            "fieldops_notification_oldest_undelivered_age_seconds",
            "Database age of oldest undelivered row; zero for empty queue",
            value=float(age),
        )
        states = GaugeMetricFamily(
            "fieldops_notification_events",
            "Persisted event count by bounded status",
            labels=["status"],
        )
        for state in ("pending", "processing", "failed", "delivered"):
            states.add_metric([state], counts.get(state, 0))
        yield states
        for state in ("delivered", "failed"):
            yield CounterMetricFamily(
                f"fieldops_notifications_{state}",
                f"Persisted terminal {state} events",
                value=counts.get(state, 0),
            )
        yield GaugeMetricFamily(
            "fieldops_worker_heartbeat_timestamp_seconds",
            "Latest persisted worker heartbeat; zero if never observed",
            value=float(heartbeat),
        )
        yield GaugeMetricFamily(
            "fieldops_worker_paused",
            "Persisted gate state; independent of heartbeat freshness",
            value=int(bool(paused)),
        )
        histogram = HistogramMetricFamily(
            "fieldops_notification_delivery_latency_seconds",
            "Persisted enqueue-to-inbox latency",
            buckets=[
                (
                    str(bound) if bound != float("inf") else "+Inf",
                    latency[index + 2] if index < len(BUCKETS) - 1 else latency.total,
                )
                for index, bound in enumerate(BUCKETS)
            ],
            sum_value=float(latency.sum),
        )
        yield histogram


class Metrics:
    def __init__(self, engine):
        self.registry = CollectorRegistry()
        self.registry.register(DatabaseMetrics(engine))
        self.requests = Counter(
            "fieldops_http_requests_total",
            "HTTP responses",
            ["method", "route", "status_class"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "fieldops_http_request_duration_seconds",
            "HTTP response latency",
            ["method", "route"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
            registry=self.registry,
        )

    def observe(self, method, route, status, elapsed):
        method = (
            method
            if method in {"GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"}
            else "OTHER"
        )
        self.requests.labels(method, route, f"{status // 100}xx").inc()
        self.duration.labels(method, route).observe(elapsed)

    def render(self):
        return generate_latest(self.registry)
