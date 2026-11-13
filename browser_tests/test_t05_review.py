"""Independent live browser checks for boundary text, reassignment and client-side history."""

import time
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from test_t05_journey import BASE, layout, sign_in


def screenshot(page, name):
    Path("artifacts").mkdir(exist_ok=True)
    page.screenshot(path=f"artifacts/t05-audit-{name}.png", full_page=True)


def wait_for_inbox(page, identifier):
    page.goto(BASE + "/app/inbox")
    link = page.locator(f'a[href="/app/interventions/{identifier}"]')
    deadline = time.monotonic() + 10
    while not link.count() and time.monotonic() < deadline:
        page.get_by_role("link", name="Refresh inbox", exact=True).click()
    expect(link).to_have_count(1)
    return link


@pytest.mark.parametrize(
    "width,javascript", [(1440, True), (375, True), (1440, False), (375, False)]
)
def test_boundary_fields_reassignment_conflicts_and_persistence(width, javascript):
    title = ("Audit-" + uuid4().hex + "X" * 160)[:160]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        manager_context = browser.new_context(
            viewport={"width": width, "height": 960}, java_script_enabled=javascript
        )
        a_context = browser.new_context(
            viewport={"width": width, "height": 960}, java_script_enabled=javascript
        )
        b_context = browser.new_context(
            viewport={"width": width, "height": 960}, java_script_enabled=javascript
        )
        manager, a, b = manager_context.new_page(), a_context.new_page(), b_context.new_page()
        sign_in(manager, "Synthetic Dispatcher · Manager")
        manager.get_by_role("link", name="+ New intervention").click()
        manager.get_by_label("Title *", exact=True).fill(title)
        manager.get_by_label("Site *", exact=True).fill("S" * 250)
        manager.get_by_label("Description", exact=True).fill('<img src=x onerror="window.bad=1">')
        manager.get_by_role("button", name="Create intervention", exact=True).click()
        url = manager.url.split("?")[0]
        identifier = url.rsplit("/", 1)[1]
        expect(manager.get_by_role("heading", name=title, exact=True)).to_be_visible()
        screenshot(manager, f"boundary-{width}-{javascript}")
        layout(manager)
        assert manager.locator('img[src="x"]').count() == 0
        stale = manager_context.new_page()
        stale.goto(url + "/edit")
        manager.get_by_role("link", name="Edit details").click()
        manager.get_by_label("Priority *").select_option("urgent")
        manager.get_by_role("button", name="Save changes").click()
        stale.get_by_label("Description", exact=True).fill("Stale unsaved description")
        with stale.expect_response(
            lambda r: r.url.endswith("/edit") and r.request.method == "POST"
        ) as result:
            stale.get_by_role("button", name="Save changes").click()
        assert result.value.status == 409
        expect(stale.get_by_role("alert")).to_contain_text("Reload the latest version")
        expect(stale.get_by_label("Description", exact=True)).to_have_value(
            "Stale unsaved description"
        )
        layout(stale)
        screenshot(stale, f"conflict-{width}-{javascript}")
        manager.get_by_label("Assign technician", exact=True).select_option(
            label="Synthetic Technician A"
        )
        manager.get_by_role("button", name="Save assignment").click()
        api = BASE + "/api/v1/interventions/" + identifier
        before = manager.request.get(api).json()
        manager.get_by_role("button", name="Save assignment").click()
        assert manager.request.get(api).json() == before
        sign_in(a, "Synthetic Technician A · Technician")
        link = wait_for_inbox(a, identifier)
        article = link.locator("xpath=ancestor::article")
        article.get_by_role("button", name="Mark as read", exact=True).click()
        a.reload()
        page = a.request.get(BASE + "/api/v1/notifications?page_size=100").json()
        item = next(item for item in page["items"] if item["intervention_id"] == identifier)
        assert item["read_at"] is not None
        link = a.locator(f'a[href="/app/interventions/{identifier}"]')
        link.locator("xpath=ancestor::article").get_by_role(
            "button", name="Mark as read again"
        ).click()
        read_again = a.request.get(BASE + "/api/v1/notifications?page_size=100").json()
        assert (
            next(n for n in read_again["items"] if n["id"] == item["id"])["read_at"]
            == item["read_at"]
        )
        manager.get_by_label("Reassign technician", exact=True).select_option(
            label="Synthetic Technician B"
        )
        manager.get_by_role("button", name="Save assignment").click()
        a.reload()
        article = a.locator(f'form[action="/app/inbox/{item["id"]}/read"]').locator(
            "xpath=ancestor::article"
        )
        expect(article).to_contain_text("Historical assignment")
        assert article.locator('a[href^="/app/interventions/"]').count() == 0
        screenshot(a, f"historical-inbox-{width}-{javascript}")
        denied = a.request.get(url)
        assert denied.status == 403 and title not in denied.text()
        token = a.locator('form[action="/app/logout"] input').get_attribute("value")
        denied = a.request.post(
            url + "/transition",
            form={
                "csrf_token": token,
                "expected_version": "4",
                "target_status": "in_progress",
            },
        )
        assert denied.status == 403
        sign_in(b, "Synthetic Technician B · Technician")
        wait_for_inbox(b, identifier).click()
        b.get_by_role("button", name="Start intervention", exact=True).click()
        b.get_by_label("Resolution *").fill("Audited repair complete")
        b.get_by_role("button", name="Complete intervention", exact=True).click()
        manager.goto(url)
        expect(manager.locator(".status-completed")).to_be_visible()
        final = manager.request.get(api)
        assert final.status == 200
        assert (
            final.json()["row_version"] == 6
            and final.json()["resolution"] == "Audited repair complete"
        )
        manager.goto(BASE + "/app/interventions?status=completed&priority=urgent&page_size=1")
        layout(manager)
        expect(manager.get_by_role("link", name=title, exact=True)).to_be_visible()
        screenshot(manager, f"filtered-{width}-{javascript}")
        print(f"T05_AUDIT_JOB id={identifier} version=6 width={width} javascript={javascript}")
        browser.close()


