"""Live operator dashboard and actual paused-delivery recovery; no alerting/model agent."""

import json
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from pydantic import SecretStr
from test_t05_journey import BASE, layout, sign_in

from fieldops.seed import persona_id

PROJECT = os.getenv("FIELDOPS_BROWSER_PROJECT", "fieldops-t07")


def compose(*args):
    if os.getenv("FIELDOPS_TEST_SUPERVISOR_PID"):
        from test_support.managed import compose as managed_compose

        return managed_compose(*args)
    return (
        subprocess.check_output(
            ["docker", "compose", "--project-name", PROJECT, *args],
            stderr=subprocess.PIPE,
            timeout=30,
        )
        .decode()
        .strip()
    )


def credential(name):
    # SecretStr keeps failed fixture representations redacted; no generated secret files/reports.
    return SecretStr(compose("exec", "-T", "web", "cat", "/run/fieldops-controls/" + name))


def operator(page):
    secret = credential("operator_key")
    page.goto(BASE + "/app/operator")
    page.get_by_label("Operator credential").fill(secret.get_secret_value())
    page.get_by_role("button", name="Open operations").click()
    expect(page.get_by_role("heading", name="Operations dashboard", exact=True)).to_be_visible()


@pytest.mark.parametrize(
    "width,javascript", [(1440, True), (375, True), (1440, False), (375, False)]
)
def test_operator_dashboard_presentation(width, javascript):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": 960}, java_script_enabled=javascript
        )
        operator(page)
        layout(page)
        for state in ("Open", "Assigned", "In Progress", "Completed", "Cancelled"):
            expect(page.get_by_role("heading", name=state, exact=True)).to_be_visible()
        expect(page.get_by_text("A database snapshot", exact=False)).to_be_visible()
        expect(page.get_by_role("heading", name="Notification worker", exact=True)).to_be_visible()
        assert page.locator("html").get_attribute("lang") == "en"
        assert page.locator("main").count() == 1
        # Traverse the actual tab order and expand the native pause disclosure by keyboard.
        for _ in range(12):
            page.keyboard.press("Tab")
            if page.locator("summary").evaluate("element => element === document.activeElement"):
                break
        expect(page.locator("summary")).to_be_focused()
        page.keyboard.press("Space")
        page.keyboard.press("Tab")
        button = page.get_by_role("button", name="Pause notification delivery")
        expect(button).to_be_focused()
        assert button.evaluate("element => getComputedStyle(element).outlineStyle") != "none"
        secret = credential("recovery_key")
        safe = secret.get_secret_value() not in page.content()
        assert safe
        Path("artifacts").mkdir(exist_ok=True)
        page.screenshot(path=f"artifacts/t07-dashboard-{width}-js-{javascript}.png", full_page=True)
        browser.close()


