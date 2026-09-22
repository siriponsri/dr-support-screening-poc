"""Capture the clinician manual from the built Retinal Review Workbench UI.

The script uses only the local public/synthetic demo surface. Start a local
review app first, then run this command from the repository root.
"""
from __future__ import annotations

import os
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / 'docs' / 'manual' / 'screenshots'
BASE_URL = os.environ.get('MANUAL_BASE_URL', 'http://127.0.0.1:8000/app/')
CHROME = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')


def capture(page, name: str, route: str) -> None:
    page.goto(f'{BASE_URL}#/{route}', wait_until='networkidle')
    page.wait_for_timeout(500)
    page.screenshot(path=str(SCREENSHOTS / name), full_page=True)


def demo_case_id(page) -> str:
    response = page.request.get(f'{BASE_URL.rstrip("/")}/../v1/cases')
    if response.ok:
        cases = response.json()
        if cases:
            return cases[0]['image_id']
    return 'SYNTH_001'


def seed_synthetic_evidence(page, case_id: str) -> None:
    api_root = BASE_URL.split('/app', 1)[0]
    headers = {'Content-Type': 'application/json'}
    for route, model_id in (('global', 'mock-global'), ('lesion-roi', 'mock-lesion')):
        response = page.request.post(
            f'{api_root}/v1/infer/{route}',
            data=json.dumps({'image_id': case_id, 'model_id': model_id}),
            headers=headers,
        )
        if not response.ok:
            raise RuntimeError(f'Could not seed synthetic {route} evidence: {response.status}')


def main() -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        case_id = demo_case_id(page)
        seed_synthetic_evidence(page, case_id)
        capture(page, '01-worklist.png', 'worklist')
        capture(page, '02-settings.png', 'settings')
        capture(page, '03-worklist-scan.png', 'worklist')
        capture(page, '04-identity.png', 'worklist')
        capture(page, '05-review.png', f'review/{case_id}')
        capture(page, '06-overlays.png', f'review/{case_id}')
        capture(page, '07-clinician-review.png', f'clinician-review/{case_id}')
        capture(page, '08-annotation-editor.png', f'edit/{case_id}')
        capture(page, '09-datasets.png', 'datasets')
        capture(page, '10-models-audit.png', 'models')
        browser.close()
    print(f'Captured {len(list(SCREENSHOTS.glob("*.png")))} screenshots in {SCREENSHOTS}')


if __name__ == '__main__':
    main()
