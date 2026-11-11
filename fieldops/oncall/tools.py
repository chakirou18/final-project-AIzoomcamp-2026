"""Fixed HTTP operations with bounded reads, pagination and no model-selected URLs."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID

from fieldops.oncall.contracts import DatabaseEvidence


class ToolFailure(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Tools:
    def __init__(self, web, recovery_key, prometheus, loki, jaeger):
        self.web = web.rstrip("/")
        self.key = recovery_key
        self.prometheus = prometheus.rstrip("/")
        self.loki = loki.rstrip("/")
        self.jaeger = jaeger.rstrip("/")
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, url, *, payload=None, authenticated=False, grant=None):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.key
        if grant:
            headers["X-FieldOps-Authorization"] = str(grant)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
        )
        try:
            with self.opener.open(request, timeout=3) as response:
                raw = response.read(524289)
            if len(raw) > 524288:
                raise ToolFailure("tool_response_limit")
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code == 503 and url.startswith(self.web + "/internal/oncall/evidence"):
                raise ToolFailure("application_database_unavailable") from None
            if error.code in {401, 403}:
                raise ToolFailure("tool_authorization_denied") from None
            raise ToolFailure("tool_http_failure") from None
        except TimeoutError:
            raise ToolFailure("tool_timeout") from None
        except (OSError, ValueError):
            raise ToolFailure("tool_unavailable") from None

    def database(self, *, cursor=None, ids=None):
        query = {}
        if cursor:
            query["cursor"] = str(cursor)
        if ids:
            query["ids"] = ",".join(str(UUID(str(value))) for value in ids)
        result = self.request(
            self.web + "/internal/oncall/evidence?" + urllib.parse.urlencode(query),
            authenticated=True,
        )
        return DatabaseEvidence.model_validate(result).model_dump(mode="json")

    def snapshot(self):
        first = self.database()
        items = first["items"].copy()
        cursor = first["next_cursor"]
        seen = {item["id"] for item in items}
        # Up to ten pages, 1,000 known affected events. Refuse truncation or changed snapshots.
        for _ in range(9):
            if not cursor:
                break
            page = self.database(cursor=cursor)
            if (
                page["generation"] != first["generation"]
                or not page["paused"]
                or any(item["id"] in seen for item in page["items"])
            ):
                raise ToolFailure("unstable_snapshot")
            items.extend(page["items"])
            seen.update(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
        if cursor or len(items) != first["undelivered"]:
            raise ToolFailure("affected_limit_or_changed_queue")
        metrics = self.request(
            self.prometheus
            + "/api/v1/query?"
            + urllib.parse.urlencode(
                {
                    "query": '{job="fieldops-web",__name__=~"fieldops_notifications_undelivered|'
                    "fieldops_notification_oldest_undelivered_age_seconds|"
                    'fieldops_metrics_database_up|up"}',
                }
            )
        )
        samples = metrics.get("data", {}).get("result", [])
        values = {}
        now = time.time()
        for sample in samples:
            name = sample.get("metric", {}).get("__name__")
            timestamp, value = sample.get("value", [0, "nan"])
            if 0 <= now - float(timestamp) <= 15:
                values[name] = float(value)
        required = {
            "fieldops_notifications_undelivered",
            "fieldops_notification_oldest_undelivered_age_seconds",
            "fieldops_metrics_database_up",
            "up",
        }
        monitoring_ok = (
            metrics.get("status") == "success"
            and required <= values.keys()
            and values["fieldops_metrics_database_up"] == 1
            and values["up"] == 1
            and values["fieldops_notifications_undelivered"] == first["undelivered"]
            and values["fieldops_notification_oldest_undelivered_age_seconds"] > 60
        )
        # Use exact UUIDs from validated application responses, never telemetry-supplied queries.
        identifiers = [item["id"] for item in items[:10]]
        query = '{service="fieldops-web"}'
        if identifiers:
            query += ' |~ "' + "|".join(identifiers) + '"'
        logs = self.request(
            self.loki
            + "/loki/api/v1/query_range?"
            + urllib.parse.urlencode(
                {
                    "query": query,
                    "start": str(int((now - 900) * 1e9)),
                    "end": str(int(now * 1e9)),
                    "limit": "100",
                }
            )
        )
        events = []
        for stream in logs.get("data", {}).get("result", [])[:100]:
            for _, line in stream.get("values", [])[:100]:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if (
                    event.get("event") in {"notification_enqueued", "notification_delivered"}
                    and event.get("outbox_id") in identifiers
                ):
                    events.append(event["event"])
        traces = []
        for identifier in dict.fromkeys(item["trace_id"] for item in items[:3] if item["trace_id"]):
            data = self.request(self.jaeger + "/api/traces/" + identifier)
            for trace in data.get("data", [])[:1]:
                traces.append(
                    {
                        "enqueue_seen": any(
                            span.get("operationName") == "notification.enqueue"
                            for span in trace.get("spans", [])[:200]
                        )
                    }
                )
        first["items"] = []  # Affected identities have their own durable table.
        return {
            "database": first,
            "affected": items,
            "metrics": values,
            "monitoring_ok": monitoring_ok
            and bool(events)
            and bool(traces)
            and all(trace["enqueue_seen"] for trace in traces),
            "logs": {"enqueue_records": events.count("notification_enqueued")},
            "traces": {
                "sampled": len(traces),
                "enqueue_seen": all(trace["enqueue_seen"] for trace in traces),
            },
        }

    def delivery(self, identifiers):
        items = []
        for offset in range(0, len(identifiers), 100):
            page = self.database(ids=identifiers[offset : offset + 100])
            if page["next_cursor"]:
                raise ToolFailure("delivery_page_overflow")
            items.extend(page["items"])
        return items, self.database()

    def resume(self, incident_id, generation, key, grant):
        return self.request(
            self.web + "/internal/worker/resume",
            authenticated=True,
            grant=grant,
            payload={
                "incident_id": str(incident_id),
                "expected_generation": generation,
                "idempotency_key": str(key),
            },
        )

    def reconcile(self, key):
        return self.request(self.web + "/internal/oncall/actions/" + str(key), authenticated=True)
