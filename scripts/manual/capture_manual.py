"""Capture focused figures from one deterministic synthetic review scenario.

Start the review workstation before running this script. It uses only the
public/synthetic case returned by the local API and never captures PHI.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = ROOT / "docs" / "manual" / "screenshots"
BASE_URL = os.environ.get("MANUAL_BASE_URL", "http://127.0.0.1:8000/app/")
CHROME = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")


def api_root() -> str:
    return BASE_URL.split("/app", 1)[0].rstrip("/")


def open_route(page: Page, route: str) -> None:
    page.goto(f"{BASE_URL}#/{route}", wait_until="networkidle")
    page.wait_for_timeout(600)


def capture(locator: Locator, name: str) -> None:
    if locator.count() == 0:
        raise RuntimeError(f"Cannot capture {name}: locator did not match")
    locator.first.screenshot(path=str(SCREENSHOTS / name))


def demo_case_id(page: Page) -> str:
    response = page.request.get(f"{api_root()}/v1/cases")
    if not response.ok:
        raise RuntimeError(f"Cannot list cases for manual capture: HTTP {response.status}")
    payload = response.json()
    cases = payload.get("value", []) if isinstance(payload, dict) else payload
    for case in cases:
        if case.get("admission", {}).get("modality_admission") == "FUNDUS_ACCEPTED":
            return case["image_id"]
    if cases:
        return cases[0]["image_id"]
    return "SYNTH_001"


def seed_synthetic_evidence(page: Page, case_id: str) -> None:
    headers = {"Content-Type": "application/json"}
    for route, model_id in (("global", "mock-global"), ("lesion-roi", "mock-lesion")):
        response = page.request.post(
            f"{api_root()}/v1/infer/{route}",
            data=json.dumps({"image_id": case_id, "model_id": model_id}),
            headers=headers,
        )
        if not response.ok:
            raise RuntimeError(f"Cannot seed {route} evidence: HTTP {response.status}")


def capture_final_ui(page: Page, case_id: str) -> None:
    open_route(page, "worklist")
    capture(page.locator("main"), "01-worklist.png")

    confirm = page.get_by_role("button", name="Confirm Image").first
    if confirm.count():
        confirm.click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        capture(dialog, "02-confirm-image.png")
        reviewer = dialog.get_by_label("Reviewer name")
        if reviewer.count() and not reviewer.input_value():
            reviewer.fill("Synthetic reviewer")
        save_button = dialog.get_by_role("button", name="Confirm Image")
        if save_button.count():
            save_button.click()
            page.wait_for_timeout(600)

    open_route(page, f"review/{case_id}")
    capture(page.locator("main"), "03-review-overview.png")
    filter_box = page.get_by_label("Filter lesion overlays")
    if filter_box.count():
        capture(filter_box.locator(".."), "04-ai-controls.png")

    open_route(page, f"clinician-review/{case_id}")
    capture(page.locator("main"), "05-confirm-dr-grade.png")

    open_route(page, f"edit/{case_id}")
    capture(page.locator("main"), "06-annotation-editor.png")
    roi = page.locator("svg [data-ai-detection-id]").first
    if roi.count():
        roi.dispatch_event("click")
        popover = page.get_by_text("Optional ROI action").locator("..")
        if popover.count():
            capture(popover, "07-roi-popover.png")

    open_route(page, "datasets")
    capture(page.locator("main"), "08-dataset-readiness.png")
    open_route(page, "models")
    capture(page.locator("main"), "09-models-audit.png")


def main() -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        case_id = demo_case_id(page)
        seed_synthetic_evidence(page, case_id)
        capture_final_ui(page, case_id)
        browser.close()

    hashes: dict[str, str] = {}
    duplicates: list[str] = []
    for image in sorted(SCREENSHOTS.glob("*.png")):
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if digest in hashes:
            duplicates.append(f"{image.name} == {hashes[digest]}")
        hashes[digest] = image.name
    if duplicates:
        raise RuntimeError("Duplicate manual figures: " + ", ".join(duplicates))
    print(f"Captured {len(hashes)} focused manual figures in {SCREENSHOTS}")


if __name__ == "__main__":
    main()
