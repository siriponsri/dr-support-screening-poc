"""Optional real-browser smoke for the static delivery preview.

Runs only when Playwright and a Chromium executable are available. API mutation behavior is
covered separately by backend/TestClient tests.
"""
import functools
import http.server
import os
import shutil
import threading
from pathlib import Path
import pytest

pytest.importorskip('playwright.sync_api')
from playwright.sync_api import sync_playwright, Error as PlaywrightError


def test_real_browser_preview_and_kku_theme():
    chromium = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or shutil.which('chromium') or shutil.which('google-chrome')
    if not chromium:
        pytest.skip('Chromium executable unavailable')
    root = Path(__file__).resolve().parents[1]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chromium, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            try:
                page.goto(f'http://127.0.0.1:{port}/PREVIEW.html')
            except PlaywrightError as exc:
                browser.close()
                if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc):
                    pytest.skip('Chromium navigation blocked by host administrator policy')
                raise
            page.wait_for_selector('#rows tr')
            assert page.locator('[data-nav]').count() == 4
            assert page.locator('#rows tr').count() == 11
            page.locator('[data-open="01_dr"]').click()
            page.wait_for_selector('#run-global')
            assert page.locator('#run-global').is_disabled()
            page.locator('a[href="#annotation"]').click()
            page.wait_for_selector('.canvas svg rect')
            assert 'Mask sync is not supported' in page.locator('.decision-panel').inner_text()
            assert '67' in page.locator('.metric-row').inner_text()
            assert '200' in page.locator('.metric-row').inner_text()
            primary = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()")
            surface = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()")
            assert primary.upper() == '#A73B24'
            assert surface.upper() == '#FCFBFA'
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
