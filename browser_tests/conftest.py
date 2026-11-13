"""Failure screenshots only: no HAR, storage-state or traces containing session credentials."""

import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright


@pytest.fixture(autouse=True)
def failure_screenshots(monkeypatch, request):
    contexts = []
    original = Browser.new_context
    original_page = Browser.new_page

    def record(self, *args, **kwargs):
        context = original(self, *args, **kwargs)
        contexts.append(context)
        return context

    monkeypatch.setattr(Browser, "new_context", record)

    def record_page(self, *args, **kwargs):
        page = original_page(self, *args, **kwargs)
        if page.context not in contexts:
            contexts.append(page.context)
        return page

    monkeypatch.setattr(Browser, "new_page", record_page)

    @contextmanager
    def monitored_playwright():
        with sync_playwright() as playwright:
            try:
                yield playwright
            except BaseException:
                save()
                raise

    def save():
        destination = Path("artifacts/failures")
        destination.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^a-zA-Z0-9_-]", "_", request.node.nodeid)[-150:]
        for index, context in enumerate(contexts):
            for number, page in enumerate(context.pages):
                if not page.is_closed():
                    try:
                        page.screenshot(
                            path=str(destination / f"{name}-{index}-{number}.png"),
                            full_page=True,
                            mask=[page.locator("input[type=password]")],
                        )
                    except Exception:
                        pass  # Preserve the original failure if the browser already closed.

    monkeypatch.setattr(request.module, "sync_playwright", monitored_playwright)
