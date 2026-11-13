"""Live Compose browser journeys, run explicitly with pytest browser_tests."""

import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("FIELDOPS_BROWSER_URL", "http://127.0.0.1:18005")


def sign_in(page, name):
    page.goto(BASE + "/app/login")
    page.get_by_label("Demo identity").select_option(label=name)
    page.get_by_role("button", name="Open workspace").click()
    expect(
        page.get_by_role("heading", name="Interventions", exact=True)
        if "Dispatcher" in name
        else page.get_by_role("heading", name="My interventions", exact=True)
    ).to_be_visible()


def layout(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    for control in page.locator("input:not([type=hidden]), select, textarea").all():
        assert control.get_attribute("id")
        assert page.locator(f'label[for="{control.get_attribute("id")}"]').count() == 1


@pytest.mark.parametrize(
    "width,javascript", [(1440, True), (375, True), (1440, False), (375, False)]
)
def test_real_manager_worker_technician_journey(width, javascript):
    title = "Browser " + uuid4().hex[:12]
    errors = []
    enhanced = []
    Path("artifacts").mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        manager_context = browser.new_context(
            viewport={"width": width, "height": 960}, java_script_enabled=javascript
        )
        technician_context = browser.new_context(
            viewport={"width": width, "height": 960}, java_script_enabled=javascript
        )
        manager = manager_context.new_page()
        technician = technician_context.new_page()
        manager.on("pageerror", lambda error: errors.append(str(error)))
        technician.on("pageerror", lambda error: errors.append(str(error)))
        technician.on("request", lambda request: enhanced.append(request.headers.get("hx-request")))
        manager.goto(BASE + "/app/login")
        manager.keyboard.press("Tab")
        expect(manager.get_by_role("link", name="Skip to content")).to_be_focused()
        sign_in(manager, "Synthetic Dispatcher · Manager")
        layout(manager)
        manager.get_by_role("link", name="+ New intervention").click()
        manager.screenshot(path=f"artifacts/t05-create-{width}-js-{javascript}.png", full_page=True)
        manager.get_by_label("Title *", exact=True).fill("")
        manager.get_by_label("Site *", exact=True).fill("Demo building")
        manager.get_by_role("button", name="Create intervention", exact=True).click()
        expect(manager.get_by_role("alert")).to_contain_text("correct")
        expect(manager.get_by_label("Site *", exact=True)).to_have_value("Demo building")
        manager.get_by_label("Title *", exact=True).fill(title)
        manager.get_by_label("Title *", exact=True).focus()
        manager.keyboard.press("Tab")
        expect(manager.get_by_label("Site *", exact=True)).to_be_focused()
        manager.keyboard.press("ControlOrMeta+A")
        manager.keyboard.type("Demo building")
        manager.get_by_label("Description", exact=True).fill("Synthetic browser work")
        manager.get_by_label("Priority *", exact=True).select_option("high")
        layout(manager)
        manager.get_by_role("button", name="Create intervention", exact=True).focus()
        manager.keyboard.press("Enter")
        expect(manager.get_by_role("heading", name=title, exact=True)).to_be_visible()
        job_url = manager.url.split("?")[0]
        manager.get_by_role("link", name="Edit details").click()
        manager.get_by_label("Site *", exact=True).fill("Demo building east")
        manager.get_by_role("button", name="Save changes", exact=True).click()
        manager.get_by_label("Assign technician", exact=True).select_option(
            label="Synthetic Technician A"
        )
        started = time.monotonic()
        manager.get_by_role("button", name="Save assignment", exact=True).click()
        job_id = job_url.rsplit("/", 1)[1]
        sign_in(technician, "Synthetic Technician A · Technician")
        technician.get_by_role("link", name="Inbox", exact=True).click()
        expect(
            technician.get_by_role("heading", name="Notification inbox", exact=True)
        ).to_be_visible()
        link = technician.locator(f'a[href="/app/interventions/{job_id}"]')
        deadline = time.monotonic() + 10
        while link.count() == 0 and time.monotonic() < deadline:
            technician.get_by_role("link", name="Refresh inbox", exact=True).click()
        expect(link).to_be_visible()
        technician.screenshot(
            path=f"artifacts/t05-inbox-{width}-js-{javascript}.png", full_page=True
        )
        elapsed = time.monotonic() - started
        article = link.locator("xpath=ancestor::article")
        article.get_by_role("button", name="Mark as read", exact=True).click()
        link = technician.locator(f'a[href="/app/interventions/{job_id}"]')
        expect(link.locator("xpath=ancestor::article")).to_contain_text("Read")
        layout(technician)
        link.click()
        technician.get_by_role("button", name="Start intervention", exact=True).click()
        technician.get_by_label("Resolution *").fill(
            "Replaced synthetic valve; verified operation."
        )
        technician.get_by_role("button", name="Complete intervention", exact=True).click()
        expect(technician.locator(".status-completed")).to_be_visible()
        manager.goto(job_url)
        expect(manager.locator(".status-completed")).to_be_visible()
        expect(
            manager.get_by_text("Replaced synthetic valve; verified operation.", exact=True)
        ).to_be_visible()
        layout(manager)
        response = manager.request.get(BASE + "/api/v1/interventions/" + job_id)
        assert response.status == 200 and response.json()["status"] == "completed"
        assert response.json()["resolution"] == "Replaced synthetic valve; verified operation."
        if javascript:
            assert "true" in enhanced
        Path("artifacts").mkdir(exist_ok=True)
        manager.screenshot(path=f"artifacts/t05-{width}-js-{javascript}.png", full_page=True)
        # A session revoked outside the current page must show an error during boosted navigation.
        token = technician.locator('form[action="/app/logout"] input').get_attribute("value")
        revoked = technician.request.post(BASE + "/auth/logout", headers={"X-CSRF-Token": token})
        assert revoked.status == 204
        technician.get_by_role("link", name="My work", exact=True).click()
        expect(
            technician.get_by_role(
                "heading",
                name=("Your session is missing or expired. Choose a demo identity to continue."),
            ).last
        ).to_be_visible()
        print(
            f"T05_BROWSER width={width} javascript={javascript} "
            f"job={job_id} inbox_seconds={elapsed:.3f}"
        )
        assert not errors, errors
        manager_context.close()
        technician_context.close()
        browser.close()
