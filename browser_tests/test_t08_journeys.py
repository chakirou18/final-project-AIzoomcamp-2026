"""Coverage gaps: native cancellation, usable pagination and unauthenticated direct URLs."""

from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from test_t05_journey import BASE, layout, sign_in


@pytest.mark.parametrize("javascript", [True, False])
def test_cancel_and_paginate_persisted_jobs_with_direct_session_denial(javascript):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 375, "height": 960}, java_script_enabled=javascript
        )
        manager = context.new_page()
        sign_in(manager, "Synthetic Dispatcher · Manager")
        manager.get_by_role("link", name="+ New intervention").click()
        title = "T08 cancellation " + uuid4().hex[:12]
        manager.get_by_label("Title *", exact=True).fill(title)
        manager.get_by_label("Site *", exact=True).fill("Synthetic cancellation site")
        manager.get_by_role("button", name="Create intervention", exact=True).click()
        identifier = manager.url.split("?")[0].rsplit("/", 1)[1]
        manager.get_by_text("Cancel intervention", exact=True).click()
        manager.get_by_role("button", name="Confirm cancellation").focus()
        manager.keyboard.press("Enter")
        expect(manager.locator(".status-cancelled")).to_be_visible()
        payload = manager.request.get(BASE + "/api/v1/interventions/" + identifier).json()
        assert payload["status"] == "cancelled" and payload["closed_at"] is not None
        history = manager.request.get(BASE + "/api/v1/interventions/" + identifier + "/history")
        assert history.status == 200
        changes = history.json()["items"]
        assert len(changes) == 2
        assert changes[0]["event_type"] == "transitioned"
        assert changes[0]["changed_fields"]["status"] == {"old": "open", "new": "cancelled"}
        assert changes[0]["changed_fields"]["closed_at"]["new"] == payload["closed_at"]
        manager.reload()
        expect(manager.locator(".status-cancelled")).to_be_visible()
        # Pagination owns its minimum dataset; running this case alone must also have two pages.
        csrf = manager.request.get(BASE + "/auth/session").json()["csrf_token"]
        second = manager.request.post(
            BASE + "/api/v1/interventions",
            data={"title": "T08 pagination " + uuid4().hex[:12], "site": "Synthetic page two"},
            headers={"X-CSRF-Token": csrf},
        )
        assert second.status == 201
        manager.goto(BASE + "/app/interventions?page_size=1")
        link = manager.get_by_role("link", name="Next", exact=True)
        expect(link).to_be_visible()
        first_page = manager.locator(".job-list article h3 a").get_attribute("href")
        link.click()
        assert "page=2" in manager.url
        assert manager.locator(".job-list article h3 a").get_attribute("href") != first_page
        layout(manager)
        manager.screenshot(path=f"artifacts/t08-pagination-js-{javascript}.png", full_page=True)
        stranger = browser.new_context().new_page()
        assert stranger.goto(BASE + "/app/dashboard").status == 401
        assert stranger.goto(BASE + "/app/interventions/" + identifier).status == 401
        browser.close()