def test_authenticated_pages_are_not_persisted_in_htmx_browser_storage():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        sign_in(page, "Synthetic Technician A · Technician")
        page.evaluate(
            "document.addEventListener('htmx:afterSettle', "
            "() => window.auditSettled = true, {once:true})"
        )
        page.get_by_role("link", name="Inbox", exact=True).click()
        expect(page.get_by_role("heading", name="Notification inbox", exact=True)).to_be_visible()
        page.wait_for_function("() => window.auditSettled === true")
        # Return a boolean only: failure reports must never serialize hidden CSRF inputs.
        empty = page.evaluate(
            "['sessionStorage','localStorage'].every(key => {"
            "const value = window[key].getItem('htmx-history-cache');"
            "return !value || value === '[]';})"
        )
        assert empty, "Authenticated HTML was persisted by HTMX"
        token = page.locator('form[action="/app/logout"] input').get_attribute("value")
        assert (
            page.request.post(BASE + "/auth/logout", headers={"X-CSRF-Token": token}).status == 204
        )
        page.go_back()
        expect(
            page.get_by_role(
                "heading",
                name=("Your session is missing or expired. Choose a demo identity to continue."),
            )
        ).to_be_visible()
        assert page.locator("h1").count() == 1
        assert page.locator("h2").count() == 0
        browser.close()


@pytest.mark.parametrize("width", [1440, 375])
def test_empty_pagination_semantics_and_visible_keyboard_focus(width):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 960})
        sign_in(page, "Synthetic Dispatcher · Manager")
        page.goto(BASE + "/app/interventions?status=open&priority=low")
        expect(page.get_by_role("heading", name="No interventions here yet")).to_be_visible()
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Skip to content")).to_be_focused()
        assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"
        assert page.evaluate("getComputedStyle(document.activeElement).outlineWidth") == "3px"
        assert page.locator("main").count() == 1 and page.locator("h1").count() == 1
        assert page.locator("html").get_attribute("lang") == "en"
        layout(page)
        screenshot(page, f"empty-focus-{width}")
        page.goto(BASE + "/app/interventions?page=999999&priority=high")
        expect(page.get_by_role("heading", name="No interventions on this page")).to_be_visible()
        assert "priority=high" in page.get_by_role(
            "link", name="Return to the first page"
        ).get_attribute("href")
        sign_in(page, "Synthetic Technician A · Technician")
        page.goto(BASE + "/app/inbox?page=999999")
        expect(page.get_by_role("heading", name="No notifications on this page")).to_be_visible()
        page.get_by_role("link", name="Return to the first page").click()
        expect(page.get_by_role("heading", name="Notification inbox", exact=True)).to_be_visible()
        layout(page)
        browser.close()
