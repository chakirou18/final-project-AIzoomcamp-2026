"""N03: five independent HTTP clients, 1,000 real jobs, 50 fully read/validated requests."""

import http.cookiejar
import json
import math
import os
import platform
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldops.database import create_database_engine
from fieldops.models import Intervention
from fieldops.schemas import InterventionCreate
from fieldops.seed import persona_id
from fieldops.services.interventions import InterventionService


def percentile(values, percentage):
    return sorted(values)[math.ceil(len(values) * percentage) - 1]


def benchmark(stack, settings, artifacts):
    engine = create_database_engine(settings)
    service = InterventionService(engine)
    try:
        identifiers = [
            str(
                service.create(
                    persona_id("demo-manager"),
                    InterventionCreate(
                        title=f"Synthetic N03 {index:04}",
                        site="Synthetic benchmark site",
                    ),
                ).id
            )
            for index in range(1000)
        ]
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Intervention)) == 1000
    finally:
        engine.dispose()
    stack.start("web", "fieldops")
    stack.start("worker", "fieldops.worker")
    from test_support.runner import ready

    ready()
    barrier = Barrier(5, timeout=30)
    base = "http://127.0.0.1:8000"

    def client(index):
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

        def get(path):
            with opener.open(base + path, timeout=5) as response:
                assert response.status == 200
                return json.load(response)

        csrf = get("/auth/csrf")["csrf_token"]
        login = urllib.request.Request(
            base + "/auth/login",
            data=json.dumps(
                {
                    "persona_id": str(persona_id("demo-manager")),
                }
            ).encode(),
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
        )
        with opener.open(login, timeout=5) as response:
            assert response.status == 200
            response.read()
        paths = [
            "/api/v1/interventions?page=1&page_size=25",
            "/api/v1/interventions/" + identifiers[index],
        ]
        for path in paths:
            get(path)  # Two warmups per client; authentication and warmups excluded.
        barrier.wait()
        samples = []
        for number in range(10):
            path = (
                f"/api/v1/interventions?page={index * 8 + number // 2 + 1}&page_size=25"
                if number % 2 == 0
                else "/api/v1/interventions/" + identifiers[index * 10 + number]
            )
            start = time.perf_counter()
            error = False
            try:
                payload = get(path)
                if number % 2 == 0:
                    assert payload["total"] == 1000 and len(payload["items"]) == 25
                else:
                    assert payload["id"] == identifiers[index * 10 + number]
            except Exception:
                error = True
            end = time.perf_counter()
            samples.append(
                {
                    "client": index,
                    "kind": "list" if number % 2 == 0 else "detail",
                    "start": start,
                    "end": end,
                    "seconds": end - start,
                    "error": error,
                }
            )
        return samples

    with ThreadPoolExecutor(max_workers=5) as executor:
        samples = [item for group in executor.map(client, range(5)) for item in group]
    values = [item["seconds"] for item in samples]
    duration = max(item["end"] for item in samples) - min(item["start"] for item in samples)
    errors = sum(item["error"] for item in samples)
    report = {
        "records": 1000,
        "clients": 5,
        "requests": 50,
        "mix": "25 JSON list + 25 JSON detail",
        "warmup_requests": 10,
        "p50_seconds": statistics.median(values),
        "p95_seconds": percentile(values, 0.95),
        "max_seconds": max(values),
        "errors": errors,
        "error_rate": errors / 50,
        "requests_per_second": 50 / duration,
        "duration_seconds": duration,
        "p95_method": "nearest rank: sorted sample 48 of 50",
        "timing": "perf_counter before HTTP open through complete JSON read and validation",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpus_visible": os.cpu_count(),
        "api": "one Uvicorn process; SQLAlchemy pool 5, overflow 0",
        "database": "PostgreSQL 17; isolated 512MiB tmpfs; 2s statement timeout",
        "worker": "one real worker; 2-second polling; no notification backlog",
        "samples": samples,
    }
    (artifacts / "n03-performance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("T08_N03 " + json.dumps({k: v for k, v in report.items() if k != "samples"}), flush=True)
    if len(samples) != 50 or errors or report["p95_seconds"] >= 1:
        raise AssertionError("N03 failed: requires 50 valid responses and p95 strictly below 1s")
