"""Explicit negative browser-runner artifact probe, excluded from normal discovery."""

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


def test_intentional_browser_failure_with_masked_operator_input():
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={"width": 375, "height": 960})
        page.goto(os.environ["FIELDOPS_BROWSER_URL"] + "/app/operator")
        secret = (Path(os.environ["FIELDOPS_TEST_CONTROL_DIRECTORY"]) / "operator_key").read_text()
        page.get_by_label("Operator credential").fill(secret)
        pytest.fail("Intentional browser failure and masked-screenshot probe")