def wait_until(function, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = function()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Bounded wait did not observe the required persisted state")


def test_t07_controlled_failure_and_recovery_demonstration():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        contexts = [browser.new_context(viewport={"width": 1440, "height": 960}) for _ in range(3)]
        ops, manager, technician = [context.new_page() for context in contexts]
        operator(ops)
        sign_in(manager, "Synthetic Dispatcher · Manager")
        sign_in(technician, "Synthetic Technician A · Technician")
        csrf = manager.request.get(BASE + "/auth/session").json()["csrf_token"]

        def create(label):
            response = manager.request.post(
                BASE + "/api/v1/interventions",
                data={
                    "title": label + " " + uuid4().hex[:10],
                    "site": "Synthetic T07 demo",
                    "technician_id": str(persona_id("demo-technician-a")),
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status == 201
            return response.json()["id"]

        def notification(identifier):
            response = technician.request.get(BASE + "/api/v1/notifications?page_size=100")
            assert response.status == 200
            return next(
                (
                    item
                    for item in response.json()["items"]
                    if item["intervention_id"] == identifier
                ),
                None,
            )

        normal = create("T07 normal delivery")
        wait_until(lambda: notification(normal))
        snapshot = ops.request.get(BASE + "/api/v1/dashboard").json()
        assert snapshot["undelivered"] == 0 and snapshot["oldest_undelivered_age_seconds"] == 0
        assert snapshot["worker"]["heartbeat_state"] == "fresh"
        original_instance = snapshot["worker"]["last_instance_id"]
        ops.reload()
        ops.get_by_text("Controlled demo pause", exact=True).click()
        ops.get_by_role("button", name="Pause notification delivery").click()
        expect(ops.locator("#worker-state")).to_contain_text("Paused")
        paused = ops.request.get(BASE + "/api/v1/dashboard").json()
        assert paused["worker"]["paused"]
        generation = paused["worker"]["generation"]

        # Separate restart test: the pause mechanism itself never stops/kills a container.
        compose("restart", "worker")
        restarted = wait_until(
            lambda: (
                data
                if (data := ops.request.get(BASE + "/api/v1/dashboard").json())["worker"][
                    "last_instance_id"
                ]
                != original_instance
                and data["worker"]["heartbeat_state"] == "fresh"
                else None
            )
        )
        assert restarted["worker"]["paused"] and restarted["worker"]["generation"] == generation
        identifier = create("T07 paused assignment")
        # UUID validation bounds SQL to a synthetic server-generated identifier.
        identifier = str(UUID(identifier))
        event = json.loads(
            compose(
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "fieldops",
                "-d",
                "fieldops",
                "-At",
                "-c",
                "SELECT json_build_object('id',id,'created_at',created_at,'status',status,"
                "'attempts',attempts) FROM notification_outbox WHERE intervention_id='"
                + identifier
                + "'",
            )
        )
        assert event["status"] == "pending" and event["attempts"] == 0
        assert notification(identifier) is None
        first = ops.request.get(BASE + "/api/v1/dashboard").json()
        assert first["undelivered"] == 1
        # Real elapsed time: no row timestamp rewrites, fabricated ages or T10 alerts.
        started = time.monotonic()
        while time.monotonic() - started < 61:
            time.sleep(0.5)
        delayed = ops.request.get(BASE + "/api/v1/dashboard").json()
        assert delayed["undelivered"] == 1 and delayed["oldest_undelivered_age_seconds"] > 60
        assert delayed["worker"]["paused"] and delayed["worker"]["heartbeat_state"] == "fresh"
        assert notification(identifier) is None
        ops.reload()
        expect(ops.get_by_text("Delayed delivery:", exact=False)).to_be_visible()
        ops.screenshot(path="artifacts/t07-paused-delivery.png", full_page=True)
        token = credential("recovery_key")
        command = {
            "incident_id": str(uuid4()),
            "idempotency_key": str(uuid4()),
            "expected_generation": generation,
        }
        response = ops.request.post(
            BASE + "/internal/worker/resume",
            data=command,
            headers={"Authorization": "Bearer " + token.get_secret_value()},
        )
        assert response.status == 200 and response.json()["success"]
        result = response.json()
        replay = ops.request.post(
            BASE + "/internal/worker/resume",
            data=command,
            headers={"Authorization": "Bearer " + token.get_secret_value()},
        )
        assert replay.status == 200 and replay.json() == result
        delivered = wait_until(lambda: notification(identifier))
        assert delivered["outbox_id"] == event["id"]
        final = ops.request.get(BASE + "/api/v1/dashboard").json()
        assert final["undelivered"] == 0 and final["oldest_undelivered_age_seconds"] == 0
        assert not final["worker"]["paused"]
        audit = json.loads(
            compose(
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "fieldops",
                "-d",
                "fieldops",
                "-At",
                "-c",
                "SELECT json_build_object('success',success,'outcome',outcome,'generation',"
                "generation,'recorded_at',recorded_at) FROM worker_resume_actions "
                "WHERE idempotency_key='" + command["idempotency_key"] + "'",
            )
        )
        assert audit["success"] and audit["generation"] == generation
        ops.reload()
        ops.screenshot(path="artifacts/t07-recovered-delivery.png", full_page=True)
        evidence = {
            "normal_intervention_id": normal,
            "affected_intervention_id": identifier,
            "outbox": event,
            "generation": generation,
            "pause": paused["worker"],
            "after_restart": restarted["worker"],
            "first_age": first["oldest_undelivered_age_seconds"],
            "delayed_age": delayed["oldest_undelivered_age_seconds"],
            "resume": result,
            "notification": delivered,
            "persisted_action": audit,
            "final_undelivered": final["undelivered"],
        }
        Path("artifacts/t07-failure-evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(
            "T07_FAILURE_EVIDENCE "
            + json.dumps(
                {
                    "event_id": event["id"],
                    "generation": generation,
                    "delayed_age": evidence["delayed_age"],
                    "delivered_at": delivered["delivered_at"],
                }
            )
        )
        browser.close()
